"""Explicit asynchronous model downloads; selected revisions and safe assets only."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from huggingface import repo_id, REVISION
from simulator import DashboardError
from training import atomic_json, contained


def model_directory(model, revision):
    repo_id(model)
    if not isinstance(revision,str) or not REVISION.fullmatch(revision):
        raise DashboardError('invalid_revision','Select a valid pinned model revision.')
    return 'hf-'+hashlib.sha256((model+'@'+revision).encode()).hexdigest()[:24]


class ModelDownloads:
    def __init__(self, root, hub):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.hub=hub
        self.lock=threading.RLock()
        self.process=None
        self.state_path=hub.root/'download.json'
        try:self.state=json.loads(self.state_path.read_text())
        except (OSError,ValueError):self.state={'status':'idle'}
        if self.state.get('status')=='downloading':
            self.state.update(status='failed',message='Download interrupted. Select the model and retry.')
            self._save()
        self.closed=False

    def _save(self):atomic_json(self.state_path,self.state)

    def status(self):
        with self.lock:
            state=dict(self.state)
            if state.get('directory'):
                folder=contained(self.root,state['directory'])
                # Include incomplete Hub files for visible network progress; never expose filesystem paths.
                state['downloaded_bytes']=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file() and not p.is_symlink()) if folder.exists() else 0
            state.pop('directory',None)
            return state

    def start(self,payload):
        if not isinstance(payload,dict) or set(payload)!={'model','revision'}:
            raise DashboardError('invalid_body','Download requires model and revision.')
        model=repo_id(payload['model'])
        info=self.hub.detail(model)
        if (info.get('gated') or info.get('private')) and not self.hub.token():
            raise DashboardError('hf_auth_required','Connect a valid Hugging Face read token in Settings.',401)
        if payload['revision']!=info['revision']:
            raise DashboardError('revision_changed','Model revision changed. Refresh the model details before downloading.',409)
        if not info['training_candidate']:
            raise DashboardError('unsupported_model','This model cannot be downloaded for this training worker.',409,{'reasons':info['reasons']})
        if not info['download_bytes']:
            raise DashboardError('unknown_model_size','Hugging Face did not report the download size. Retry the model details.',409)
        if shutil.disk_usage(self.root).free < info['download_bytes'] + 2*1024**3:
            raise DashboardError('disk_space','The model download needs its listed size plus 2 GB of free disk space.',409)
        with self.lock:
            if self.closed:raise DashboardError('download_unavailable','Model downloader is closed.',409)
            if self.process is not None:
                raise DashboardError('download_busy','A model download is already running.',409)
            folder=contained(self.root,model_directory(model,info['revision']))
            folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            job_path=self.hub.root/'download-job.json'
            atomic_json(job_path,{'model':model,'revision':info['revision'],'directory':str(folder),
                'files':[f['name'] for f in info['files']],
                'manifest':{k:info[k] for k in ('id','kind','family','license','revision','publisher','parameters','architectures')}})
            environment=os.environ.copy()
            # Read the connected dashboard account only, never an operator's ambient Hub credentials.
            environment['HF_TOKEN']=self.hub.token() or ''
            environment['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
            environment['HF_HUB_DISABLE_PROGRESS_BARS']='1'
            environment['HF_HUB_DISABLE_XET']='1'
            command=[sys.executable,str(Path(__file__).resolve().parent/'tools/download_models.py'),'--job',str(job_path)]
            try:
                self.process=subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            except OSError:
                raise DashboardError('download_unavailable','Unable to start the model downloader.',503) from None
            self.state={'status':'downloading','model':model,'revision':info['revision'],'directory':folder.name,
                'expected_bytes':info['download_bytes'],'started_at':time.time(),'message':'Downloading model files.'}
            self._save()
            process=self.process
            threading.Thread(target=self._finish,args=(process,folder),daemon=True,name='hub-download').start()
            return self.status()

    def _finish(self,process,folder):
        code=process.wait()
        with self.lock:
            if self.process is not process:return
            self.process=None
            if self.state['status']=='canceled':return
            ready=code==0 and (folder/'forge-model.json').is_file()
            self.state.update(status='completed' if ready else 'failed',message='Model installed.' if ready else 'Download failed. Check account access, network and disk space, then retry.')
            self._save()

    def cancel(self):
        with self.lock:
            process=self.process
            if not process:return self.status()
            self.state.update(status='canceled',message='Model download canceled.')
            self._save()
            process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        with self.lock:
            if self.process is process:self.process=None
            return self.status()

    def close(self):
        self.closed=True
        self.cancel()
