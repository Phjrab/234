"""Persistent single-GPU supervisor. Validated local snapshots run with native Transformers architectures."""
from __future__ import annotations
import base64
import copy
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from simulator import DashboardError, timestamp, validate_config
from architectures import training_architecture, native_support

MODELS = {
    'Qwen/Qwen2.5-0.5B-Instruct': {'kind': 'LLM', 'directory': 'qwen2.5-0.5b', 'license': 'Apache-2.0'},
    'HuggingFaceTB/SmolVLM-256M-Instruct': {'kind': 'VLM', 'directory': 'smolvlm-256m', 'license': 'Apache-2.0'},
}
RUN_ID = re.compile(r'train-[a-f0-9]{12}')
CHECKPOINT = re.compile(r'checkpoint-[0-9]{6}')
TERMINAL = {'completed', 'failed', 'canceled'}


def atomic_json(path, payload):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    temp.chmod(0o600)
    temp.replace(path)


def contained(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise DashboardError('invalid_path', 'Training file escapes its configured root.')
    return path


class TrainingManager:
    def __init__(self, root, workspace, *, enabled=False, model_root=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace = workspace
        self.model_root = Path(model_root or self.root / 'models').resolve()
        self.enabled = enabled
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'training.sqlite3', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS training_runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.commit()
        self.process = None
        self.current_id = None
        self.event_file = None
        self.stderr_file = None
        self.thread = None
        self.stop = threading.Event()
        self.device = None
        self.probe_error = None
        self.lease = None
        self.gpu_cache = None
        self.gpu_checked_at = 0
        # A host lease prevents two dashboards launching independent workers.
        if enabled:
            try:
                import fcntl
                self.lease = (self.root / 'worker.lock').open('a')
                fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (ImportError, BlockingIOError):
                self.db.close()
                raise RuntimeError('Another training supervisor owns this root, or host locking is unavailable.')
            try:
                probe = subprocess.run([sys.executable, '-c',
                    'import torch,json; print(json.dumps({"available":torch.cuda.is_available(),"name":torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"runtime":torch.version.cuda,"total_gb":torch.cuda.get_device_properties(0).total_memory/1024**3 if torch.cuda.is_available() else None}))'],
                    capture_output=True, text=True, timeout=30)
                self.device = json.loads(probe.stdout) if probe.returncode == 0 else None
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.device = None
            if not self.device or not self.device.get('available'):
                self.probe_error = 'CUDA-enabled PyTorch could not detect a GPU.'
        # Workers are owned child processes; service restart interrupts them.
        # Preserve the last checkpoint, require an explicit retry/resume decision.
        with self.lock:
            for run in self._runs():
                if run['status'] in {'running', 'pausing', 'canceling'}:
                    self._ingest_existing(run)
                    if run['status'] not in TERMINAL | {'paused'}:
                        run['status'] = 'failed'
                        run['error'] = 'Service interrupted the worker. Retry from its latest checkpoint.'
                        self._log(run, run['error'], 'warning')
                        self._save(run)

    def _runs(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM training_runs ORDER BY rowid')]

    def _save(self, run):
        run['updated_at'] = timestamp(time.time())
        with self.db:
            self.db.execute('INSERT INTO training_runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                            (run['id'], json.dumps(run, ensure_ascii=False, allow_nan=False)))

    def _find(self, run_id):
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise DashboardError('not_found', 'Training run does not exist.', 404)
        row = self.db.execute('SELECT payload FROM training_runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise DashboardError('not_found', 'Training run does not exist.', 404)
        return json.loads(row[0])

    @staticmethod
    def _log(run, message, level='info'):
        run['logs'].append({'time': timestamp(time.time()), 'level': level, 'message': message})
        run['logs'] = run['logs'][-200:]

    def model_definitions(self):
        definitions = {key: dict(value) for key, value in MODELS.items()}
        if self.model_root.exists():
            for folder in sorted(self.model_root.glob('hf-*')):
                if not folder.is_dir() or folder.is_symlink():
                    continue
                try:
                    from model_downloads import model_directory
                    manifest = json.loads((folder / 'forge-model.json').read_text())
                    model = manifest['model']
                    if folder.name != model_directory(model, manifest['revision']):
                        continue
                    definitions[model] = {key: manifest.get(key) for key in ('kind','license','family','publisher','parameters','architectures')}
                    definitions[model]['directory'] = folder.name
                except (OSError,ValueError,KeyError,DashboardError):
                    continue
        return definitions

    def _model(self, model):
        definitions = self.model_definitions()
        if model not in definitions:
            raise DashboardError('unsupported_model', 'Download the selected Hugging Face model before training.')
        folder = contained(self.model_root, definitions[model]['directory'])
        try:
            manifest = json.loads((folder / 'forge-model.json').read_text())
            if manifest['model'] != model or not re.fullmatch('[a-f0-9]{40}', manifest['revision']):
                raise ValueError()
            if not (folder / 'config.json').is_file() or not list(folder.glob('*.safetensors')):
                raise ValueError()
        except (OSError, ValueError, KeyError):
            raise DashboardError('model_unavailable', 'Download the selected model before training.', 409) from None
        return folder, manifest

    def capabilities(self):
        deps = all(importlib.util.find_spec(name) for name in ('torch', 'transformers', 'peft', 'PIL', 'bitsandbytes'))
        models = []
        for key, value in self.model_definitions().items():
            try:
                _, manifest = self._model(key)
                ready, revision = True, manifest['revision']
                config = json.loads((self.model_root / value['directory'] / 'config.json').read_text())
                value['family'] = value.get('family') or config.get('model_type')
                value.setdefault('publisher', key.split('/')[0])
                value.setdefault('architectures', config.get('architectures', []))
                value['training_architecture'] = training_architecture(config, value['kind'])
            except DashboardError:
                ready, revision = False, None
            models.append({'id': key, **{k:v for k,v in value.items() if k != 'directory'}, 'installed': ready, 'revision': revision})
        available = bool(self.enabled and deps and self.device and self.device.get('available'))
        return {'available': available, 'enabled': self.enabled, 'status': 'ready' if available else 'disabled',
                'real_training': available, 'pause': True, 'resume': True, 'cancel': True,
                'llm': True, 'vlm': True, 'seq2seq': True, 'models': models, 'gpu': self.device,
                'message': 'Local LoRA/QLoRA worker ready.' if available else self.probe_error or 'Enable the training environment and install its dependencies.',
                'limits': {'batch_size':4,'sequence_length':2048,'lora_rank':32,'image_bytes':2097152,'image_pixels':16777216}}

    def preflight(self, raw):
        if not self.capabilities()['available']:
            raise DashboardError('training_unavailable', 'Real training is unavailable on this server.', 409)
        config = validate_config(raw)
        definition = self.model_definitions().get(config['model'])
        if not definition or definition['kind'] != config['kind']:
            raise DashboardError('unsupported_model', 'Download a model matching the dataset kind.')
        if config['failure_mode'] != 'none':
            raise DashboardError('invalid_config', 'Failure injection is available only in demo mode.')
        for key, high in [('batch_size',4),('gradient_accumulation',32),('lora_rank',32),('sequence_length',2048),('epochs',20)]:
            if config[key] > high:
                raise DashboardError('resource_limit', f'Real training {key} is limited to {high}.')
        folder, manifest = self._model(config['model'])
        model_config = json.loads((folder / 'config.json').read_text())
        architecture = training_architecture(model_config, config['kind'])
        if native_support(model_config, config['kind']) is False:
            raise DashboardError('unsupported_model', 'The local LLM/VLM worker does not support this architecture with the installed Transformers version.', 409)
        with self.workspace.lock:
            dataset, records = self.workspace._load(config['dataset'])
            dataset, records = copy.deepcopy(dataset), copy.deepcopy(records)
        if dataset['kind'] != config['kind']:
            raise DashboardError('dataset_kind_mismatch', 'The dataset kind must match the model.')
        if not dataset.get('split'):
            raise DashboardError('split_required', 'Create a train/validation split before real training.', 409)
        if any(w['code'] == 'duplicate_leakage_risk' for w in dataset['split']['warnings']):
            raise DashboardError('dataset_leakage', 'Remove exact train/validation duplicates before training.')
        image_bytes = {}
        for item in records:
            row = item['record']
            if 'messages' in row and row['messages'][-1]['role'] != 'assistant':
                raise DashboardError('invalid_dataset', 'Each training record must end with an assistant answer.')
            if config['kind'] == 'VLM':
                if len(row['images']) != 1:
                    raise DashboardError('invalid_dataset', 'This VLM recipe supports one uploaded image per record.')
                for label in row['images']:
                    path = contained(self.root / 'images' / dataset['id'], label)
                    if not path.is_file():
                        raise DashboardError('image_required', 'Upload every image referenced by the VLM dataset before training.', 409)
                    if label not in image_bytes:
                        if path.stat().st_size > 2097152 or sum(len(v) for v in image_bytes.values()) + path.stat().st_size > 128*1024**2:
                            raise DashboardError('image_limit','A training snapshot is limited to 128 MB of images.',413)
                        image_bytes[label] = path.read_bytes()
        if shutil.disk_usage(self.root).free < 2 * 1024**3:
            raise DashboardError('disk_space', 'At least 2 GB of free output space is required.', 409)
        train = [records[i]['record'] for i in dataset['split_indices']['train']]
        validation = [records[i]['record'] for i in dataset['split_indices']['validation']]
        batches = math.ceil(len(train) / config['batch_size'])
        total = min(config['max_steps'], math.ceil(batches / config['gradient_accumulation']) * config['epochs'])
        return config, {'valid':True,'model_revision':manifest['revision'],'license':definition['license'],
                        'training_architecture':architecture,
                        'train_count':len(train),'validation_count':len(validation),'total_steps':total,
                        'evaluation':'held-out assistant-token cross entropy','can_train':True,
                        'warnings':['A small dataset verifies the pipeline; it does not establish model quality.','Context token lengths and actual VRAM are checked by the worker before optimization.']}, folder, train, validation, image_bytes

    def queue(self, raw, *, retry_of=None, resume_from=None):
        config, report, folder, train, validation, images = self.preflight(raw)
        with self.lock:
            if len(self._runs()) >= 50:
                raise DashboardError('run_limit', 'Real training has reached 50 stored runs.', 409)
            run_id = 'train-' + uuid.uuid4().hex[:12]
            directory = contained(self.root, run_id)
            directory.mkdir(mode=0o700)
            for label, body in images.items():
                dest = contained(directory / 'images', label)
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                dest.write_bytes(body)
            job = {'config':config,'model_path':str(folder),'train':train,'validation':validation,
                   'output':str(directory),'model_revision':report['model_revision'],'resume_from':resume_from,
                   'training_architecture':report['training_architecture']}
            atomic_json(directory / 'job.json', job)
            atomic_json(directory / 'control.json', {'action':'run'})
            run = {'id':run_id,'name':config['name'],'kind':config['kind'],'model':config['model'],'model_id':config['model'],
                   'method':config['method'],'config':config,'status':'queued','simulated':False,'source':'real',
                   'created_at':timestamp(time.time()),'started_at':None,'finished_at':None,'step':0,'current_step':0,
                   'total_steps':report['total_steps'],'elapsed_seconds':0,'metrics':[],'logs':[],'checkpoints':[],
                   'error':None,'retry_of':retry_of,'evaluation':None,'model_revision':report['model_revision'],
                   'last_sequence':0,'event_offset':0,'preflight':report}
            self._log(run, 'Real GPU training queued; dataset split and images were snapshotted.')
            self._save(run)
            return self._render(run)

    def _render(self, run):
        result = copy.deepcopy(run)
        result.pop('event_offset',None)
        result['latest_metrics'] = result['metrics'][-1] if result['metrics'] else None
        result['progress'] = round(min(100, 100 * result['step'] / max(1,result['total_steps'])),1)
        result['eta_seconds'] = None
        result['allowed_actions'] = {'queued':['start','cancel'],'running':['pause','cancel'],
            'pausing':['cancel'],'paused':['resume','cancel'],'canceling':[],
            'completed':[],'failed':['retry'],'canceled':['retry']}[result['status']]
        return result

    def get_run(self, run_id):
        with self.lock:
            return self._render(self._find(run_id))

    def runs(self):
        with self.lock:
            return [self._render(r) for r in reversed(self._runs())]

    def _checkpoint(self, run):
        for cp in reversed(run['checkpoints']):
            path = contained(self.root / run['id'], cp['name'])
            if (path / 'adapter_model.safetensors').is_file() and (path / 'training-state.pt').is_file():
                return str(path)
        return None

    def action(self, run_id, action):
        with self.lock:
            run = self._find(run_id)
            if action not in self._render(run)['allowed_actions']:
                raise DashboardError('invalid_transition', 'This action is unavailable in the current training state.', 409)
            if action == 'cancel' and run['status'] in {'queued','paused'}:
                run['status']='canceled';run['finished_at']=timestamp(time.time())
            elif action == 'cancel':
                run['status']='canceling';run['control_requested_at']=time.time()
                atomic_json(self.root / run_id / 'control.json', {'action':'cancel'})
            elif action == 'pause':
                run['status']='pausing';run['control_requested_at']=time.time()
                atomic_json(self.root / run_id / 'control.json', {'action':'pause'})
            elif action == 'resume':
                checkpoint = self._checkpoint(run)
                if checkpoint is None:
                    raise DashboardError('checkpoint_required','No resumable checkpoint exists.',409)
                job_path=self.root/run_id/'job.json';job=json.loads(job_path.read_text())
                job['resume_from']=checkpoint;atomic_json(job_path,job)
                atomic_json(self.root/run_id/'control.json',{'action':'run'})
                run['status']='queued';run['error']=None
            elif action == 'retry':
                checkpoint=self._checkpoint(run)
                return self.retry_snapshot(run,checkpoint)
            elif action == 'start':
                if self.process or any(r['status']=='paused' for r in self._runs()):
                    raise DashboardError('gpu_busy','The GPU queue is occupied or paused.',409)
                self._save(run);self._launch(run);return self.get_run(run_id)
            self._save(run)
            return self._render(run)

    def retry_snapshot(self, previous, checkpoint):
        if len(self._runs()) >= 50:
            raise DashboardError('run_limit','Real training has reached 50 stored runs.',409)
        run=copy.deepcopy(previous)
        run_id='train-'+uuid.uuid4().hex[:12]
        original=self.root/previous['id'];directory=self.root/run_id
        directory.mkdir(mode=0o700)
        if (original/'images').exists():shutil.copytree(original/'images',directory/'images')
        if checkpoint:
            dest=directory/Path(checkpoint).name;shutil.copytree(checkpoint,dest);checkpoint=str(dest)
            run['checkpoints']=[cp for cp in run['checkpoints'] if cp['name']==dest.name]
        else:run['checkpoints']=[]
        job=json.loads((original/'job.json').read_text());job['output']=str(directory);job['resume_from']=checkpoint
        run['evaluation']=None
        atomic_json(directory/'job.json',job);atomic_json(directory/'control.json',{'action':'run'})
        run.update(id=run_id,status='queued',created_at=timestamp(time.time()),started_at=None,finished_at=None,
                   retry_of=previous['id'],error=None,logs=[],last_sequence=0,event_offset=0)
        run.pop('worker_outcome',None)
        self._log(run,'Retry queued from immutable original dataset and latest saved checkpoint.')
        self._save(run);return self._render(run)

    def gpu_snapshot(self):
        with self.lock:
            if self.gpu_cache and time.time()-self.gpu_checked_at < 3:return copy.deepcopy(self.gpu_cache)
            gpu={'name':(self.device or {}).get('name','CUDA GPU'),'total_gb':(self.device or {}).get('total_gb'),
                 'used_gb':None,'utilization':None,'temp_c':None,'simulated':False,'source':'nvidia-smi'}
            try:
                result=subprocess.run(['nvidia-smi','--query-gpu=memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
                total,used,util,temp=[float(v.strip()) for v in result.stdout.splitlines()[0].split(',')]
                if not all(math.isfinite(x) for x in [total,used,util,temp]):raise ValueError()
                gpu.update(total_gb=total/1024,used_gb=used/1024,utilization=util,temp_c=temp)
            except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):gpu['source']='measurement_unavailable'
            self.gpu_cache=gpu;self.gpu_checked_at=time.time();return copy.deepcopy(gpu)

    def upload_image(self, dataset_id, payload):
        from PIL import Image
        if not isinstance(payload,dict) or set(payload) != {'label','content_base64'}:
            raise DashboardError('invalid_image','Image upload requires label and content_base64.')
        label=payload['label']
        if not isinstance(label,str) or not re.fullmatch(r'images/[A-Za-z0-9_.-]{1,100}\.(png|jpg|jpeg)',label):
            raise DashboardError('invalid_image','Use an images/name.png or images/name.jpg label.')
        with self.workspace.lock:
            dataset,records=self.workspace._load(dataset_id)
        if dataset['kind']!='VLM' or label not in {p for r in records for p in r['record'].get('images',[])}:
            raise DashboardError('invalid_image','The image label must be referenced by this VLM dataset.')
        encoded=payload['content_base64']
        if not isinstance(encoded,str) or len(encoded)>2800000:
            raise DashboardError('invalid_image','Image limit is 2 MB.',413)
        try:
            body=base64.b64decode(encoded,validate=True)
            if not body or len(body)>2097152:raise ValueError()
            image=Image.open(io.BytesIO(body))
            if image.format not in {'PNG','JPEG'} or image.width*image.height>16777216:raise ValueError()
            image.verify()
        except Exception:
            raise DashboardError('invalid_image','Supply a valid PNG/JPEG of at most 2 MB and 16 megapixels.') from None
        dest=contained(self.root/'images'/dataset_id,label)
        dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temp=dest.with_suffix(dest.suffix+'.upload');temp.write_bytes(body);temp.chmod(0o600);temp.replace(dest)
        return {'uploaded':True,'label':label,'bytes':len(body)}

    def _launch(self, run):
        directory=self.root/run['id']
        env={key:value for key,value in os.environ.items() if key not in {'HF_TOKEN','HUGGING_FACE_HUB_TOKEN','DASHBOARD_INITIAL_PASSWORD'}}
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='4')
        self.stderr_file=(directory/'worker-private.log').open('ab')
        run.pop('worker_outcome',None)
        self.process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('train_worker.py')),'--job',str(directory/'job.json')],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=self.stderr_file,env=env,start_new_session=True,pass_fds=(self.lease.fileno(),) if self.lease else ())
        self.current_id=run['id'];run['status']='running';run['started_at']=run['started_at'] or timestamp(time.time())
        self._log(run,'Owned local GPU worker started. Model loading may take a moment.');self._save(run)

    def _event(self, run, event):
        if event.get('run_id')!=run['id'] or event.get('sequence',0)<=run.get('last_sequence',0):return
        kind,payload=event.get('kind'),event.get('payload',{})
        if not isinstance(payload,dict):return
        if kind=='metric':
            if not all(v is None or isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in payload.values()):return
            if payload.get('step',-1)<run['step'] or payload.get('step',0)>run['total_steps']:return
            run['step']=run['current_step']=int(payload['step']);run['metrics'].append(payload);run['metrics']=run['metrics'][-2000:]
            run['elapsed_seconds']=payload.get('elapsed_seconds',run['elapsed_seconds'])
        elif kind=='log':self._log(run,str(payload.get('message',''))[:500],payload.get('level','info'))
        elif kind=='checkpoint':
            name=payload.get('name','')
            if not CHECKPOINT.fullmatch(name):return
            path=contained(self.root/run['id'],name)
            if not (path/'adapter_model.safetensors').is_file():return
            run['checkpoints']=[cp for cp in run['checkpoints'] if cp['name']!=name]+[payload]
        elif kind=='evaluation':run['evaluation']=payload
        elif kind=='status':
            status=payload.get('status')
            # A process-exit check below is authoritative for terminal state.
            if status in TERMINAL | {'paused'}:run['worker_outcome']=status
            if payload.get('error'):run['error']=str(payload['error'])[:500]
        run['last_sequence']=event['sequence']

    def _ingest_existing(self, run):
        path=self.root/run['id']/'events.jsonl'
        if not path.exists():return
        with path.open('rb') as f:
            f.seek(run.get('event_offset',0))
            while True:
                pos=f.tell();line=f.readline(16385)
                if not line or not line.endswith(b'\n'):break
                if len(line)>16384:break
                try:self._event(run,json.loads(line))
                except (ValueError,KeyError,TypeError,DashboardError):pass
                run['event_offset']=f.tell()
        self._save(run)

    def tick(self):
        with self.lock:
            if self.process:
                run=self._find(self.current_id);self._ingest_existing(run)
                code=self.process.poll()
                if code is None and run['status']=='canceling' and time.time()-run.get('control_requested_at',time.time())>30:
                    self.process.terminate()
                    try:self.process.wait(10)
                    except subprocess.TimeoutExpired:self.process.kill();self.process.wait(10)
                    code=self.process.returncode
                if code is not None:
                    outcome=run.pop('worker_outcome',None)
                    if run['status']=='canceling':outcome='canceled'
                    run['status']=outcome if outcome in TERMINAL | {'paused'} and (code==0 or outcome=='canceled') else 'failed'
                    if run['status']=='failed' and not run['error']:run['error']='Worker exited unexpectedly; see the private host worker log.'
                    if run['status'] in TERMINAL:run['finished_at']=timestamp(time.time())
                    self._save(run);self.process=None;self.current_id=None;self.stderr_file.close();self.stderr_file=None
            if self.enabled and self.process is None and not self.stop.is_set():
                runs=self._runs()
                if not any(r['status']=='paused' for r in runs):
                    pending=next((r for r in runs if r['status']=='queued'),None)
                    if pending:self._launch(pending)

    def start(self):
        if self.thread:return
        def work():
            while not self.stop.wait(.5):
                try:self.tick()
                except Exception:
                    # Persist a bounded error without leaking job data or paths.
                    with self.lock:
                        if self.current_id:
                            run=self._find(self.current_id);self._log(run,'Supervisor could not update worker state.','error');self._save(run)
        self.thread=threading.Thread(target=work,name='real-training-supervisor',daemon=True);self.thread.start()

    def artifact(self, run_id, name):
        with self.lock:
            run=self._find(run_id)
            if not CHECKPOINT.fullmatch(name or '') or not any(cp['name']==name for cp in run['checkpoints']):
                raise DashboardError('not_found','Checkpoint does not exist.',404)
            folder=contained(self.root/run_id,name)
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
                total=0
                for path in sorted(folder.iterdir()):
                    if path.suffix not in {'.safetensors','.json','.txt','.model'} or path.is_symlink() or not path.is_file():continue
                    if not path.resolve().is_relative_to(folder):continue
                    total+=path.stat().st_size
                    if total>256*1024**2:raise DashboardError('artifact_limit','Checkpoint export exceeds 256 MB.',413)
                    if path.suffix=='.json':
                        # PEFT/tokenizer metadata may remember the private local model root.
                        job=json.loads((self.root/run_id/'job.json').read_text())
                        text=path.read_text().replace(job['model_path'],run['config']['model'])
                        z.writestr(path.name,text)
                    else:z.write(path,path.name)
            return output.getvalue(),f'{run_id}-{name}.zip'

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
        with self.lock:
            if self.process:
                self.process.terminate()
                try:self.process.wait(10)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(10)
                self._ingest_existing(self._find(self.current_id))
                run=self._find(self.current_id)
                run['status']='failed';run['error']='Service stopped; retry from the latest checkpoint.';self._save(run)
                self.stderr_file.close()
            self.db.close()
            if self.lease:self.lease.close()
