# Forge Fine-tuning Dashboard

**한국어/English를 지원하는 로컬 LLM·VLM GPU 파인튜닝 대시보드**입니다. 데이터셋 준비부터 LoRA/QLoRA 학습, 체크포인트, 검증 손실과 생성 결과 확인까지 한 서버에서 실행합니다.

## 실제로 동작하는 기능

- JSONL 데이터셋 검증·저장·재현 가능한 train/validation 분할
- VLM용 PNG/JPEG 이미지 업로드와 비공개 저장
- CUDA에서 LLM/VLM **LoRA와 4-bit NF4 QLoRA** 학습
- 단일 GPU FIFO 큐, 진행률·실제 손실·GPU 메모리·로그
- 체크포인트 저장 후 일시정지, optimizer/RNG 상태를 포함한 재개, 취소와 재시도
- 학습 전후 held-out assistant-token loss, perplexity와 실제 생성 응답
- 어댑터 가중치 ZIP 및 실험 JSON/CSV 다운로드
- 로그인·CSRF·LAN 보기/제어 권한, 직접 HTTPS 접속, 설정의 한국어/English 선택

**데모 실험도 남아 있습니다.** 실행 목록의 `Real GPU / 실제 GPU`와 `Demo / 데모` 표시를 확인하세요. 데모 손실·진행률·체크포인트는 합성이며 실제 GPU 학습과 별도로 동작합니다.

## 지원 모델

| 모델 | 종류 | 학습 | 라이선스 |
|---|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | LLM | LoRA / QLoRA | Apache-2.0 |
| HuggingFaceTB/SmolVLM-256M-Instruct | VLM | LoRA / QLoRA | Apache-2.0 |

검증된 작은 모델 두 개를 허용합니다. 다른 모델 ID, 원격 코드, 임의 실행 명령은 받을 수 없습니다. 더 큰 모델·다중 GPU·별도 원격 워커는 현재 지원하지 않습니다. VLM은 레코드당 이미지 한 장을 지원합니다.

## 설치 · Ubuntu + NVIDIA CUDA GPU

기본 `main` 브랜치에서 설치합니다. 실제 CUDA 학습과 별도의 합성 데모를 포함합니다.

```bash
git clone https://github.com/Phjrab/forge-finetune-dashboard.git
cd forge-finetune-dashboard
sudo apt-get install python3-venv
python3 -m venv .venv
.venv/bin/pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.venv/bin/pip install -r requirements-training.txt
.venv/bin/python tools/download_models.py --root data/training/models
.venv/bin/python server.py --enable-training
```

다운로드 도구는 지원 모델을 Hugging Face에서 받고 정확한 commit revision을 기록합니다. 학습 워커는 이후 **로컬 safetensors만** 읽으며 모델 다운로드와 원격 코드를 실행하지 않습니다. 인터넷 접속은 라이브러리 설치·모델 준비 때 필요합니다.

앱만 실행하거나 데모를 보려면 Python 3.10 이상의 `python3 server.py`로 시작할 수 있습니다. 실제 학습에는 전용 `.venv`와 `--enable-training`이 필요합니다. 검증한 환경은 Ubuntu 24.04.5, RTX 3060 12 GB, 드라이버 595.91.07, PyTorch 2.8.0+cu128입니다. 설치된 CUDA Toolkit 13.2와 PyTorch의 CUDA 12.8 wheel runtime은 별개입니다.

## 첫 실행과 학습

1. 서버 PC에서 `http://127.0.0.1:8765`를 엽니다. 초기 `admin/admin`으로 로그인하고 고유한 강한 비밀번호로 변경합니다. 초기 계정은 LAN에서 사용할 수 없습니다.
2. 설정 → **표시 언어(Display language)**에서 한국어 또는 English를 선택합니다. 브라우저별로 저장됩니다.
3. **데이터셋**에서 JSONL을 검증·저장하고 train/validation을 분할합니다. 중복이 양쪽에 겹치면 원본을 정리해야 실제 학습을 시작할 수 있습니다.
4. VLM은 저장된 데이터셋 카드의 이미지 업로드에서 `images/파일이름.png`와 일치하는 PNG/JPEG를 올립니다.
5. **학습 설정**에서 설치된 모델과 분할된 데이터셋을 고르고 학습률·배치·rank·context·epochs·최대 스텝을 설정합니다.
6. **실제 학습 검사 → 실제 GPU 학습 시작**을 누릅니다. `Queue demo only`는 합성 데모 버튼입니다.
7. **실험**에서 실제 손실을 확인하고 저장 후 일시정지·재개·취소합니다. 완료 후 **평가** 탭에서 학습 전후 손실과 생성 응답, **체크포인트** 탭에서 가중치를 다운로드합니다.

