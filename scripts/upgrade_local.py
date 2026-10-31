"""Explicit local upgrade; preserves runtime, backs up marketplace, never trusts hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from quota_gate import __version__
from quota_gate.bundle import build
p=argparse.ArgumentParser()
p.add_argument('--base',type=Path,default=Path.home()/'Library/Application Support/TE Quota Gate')
p.add_argument('--codex',default='/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
a=p.parse_args();base=a.base.resolve()
settings=base/'runtime/settings.json'
if not settings.is_file():raise SystemExit('Existing installation required; no settings created')
manifest=base/'marketplace/plugin/.codex-plugin/plugin.json'
if manifest.is_file() and json.loads(manifest.read_text()).get('version')==__version__:
 raise SystemExit('This marketplace is already updated. Review /hooks in Codex; no reinstall performed.')
settings_hash=hashlib.sha256(settings.read_bytes()).hexdigest()
stamp=time.strftime('%Y%m%dT%H%M%S')
stage=base/('marketplace-staging-'+stamp)
build(base/'upstream',stage,base/'runtime/quota.json',settings)
backup=base/'backups'/('observation-upgrade-'+stamp)
backup.mkdir(parents=True,mode=0o700)
shutil.copy2(Path.home()/'.codex/config.toml',backup/'config.toml')
marketplace=base/'marketplace'
if marketplace.exists(): marketplace.rename(backup/'marketplace')
stage.rename(marketplace)
try:
 subprocess.run([a.codex,'plugin','add','te-quota-gate@te-quota-gate','--json'],check=True)
finally:
 if hashlib.sha256(settings.read_bytes()).hexdigest()!=settings_hash:
  raise RuntimeError('Settings changed concurrently; inspect before proceeding')
print('Updated. Review the five te-quota-gate hooks in Codex /hooks. Trust was not modified.')
print('Backup: '+str(backup))
