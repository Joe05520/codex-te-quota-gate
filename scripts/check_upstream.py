"""Optional offline check against the pinned upstream source. No live agent required."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

# Allow direct execution from scripts/ without installing this package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quota_gate.bridge import SAFE_ENV
from quota_gate.bundle import REVIEWED_REVISION, build
from quota_gate.policy import decide
from quota_gate.storage import write_snapshot

p = argparse.ArgumentParser()
p.add_argument("--source", required=True)
args = p.parse_args()
source = Path(args.source).resolve()
sys.path.insert(0, str(source))
from tokeneconomizer.plugin.config import load_config
from tokeneconomizer.config import InjectionConfig

with tempfile.TemporaryDirectory(prefix="te-gate-upstream-") as tmp:
    root = Path(tmp)
    (root / "config.json").write_text(json.dumps({"microskills": "on", "toolprune": "auto",
                                                 "loopguard": "on", "repomap": "on"}))
    cfg = load_config(str(root), env=SAFE_ENV)
    assert cfg.microskills == "envfacts"
    assert cfg.toolprune == cfg.loopguard == cfg.repomap == "off"
    assert not InjectionConfig(enabled=True, profile=cfg.microskills).paid
    result = build(source, root / "marketplace", root / "runtime/quota.json")
    assert result["upstreamRevision"] == REVIEWED_REVISION
    # The real upstream bootstrap accepts an inactive hook, with all state kept synthetic.
    # This intentionally uses a high quota so no upstream hook/state mutation can occur.
    import time
    now = time.time()
    write_snapshot(root / "runtime/quota.json", {"schemaVersion": 1, "observedAt": now,
        "limitId": "codex", "windows": [
            {"windowDurationMins": d, "usedPercent": 20, "resetsAt": now + 3600}
            for d in (300, 10080)]})
    run = subprocess.run([sys.executable, str(root / "marketplace/plugin/run_hook.py")],
                          input=b'{"session_id":"synthetic","hook_event_name":"SessionStart"}',
                          capture_output=True, check=True)
    assert json.loads(run.stdout) == {}
    assert not (root / "runtime/te-state").exists()
print(json.dumps({"upstreamRevision": REVIEWED_REVISION, "configOverrides": "pass",
                  "paidProposerDisabled": True, "realSourceBundle": "pass",
                  "inactiveHook": "pass", "liveAgentTested": False}, indent=2))
