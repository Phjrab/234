"""Operator-only explicit download of allowlisted safe-weight model snapshots."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from training import MODELS,atomic_json

def main():
    from huggingface_hub import HfApi,snapshot_download
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--model',choices=list(MODELS),action='append')
    args=parser.parse_args()
    for model in args.model or MODELS:
        info=HfApi().model_info(model)
        target=args.root/MODELS[model]['directory']
        snapshot_download(model,revision=info.sha,local_dir=target,
            allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'],
            ignore_patterns=['*.bin','*.pt','*.py'])
        atomic_json(target/'forge-model.json',{'model':model,'revision':info.sha,'license':MODELS[model]['license']})
        print(json.dumps({'model':model,'revision':info.sha,'downloaded':True}))

if __name__=='__main__':main()
