import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from huggingface import HuggingFaceHub, classify, repo_id
from model_downloads import ModelDownloads, model_directory
from simulator import DashboardError
from training import TrainingManager, atomic_json
from workspace import Workspace

TOKEN='hf_SyntheticReadTokenForUnitTestingOnly123'
MODEL='example/model-not-in-the-default-list'
REV='a'*40

def fixture(**changes):
    info={'id':MODEL,'author':'example','sha':REV,'pipeline_tag':'text-generation',
          'config':{'model_type':'qwen2','architectures':['Qwen2ForCausalLM']},
          'tags':['license:apache-2.0'],'safetensors':{'total':100},'downloads':12,
          'siblings':[{'rfilename':'config.json','size':10},{'rfilename':'model.safetensors','size':100},
                      {'rfilename':'tokenizer.json','size':20},{'rfilename':'code.py','size':1},
                      {'rfilename':'pytorch_model.bin','size':2},{'rfilename':'sub/model.safetensors','size':2}]}
    info.update(changes);return info

class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.hub=HuggingFaceHub(self.root/'private')
    def tearDown(self):self.tmp.cleanup()
    def test_kind_uses_metadata_not_model_name(self):
        self.assertEqual(classify(fixture(id='example/vision-name')),'LLM')
        self.assertEqual(classify(fixture(id='example/text-name',pipeline_tag='image-text-to-text')),'VLM')
        self.assertEqual(classify(fixture(pipeline_tag='text2text-generation')),'LLM')
        self.assertEqual(classify(fixture(pipeline_tag='any-to-any',tags=['image-text-to-text'])),'VLM')
        self.assertEqual(classify(fixture(pipeline_tag='feature-extraction')),'OTHER')
        self.assertEqual(classify({'id':'example/no-metadata'}),'UNKNOWN')
        self.assertEqual(classify({'config':{'architectures':['GPT2LMHeadModel']}}),'UNKNOWN')
    def test_family_and_publisher_are_structured_metadata(self):
        result=self.hub.normalize(fixture())
        self.assertEqual(result['publisher'],'example');self.assertEqual(result['family'],'qwen2')
        self.assertEqual(result['license'],'apache-2.0');self.assertEqual(result['parameters'],100)
    def test_connect_checks_identity_and_persists_owner_only_without_echo(self):
        with patch.object(self.hub,'_request',return_value=({'name':'example'},'')) as request:
            result=self.hub.connect({'token':TOKEN})
        self.assertEqual(result,{'connected':True,'username':'example'})
        self.assertNotIn(TOKEN,json.dumps(result));self.assertEqual(self.hub.path.stat().st_mode&0o777,0o600)
        request.assert_called_once_with('/api/whoami-v2',token=TOKEN)
        restored=HuggingFaceHub(self.root/'private');self.assertEqual(restored.token(),TOKEN)
        self.hub.cache['private/model']=(1,{})
        self.hub.disconnect();self.assertFalse(self.hub.path.exists());self.assertFalse(self.hub.cache)
    def test_rejected_identity_does_not_replace_existing_account(self):
        with patch.object(self.hub,'_request',return_value=({'name':'example'},'')):self.hub.connect({'token':TOKEN})
        with patch.object(self.hub,'_request',side_effect=DashboardError('hf_auth_required','Denied',401)):
            with self.assertRaises(DashboardError):self.hub.connect({'token':TOKEN+'2'})
        self.assertEqual(self.hub.token(),TOKEN)
    def test_model_ids_refuse_traversal_urls_and_commands(self):
        for value in ('../model','org/../model','https://example.com/model','org/model;cmd','org/model\n',None):
            with self.assertRaises(DashboardError):repo_id(value)
    def test_search_pagination_stays_on_hub_and_keeps_filters(self):
        with patch.object(self.hub,'_request',return_value=([fixture()],'<https://huggingface.co/api/models?cursor=next-page>; rel="next"')) as request:
            result=self.hub.search({'author':'example','kind':'LLM','family':'qwen2','cursor':'old'})
        self.assertEqual(result['next_cursor'],'next-page')
        url=request.call_args.args[0]
        self.assertTrue(url.startswith('/api/models?'));self.assertIn('pipeline_tag=text-generation',url)
        self.assertIn('filter=qwen2',url);self.assertIn('author=example',url)
        with patch.object(self.hub,'_request',return_value=([], '<https://attacker.test/api/models?cursor=bad>; rel="next"')):
            self.assertIsNone(self.hub.search({})['next_cursor'])
    def test_invalid_search_never_makes_network_call(self):
        with patch.object(self.hub,'_request') as request:
            for query in ({'url':'https://attacker.test'},{'author':'../x'},{'sort':'arbitrary'},{'kind':'GPU'}):
                with self.assertRaises(DashboardError):self.hub.search(query)
            request.assert_not_called()
    def test_detail_pins_revision_and_excludes_code_pickle_and_nested_assets(self):
        with patch.object(self.hub,'_request',return_value=(fixture(),'')),patch.object(self.hub,'publisher',return_value={'name':'example'}):
            result=self.hub.detail(MODEL)
        self.assertEqual(result['revision'],REV);self.assertTrue(result['training_candidate'])
        self.assertEqual([f['name'] for f in result['files']],['config.json','model.safetensors','tokenizer.json'])
        self.assertEqual(result['download_bytes'],130)
    def test_unsupported_tasks_and_weight_formats_stay_selectable_with_reasons(self):
        with patch.object(self.hub,'_request',return_value=(fixture(pipeline_tag='text-to-image',siblings=[{'rfilename':'weights.gguf'}]),'')),patch.object(self.hub,'publisher',return_value={}):
            result=self.hub.detail(MODEL)
        self.assertEqual(result['id'],MODEL);self.assertFalse(result['training_candidate']);self.assertEqual(len(result['reasons']),2)
    def test_publisher_uses_official_avatar_and_rejects_external_hosts(self):
        with patch.object(self.hub,'_request',return_value=({'fullname':'Official Example','avatarUrl':'https://attacker.test/private'},'')):
            result=self.hub.publisher('example')
        self.assertEqual(result['name'],'Official Example');self.assertIsNone(result['avatar'])

