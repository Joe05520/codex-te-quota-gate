#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 scripts/upgrade_local.py
printf '\n%s\n' 'Then reopen Codex and review the five te-quota-gate hooks in /hooks.'
printf '%s\n' 'Press Enter to close.'
read -r answer
