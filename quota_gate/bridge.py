"""Gate a single upstream hook; guard settings cannot be weakened through TE env vars."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .policy import decide
from .rpc import stop_process
from .storage import read_snapshot
from .settings import read_settings, project_block
from .activity import record_activity

SAFE_ENV = {
    "TE_DISABLE": "0", "TE_MICROSKILLS": "envfacts", "TE_TOOLPRUNE": "off",
    "TE_LOOPGUARD": "off", "TE_REPOMAP": "off",
}


def run_hook(payload, *, snapshot_path, bootstrap, expected_sha256,
             threshold=15.0, max_age=90.0, timeout=10.0, env=None, settings_path=None):
    started = time.monotonic()
    answer, reason = _run_hook(payload, snapshot_path=snapshot_path, bootstrap=bootstrap,
        expected_sha256=expected_sha256, threshold=threshold, max_age=max_age,
        timeout=timeout, env=env, settings_path=settings_path)
    record_activity(snapshot_path, payload, answer, reason, time.monotonic() - started,
                    diagnostic=(os.environ if env is None else env).get("TE_GATE_DIAGNOSTIC") == "1")
    return answer, reason


def _run_hook(payload, *, snapshot_path, bootstrap, expected_sha256,
              threshold=15.0, max_age=90.0, timeout=10.0, env=None, settings_path=None):
    parent_env = os.environ if env is None else env
    truthy = ("1", "true", "yes", "on")
    if any(str(parent_env.get(k, "")).strip().lower() in truthy
           for k in ("TE_DISABLE", "TE_SIDECALL")):
        return {}, "explicitly_disabled"
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or not data.get("session_id"):
            return {}, "invalid_hook_payload"
        # Codex caps SessionEnd at 3 seconds. Reserve time for startup and cleanup.
        if data.get("hook_event_name") == "SessionEnd":
            timeout = min(timeout, 2.0)
        settings = read_settings(settings_path)
        blocked = project_block(settings, data.get("cwd"))
        if blocked:
            return {}, blocked
        thresholds = ({"threshold_5h": settings["threshold_5h"],
                       "threshold_weekly": settings["threshold_weekly"]}
                      if settings_path is not None else {})
        decision = decide(read_snapshot(snapshot_path), threshold=threshold,
                          max_age=max_age, **thresholds)
        if not decision.active:
            return {}, decision.reason
        bootstrap = Path(bootstrap).resolve(strict=True)
        if hashlib.sha256(bootstrap.read_bytes()).hexdigest() != expected_sha256:
            return {}, "upstream_bootstrap_changed"
    except (OSError, ValueError, TypeError):
        return {}, "unavailable_or_invalid_input"
    # Restrict Python import routing; the builder pins the upstream checkout explicitly.
    child_env = dict(parent_env)
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONHOME", None)
    child_env.update(SAFE_ENV)
    child_env["TE_CORE_PATH"] = str(bootstrap.parents[2])
    child_env["TOKENECONOMIZER_HOME"] = str(Path(snapshot_path).resolve().parent / "te-state")
    proc = None
    try:
        proc = subprocess.Popen([sys.executable, str(bootstrap), "hook", "--host", "codex"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=child_env,
                                start_new_session=(os.name == "posix"))
        out, _ = proc.communicate(payload, timeout=timeout)
        if proc.returncode != 0 or len(out) > 2_000_000:
            return {}, "upstream_failed"
        # Upstream may emit JSON progress lines before the final hook object.
        messages = [json.loads(line) for line in out.splitlines() if line.strip()]
        if not messages:
            return {}, "invalid_upstream_output"
        if any(not isinstance(m, dict) or m.get("type") != "progress" for m in messages[:-1]):
            return {}, "invalid_upstream_output"
        answer = messages[-1]
        if not isinstance(answer, dict):
            return {}, "invalid_upstream_output"
        if answer.get("type") == "progress":
            return {}, "invalid_upstream_output"
        return answer, "forwarded_envfacts"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        if proc is not None:
            stop_process(proc)
            proc.communicate()
        return {}, "upstream_failed"
