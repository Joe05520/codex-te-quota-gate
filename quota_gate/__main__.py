import argparse
import json
from pathlib import Path
import sys
import time

from .bridge import run_hook
from .bundle import build
from .policy import decide
from .rpc import QuotaReadError, read_quota
from .storage import read_snapshot, write_snapshot
from .settings import configured_decision, read_settings


def demo():
    now = 1800000000
    for label, h, w, age in [
        ("normal", 40, 60, 0), ("low 5h", 14, 60, 0),
        ("low weekly", 40, 14, 0), ("both low", 14, 14, 0),
        ("exactly 15", 15, 15, 0), ("quota reset", 100, 100, 0),
        ("stale", 14, 60, 100)]:
        sample = {"schemaVersion": 1, "observedAt": now - age, "limitId": "codex",
                  "windows": [{"windowDurationMins": duration, "usedPercent": 100 - rem,
                               "resetsAt": now + 3600}
                              for duration, rem in ((300, h), (10080, w))]}
        decision = decide(sample, now=now)
        print(f"{label:16} 5h={h:3}% weekly={w:3}% -> "
              f"{'ACTIVE' if decision.active else 'OFF':6} {decision.reason}")
    print("\nSynthetic data only. No login, network, plugin install, or model calls.")


def parser():
    p = argparse.ArgumentParser(description="Quota gate: either remaining window <15%; envfacts only")
    subs = p.add_subparsers(dest="action", required=True)
    subs.add_parser("demo", help="offline synthetic threshold demonstration")
    ev = subs.add_parser("evaluate", help="read a sanitized snapshot without running a hook")
    ev.add_argument("--snapshot", required=True)
    ev.add_argument("--settings", help="shared local settings file")
    ev.add_argument("--project", help="absolute project/working-directory path")
    for name in ("capture", "watch"):
        c = subs.add_parser(name, help="read quotas, never start a model turn")
        c.add_argument("--codex", default="codex", help="CLI executable or absolute bundled binary path")
        c.add_argument("--output", required=True, help="explicit private runtime snapshot path")
        if name == "watch":
            c.add_argument("--interval", type=float, default=60, help="seconds; minimum 30, maximum 75")
    h = subs.add_parser("hook", help="gate one hook against a sanitized snapshot")
    h.add_argument("--snapshot", required=True)
    h.add_argument("--bootstrap", required=True)
    h.add_argument("--bootstrap-sha256", required=True)
    h.add_argument("--settings", help="shared local settings file; re-read on every hook")
    b = subs.add_parser("build", help="generate marketplace only; does not install")
    b.add_argument("--source", required=True, help="clean pinned upstream checkout")
    b.add_argument("--output", required=True, help="new local marketplace directory")
    b.add_argument("--snapshot", required=True, help="same absolute path used by capture/watch")
    b.add_argument("--settings", help="shared settings path; defaults beside the snapshot")
    gui = subs.add_parser("gui", help="local browser GUI; no plugin install or live account reads")
    gui.add_argument("--settings", help="settings path; defaults to runtime/settings.json")
    gui.add_argument("--snapshot", help="snapshot path; defaults to runtime/quota.json")
    gui.add_argument("--demo", action="store_true", help="synthetic quotas in separate runtime/demo")
    gui.add_argument("--port", type=int, default=0, help="loopback port, 0 selects an available port")
    gui.add_argument("--open", action="store_true", help="open the local GUI in the default browser")
    return p


def capture(args):
    try:
        snapshot = read_quota(args.codex)
        write_snapshot(args.output, snapshot)
        print(json.dumps(decide(snapshot).as_dict()), flush=True)
        return 0
    except (OSError, ValueError, QuotaReadError):
        # Invalidate immediately rather than reuse an old active decision on failure.
        write_snapshot(args.output, {"schemaVersion": 1, "observedAt": time.time(),
                                     "limitId": "codex", "windows": [],
                                     "error": "quota_unavailable"})
        print("Quota unavailable; gate is OFF. Check CLI path/login. No login was attempted.",
              file=sys.stderr, flush=True)
        return 1


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == "demo":
            demo()
        elif args.action == "evaluate":
            try:
                decision = configured_decision(read_snapshot(args.snapshot),
                                               read_settings(args.settings), cwd=args.project)
            except (OSError, ValueError):
                print(json.dumps({"active": False, "reason": "snapshot_unavailable"}))
            else:
                print(json.dumps(decision.as_dict()))
        elif args.action == "capture":
            return capture(args)
        elif args.action == "watch":
            if not 30 <= args.interval <= 75:
                raise ValueError("interval must be 30 to 75 seconds")
            print("Quota reader running. Ctrl+C stops it; no model calls are made.", flush=True)
            try:
                while True:
                    capture(args)
                    time.sleep(args.interval)
            finally:
                write_snapshot(args.output, {"schemaVersion": 1, "observedAt": time.time(),
                                             "limitId": "codex", "windows": []})
        elif args.action == "hook":
            out, _ = run_hook(sys.stdin.buffer.read(), snapshot_path=args.snapshot,
                              bootstrap=args.bootstrap,
                              expected_sha256=args.bootstrap_sha256, settings_path=args.settings)
            print(json.dumps(out))
        elif args.action == "build":
            print(json.dumps(build(args.source, args.output, args.snapshot, args.settings), indent=2))
        elif args.action == "gui":
            from .gui import serve
            if args.demo and (args.settings or args.snapshot):
                raise ValueError("demo uses runtime/demo only; do not point it at live runtime files")
            base = Path("runtime/demo" if args.demo else "runtime")
            serve(args.settings or base / "settings.json", args.snapshot or base / "quota.json",
                  demo=args.demo, port=args.port, open_browser=args.open)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, QuotaReadError) as exc:
        if args.action == "hook":
            print("{}")
            return 0
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
