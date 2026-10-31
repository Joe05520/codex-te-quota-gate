import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from quota_gate import bundle
from quota_gate.bridge import run_hook, SAFE_ENV
from quota_gate.policy import decide, normalize
from quota_gate.rpc import read_quota, QuotaReadError
from quota_gate.storage import write_snapshot


def sample(h=40, w=60, now=None):
    now = time.time() if now is None else now
    return {"schemaVersion": 1, "limitId": "codex", "observedAt": now,
            "windows": [{"windowDurationMins": duration, "usedPercent": 100 - remaining,
                         "resetsAt": now + 3600}
                        for duration, remaining in ((300, h), (10080, w))]}


class PolicyTests(unittest.TestCase):
    def test_threshold_and_or(self):
        for h, w, active in [(40, 60, False), (14, 60, True), (40, 14, True),
                             (14, 14, True), (15, 15, False), (0, 100, True),
                             (100, 100, False), (14.99, 100, True)]:
            with self.subTest(h=h, w=w):
                self.assertEqual(decide(sample(h, w)).active, active)

    def test_age_and_reset(self):
        for change, reason in [(lambda s: s.update(observedAt=900), "stale_snapshot"),
                               (lambda s: s.update(observedAt=1001), "invalid_timestamp"),
                               (lambda s: s["windows"][0].update(resetsAt=1000), "reset_requires_refresh")]:
            s = sample(14, 60, now=1000)
            change(s)
            self.assertEqual(decide(s, now=1000).reason, reason)
        self.assertTrue(decide(sample(14, 60, now=911), now=1000).active)
        self.assertFalse(decide(sample(14, 60, now=910), now=1000).active)

    def test_unknown_missing_duplicate_and_wrong_bucket(self):
        self.assertFalse(decide(None).active)
        self.assertFalse(decide({}).active)
        s = sample(14, 60)
        s["windows"].pop()
        self.assertEqual(decide(s).reason, "missing_5h_or_weekly")
        s = sample(14, 60)
        s["windows"].append(s["windows"][0])
        self.assertEqual(decide(s).reason, "duplicate_window")
        s = sample(14, 60)
        s["limitId"] = "different-model"
        self.assertEqual(decide(s).reason, "wrong_bucket")

    def test_bad_percentages_and_resets(self):
        for field in ("usedPercent", "resetsAt", "windowDurationMins"):
            for bad in (None, "14", True, float("nan"), float("inf")):
                s = sample(14, 60)
                s["windows"][0][field] = bad
                with self.subTest(field=field, bad=bad):
                    self.assertFalse(decide(s).active)
        for bad in (-1, 101):
            s = sample(14, 60)
            s["windows"][0]["usedPercent"] = bad
            self.assertFalse(decide(s).active)

    def test_window_identity_uses_duration_not_primary(self):
        s = sample(14, 60)
        s["windows"].reverse()
        self.assertEqual(decide(s).remaining_5h, 14)

    def test_normalize_prefers_bucket_and_sanitizes(self):
        low = {"primary": sample(14, 60)["windows"][0],
               "secondary": sample(14, 60)["windows"][1], "accountId": "never-store"}
        high = {"limitId": "codex", "primary": sample()["windows"][0],
                "secondary": sample()["windows"][1]}
        n = normalize({"rateLimits": high, "rateLimitsByLimitId": {"codex": low}})
        self.assertTrue(decide(n).active)
        self.assertNotIn("never-store", json.dumps(n))
        self.assertNotIn("accountId", json.dumps(n))
        with self.assertRaises(ValueError):
            normalize({"rateLimits": high, "rateLimitsByLimitId": {"other": low}})
        self.assertFalse(decide(normalize({"rateLimits": {"limitId": "codex"}})).active)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshot = self.root / "runtime/quota.json"
        self.bootstrap = self.root / "upstream/plugin/scripts/te_bootstrap.py"
        self.bootstrap.parent.mkdir(parents=True)
        self.bootstrap.write_text('''import json, os, sys
data = json.load(sys.stdin)
print(json.dumps({"additionalContext": "synthetic envfacts", "seen": data,
    "safe": {k: os.environ.get(k) for k in
        ("TE_MICROSKILLS", "TE_TOOLPRUNE", "TE_LOOPGUARD", "TE_REPOMAP", "TOKENECONOMIZER_HOME")}}))
''')

    def call(self, payload=None, **kwargs):
        return run_hook(json.dumps(payload or {"session_id": "synthetic", "hook_event_name": "SessionStart"}).encode(),
                        snapshot_path=self.snapshot, bootstrap=self.bootstrap,
                        expected_sha256=hashlib.sha256(self.bootstrap.read_bytes()).hexdigest(),
                        env={}, **kwargs)

    def test_full_switch_cycle_same_session(self):
        payload = {"session_id": "synthetic", "hook_event_name": "UserPromptSubmit", "prompt": "測試"}
        for h, w, active in [(40, 60, False), (14, 60, True), (100, 100, False), (40, 14, True)]:
            write_snapshot(self.snapshot, sample(h, w))
            answer, reason = self.call(payload)
            self.assertEqual(bool(answer), active)
            if active:
                self.assertEqual(answer["seen"], payload)
                self.assertEqual(reason, "forwarded_envfacts")

    def test_settings_override_and_separate_state(self):
        write_snapshot(self.snapshot, sample(14, 60))
        out, _ = run_hook(b'{"session_id":"s"}', snapshot_path=self.snapshot,
                          bootstrap=self.bootstrap,
                          expected_sha256=hashlib.sha256(self.bootstrap.read_bytes()).hexdigest(),
                          env={"TE_MICROSKILLS": "on", "TE_TOOLPRUNE": "auto", "TE_LOOPGUARD": "on",
                               "TOKENECONOMIZER_HOME": "/do-not-use"})
        for key in ("TE_MICROSKILLS", "TE_TOOLPRUNE", "TE_LOOPGUARD", "TE_REPOMAP"):
            self.assertEqual(out["safe"][key], SAFE_ENV[key])
        self.assertEqual(out["safe"]["TOKENECONOMIZER_HOME"], str(self.snapshot.resolve().parent / "te-state"))

    def test_missing_corrupt_stale_and_reset_never_forward(self):
        self.assertEqual(self.call()[0], {})
        self.snapshot.parent.mkdir(exist_ok=True)
        self.snapshot.write_text("not json")
        self.assertEqual(self.call()[0], {})
        s = sample(14, 60, now=time.time() - 100)
        write_snapshot(self.snapshot, s)
        self.assertEqual(self.call()[0], {})
        s = sample(14, 60)
        s["windows"][1]["resetsAt"] = time.time() - 1
        write_snapshot(self.snapshot, s)
        self.assertEqual(self.call()[0], {})

    def test_emergency_disable_and_sidecall(self):
        for key in ("TE_DISABLE", "TE_SIDECALL"):
            answer, reason = run_hook(b'{}', snapshot_path=self.snapshot,
                                      bootstrap=self.bootstrap, expected_sha256="invalid",
                                      env={key: "1"})
            self.assertEqual(answer, {})
            self.assertEqual(reason, "explicitly_disabled")

    def test_upstream_hash_mismatch(self):
        write_snapshot(self.snapshot, sample(14, 60))
        out, reason = run_hook(b'{"session_id":"s"}', snapshot_path=self.snapshot,
                               bootstrap=self.bootstrap, expected_sha256="wrong", env={})
        self.assertEqual(out, {})
        self.assertEqual(reason, "upstream_bootstrap_changed")

    def test_upstream_failure_output_and_timeout(self):
        write_snapshot(self.snapshot, sample(14, 60))
        for code in ("raise SystemExit(3)", "print('not json')", "print('[]')",
                     "import time; time.sleep(10)"):
            self.bootstrap.write_text(code)
            started = time.monotonic()
            self.assertEqual(self.call(timeout=0.1)[0], {})
            self.assertLess(time.monotonic() - started, 2)

    def test_cli_hook_stdout_only_json(self):
        result = subprocess.run([sys.executable, "-m", "quota_gate", "hook", "--snapshot",
                                 str(self.snapshot), "--bootstrap", str(self.bootstrap),
                                 "--bootstrap-sha256", "none"], input=b'{}', capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertEqual(result.stderr, b"")

    def test_snapshot_permissions(self):
        write_snapshot(self.snapshot, sample(14, 60))
        self.assertEqual(self.snapshot.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.snapshot.parent.stat().st_mode & 0o777, 0o700)

    def test_collector_failure_invalidates_previous_active_snapshot(self):
        write_snapshot(self.snapshot, sample(14, 60))
        result = subprocess.run([sys.executable, "-m", "quota_gate", "capture", "--codex",
                                 str(self.root / "missing-codex"), "--output", str(self.snapshot)],
                                capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(decide(json.loads(self.snapshot.read_text())).active, False)


@unittest.skipUnless(os.name == "posix", "POSIX stdio collector")
class RpcTests(unittest.TestCase):
    def test_real_subprocess_handshake_read_and_no_turns(self):
        script = '''import json, sys
for line in sys.stdin:
 m = json.loads(line)
 if m.get('method') == 'initialize':
  print(json.dumps({'id': m['id'], 'result': {}}), flush=True)
 elif m.get('method') == 'initialized':
  pass
 elif m.get('method') == 'account/rateLimits/read':
  print(json.dumps({'method':'notice','params':{}}), flush=True)
  print(json.dumps({'id':99,'method':'approval/request','params':{}}), flush=True)
 elif m.get('id') == 99:
  assert 'error' in m
  import time
  w = lambda d, u: {'windowDurationMins':d,'usedPercent':u,'resetsAt':time.time()+3600}
  print(json.dumps({'id':2,'result':{'rateLimitsByLimitId':{'codex':{
    'primary':w(10080,10),'secondary':w(300,86),'accountId':'private'}}}}), flush=True)
 else:
  raise SystemExit('unexpected method: '+str(m))
'''
        snapshot = read_quota(command=[sys.executable, "-u", "-c", script])
        self.assertTrue(decide(snapshot).active)
        self.assertNotIn("private", json.dumps(snapshot))

    def test_timeout_error_and_invalid_json(self):
        for code in ("import time; time.sleep(10)",
                     "print('bad', flush=True)",
                     "print('{\"id\":1,\"error\":{}}', flush=True)"):
            with self.subTest(code=code), self.assertRaises(QuotaReadError):
                read_quota(command=[sys.executable, "-u", "-c", code], timeout=0.2)


class BundleTests(unittest.TestCase):
    def test_generated_bundle_and_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "upstream"
            (source / "tokeneconomizer/plugin").mkdir(parents=True)
            (source / "tokeneconomizer/plugin/hook.py").write_text("# stub\n")
            boot = source / "plugin/scripts/te_bootstrap.py"
            boot.parent.mkdir(parents=True)
            boot.write_text('import json,sys; json.load(sys.stdin); print(\'{"synthetic":true}\')')
            dest = root / "marketplace"
            snap = root / "runtime/quota.json"
            with patch("quota_gate.bundle.subprocess.check_output",
                       side_effect=[bundle.REVIEWED_REVISION + "\n", ""]):
                result = bundle.build(source, dest, snap)
            self.assertFalse(result["installed"])
            hooks = json.loads((dest / "plugin/hooks/codex-hooks.json").read_text())
            self.assertEqual(set(hooks["hooks"]), set(bundle.EVENTS))
            self.assertIn("PLUGIN_ROOT", hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"])
            write_snapshot(snap, sample(14, 60))
            for changed in (False, True):
                if changed:
                    (source / "tokeneconomizer/plugin/hook.py").write_text("# changed\n")
                run = subprocess.run([sys.executable, str(dest / "plugin/run_hook.py")],
                                     input=b'{"session_id":"s"}', capture_output=True)
                self.assertEqual(json.loads(run.stdout), {} if changed else {"synthetic": True})
            with patch("quota_gate.bundle.subprocess.check_output", side_effect=["wrong\n", ""]):
                with self.assertRaises(ValueError):
                    bundle.build(source, root / "other", snap)


if __name__ == "__main__":
    unittest.main()