최대 스텝은 optimizer 업데이트 상한입니다. 데이터 수와 epochs로 계산한 업데이트가 먼저 끝나면 그 시점에 완료됩니다. Gradient accumulation은 마이크로 배치를 모아 한 번 업데이트합니다. 최종 assistant 응답 토큰만 학습 대상으로 사용하며, context를 넘는 입력은 조용히 잘라내지 않고 거부합니다.

## 데이터와 저장 범위

JSONL은 UTF-8 텍스트 128 KiB / 1000행 / 50개 데이터셋까지 지원합니다. LLM은 instruction/input/output 또는 messages 형식, VLM은 messages와 images 배열을 사용합니다. [샘플](docs/samples/)과 [초보자 안내](docs/beginner-guide.md)를 참고하세요.

이미지는 PNG/JPEG 각 2 MB / 16 megapixels, 학습 snapshot 전체 128 MB까지 허용하며 워커에서 최대 384×384로 축소합니다. 모델별 processor의 이미지 토큰 비용은 실제 context 검사에 포함합니다. 최대 batch 4, accumulation 32, LoRA rank 32, context 2048, epochs 20, max steps 2000입니다. 실제 VRAM 요구량은 설정과 이미지에 따라 달라지며 OOM일 때 오류로 종료합니다.

계정·JSONL은 기존 `data/` SQLite에, 모델·이미지·학습 상태·가중치는 `data/training/`에 저장됩니다. 재시도는 원래 작업의 데이터 snapshot과 최신 checkpoint를 보존합니다. 재시작으로 중단된 작업은 실패로 표시하고 사용자가 재시도할 수 있습니다. 체크포인트 ZIP은 adapter/tokenizer/processor와 설정이며 기본 모델 전체 가중치와 비공개 optimizer 파일은 포함하지 않습니다.

## HTTPS LAN 배포

[배포 가이드](docs/deployment.md)와 [LAN/인증](docs/lan-access.md)을 따르세요. 학습 서비스는 `.venv/bin/python server.py --enable-training`으로 실행합니다. 기존 설치의 서비스·디렉터리 이름을 유지해도 데이터와 계정은 호환됩니다.

## 검증

2026-10-04 RTX 3060에서 네 가지 실제 GPU 경로를 각각 10 optimizer steps 실행했습니다.

| 경로 | 학습 전 검증 손실 | 학습 후 검증 손실 |
|---|---:|---:|
| LLM LoRA | 3.8124 | 2.5632 |
| LLM QLoRA | 3.7137 | 2.3686 |
| VLM LoRA | 3.9072 | 3.5259 |
| VLM QLoRA | 3.6372 | 3.2435 |

이 수치는 작은 **합성 데이터의 파이프라인 검사**입니다. 실제 업무 데이터에서의 품질·일반화 성능을 보장하지 않습니다. LLM checkpoint 재개와 어댑터 ZIP도 확인했습니다. Python 108개 테스트, DOM 37개, i18n 테스트가 통과했습니다. 전체 증거와 브라우저 확인 범위는 [검증 기록](docs/validation.md)에 있습니다.

```bash
python3 -m unittest discover -s tests -v
node tests/test_frontend.js
node tests/test_i18n.js
python3 tools/build_preview.py
```

`docs/offline-preview.html`은 네트워크·GPU·학습 쓰기가 없는 합성 읽기 전용 미리보기입니다.

## 개발과 보안

[학습 워커/API](docs/adapter-contract.md), [데이터/준비 API](docs/workspace-api.md), [보안 범위](docs/security.md)를 참고하세요. 데이터 준비 dry-run은 휴리스틱 검사이며 GPU 프로세스를 실행하지 않습니다. 실제 학습 사전 검사와 실행 API는 별개입니다.

공개 저장소에 비밀번호·토큰·인증서/개인 키·실제 데이터·모델 가중치·런타임 DB·비공개 워커 로그를 커밋하지 마세요. 프로젝트 브랜드는 **Forge Fine-tuning Dashboard**, 저장소는 **forge-finetune-dashboard**입니다.
