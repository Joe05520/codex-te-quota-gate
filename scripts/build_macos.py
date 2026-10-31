"""Build a native local .app without third-party packages or changes to Codex."""
import argparse
from pathlib import Path
import plistlib
import platform
import shutil
import subprocess
import sys

p=argparse.ArgumentParser()
p.add_argument('--output', required=True)
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
app=Path(a.output).resolve()
if app.exists(): raise SystemExit('Output already exists; choose a new path')
contents=app/'Contents'; macos=contents/'MacOS'; resources=contents/'Resources'
macos.mkdir(parents=True);resources.mkdir()
shutil.copytree(root/'quota_gate',resources/'python/quota_gate',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
with (contents/'Info.plist').open('wb') as f:
 plistlib.dump({'CFBundleIdentifier':'io.github.Joe05520.te-quota-bar','CFBundleName':'TE Quota Bar',
  'CFBundleDisplayName':'TE Quota Bar','CFBundleExecutable':'TEQuotaBar','CFBundlePackageType':'APPL',
  'CFBundleShortVersionString':'0.3.0','CFBundleVersion':'3','LSUIElement':True,'LSMinimumSystemVersion':'13.0',
  'NSHighResolutionCapable':True},f)
with (resources/'Runtime.plist').open('wb') as f:plistlib.dump({'PythonExecutable':sys.executable},f)
subprocess.run(['xcrun','swiftc','-O','-swift-version','5','-target',platform.machine()+'-apple-macosx13.0',str(root/'macos/TEQuotaBar.swift'),'-o',str(macos/'TEQuotaBar'),'-framework','AppKit','-framework','SwiftUI'],check=True)
subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
print(app)
