"""Generate a reviewable local marketplace. Never install or trust it automatically."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd")
REVIEWED_REVISION = "e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9"


def source_hashes(source):
    source = Path(source)
    files = list((source / "tokeneconomizer").rglob("*.py"))
    files.append(source / "plugin/scripts/te_bootstrap.py")
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def build(source, destination, snapshot):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"],
                                    text=True).strip()
    if revision != REVIEWED_REVISION or dirty:
        raise ValueError("requires clean upstream checkout at reviewed revision " + REVIEWED_REVISION)
    if not (source / "tokeneconomizer/plugin/hook.py").is_file():
        raise ValueError("missing upstream package")
    hashes = source_hashes(source)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    plugin = destination / "plugin"
    plugin.mkdir()
    shutil.copytree(Path(__file__).parent, plugin / "quota_gate",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    config = {"source": str(source), "source_hashes": hashes,
              "snapshot": str(Path(snapshot).resolve()), "threshold": 15, "max_age": 90,
              "bootstrap": str(source / "plugin/scripts/te_bootstrap.py"),
              "bootstrap_sha256": hashes["plugin/scripts/te_bootstrap.py"]}
    (plugin / "gate-config.json").write_text(json.dumps(config, indent=2) + "\n")
    (plugin / "run_hook.py").write_text('''import json
from pathlib import Path
import sys
from quota_gate.bridge import run_hook
from quota_gate.bundle import source_hashes

try:
    cfg = json.loads((Path(__file__).parent / "gate-config.json").read_text())
    if source_hashes(cfg["source"]) != cfg["source_hashes"]:
        raise ValueError("upstream changed: regenerate and review the bundle")
    result, reason = run_hook(sys.stdin.buffer.read(), snapshot_path=cfg["snapshot"],
        bootstrap=cfg["bootstrap"], expected_sha256=cfg["bootstrap_sha256"],
        threshold=cfg["threshold"], max_age=cfg["max_age"])
except Exception:
    result = {}
print(json.dumps(result))
''')
    command = (shlex.quote(sys.executable)
               + ' "${PLUGIN_ROOT:-$CLAUDE_PLUGIN_ROOT}/run_hook.py"')
    hooks = {event: [{"hooks": [{"type": "command", "command": command, "timeout": 15}]}]
             for event in EVENTS}
    (plugin / "hooks").mkdir()
    (plugin / "hooks/codex-hooks.json").write_text(json.dumps({"hooks": hooks}, indent=2) + "\n")
    (plugin / ".codex-plugin").mkdir()
    (plugin / ".codex-plugin/plugin.json").write_text(json.dumps({
        "name": "te-quota-gate", "version": "0.1.0", "license": "MIT",
        "description": "Quota-gated envfacts only. No tool pruning or loop guard.",
        "hooks": "./hooks/codex-hooks.json"}, indent=2) + "\n")
    (destination / ".claude-plugin").mkdir()
    (destination / ".claude-plugin/marketplace.json").write_text(json.dumps({
        "name": "te-quota-gate", "owner": {"name": "TE Quota Gate contributors"},
        "plugins": [{"name": "te-quota-gate", "source": "./plugin",
                     "description": "Conservative local quota gate"}]}, indent=2) + "\n")
    # These outputs contain machine paths: a root marker prevents accidental publication.
    (destination / ".gitignore").write_text("*\n")
    return {"marketplace": str(destination), "upstreamRevision": revision,
            "installed": False, "hooksTrusted": False}
