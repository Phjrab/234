"""Download a selected Hub revision without executable remote assets."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from training import MODELS,atomic_json
from huggingface import repo_id,REVISION


def download_job(job):
    from huggingface_hub import snapshot_download
    model=repo_id(job['model'])
    if not REVISION.fullmatch(job['revision']):raise ValueError('Invalid revision')
    files=job['files']
    if not files or any('/' in name or name.startswith('.') or not name.endswith(('.json','.safetensors','.txt','.model','.tiktoken')) for name in files):
        raise ValueError('Unsupported model assets')
    target=Path(job['directory'])
    snapshot_download(model,revision=job['revision'],local_dir=target,
        token=os.environ.pop('HF_TOKEN',None) or False,allow_patterns=files,
        ignore_patterns=['*.bin','*.pt','*.py'],max_workers=2)
    if not (target/'config.json').is_file() or not list(target.glob('*.safetensors')):
        raise ValueError('Missing model files')
    for index in target.glob('*.safetensors.index.json'):
        for weight in set(json.loads(index.read_text()).get('weight_map',{}).values()):
            if '/' in weight or not weight.endswith('.safetensors') or not (target/weight).is_file():
                raise ValueError('Incomplete sharded model')
    manifest=job['manifest'];manifest['model']=model
    atomic_json(target/'forge-model.json',manifest)


def main():
    from huggingface_hub import HfApi,snapshot_download
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',type=Path)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model',action='append')
    args=parser.parse_args()
    if args.job:
        download_job(json.loads(args.job.read_text()))
        return
    if not args.root:parser.error('--root or --job is required')
    for model in args.model or MODELS:
        repo_id(model)
        if model not in MODELS:parser.error('Use dashboard model selection for additional Hub models.')
        info=HfApi().model_info(model)
        target=args.root/MODELS[model]['directory']
        snapshot_download(model,revision=info.sha,local_dir=target,
            allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'],ignore_patterns=['*.bin','*.pt','*.py'])
        atomic_json(target/'forge-model.json',{'model':model,'revision':info.sha,'license':MODELS[model]['license']})
        print(json.dumps({'model':model,'revision':info.sha,'downloaded':True}))

if __name__=='__main__':main()
