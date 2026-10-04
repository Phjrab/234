"""Real training API remains behind the dashboard authentication/CSRF boundary."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from auth import AuthStore,COOKIE_NAME
from server import DashboardServer
from simulator import Simulator
from training import TrainingManager,MODELS,atomic_json
from workspace import Workspace

class TrainingAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();r=Path(self.tmp.name)
        self.w=Workspace(r/'workspace.sqlite3');self.sim=Simulator(r/'state.sqlite3',seed_demo=False)
        self.auth=AuthStore(r/'auth.sqlite3')
        token,session=self.auth.login('admin','admin','127.0.0.1')
        self.token,self.session=self.auth.change_password(token,'127.0.0.1','admin','Synthetic-Training-API-Password-123!',session['csrf_token'])
        self.m=TrainingManager(r/'training',self.w)
        self.cap=patch.object(self.m,'capabilities',return_value={'available':True,'models':[]});self.cap.start()
        model=next(iter(MODELS));folder=self.m.model_root/MODELS[model]['directory'];folder.mkdir(parents=True)
        (folder/'config.json').write_text('{}');(folder/'model.safetensors').write_bytes(b'synthetic')
        atomic_json(folder/'forge-model.json',{'model':model,'revision':'a'*40})
        ds=self.w.import_dataset({'text':'\n'.join(json.dumps({'instruction':f'{i}','output':f'{i}'}) for i in range(5))})['dataset']
        self.w.split_dataset(ds['id'],{})
        self.config={'model':model,'dataset':ds['id'],'method':'lora'}
        self.server=DashboardServer(('127.0.0.1',0),self.sim,r,auth=self.auth,workspace=self.w,training=self.m)
        self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.cap.stop()
        self.auth.close();self.w.close();self.sim.close();self.tmp.cleanup()
    def request(self,path,body=None,auth=True,csrf=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers={}
        if auth:headers['Cookie']=COOKIE_NAME+'='+self.token
        if body is not None:
            headers.update({'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}'})
            if csrf:headers['X-CSRF-Token']=self.session['csrf_token']
        conn.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
        res=conn.getresponse();raw=res.read();status=res.status;conn.close()
        return status,json.loads(raw)
    def test_new_endpoints_require_login_and_csrf(self):
        for path,body in [('/api/training',None),('/api/training/preflight',self.config),('/api/training/runs',self.config)]:
            self.assertEqual(self.request(path,body,auth=False)[0],401)
        self.assertEqual(self.request('/api/training/runs',self.config,csrf=False)[0],403)
        self.assertEqual(self.m.runs(),[])
    def test_preflight_and_queue_then_generic_run_routes(self):
        status,report=self.request('/api/training/preflight',self.config);self.assertEqual(status,200);self.assertTrue(report['can_train'])
        status,payload=self.request('/api/training/runs',self.config);self.assertEqual(status,201)
        run=payload['run'];self.assertFalse(run['simulated'])
        self.assertEqual(self.request('/api/runs/'+run['id'])[0],200)
        self.assertEqual(self.request('/api/runs/'+run['id']+'/pause',{})[0],409)
        self.assertEqual(self.request('/api/runs/'+run['id']+'/cancel',{})[1]['run']['status'],'canceled')
    def test_export_distinguishes_real_metadata_and_denies_unauthorized_artifact(self):
        _,payload=self.request('/api/training/runs',self.config);run=payload['run']
        status,export=self.request('/api/runs/'+run['id']+'/export?format=json')
        self.assertEqual(status,200);self.assertEqual(export['mode'],'real_training');self.assertFalse(export['synthetic'])
        self.assertNotIn(str(self.m.root),json.dumps(export))
        self.assertEqual(self.request('/api/runs/'+run['id']+'/artifacts/checkpoint-000001',auth=False)[0],401)
        self.assertEqual(self.request('/api/runs/'+run['id']+'/artifacts/checkpoint-000001')[0],404)
    def test_arbitrary_command_or_model_cannot_be_queued(self):
        status,_=self.request('/api/training/runs',{**self.config,'command':'echo unexpected'})
        self.assertEqual(status,400);self.assertEqual(self.m.runs(),[])
        status,_=self.request('/api/training/runs',{**self.config,'model':'unapproved/model'})
        self.assertEqual(status,400);self.assertEqual(self.m.runs(),[])

if __name__=='__main__':unittest.main()
