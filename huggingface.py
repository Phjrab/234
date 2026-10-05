"""Hugging Face catalog and private account token, behind dashboard permissions."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, urlsplit, parse_qs
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from simulator import DashboardError
from architectures import training_architecture, native_support

REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}')
AUTHOR = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}')
REVISION = re.compile(r'[a-f0-9]{40}')
VLM_TASKS = {'image-text-to-text', 'image-to-text', 'visual-question-answering'}


def repo_id(value):
    if not isinstance(value, str) or not REPO.fullmatch(value) or '..' in value:
        raise DashboardError('invalid_model', 'Use a Hugging Face model ID in publisher/model format.')
    return value


def classify(info):
    config = info.get('config') or {}
    task = info.get('pipeline_tag') or ''
    architectures = config.get('architectures') or []
    if task in VLM_TASKS or config.get('vision_config') or any(tag in VLM_TASKS for tag in info.get('tags') or []):
        return 'VLM'
    if task in {'text-generation','text2text-generation','summarization','translation'}:
        return 'LLM'
    if not task and any(str(a).endswith(('ForCausalLM', 'LMHeadModel', 'ForConditionalGeneration', 'ForSeq2SeqLM')) for a in architectures):
        return 'LLM'
    return 'OTHER' if task else 'UNKNOWN'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HuggingFaceHub:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'account.json'
        self.lock = threading.RLock()
        self.cache = {}
        self.publishers = {}

    def token(self):
        with self.lock:
            try:
                return json.loads(self.path.read_text())['token']
            except (OSError, ValueError, KeyError):
                return None

    def account(self):
        with self.lock:
            try:
                data = json.loads(self.path.read_text())
                return {'connected': True, 'username': data['username']}
            except (OSError, ValueError, KeyError):
                return {'connected': False, 'username': None}

    def _request(self, path, *, token=None, authenticated=True):
        headers = {'User-Agent': 'Forge-Finetune-Dashboard/4', 'Accept': 'application/json'}
        credential = token if token is not None else self.token() if authenticated else None
        if credential:
            headers['Authorization'] = 'Bearer ' + credential
        try:
            # The catalog and whoami APIs do not redirect. Never forward a token to a redirect host.
            with build_opener(NoRedirect()).open(Request('https://huggingface.co' + path, headers=headers), timeout=18) as response:
                raw = response.read(4 * 1024**2 + 1)
                if len(raw) > 4 * 1024**2:
                    raise DashboardError('hf_response_limit', 'Hugging Face response is too large.', 502)
                return json.loads(raw), response.headers.get('Link', '')
        except HTTPError as error:
            code = {401:'hf_auth_required',403:'hf_access_denied',404:'hf_not_found',429:'hf_rate_limited'}.get(error.code, 'hf_unavailable')
            message = {401:'Connect a valid Hugging Face read token in Settings.',403:'Accept the model access terms on Hugging Face and check token permissions.',404:'Hugging Face model or profile was not found.',429:'Hugging Face rate limit reached. Retry later.'}.get(error.code, 'Hugging Face is unavailable. Retry later.')
            raise DashboardError(code, message, 502 if error.code not in {401,403,404,429} else error.code) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise DashboardError('hf_unavailable', 'Cannot reach Hugging Face. Check the server connection.', 502) from None

    def connect(self, payload):
        if not isinstance(payload,dict) or set(payload) != {'token'} or not isinstance(payload['token'],str) or not re.fullmatch(r'hf_[A-Za-z0-9]{12,256}',payload['token']):
            raise DashboardError('invalid_hf_token', 'Enter a Hugging Face access token with read permission.')
        info, _ = self._request('/api/whoami-v2', token=payload['token'])
        username = info.get('name')
        if not isinstance(username,str) or not AUTHOR.fullmatch(username):
            raise DashboardError('invalid_hf_account', 'Hugging Face did not return a valid account.',502)
        with self.lock:
            temp = self.root / 'account.tmp'
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as output:
                json.dump({'token':payload['token'],'username':username},output)
            temp.replace(self.path)
            self.cache.clear()
        return self.account()

    def disconnect(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self.cache.clear()
        return self.account()

    def publisher(self, author):
        if not isinstance(author,str) or not AUTHOR.fullmatch(author):
            raise DashboardError('invalid_author','Invalid Hugging Face publisher.')
        with self.lock:
            cached = self.publishers.get(author)
            if cached and time.time()-cached[0] < 3600:
                return cached[1]
        info = {}
        for category in ('organizations','users'):
            try:
                info,_=self._request(f'/api/{category}/{quote(author)}/overview',authenticated=False)
                break
            except DashboardError as error:
                if error.code != 'hf_not_found':
                    break
        avatar = info.get('avatarUrl','')
        parsed = urlsplit(avatar)
        if parsed.scheme != 'https' or parsed.hostname != 'cdn-avatars.huggingface.co' or parsed.username or parsed.password:
            avatar = None
        result={'id':author,'name':str(info.get('fullname') or author)[:160],'avatar':avatar}
        with self.lock:
            self.publishers[author]=(time.time(),result)
        return result

    def avatar(self, author):
        avatar = self.publisher(author)['avatar']
        if not avatar:
            raise DashboardError('not_found','Publisher icon is unavailable.',404)
        try:
            with build_opener(NoRedirect()).open(Request(avatar,headers={'User-Agent':'Forge-Finetune-Dashboard/4'}),timeout=10) as response:
                mime = response.headers.get_content_type()
                body = response.read(512*1024+1)
                if mime not in {'image/png','image/jpeg','image/webp','image/gif'} or len(body)>512*1024:
                    raise ValueError()
                return body,mime
        except (HTTPError,URLError,ValueError,OSError):
            raise DashboardError('not_found','Publisher icon is unavailable.',404) from None

    @staticmethod
    def normalize(info):
        model=repo_id(info.get('id') or info.get('modelId'))
        author=info.get('author') or model.split('/')[0]
        config=info.get('config') or {}
        tags=info.get('tags') or []
        family=config.get('model_type') or None
        params=(info.get('safetensors') or {}).get('total')
        return {'id':model,'name':model.split('/',1)[1],'publisher':author,'family':family,
                'kind':classify(info),'task':info.get('pipeline_tag') or None,'revision':info.get('sha'),
                'downloads':info.get('downloads',0),'parameters':params,'gated':bool(info.get('gated')),
                'private':bool(info.get('private')),'license':(info.get('cardData') or {}).get('license') or next((tag[8:] for tag in tags if tag.startswith('license:')),None),
                'architectures':config.get('architectures') or [],
                'training_architecture':training_architecture(config, classify(info)) if classify(info) in {'LLM','VLM'} else None,
                'avatar_url':'/api/huggingface/avatar?author='+quote(author),
                'url':'https://huggingface.co/'+model}

    def search(self, query):
        allowed={'search','author','kind','family','sort','cursor','text_task'}
        if set(query)-allowed or any(not isinstance(v,str) or len(v)>1200 for v in query.values()):
            raise DashboardError('invalid_query','Invalid model search.')
        kind=query.get('kind','ALL');sort=query.get('sort','downloads')
        if kind not in {'ALL','LLM','VLM'} or sort not in {'downloads','trendingScore','lastModified'} or query.get('text_task','causal') not in {'causal','seq2seq'}:
            raise DashboardError('invalid_query','Invalid model filter.')
        if query.get('author') and not AUTHOR.fullmatch(query['author']):
            raise DashboardError('invalid_query','Invalid publisher filter.')
        if query.get('family') and not re.fullmatch('[A-Za-z0-9_-]{1,80}',query['family']):
            raise DashboardError('invalid_query','Invalid model family filter.')
        params=[('limit','30'),('sort',sort),('direction','-1')]
        for key in ('search','author','cursor'):
            if query.get(key):params.append((key,query[key]))
        if kind!='ALL':params.append(('pipeline_tag',('text2text-generation' if query.get('text_task')=='seq2seq' else 'text-generation') if kind=='LLM' else 'image-text-to-text'))
        if query.get('family'):params.append(('filter',query['family']))
        for field in ('author','config','pipeline_tag','tags','gated','private','downloads','safetensors','sha'):
            params.append(('expand[]',field))
        data,link=self._request('/api/models?'+urlencode(params))
        if not isinstance(data,list):raise DashboardError('hf_unavailable','Invalid Hugging Face catalog response.',502)
        models=[]
        for info in data:
            try:models.append(self.normalize(info))
            except DashboardError:continue
        cursor=None
        for url in re.findall(r'<([^>]+)>;\s*rel="next"',link):
            parsed=urlsplit(url)
            if parsed.scheme=='https' and parsed.hostname=='huggingface.co' and parsed.path=='/api/models':
                cursor=parse_qs(parsed.query).get('cursor',[None])[0]
        return {'models':models,'next_cursor':cursor,'source':'Hugging Face','page_size':30}

    def detail(self, model):
        model=repo_id(model)
        # Lock also serializes account changes, so private metadata never crosses an account change.
        with self.lock:
            cached=self.cache.get(model)
            if cached and time.time()-cached[0]<120:return dict(cached[1])
            info,_=self._request('/api/models/'+quote(model,safe='/')+'?blobs=true')
            result=self.normalize(info)
            if not REVISION.fullmatch(result.get('revision') or ''):
                raise DashboardError('hf_invalid_revision','Hugging Face returned an invalid revision.',502)
            files=[]
            for sibling in info.get('siblings') or []:
                name=sibling.get('rfilename','')
                # Only root-level safe weights/tokenizer/config assets; Python and pickle are excluded.
                if '/' not in name and not name.startswith('.') and name.endswith(('.json','.safetensors','.txt','.model','.tiktoken')):
                    files.append({'name':name,'size':sibling.get('size') or (sibling.get('lfs') or {}).get('size') or 0})
            result['files']=files
            result['download_bytes']=sum(f['size'] for f in files)
            reasons=[]
            if result['kind'] not in {'LLM','VLM'}:reasons.append('This task is not supported by the LLM/VLM training worker.')
            if not any(f['name'].endswith('.safetensors') for f in files):reasons.append('This repository has no safetensors weights.')
            config=info.get('config') or {}
            if config.get('quantization_config') or any(tag in {'gguf','gptq','awq'} for tag in info.get('tags') or []):
                reasons.append('Use the original unquantized Transformers model for LoRA/QLoRA training.')
            if result['kind'] in {'LLM','VLM'} and native_support(config, result['kind']) is False:
                reasons.append('The local LLM/VLM worker does not support this architecture with the installed Transformers version.')
            result['training_candidate']=not reasons
            result['reasons']=reasons
            result['publisher_info']=self.publisher(result['publisher'])
            self.cache[model]=(time.time(),result)
            return dict(result)