class FakeProcess:
    def __init__(self):self.event=threading.Event();self.returncode=0
    def wait(self,timeout=None):self.event.wait(timeout);return self.returncode
    def terminate(self):self.returncode=-15;self.event.set()
    def kill(self):self.terminate()

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.hub=HuggingFaceHub(self.root/'private');self.downloads=ModelDownloads(self.root/'models',self.hub)
        self.info={**self.hub.normalize(fixture()),'download_bytes':130,'files':[{'name':'config.json'},{'name':'model.safetensors'}], 'training_candidate':True,'reasons':[]}
    def tearDown(self):self.downloads.close();self.tmp.cleanup()
    def test_explicit_download_keeps_token_out_of_jobs_and_public_status(self):
        process=FakeProcess()
        with patch.object(self.hub,'detail',return_value=self.info),patch.object(self.hub,'token',return_value=TOKEN),patch('model_downloads.subprocess.Popen',return_value=process) as popen:
            result=self.downloads.start({'model':MODEL,'revision':REV})
            self.assertEqual(result['status'],'downloading');self.assertNotIn(TOKEN,json.dumps(result))
            self.assertNotIn(TOKEN,(self.hub.root/'download-job.json').read_text())
            self.assertEqual(popen.call_args.kwargs['env']['HF_TOKEN'],TOKEN)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            with self.assertRaises(DashboardError):self.downloads.start({'model':MODEL,'revision':REV})
        self.assertEqual(self.downloads.cancel()['status'],'canceled');self.assertEqual(process.returncode,-15)
    def test_changed_revision_and_insufficient_disk_rejected_before_launch(self):
        with patch.object(self.hub,'detail',return_value=self.info),patch('model_downloads.subprocess.Popen') as popen:
            with self.assertRaises(DashboardError):self.downloads.start({'model':MODEL,'revision':'b'*40})
            with patch('model_downloads.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
                with self.assertRaises(DashboardError):self.downloads.start({'model':MODEL,'revision':REV})
            popen.assert_not_called()
    def test_restart_marks_incomplete_download_failed_without_starting_a_process(self):
        atomic_json(self.downloads.state_path,{'status':'downloading','model':MODEL})
        restored=ModelDownloads(self.downloads.root,self.hub)
        self.assertEqual(restored.status()['status'],'failed');self.assertIsNone(restored.process);restored.close()
    def test_additional_pinned_model_is_discovered_and_can_queue(self):
        workspace=Workspace(self.root/'workspace.sqlite3');manager=TrainingManager(self.root/'training',workspace,model_root=self.downloads.root)
        folder=self.downloads.root/model_directory(MODEL,REV);folder.mkdir()
        atomic_json(folder/'forge-model.json',{'model':MODEL,'revision':REV,'kind':'LLM','family':'qwen2','license':'apache-2.0'})
        (folder/'config.json').write_text('{"model_type":"qwen2"}');(folder/'model.safetensors').write_bytes(b'synthetic')
        ds=workspace.import_dataset({'text':'\n'.join(json.dumps({'instruction':str(i),'output':str(i)}) for i in range(5))})['dataset'];workspace.split_dataset(ds['id'],{})
        try:
            models=manager.capabilities()['models'];self.assertTrue(any(m['id']==MODEL and m['installed'] for m in models))
            with patch.object(manager,'capabilities',return_value={'available':True}):
                run=manager.queue({'model':MODEL,'dataset':ds['id'],'kind':'LLM','method':'lora'})
            self.assertEqual(run['model_revision'],REV);self.assertFalse(run['simulated'])
        finally:manager.close();workspace.close()

if __name__=='__main__':unittest.main()
