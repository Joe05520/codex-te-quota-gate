import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from quota_gate.activity import record_activity
from quota_gate.desktop import status, intervention
from quota_gate.gui import synthetic_snapshot
from quota_gate.rpc import read_hooks, QuotaReadError
from quota_gate.settings import DEFAULTS
from quota_gate.storage import write_snapshot


class ActivityTests(unittest.TestCase):
    def test_receipts_distinguish_check_forward_context_without_sensitive_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)/'quota.json'
            payload=json.dumps({'session_id':'SECRET_SESSION','cwd':'/SECRET_PROJECT','prompt':'SECRET_PROMPT','hook_event_name':'SessionStart'}).encode()
            for answer, reason in [({},'quota_sufficient'),({},'forwarded_envfacts'),({'additionalContext':'SECRET_CONTEXT'},'forwarded_envfacts')]:
                record_activity(snapshot,payload,answer,reason,.05)
            receipt=json.loads((Path(tmp)/'hook-activity.json').read_text())
            self.assertEqual(receipt['counts'],{'checked':3,'forwarded':2,'contextEmitted':1})
            self.assertTrue(receipt['lastContext']['contextEmitted'])
            self.assertNotIn('SECRET',json.dumps(receipt))
            self.assertEqual((Path(tmp)/'hook-activity.json').stat().st_mode & 0o777,0o600)
            for _ in range(45):record_activity(snapshot,payload,{},'quota_sufficient',.01)
            receipt=json.loads((Path(tmp)/'hook-activity.json').read_text())
            self.assertEqual(len(receipt['recent']),40)
            self.assertEqual(receipt['counts']['checked'],48)
            self.assertEqual(receipt['lastForwarded']['at'],receipt['lastContext']['at'])

    def test_observation_failure_does_not_break_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker=Path(tmp)/'file';blocker.write_text('file')
            record_activity(blocker/'quota.json',b'{}',{},'quota_sufficient',0)

    def test_status_stale_or_missing_is_never_active_and_missing_receipts_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertFalse(status(root)['decision']['active'])
            write_snapshot(root/'settings.json',DEFAULTS)
            write_snapshot(root/'quota.json',synthetic_snapshot('low5h'))
            s=status(root)
            self.assertTrue(s['decision']['active'])
            self.assertIsNone(s['activity'])
            self.assertIsNone(s['hooks'])
            write_snapshot(root/'quota.json',synthetic_snapshot('stale'))
            self.assertFalse(status(root)['decision']['active'])

    def test_read_only_hooks_rpc_filters_and_redacts(self):
        script='''import json,sys
for line in sys.stdin:
 m=json.loads(line)
 if m.get('method')=='initialize': print(json.dumps({'id':m['id'],'result':{}}),flush=True)
 elif m.get('method')=='initialized': pass
 elif m.get('method')=='hooks/list':
  assert m['params']['cwds']==['/demo']
  h={'pluginId':'te-quota-gate@te-quota-gate','enabled':True,'trustStatus':'trusted','command':'SECRET'}
  print(json.dumps({'id':m['id'],'result':{'data':[{'hooks':[h]*5,'errors':[],'warnings':[]}]}}),flush=True)
 else: raise SystemExit('Unexpected request')
'''
        result=read_hooks(cwd='/demo',command=[sys.executable,'-u','-c',script])
        self.assertTrue(result['ready'])
        self.assertNotIn('SECRET',json.dumps(result))

    def test_native_backend_demo_is_separate_and_exits_on_stdin_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';runtime.mkdir()
            (runtime/'settings.json').write_text('preserve me')
            proc=subprocess.Popen([sys.executable,'-u','-m','quota_gate.desktop','--base',str(root),'--codex','/nonexistent','--demo'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            value=json.loads(proc.stdout.readline())
            self.assertTrue(value['demo'])
            self.assertIsNone(value['hooks'])
            proc.stdin.close();self.assertEqual(proc.wait(timeout=3),0)
            proc.stdout.close();proc.stderr.close()
            self.assertEqual((runtime/'settings.json').read_text(),'preserve me')
            self.assertFalse((runtime/'quota.json').exists())

    def test_native_backend_refreshes_invalid_fresh_snapshot_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';runtime.mkdir()
            write_snapshot(runtime/'settings.json',DEFAULTS)
            write_snapshot(runtime/'quota.json',{'schemaVersion':1,'observedAt':time.time(),'limitId':'codex','windows':[]})
            fake=root/'fake-codex'
            fake.write_text('#!'+sys.executable+'\n'+'''import json,sys,time
for line in sys.stdin:
 m=json.loads(line)
 if m.get('method')=='initialize': result={}
 elif m.get('method')=='initialized': continue
 elif m.get('method')=='hooks/list': result={'data':[{'hooks':[],'errors':[],'warnings':[]}]}
 elif m.get('method')=='account/rateLimits/read':
  w=lambda d:{'windowDurationMins':d,'usedPercent':86,'resetsAt':time.time()+3600}
  result={'rateLimitsByLimitId':{'codex':{'primary':w(300),'secondary':w(10080)}}}
 else: raise SystemExit('Unexpected method')
 print(json.dumps({'id':m['id'],'result':result}),flush=True)
''')
            fake.chmod(0o700)
            proc=subprocess.Popen([sys.executable,'-u','-m','quota_gate.desktop','--base',str(root),'--codex',str(fake)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            value=json.loads(proc.stdout.readline())
            self.assertTrue(value['decision']['active'])
            self.assertFalse(value['hooks']['ready'])
            self.assertEqual(value['decision']['remaining_5h'],14)
            proc.stdin.close();self.assertEqual(proc.wait(timeout=3),0)
            proc.stdout.close();proc.stderr.close()

    def test_intervention_requires_receipt_and_separates_failure_and_context(self):
        self.assertEqual(intervention(None)['state'],'unknown')
        for receipt, expected in [({'reason':'quota_sufficient'},'skipped'),({'reason':'upstream_failed'},'failed'),({'reason':'forwarded_envfacts','forwarded':True},'forwarded'),({'reason':'forwarded_envfacts','forwarded':True,'contextEmitted':True},'context_returned')]:
            self.assertEqual(intervention({'lastEvent':receipt})['state'],expected)

    def test_diagnostic_does_not_increment_live_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'quota.json'
            record_activity(path,b'{"hook_event_name":"SessionStart"}',{'additionalContext':'fixture'},'forwarded_envfacts',0,diagnostic=True)
            self.assertFalse((Path(tmp)/'hook-activity.json').exists())
            state=json.loads((Path(tmp)/'diagnostic-hook-activity.json').read_text())
            self.assertEqual(state['lastEvent']['source'],'diagnostic')
