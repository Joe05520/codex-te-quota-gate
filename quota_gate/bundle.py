"""Generate a reviewable local marketplace. Never install or trust it automatically."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from . import __version__
from .settings import read_settings
from .storage import write_snapshot

EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd")
REVIEWED_REVISION = "e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9"


def source_hashes(source):
    source = Path(source)
    files = list((source / "tokeneconomizer").rglob("*.py"))
    files.append(source / "plugin/scripts/te_bootstrap.py")
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def build(source, destination, snapshot, settings=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("marketplace destination already exists")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"],
                                    text=True).strip()
    if revision != REVIEWED_REVISION or dirty:
        raise ValueError("requires clean upstream checkout at reviewed revision " + REVIEWED_REVISION)
    if not (source / "tokeneconomizer/plugin/hook.py").is_file():
        raise ValueError("missing upstream package")
    hashes = source_hashes(source)
    settings_path = (Path(settings).resolve() if settings is not None
                     else Path(snapshot).resolve().parent / "settings.json")
    if settings_path == Path(snapshot).resolve():
        raise ValueError("settings and snapshot paths must differ")
    if settings_path.is_relative_to(destination) or Path(snapshot).resolve().is_relative_to(destination):
        raise ValueError("shared runtime files must be outside the generated marketplace")
    if settings_path.exists():
        read_settings(settings_path)
    else:
        write_snapshot(settings_path, read_settings())
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    plugin = destination / "plugin"
    plugin.mkdir()
    shutil.copytree(Path(__file__).parent, plugin / "quota_gate",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    config = {"source": str(source), "source_hashes": hashes,
              "snapshot": str(Path(snapshot).resolve()), "settings": str(settings_path),
              "threshold": 15, "max_age": 90,
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
        threshold=cfg["threshold"], max_age=cfg["max_age"], settings_path=cfg["settings"])
except Exception:
    result = {}
print(json.dumps(result))
''')
    command = (shlex.quote(sys.executable)
               + ' "${PLUGIN_ROOT:-$CLAUDE_PLUGIN_ROOT}/run_hook.py"')
    hooks = {event: [{"hooks": [{"type": "command", "command": command,
                               "timeout": 3 if event == "SessionEnd" else 15}]}]
             for event in EVENTS}
    (plugin / "hooks").mkdir()
    (plugin / "hooks/codex-hooks.json").write_text(json.dumps({"hooks": hooks}, indent=2) + "\n")
    (plugin / ".codex-plugin").mkdir()
    (plugin / ".codex-plugin/plugin.json").write_text(json.dumps({
        "name": "te-quota-gate", "version": __version__, "license": "MIT",
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
