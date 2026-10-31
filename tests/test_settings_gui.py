from copy import deepcopy
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from quota_gate.bridge import run_hook
from quota_gate.bundle import build, REVIEWED_REVISION
from quota_gate.gui import GuiState, make_server, synthetic_snapshot
from quota_gate.policy import decide
from quota_gate.settings import DEFAULTS, configured_decision, project_block, read_settings, validate_settings
from quota_gate.storage import write_snapshot


class SettingsTests(unittest.TestCase):
    def test_independent_thresholds_and_zero(self):
        quota = synthetic_snapshot("normal")  # 40% / 60%
        for h, w, expected in [(40, 60, False), (41, 0, True), (0, 61, True),
                               (0, 0, False), (100, 100, True), (15, 15, False)]:
            config = {**deepcopy(DEFAULTS), "threshold_5h": h, "threshold_weekly": w}
            self.assertEqual(configured_decision(quota, config).active, expected)

    def test_invalid_settings(self):
        for field, bad in [("threshold_5h", -1), ("threshold_weekly", 101),
                           ("threshold_5h", True), ("threshold_weekly", float("nan")),
                           ("enabled", 1), ("schemaVersion", True), ("projects", {})]:
            config = deepcopy(DEFAULTS)
            config[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                validate_settings(config)
        for path in ("relative/path", "", None):
            config = deepcopy(DEFAULTS)
            config["projects"] = [{"name": "test", "path": path, "excluded": True}]
            with self.assertRaises(ValueError):
                validate_settings(config)

    def test_project_exclusion_children_not_prefix_neighbors(self):
        cfg = deepcopy(DEFAULTS)
        cfg["projects"] = [{"name": "main", "path": "/demo/project-a", "excluded": True}]
        for path, blocked in [("/demo/project-a", True), ("/demo/project-a/sub", True),
                               ("/demo/project-ab", False), ("/demo/other", False)]:
            self.assertEqual(project_block(cfg, path) == "project_excluded", blocked)
        self.assertEqual(project_block(cfg, None), "project_unknown")
        cfg["projects"][0]["excluded"] = False
        self.assertIsNone(project_block(cfg, None))
        self.assertTrue(configured_decision(synthetic_snapshot("low5h"), cfg,
                                            cwd="/demo/project-a").active)

    def test_symlink_alias_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            cfg = deepcopy(DEFAULTS)
            cfg["projects"] = [{"name": "root", "path": str(root / "real"), "excluded": True}]
            self.assertEqual(project_block(cfg, str(root / "alias/sub")), "project_excluded")
            cfg["projects"].append({"name": "alias", "path": str(root / "alias"), "excluded": False})
            with self.assertRaises(ValueError):
                validate_settings(cfg)

    def test_master_disable(self):
        cfg = {**deepcopy(DEFAULTS), "enabled": False}
        self.assertEqual(configured_decision(synthetic_snapshot("low5h"), cfg).reason,
                         "disabled_by_settings")

    def test_demo_cli_rejects_live_file_overrides(self):
        result = subprocess.run([sys.executable, "-m", "quota_gate", "gui", "--demo",
                                 "--settings", "/do-not-write/settings.json"], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"demo uses runtime/demo only", result.stderr)


class SharedHookTests(unittest.TestCase):
    def test_live_settings_changes_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "upstream/plugin/scripts/te_bootstrap.py"
            boot.parent.mkdir(parents=True)
            boot.write_text('import json,sys; json.load(sys.stdin); print(\'{"forwarded":true}\')')
            sha = hashlib.sha256(boot.read_bytes()).hexdigest()
            snap, settings = root / "quota.json", root / "settings.json"
            write_snapshot(snap, synthetic_snapshot("normal"))
            cfg = deepcopy(DEFAULTS)
            def invoke(cwd="/demo/project-a/sub"):
                return run_hook(json.dumps({"session_id": "s", "cwd": cwd}).encode(),
                                snapshot_path=snap, bootstrap=boot, expected_sha256=sha,
                                settings_path=settings, env={})
            write_snapshot(settings, cfg)
            self.assertEqual(invoke()[0], {})
            cfg["threshold_5h"] = 41
            write_snapshot(settings, cfg)
            self.assertTrue(invoke()[0]["forwarded"])
            cfg["projects"] = [{"name": "a", "path": "/demo/project-a", "excluded": True}]
            write_snapshot(settings, cfg)
            self.assertEqual(invoke()[1], "project_excluded")
            self.assertTrue(invoke("/demo/project-ab")[0]["forwarded"])
            cfg["projects"][0]["excluded"] = False
            write_snapshot(settings, cfg)
            self.assertTrue(invoke()[0]["forwarded"])
            settings.write_text("broken")
            self.assertEqual(invoke()[0], {})

    def test_generated_bundle_reads_same_gui_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "upstream"
            (source / "tokeneconomizer/plugin").mkdir(parents=True)
            (source / "tokeneconomizer/plugin/hook.py").write_text("# fixture")
            boot = source / "plugin/scripts/te_bootstrap.py"
            boot.parent.mkdir(parents=True)
            boot.write_text('import json,sys; json.load(sys.stdin); print(\'{"forwarded":true}\')')
            snapshot, settings = root / "runtime/quota.json", root / "runtime/settings.json"
            state = GuiState(settings, snapshot, demo=True)
            with patch("quota_gate.bundle.subprocess.check_output", side_effect=[REVIEWED_REVISION, ""]):
                build(source, root / "bundle", snapshot, settings)
            initial = state.status()
            config = deepcopy(initial["settings"])
            config["threshold_weekly"] = 61
            state.save(config, initial["revision"])
            runner = root / "bundle/plugin/run_hook.py"
            payload = b'{"session_id":"s","cwd":"/demo/project-a"}'
            def run():
                return json.loads(subprocess.run([sys.executable, str(runner)], input=payload,
                                                capture_output=True, check=True).stdout)
            self.assertTrue(run()["forwarded"])
            result = state.status()
            config["projects"] = [{"name": "a", "path": "/demo/project-a", "excluded": True}]
            state.save(config, result["revision"])
            self.assertEqual(run(), {})


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = GuiState(self.root / "settings.json", self.root / "quota.json", demo=True)
        self.server = make_server(self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, body=None, **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        base = {"X-Gate-Token": self.state.token}
        if body is not None:
            base.update({"Content-Type": "application/json",
                         "Origin": f"http://127.0.0.1:{self.server.server_port}"})
        base.update(headers)
        connection.request("GET" if body is None else "POST", path,
                           body=None if body is None else json.dumps(body), headers=base)
        response = connection.getresponse()
        data = response.read()
        result = (response.status, response.getheaders(), data)
        connection.close()
        return result

    def test_page_and_assets(self):
        for path in ("/", "/app.js", "/style.css"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("Content-Security-Policy", dict(headers))
            self.assertTrue(body)
            self.assertNotIn(b"__GATE_TOKEN__", body)
        self.assertEqual(self.request("/../../settings.json")[0], 404)

    def test_save_persist_preview_and_conflict(self):
        data = json.loads(self.request("/api/state")[2])
        cfg = deepcopy(data["settings"])
        cfg.update(threshold_5h=45, threshold_weekly=7)
        cfg["projects"] = [{"name": "<img src=x onerror=alert(1)>", "path": "/demo/project", "excluded": True}]
        status, _, body = self.request("/api/settings", {"settings": cfg, "revision": data["revision"]})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["decision"]["active"])
        self.assertEqual(read_settings(self.state.settings_path)["threshold_5h"], 45)
        self.assertEqual(self.request("/api/settings", {"settings": cfg, "revision": data["revision"]})[0], 409)
        preview = self.request("/api/preview", {"settings": cfg, "cwd": "/demo/project/sub"})
        self.assertEqual(json.loads(preview[2])["decision"]["reason"], "project_excluded")
        self.assertEqual(self.request("/api/preview", {"settings": cfg, "cwd": ""})[0], 400)
        new_state = GuiState(self.state.settings_path, self.state.snapshot_path)
        self.assertEqual(new_state.status()["settings"]["threshold_weekly"], 7)

    def test_host_origin_and_token_rejected(self):
        self.assertEqual(self.request("/api/state", **{"X-Gate-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("/", Host="evil.example")[0], 403)
        body = {"settings": DEFAULTS, "revision": "x"}
        self.assertEqual(self.request("/api/settings", body, Origin="https://evil.example")[0], 403)
        self.assertEqual(self.request("/api/settings", body, **{"X-Gate-Token": "wrong"})[0], 403)

    def test_invalid_input_never_changes_settings(self):
        old = self.state.settings_path.read_bytes()
        for bad in (-1, 101, True, "20"):
            cfg = deepcopy(DEFAULTS)
            cfg["threshold_5h"] = bad
            rev = self.state.status()["revision"]
            self.assertEqual(self.request("/api/settings", {"settings": cfg, "revision": rev})[0], 400)
            self.assertEqual(self.state.settings_path.read_bytes(), old)

    def test_demo_scenarios_and_live_mode_no_simulation(self):
        status, _, body = self.request("/api/scenario", {"scenario": "low5h"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["decision"]["active"])
        self.assertEqual(self.request("/api/scenario", {"scenario": "not-a-scenario"})[0], 400)
        self.state.demo = False
        self.assertEqual(self.request("/api/scenario", {"scenario": "low5h"})[0], 404)

    def test_invalid_existing_settings_not_overwritten(self):
        self.state.settings_path.write_text("broken")
        with self.assertRaises(ValueError):
            GuiState(self.state.settings_path, self.state.snapshot_path)
        self.assertEqual(self.state.settings_path.read_text(), "broken")
        self.assertEqual(self.request("/api/state")[0], 503)


if __name__ == "__main__":
    unittest.main()
