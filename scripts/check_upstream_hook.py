"""Check real pinned upstream output with isolated synthetic quota/context; no model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quota_gate.bridge import run_hook, SAFE_ENV
from quota_gate.bundle import REVIEWED_REVISION
from quota_gate.gui import synthetic_snapshot
from quota_gate.storage import write_snapshot
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
source=a.source.resolve()
revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if revision!=REVIEWED_REVISION:raise SystemExit('Unexpected upstream revision')
sys.path.insert(0,str(source))
from tokeneconomizer.plugin.context import LiveContext
from tokeneconomizer.plugin.hosts import Codex
with tempfile.TemporaryDirectory(prefix='te-real-upstream-check-') as tmp:
 root=Path(tmp);project=root/'synthetic-project';project.mkdir();runtime=root/'runtime';runtime.mkdir()
 bootstrap=source/'plugin/scripts/te_bootstrap.py'
 env={**os.environ,**SAFE_ENV,'TE_SIDECALL':'0','TE_GATE_DIAGNOSTIC':'1','TOKENECONOMIZER_HOME':str(runtime/'te-state')}
 payload={'session_id':'synthetic-upstream-check','hook_event_name':'SessionStart','source':'startup','cwd':str(project)}
 kwargs={'snapshot_path':runtime/'quota.json','bootstrap':bootstrap,'expected_sha256':hashlib.sha256(bootstrap.read_bytes()).hexdigest(),'env':env}
 write_snapshot(runtime/'quota.json',synthetic_snapshot('normal'))
 out,reason=run_hook(json.dumps(payload).encode(),**kwargs)
 assert not out and reason=='quota_sufficient'
 write_snapshot(runtime/'quota.json',synthetic_snapshot('low5h'))
 out,reason=run_hook(json.dumps(payload).encode(),**kwargs)
 assert reason=='forwarded_envfacts',reason
 empty_forward=not out
 ctx=LiveContext.build(Codex(),str(project),env,session_id=payload['session_id'])
 text='[Synthetic diagnostic fixture]\n- Use the project-specific test interpreter for this synthetic project.'
 ctx.store.write('injection.json',{'rendered':text})
 out,reason=run_hook(json.dumps(payload).encode(),**kwargs)
 assert reason=='forwarded_envfacts'
 assert out.get('hookSpecificOutput',{}).get('additionalContext')==text,out
 activity=json.loads((runtime/'diagnostic-hook-activity.json').read_text())
 assert activity['counts']=={'checked':3,'forwarded':2,'contextEmitted':1}
 assert not (runtime/'hook-activity.json').exists()
 report={'passed':True,'upstreamRevision':revision,'paidModelCalls':0,'syntheticDataOnly':True,'realUpstreamBootstrap':True,'sufficientQuotaSkipped':True,'lowQuotaForwarded':True,'emptyContextDistinguished':empty_forward,'cachedSyntheticContextReturned':True,'receiptCounts':activity['counts'],'liveRuntimeModified':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
