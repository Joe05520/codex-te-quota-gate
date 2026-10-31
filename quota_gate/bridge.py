"""Gate a single upstream hook; guard settings cannot be weakened through TE env vars."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .policy import decide
from .rpc import stop_process
from .storage import read_snapshot

SAFE_ENV = {
    "TE_DISABLE": "0", "TE_MICROSKILLS": "envfacts", "TE_TOOLPRUNE": "off",
    "TE_LOOPGUARD": "off", "TE_REPOMAP": "off",
}


def run_hook(payload, *, snapshot_path, bootstrap, expected_sha256,
             threshold=15.0, max_age=90.0, timeout=10.0, env=None):
    parent_env = os.environ if env is None else env
    truthy = ("1", "true", "yes", "on")
    if any(str(parent_env.get(k, "")).strip().lower() in truthy
           for k in ("TE_DISABLE", "TE_SIDECALL")):
        return {}, "explicitly_disabled"
    try:
        decision = decide(read_snapshot(snapshot_path), threshold=threshold, max_age=max_age)
        if not decision.active:
            return {}, decision.reason
        data = json.loads(payload)
        if not isinstance(data, dict) or not data.get("session_id"):
            return {}, "invalid_hook_payload"
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
        answer = json.loads(out)
        if not isinstance(answer, dict):
            return {}, "invalid_upstream_output"
        return answer, "forwarded_envfacts"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        if proc is not None:
            stop_process(proc)
            proc.communicate()
        return {}, "upstream_failed"
