"""Menu-bar backend: read-only diagnostics plus the existing local GUI and quota reader."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import sys
import threading
import time
from .gui import GuiState, make_server, synthetic_snapshot
from .policy import decide
from .rpc import read_hooks, read_quota
from .settings import configured_decision, read_settings
from .storage import read_snapshot, write_snapshot


def intervention(activity):
    last = activity.get('lastEvent') if isinstance(activity, dict) else None
    if not isinstance(last, dict):
        return {'state': 'unknown', 'label': '尚未確認介入 · 尚無 hook 紀錄'}
    reason = last.get('reason')
    if reason in ('upstream_failed', 'invalid_upstream_output', 'upstream_bootstrap_changed', 'runner_failed'):
        state, label = 'failed', 'TE 執行失敗 · 請查看最後結果'
    elif last.get('contextEmitted'):
        state, label = 'context_returned', 'TE 已回傳注入內容（最近一次）'
    elif last.get('forwarded'):
        state, label = 'forwarded', 'TE 已執行 · 未回傳注入內容'
    else:
        state, label = 'skipped', '未介入 · 最近一次 hook 已跳過'
    return {'state': state, 'label': label, 'at': last.get('at')}


def status(runtime, trust=None):
    runtime = Path(runtime)
    try:
        settings = read_settings(runtime / 'settings.json')
        quota = read_snapshot(runtime / 'quota.json')
        # Global eligibility does not imply participation for an individual cwd.
        result = configured_decision(quota, {**settings, 'projects': []}).as_dict()
        thresholds = [settings['threshold_5h'], settings['threshold_weekly']]
        excluded = sum(p['excluded'] for p in settings['projects'])
    except (OSError, ValueError):
        quota = None; result = decide(None).as_dict(); thresholds = [None, None]; excluded = None
    try:
        activity = read_snapshot(runtime / 'hook-activity.json')
        if activity.get('schemaVersion') != 1: activity = None
    except (OSError, ValueError, AttributeError):
        activity = None
    return {'updatedAt': time.time(), 'decision': result, 'thresholds': thresholds,
            'excludedProjects': excluded, 'snapshotAt': quota.get('observedAt') if isinstance(quota, dict) else None,
            'activity': activity, 'hooks': trust, 'intervention': intervention(activity),
            'windows': quota.get('windows', []) if isinstance(quota, dict) else []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--codex', required=True)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    base = Path(args.base).resolve(); runtime = base / 'runtime'
    if args.demo:
        runtime = base / 'demo-runtime'  # Never write real runtime during native preview.
        write_snapshot(runtime / 'settings.json', read_settings())
        write_snapshot(runtime / 'quota.json', synthetic_snapshot('normal'))
    if not runtime.is_dir(): raise SystemExit('Existing installation runtime is required')
    lock = open(runtime / 'desktop-monitor.lock', 'a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('A menu-bar monitor is already running')
    server = None
    if not args.demo:
        try:
            server = make_server(GuiState(runtime/'settings.json', runtime/'quota.json'), 8766)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        except OSError:
            pass  # Existing browser GUI can continue independently.
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    trust = None; last_probe = 0; next_emit = 0
    try:
        while not stopped:
            now = time.time()
            if not args.demo and now - last_probe >= 60:
                last_probe = now
                try:
                    old = read_snapshot(runtime/'quota.json')
                    age = now - old.get('observedAt', 0)
                except (OSError, ValueError, TypeError): age = 999
                if age >= 55 or decide(old).remaining_5h is None:
                    try: write_snapshot(runtime/'quota.json', read_quota(args.codex))
                    except Exception:
                        write_snapshot(runtime/'quota.json', {'schemaVersion':1,'observedAt':time.time(), 'limitId':'codex','windows':[]})
                try: trust = read_hooks(args.codex, cwd=str(base))
                except Exception: trust = None
            if now >= next_emit:
                snapshot = status(runtime, trust)
                snapshot['demo'] = args.demo
                print(json.dumps(snapshot, allow_nan=False), flush=True)
                next_emit = now + 3
            ready, _, _ = select.select([sys.stdin], [], [], .5)
            if ready:
                line = sys.stdin.readline()
                if not line: break
                if line.strip() == 'refresh': last_probe = 0; next_emit = 0
    finally:
        if server: server.shutdown(); server.server_close()
        lock.close()


if __name__ == '__main__':
    main()
