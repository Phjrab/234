"""Owned CUDA LoRA/QLoRA process, loading only operator-staged local models."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import random
import signal
import sys
import subprocess
import time
import traceback
from training import atomic_json, contained
from architectures import training_architecture, native_support, lora_targets


def messages(row):
    if 'messages' in row:return row['messages']
    prompt=row['instruction']+ ('\n'+row['input'] if row.get('input') else '')
    return [{'role':'user','content':prompt},{'role':'assistant','content':row['output']}]


def seq2seq_text(row):
    convo = messages(row)
    if not convo or convo[-1]['role'] != 'assistant':
        raise ValueError('Each training record must end with an assistant answer.')
    context = convo[:-1]
    source = context[0]['content'] if len(context) == 1 and context[0]['role'] == 'user' else '\n'.join(m['role'] + ': ' + m['content'] for m in context)
    return source, convo[-1]['content']


def encode_seq2seq(tokenizer, rows, sequence_length, *, prompt_only=False):
    """Encoder sees context only; decoder labels contain only the final answer."""
    forms = [seq2seq_text(row) for row in rows]
    batch = tokenizer([source for source, _ in forms], padding=True, return_tensors='pt')
    if batch['input_ids'].shape[1] > sequence_length:
        raise ValueError('Encoder input exceeds configured token context.')
    # Some tokenizers return token_type_ids, which T5/BART do not accept.
    batch = {key: value for key, value in batch.items() if key in {'input_ids', 'attention_mask'}}
    if not prompt_only:
        targets = tokenizer(text_target=[answer for _, answer in forms], padding=True, return_tensors='pt')
        if targets['input_ids'].shape[1] > sequence_length:
            raise ValueError('Decoder answer exceeds configured token context.')
        labels = targets['input_ids'].clone()
        labels[targets['attention_mask'] == 0] = -100
        if not (labels != -100).any(dim=1).all():
            raise ValueError('Training record has no assistant target tokens.')
        batch['labels'] = labels
    return batch


def target_token_count(labels, architecture):
    # Causal loss shifts labels by one. Seq2seq shifts decoder inputs internally.
    supervised = labels if architecture == 'seq2seq' else labels[:, 1:]
    return int((supervised != -100).sum())


def plans(count, config):
    groups=[]
    for epoch in range(config['epochs']):
        order=list(range(count));random.Random(config['seed']+epoch).shuffle(order)
        batches=[order[i:i+config['batch_size']] for i in range(0,count,config['batch_size'])]
        groups.extend([batches[i:i+config['gradient_accumulation']] for i in range(0,len(batches),config['gradient_accumulation'])])
    return groups[:config['max_steps']]


def train(job_path):
    import torch
    from PIL import Image
    from transformers import AutoConfig,AutoModelForCausalLM,AutoModelForSeq2SeqLM,AutoModelForImageTextToText,AutoTokenizer,AutoProcessor,BitsAndBytesConfig
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training,PeftModel
    job=json.loads(job_path.read_text());config=job['config'];out=Path(job['output']).resolve()
    events=out/'events.jsonl';control=out/'control.json'
    seq=0
    if events.exists():
        for line in events.read_text().splitlines():
            try:seq=max(seq,json.loads(line)['sequence'])
            except (ValueError,KeyError):pass
    def emit(kind,payload):
        nonlocal seq
        seq+=1
        with events.open('a') as f:
            f.write(json.dumps({'version':1,'run_id':out.name,'sequence':seq,'kind':kind,'payload':payload},ensure_ascii=False,allow_nan=False)+'\n')
            f.flush()
    def command():
        try:return json.loads(control.read_text()).get('action','run')
        except (OSError,ValueError):return 'run'
    def stopped_before_training():
        action=command()
        if action=='cancel':emit('status',{'status':'canceled'});return True
        return False
    started=time.monotonic()
    torch.set_num_threads(4)
    torch.manual_seed(config['seed']);random.seed(config['seed'])
    if not torch.cuda.is_available():raise RuntimeError('CUDA GPU unavailable')
    torch.cuda.set_device(0)
    free,total=torch.cuda.mem_get_info()
    if free<1024**3:raise RuntimeError('Insufficient free GPU memory before model loading')
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantized=config['method']=='qlora'
    kwargs={'local_files_only':True,'trust_remote_code':False,'dtype':dtype,'use_safetensors':True}
    if quantized:
        kwargs.update(quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype),device_map={'':'cuda:0'})
    is_vlm=config['kind']=='VLM'
    model_config=AutoConfig.from_pretrained(job['model_path'],local_files_only=True,trust_remote_code=False)
    architecture=training_architecture(model_config.to_dict(),config['kind'])
    if native_support(model_config.to_dict(),config['kind']) is False:
        raise ValueError('Installed Transformers does not support this model architecture.')
    if job.get('training_architecture',architecture)!=architecture:
        raise ValueError('Model architecture changed after preflight.')
    cls={'causal':AutoModelForCausalLM,'seq2seq':AutoModelForSeq2SeqLM,'image_text_to_text':AutoModelForImageTextToText}[architecture]
    emit('log',{'message':'Loading staged model and tokenizer on CUDA. No remote code or network downloads.'})
    model=cls.from_pretrained(job['model_path'],**kwargs)
    processor=AutoProcessor.from_pretrained(job['model_path'],local_files_only=True,trust_remote_code=False) if is_vlm else None
    tokenizer=processor.tokenizer if processor else AutoTokenizer.from_pretrained(job['model_path'],local_files_only=True,trust_remote_code=False)
    tokenizer.padding_side='right'
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token is None:raise ValueError('Tokenizer needs a padding or EOS token.')
        tokenizer.pad_token=tokenizer.eos_token
    if processor and hasattr(processor.image_processor, 'do_image_splitting'):
        processor.image_processor.do_image_splitting=False
    if stopped_before_training():return
    model.config.use_cache=False
    if quantized:model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False})
    else:
        model=model.to('cuda');model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.enable_input_require_grads()
    resume=job.get('resume_from')
    if resume:
        resume=Path(resume)
        model=PeftModel.from_pretrained(model,str(resume),is_trainable=True,local_files_only=True)
    else:
        targets = lora_targets(model,architecture)
        model=get_peft_model(model,LoraConfig(r=config['lora_rank'],lora_alpha=config['lora_rank']*2,lora_dropout=0.0,
              target_modules=targets,bias='none',task_type='SEQ_2_SEQ_LM' if architecture=='seq2seq' else 'CAUSAL_LM'))
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=config['learning_rate'])
    plan=plans(len(job['train']),config)
    step=0;prior_elapsed=0;baseline=None
    if resume:
        state=torch.load(resume/'training-state.pt',map_location='cpu',weights_only=True)
        step=state['step'];prior_elapsed=state['elapsed_seconds'];baseline=state['baseline_eval_loss']
        optimizer.load_state_dict(state['optimizer'])
        if 'cuda_rng' in state:torch.cuda.set_rng_state(state['cuda_rng'])
        if 'cpu_rng' in state:torch.set_rng_state(state['cpu_rng'])
    trainable=sum(p.numel() for p in model.parameters() if p.requires_grad)
    emit('log',{'message':f'Real {config["method"].upper()} {config["kind"]}: {trainable:,} trainable parameters, {len(plan)} optimizer steps.'})

    def templates(row):
        convo=messages(row)
        if processor:
            structured=[]
            for index,m in enumerate(convo):
                content=[{'type':'text','text':m['content']}]
                if m['role']=='user' and not any(x['role']=='user' for x in structured):content.insert(0,{'type':'image'})
                structured.append({'role':m['role'],'content':content})
            full=processor.apply_chat_template(structured,tokenize=False,add_generation_prompt=False)
            prefix=processor.apply_chat_template(structured[:-1],tokenize=False,add_generation_prompt=True)
        else:
            if tokenizer.chat_template:
                full=tokenizer.apply_chat_template(convo,tokenize=False,add_generation_prompt=False)
                prefix=tokenizer.apply_chat_template(convo[:-1],tokenize=False,add_generation_prompt=True)
            else:
                prefix=''.join(m['role']+': '+m['content']+'\n' for m in convo[:-1])+'assistant: '
                full=prefix+convo[-1]['content']+(tokenizer.eos_token or '')
        return full,prefix

    def load_images(row):
        images=[]
        for label in row.get('images',[]):
            with Image.open(contained(out/'images',label)) as raw:
                image=raw.convert('RGB');image.thumbnail((384,384));images.append(image.copy())
        return images

    def encode(rows,*,prompt_only=False):
        if architecture=='seq2seq':
            batch=encode_seq2seq(tokenizer,rows,config['sequence_length'],prompt_only=prompt_only)
            return {key:value.to('cuda') for key,value in batch.items()}
        forms=[templates(row) for row in rows]
        texts=[f[1] if prompt_only else f[0] for f in forms]
        if processor:
            images=[load_images(row) for row in rows]
            batch=processor(text=texts,images=images,padding=True,return_tensors='pt')
            prefix_batch=processor(text=[f[1] for f in forms],images=images,padding=True,return_tensors='pt') if not prompt_only else None
        else:
            batch=tokenizer(texts,padding=True,return_tensors='pt',add_special_tokens=False)
            prefix_batch=tokenizer([f[1] for f in forms],padding=True,return_tensors='pt',add_special_tokens=False) if not prompt_only else None
        if batch['input_ids'].shape[1]>config['sequence_length']:
            raise ValueError('Record exceeds configured token context. Shorten the text or increase context up to 2048.')
        if not prompt_only:
            labels=batch['input_ids'].clone()
            for i in range(len(rows)):
                n=int(prefix_batch['attention_mask'][i].sum())
                # Never silently train on a mismatched prompt boundary.
                if not torch.equal(batch['input_ids'][i,:n],prefix_batch['input_ids'][i,:n]):
                    raise ValueError('Chat template prompt prefix does not align with assistant response.')
                labels[i,:n]=-100
            labels[batch['attention_mask']==0]=-100
            if not (labels!=-100).any(dim=1).all():raise ValueError('Training record has no assistant target tokens.')
            batch['labels']=labels
        return {key:value.to('cuda') for key,value in batch.items()}

    # Check every record before optimizer updates; user text stays out of logs.
    emit('log',{'message':'Checking tokenized contexts and image tensors for every snapshotted record.'})
    for row in job['train']+job['validation']:
        if stopped_before_training():return
        batch=encode([row]);del batch

    def evaluate():
        model.eval();weighted=0;tokens=0
        with torch.no_grad():
            for row in job['validation']:
                batch=encode([row]);loss=model(**batch).loss
                count=target_token_count(batch['labels'],architecture)
                if not math.isfinite(float(loss.detach())):raise ValueError('Nonfinite validation loss')
                weighted+=float(loss)*count;tokens+=count
                del batch,loss
        model.train()
        return weighted/max(1,tokens)

    def telemetry():
        result={'vram_used_gb':torch.cuda.memory_allocated()/1024**3,'vram_reserved_gb':torch.cuda.memory_reserved()/1024**3}
        try:
            r=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
            used,util,temp=[float(v.strip()) for v in r.stdout.splitlines()[0].split(',')]
            result.update(vram_used_gb=used/1024,gpu_utilization=util,gpu_temp_c=temp)
        except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):pass
        return result

    def elapsed():return prior_elapsed+time.monotonic()-started
    if baseline is None:
        baseline=evaluate()
        emit('metric',{'step':0,'loss':None,'eval_loss':baseline,'learning_rate':config['learning_rate'],'elapsed_seconds':elapsed(),**telemetry()})

    def checkpoint():
        name=f'checkpoint-{step:06d}';final=out/name;target=out/(name+'.tmp')
        if final.exists():return final
        target.mkdir(exist_ok=True,mode=0o700)
        model.save_pretrained(target,safe_serialization=True)
        (processor or tokenizer).save_pretrained(target)
        torch.save({'step':step,'optimizer':optimizer.state_dict(),'elapsed_seconds':elapsed(),'baseline_eval_loss':baseline,
                    'cuda_rng':torch.cuda.get_rng_state(),'cpu_rng':torch.get_rng_state(),'scaler':scaler.state_dict()},target/'training-state.pt')
        atomic_json(target/'forge-checkpoint.json',{'step':step,'config':config,'model_revision':job['model_revision'],
            'kind':config['kind'],'method':config['method'],'base_model':config['model'],'baseline_eval_loss':baseline,
            'training_architecture':architecture})
        for config_file in target.glob('*.json'):
            config_file.write_text(config_file.read_text().replace(job['model_path'],config['model']))
        target.rename(final)
        emit('checkpoint',{'id':name,'name':name,'step':step,'size_mb':round(sum(f.stat().st_size for f in final.iterdir() if f.is_file())/1024**2,2),'virtual':False})
        return final

    model.train();optimizer.zero_grad(set_to_none=True)
    scaler=torch.amp.GradScaler('cuda',enabled=dtype==torch.float16)
    if resume and 'scaler' in state:scaler.load_state_dict(state['scaler'])
    eval_interval=max(1,min(25,len(plan)//4))
    for index in range(step,len(plan)):
        action=command()
        if action in {'cancel','pause'}:
            checkpoint();emit('status',{'status':'canceled' if action=='cancel' else 'paused'});return
        group=plan[index];loss_sum=0;target_tokens=0;iteration=time.monotonic()
        lr=config['learning_rate']*(1-index/max(1,len(plan)))
        for param_group in optimizer.param_groups:param_group['lr']=lr
        for indices in group:
            batch=encode([job['train'][i] for i in indices])
            with torch.autocast('cuda',dtype=dtype):loss=model(**batch).loss
            if not math.isfinite(float(loss.detach())):raise ValueError('Nonfinite training loss')
            loss_sum+=float(loss.detach());target_tokens+=target_token_count(batch['labels'],architecture)
            scaler.scale(loss/len(group)).backward();del batch,loss
        scaler.unscale_(optimizer)
        norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.0)
        if not math.isfinite(float(norm)):raise ValueError('Nonfinite gradient norm')
        scaler.step(optimizer);scaler.update();optimizer.zero_grad(set_to_none=True)
        step=index+1
        evaluation=evaluate() if step%eval_interval==0 or step==len(plan) else None
        emit('metric',{'step':step,'loss':loss_sum/len(group),'eval_loss':evaluation,'learning_rate':lr,
                      'tokens_per_second':target_tokens/max(.001,time.monotonic()-iteration),'elapsed_seconds':elapsed(),**telemetry()})
        if step%max(1,min(50,len(plan)//3))==0 or step==len(plan):checkpoint()
    final=evaluate()
    model.eval();model.config.use_cache=True
    sample=job['validation'][0]
    prompt=encode([sample],prompt_only=True)
    with torch.no_grad():
        generated=model.generate(**prompt,max_new_tokens=32,do_sample=False,pad_token_id=tokenizer.pad_token_id,eos_token_id=tokenizer.eos_token_id)
    response=tokenizer.decode(generated[0] if architecture=='seq2seq' else generated[0,prompt['input_ids'].shape[1]:],skip_special_tokens=True)
    emit('evaluation',{'baseline_eval_loss':baseline,'eval_loss':final,'perplexity':math.exp(min(final,50)),
          'validation_count':len(job['validation']),'trained_parameters':trainable,'generated_response':response[:2000],
          'reference':messages(sample)[-1]['content'][:2000],'synthetic_dataset_quality_warning':True,
          'model_revision':job['model_revision'],'training_architecture':architecture})
    emit('log',{'message':'Training, held-out evaluation and adapter generation completed. Adapter weights were saved.'})
    emit('status',{'status':'completed'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True,type=Path);args=parser.parse_args()
    os.umask(0o077)
    if sys.platform.startswith('linux'):
        import ctypes
        ctypes.CDLL(None).prctl(1,signal.SIGTERM)
        if os.getppid()==1:raise SystemExit(1)
    try:train(args.job)
    except Exception as exc:
        # Detailed private host log is never served as a frontend asset.
        traceback.print_exc()
        job=json.loads(args.job.read_text());out=Path(job['output']);path=out/'events.jsonl';seq=0
        if path.exists():
            for line in path.read_text().splitlines():
                try:seq=max(seq,json.loads(line)['sequence'])
                except (ValueError,KeyError):pass
        code='oom' if 'out of memory' in str(exc).lower() else type(exc).__name__
        message='CUDA out of memory. Reduce batch size/context or use QLoRA.' if code=='oom' else 'Worker failed ('+code+'). Inspect the private host log; verify dataset context and installed dependencies.'
        with path.open('a') as f:f.write(json.dumps({'version':1,'run_id':out.name,'sequence':seq+1,'kind':'status','payload':{'status':'failed','error':message}})+'\n')
        raise SystemExit(1)


if __name__=='__main__':main()
