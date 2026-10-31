"""Bounded local receipts: never persist prompts, context, session IDs or project paths."""
import json
import os
from pathlib import Path
import time
from .storage import read_snapshot, write_snapshot

EVENTS = {'SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop', 'SessionEnd'}


def record_activity(snapshot_path, payload, answer, reason, duration, *, diagnostic=False):
    try:
        import fcntl
        directory = Path(snapshot_path).resolve().parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(directory / 'hook-activity.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = directory / ('diagnostic-hook-activity.json' if diagnostic else 'hook-activity.json')
            try:
                state = read_snapshot(path)
                if state.get('schemaVersion') != 1 or not isinstance(state.get('counts'), dict):
                    state = {}
            except (OSError, ValueError, AttributeError):
                state = {}
            data = json.loads(payload)
            event = data.get('hook_event_name') if isinstance(data, dict) else None
            event = event if event in EVENTS else 'Unknown'
            extra = answer.get('hookSpecificOutput')
            context = answer.get('additionalContext') or (extra.get('additionalContext') if isinstance(extra, dict) else None)
            emitted = isinstance(context, str) and bool(context.strip())
            forwarded = reason == 'forwarded_envfacts'
            receipt = {'at': time.time(), 'event': event, 'reason': reason,
                       'source': 'diagnostic' if diagnostic else 'host',
                       'forwarded': forwarded, 'contextEmitted': forwarded and emitted,
                       'durationMs': round(duration * 1000)}
            counts = state.get('counts', {})
            for key, increment in [('checked', 1), ('forwarded', int(forwarded)),
                                   ('contextEmitted', int(forwarded and emitted))]:
                counts[key] = int(counts.get(key, 0)) + increment
            state.update(schemaVersion=1, lastEvent=receipt, counts=counts)
            if forwarded:
                state['lastForwarded'] = receipt
            if forwarded and emitted:
                state['lastContext'] = receipt
            state['recent'] = (state.get('recent', []) + [receipt])[-40:]
            write_snapshot(path, state)
    except Exception:
        pass  # Observability must never alter hook output or stall a session.
