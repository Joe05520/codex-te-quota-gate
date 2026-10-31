"""Real installed Codex hooks against a loopback-only canned response, never a paid model.

Python 3.11+ diagnostic. Does not install/trust hooks or modify quota/settings.
Only sanitized summaries are saved. Diagnostic receipts stay separate from normal activity.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quota_gate.rpc import read_hooks

p=argparse.ArgumentParser()
p.add_argument('--codex',required=True)
p.add_argument('--output',required=True,type=Path)
p.add_argument('--runtime',type=Path,default=Path.home()/'Library/Application Support/TE Quota Gate/runtime')
a=p.parse_args()
ready=read_hooks(a.codex)
if not ready['ready']:raise SystemExit('Hooks are not trusted/ready; no test was run.')
config=tomllib.loads((Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml').read_text())
seen=[]
class Model(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length','0')))
  seen.append(self.path)
  def event(kind,**fields):return 'event: '+kind+'\ndata: '+json.dumps(dict(type=kind,**fields))+'\n\n'
  result=(event('response.created',response={'id':'resp_local_fixture'})+
   event('response.output_item.done',item={'type':'message','role':'assistant','id':'msg_local_fixture','content':[{'type':'output_text','text':'Local diagnostic complete.'} ]})+
   event('response.completed',response={'id':'resp_local_fixture','usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}})).encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)
server=ThreadingHTTPServer(('127.0.0.1',0),Model)
threading.Thread(target=server.serve_forever,daemon=True).start()
report={'diagnostic':True,'paidModelCalls':0,'hooksReady':ready}
try:
 with tempfile.TemporaryDirectory(prefix='te-codex-diagnostic-') as tmp:
  # Explicit false entries override merged user settings without copying credentials.
  mcp='{'+','.join(json.dumps(k)+'={enabled=false}' for k in config.get('mcp_servers',{}))+'}'
  plugins='{'+','.join(json.dumps(k)+'={enabled='+('true' if k=='te-quota-gate@te-quota-gate' else 'false')+'}' for k in config.get('plugins',{}))+'}'
  args=[a.codex,'exec','--ephemeral','--skip-git-repo-check','-C',tmp,'--sandbox','read-only','--json','-m','te-local-fixture',
   '-c','model_provider="te_fixture"','-c','features.apps=false','-c','mcp_servers='+mcp,'-c','plugins='+plugins,
   '-c','model_providers.te_fixture={name="Local fixture",base_url="http://127.0.0.1:'+str(server.server_port)+'/v1",wire_api="responses",supports_websockets=false,requires_openai_auth=false,request_max_retries=0,stream_max_retries=0}',
   'Reply with the fixed local fixture response. Do not use tools.']
  result=subprocess.run(args,capture_output=True,text=True,timeout=40,env=dict(os.environ,TE_GATE_DIAGNOSTIC='1'))
  events=[]
  for line in result.stdout.splitlines():
   try:events.append(json.loads(line).get('type'))
   except ValueError:pass
  report.update(exitCode=result.returncode,localRequests=seen,eventTypes=events)
  if result.returncode or not seen:report['passed']=False
  else:report['passed']='turn.completed' in events
except subprocess.TimeoutExpired:
 report.update(passed=False,error='diagnostic_timeout')
finally:
 server.shutdown();server.server_close()
try:
 activity=json.loads((a.runtime/'diagnostic-hook-activity.json').read_text())
 receipts=[r for r in activity.get('recent',[]) if r.get('source')=='diagnostic' and r.get('at',0)>=ready['observedAt']]
 report['hookCallbacksObserved']=[r['event'] for r in receipts]
 report['passed']=bool(report.get('passed') and receipts)
except (OSError,ValueError):
 report.update(passed=False,error='no_diagnostic_hook_receipt')
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(0 if report.get('passed') else 1)
