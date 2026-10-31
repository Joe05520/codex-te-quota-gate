#!/bin/sh
cd "$(dirname "$0")" || exit 1
for gate_python in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if "$gate_python" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
        exec "$gate_python" -m quota_gate gui --open "$@"
    fi
done
echo 'Python 3.10 or newer is required. No software has been installed.'
read -r gate_reply
