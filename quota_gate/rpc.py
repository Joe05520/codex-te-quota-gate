"""Read quotas through documented Codex app-server stdio, without starting turns."""
import json
import os
import selectors
import signal
import subprocess
import time

from .policy import normalize


class QuotaReadError(RuntimeError):
    pass


def stop_process(proc):
    """Bounded cleanup, including a timed-out hook's process group on POSIX."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=0.3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait(timeout=1)


def read_quota(codex="codex", *, timeout=5.0, limit_id="codex", command=None):
    if os.name != "posix":
        raise QuotaReadError("live quota collector currently supports macOS/Linux only")
    # command is injectable for protocol tests; the public CLI accepts a binary path only.
    cmd = command if command is not None else [codex, "app-server"]
    env = dict(os.environ, TE_DISABLE="1", TE_SIDECALL="1")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    deadline = time.monotonic() + timeout
    pending = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)

    def send(message):
        proc.stdin.write((json.dumps(message) + "\n").encode())
        proc.stdin.flush()

    def receive(expected):
        while True:
            if b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                try:
                    msg = json.loads(line)
                except (ValueError, UnicodeError):
                    raise QuotaReadError("invalid app-server JSON") from None
                if not isinstance(msg, dict):
                    raise QuotaReadError("invalid app-server message")
                if "method" in msg and "id" in msg:
                    # Never approve a server-initiated action or authentication request.
                    send({"id": msg["id"], "error": {
                        "code": -32601, "message": "quota reader does not approve actions"}})
                if msg.get("id") == expected and "method" not in msg:
                    if "error" in msg or not isinstance(msg.get("result"), dict):
                        raise QuotaReadError("quota RPC failed; verify login and CLI compatibility")
                    return msg["result"]
                continue
            left = deadline - time.monotonic()
            if left <= 0 or not selector.select(left):
                raise QuotaReadError("quota RPC timed out")
            block = os.read(proc.stdout.fileno(), 65536)
            if not block:
                raise QuotaReadError("app-server exited before replying")
            pending.extend(block)
            if len(pending) > 2_000_000:
                raise QuotaReadError("app-server reply too large")

    try:
        send({"method": "initialize", "id": 1, "params": {"clientInfo": {
            "name": "te_quota_gate", "title": "TE Quota Gate", "version": "0.1.0"}}})
        receive(1)
        send({"method": "initialized", "params": {}})
        send({"method": "account/rateLimits/read", "id": 2})
        return normalize(receive(2), limit_id=limit_id)
    finally:
        selector.close()
        stop_process(proc)
        proc.stdin.close()
        proc.stdout.close()
