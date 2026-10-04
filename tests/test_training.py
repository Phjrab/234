"""Supervisor persistence, immutable snapshots, control and artifact boundaries."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from simulator import DashboardError
from training import TrainingManager,contained,atomic_json,MODELS
from train_worker import plans,messages
from workspace import Workspace

class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.w=Workspace(self.root/'workspace.sqlite3')
        self.m=TrainingManager(self.root/'training',self.w)
        self.cap=patch.object(self.m,'capabilities',return_value={'available':True});self.cap.start()
        key=next(iter(MODELS));folder=self.m.model_root/MODELS[key]['directory'];folder.mkdir(parents=True)
        (folder/'config.json').write_text('{}');(folder/'model.safetensors').write_bytes(b'synthetic fixture')
        atomic_json(folder/'forge-model.json',{'model':key,'revision':'a'*40})
        ds=self.w.import_dataset({'name':'synthetic','kind':'LLM','text':'\n'.join(json.dumps({'instruction':f'Item {i}','output':f'Reply {i}'}) for i in range(12))})['dataset']
        self.w.split_dataset(ds['id'],{'seed':42,'val_ratio':.25})
        self.config={'model':key,'dataset':ds['id'],'method':'lora','max_steps':10,'gradient_accumulation':1}
    def tearDown(self):
        self.cap.stop();self.m.close();self.w.close();self.tmp.cleanup()
    def code(self,expected,call):
        with self.assertRaises(DashboardError) as e:call()
        self.assertEqual(e.exception.code,expected)
    def checkpoint(self,run,step=2):
        folder=self.m.root/run['id']/f'checkpoint-{step:06d}';folder.mkdir()
        (folder/'adapter_model.safetensors').write_bytes(b'synthetic-adapter')
        (folder/'training-state.pt').write_bytes(b'private optimizer state')
        return folder
    def test_queue_snapshots_text_and_persists_without_launching(self):
        run=self.m.queue(self.config);self.assertFalse(run['simulated']);self.assertEqual(run['status'],'queued')
        job=json.loads((self.m.root/run['id']/'job.json').read_text())
        self.assertEqual(len(job['train']),9);self.assertEqual(len(job['validation']),3)
        self.assertEqual(run['total_steps'],10);self.assertIsNone(self.m.process)
        self.assertNotIn('model_path',json.dumps(run));self.assertNotIn('output',run['config'])
        restored=TrainingManager(self.m.root,self.w)
        self.assertEqual(restored.get_run(run['id'])['config'],run['config']);restored.close()
    def test_model_and_resource_allowlists(self):
        self.code('unsupported_model',lambda:self.m.queue({**self.config,'model':'arbitrary/python-model'}))
        self.code('resource_limit',lambda:self.m.queue({**self.config,'batch_size':64}))
        self.code('invalid_config',lambda:self.m.queue({**self.config,'trust_remote_code':True}))
        self.code('invalid_config',lambda:self.m.queue({**self.config,'failure_mode':'oom'}))
    def test_unsplit_and_duplicate_leakage_rejected(self):
        ds=self.w.import_dataset({'text':'\n'.join([json.dumps({'instruction':'same','output':'same'})]*3)})['dataset']
        self.code('split_required',lambda:self.m.queue({**self.config,'dataset':ds['id']}))
        self.w.split_dataset(ds['id'],{})
        self.code('dataset_leakage',lambda:self.m.queue({**self.config,'dataset':ds['id']}))
    def test_pausing_is_acknowledgement_until_worker_exit(self):
        run=self.m.queue(self.config);internal=self.m._find(run['id']);internal['status']='running';self.m._save(internal)
        result=self.m.action(run['id'],'pause');self.assertEqual(result['status'],'pausing')
        self.assertEqual(json.loads((self.m.root/run['id']/'control.json').read_text())['action'],'pause')
        self.assertNotIn('resume',result['allowed_actions'])
        self.m.action(run['id'],'cancel');self.assertEqual(self.m.get_run(run['id'])['status'],'canceling')
    def test_queued_cancel_does_not_kill_other_processes(self):
        run=self.m.queue(self.config);self.assertEqual(self.m.action(run['id'],'cancel')['status'],'canceled')
        self.assertIsNone(self.m.process)
        self.code('invalid_transition',lambda:self.m.action(run['id'],'pause'))
    def test_event_identity_sequence_finite_values_and_artifact_paths(self):
        run=self.m._find(self.m.queue(self.config)['id'])
        self.m._event(run,{'run_id':'train-000000000000','sequence':1,'kind':'metric','payload':{'step':1,'loss':2}})
        self.assertEqual(run['step'],0)
        event={'run_id':run['id'],'sequence':1,'kind':'metric','payload':{'step':1,'loss':2}}
        self.m._event(run,event);self.m._event(run,event);self.assertEqual(len(run['metrics']),1)
        self.m._event(run,{**event,'sequence':2,'payload':{'step':2,'loss':float('nan')}})
        self.assertEqual(run['step'],1)
        self.m._event(run,{**event,'sequence':3,'kind':'checkpoint','payload':{'name':'../../secret'}})
        self.assertEqual(run['checkpoints'],[])
    def test_artifact_exports_adapter_without_optimizer_or_symlink(self):
        run=self.m._find(self.m.queue(self.config)['id']);folder=self.checkpoint(run)
        (folder/'outside.json').symlink_to(self.root/'workspace.sqlite3')
        model_path=json.loads((self.m.root/run['id']/'job.json').read_text())['model_path']
        (folder/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':model_path}))
        run['checkpoints']=[{'name':folder.name}];self.m._save(run)
        body,_=self.m.artifact(run['id'],folder.name)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertIn('adapter_model.safetensors',z.namelist())
            self.assertNotIn('training-state.pt',z.namelist());self.assertNotIn('outside.json',z.namelist())
            self.assertNotIn(str(self.root),z.read('adapter_config.json').decode())
            self.assertEqual(json.loads(z.read('adapter_config.json'))['base_model_name_or_path'],self.config['model'])
        self.code('not_found',lambda:self.m.artifact(run['id'],'../../secret'))
    def test_retry_preserves_original_snapshot_and_copies_checkpoint(self):
        run=self.m._find(self.m.queue(self.config)['id']);folder=self.checkpoint(run)
        run['status']='failed';run['step']=2;run['checkpoints']=[{'name':folder.name}];self.m._save(run)
        original=json.loads((self.m.root/run['id']/'job.json').read_text())
        self.w.split_dataset(self.config['dataset'],{'seed':99,'val_ratio':.5})
        retry=self.m.action(run['id'],'retry');job=json.loads((self.m.root/retry['id']/'job.json').read_text())
        self.assertEqual(job['train'],original['train']);self.assertEqual(job['validation'],original['validation'])
        self.assertEqual(retry['retry_of'],run['id']);self.assertTrue(Path(job['resume_from']).is_dir())
        self.assertTrue((Path(job['resume_from'])/'training-state.pt').is_file())
        self.assertTrue(self.m.artifact(retry['id'],folder.name)[0])
    def test_recovery_marks_interrupted_work_failed_without_reset(self):
        run=self.m._find(self.m.queue(self.config)['id']);run['status']='running';run['step']=2;self.m._save(run)
        restored=TrainingManager(self.m.root,self.w)
        self.assertEqual(restored.get_run(run['id'])['status'],'failed')
        self.assertEqual(restored.get_run(run['id'])['step'],2);restored.close()
    def test_paths_refuse_symlink_escape(self):
        (self.m.root/'escape').symlink_to(self.root)
        self.code('invalid_path',lambda:contained(self.m.root,'escape/workspace.sqlite3'))
        self.code('invalid_path',lambda:contained(self.m.root,'../workspace.sqlite3'))
    def test_accumulation_epochs_and_seed_are_reproducible(self):
        cfg={'epochs':2,'batch_size':2,'gradient_accumulation':2,'seed':42,'max_steps':10}
        p=plans(5,cfg);self.assertEqual(p,plans(5,cfg));self.assertEqual(len(p),4)
        self.assertEqual(sorted(i for group in p[:2] for batch in group for i in batch),list(range(5)))
        self.assertEqual(messages({'instruction':'hi','input':'there','output':'yes'})[-1]['content'],'yes')

if __name__=='__main__':unittest.main()
