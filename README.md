# Forge Fine-tuning Dashboard

**한국어/English를 지원하는 로컬 LLM·VLM AI Training Workbench**입니다. 데이터셋 준비부터 LoRA/QLoRA 학습, 체크포인트, 검증 손실과 생성 결과 확인까지 한 서버에서 실행합니다.

## 실제로 동작하는 기능

- JSONL 데이터셋 검증·저장·재현 가능한 train/validation 분할
- VLM용 PNG/JPEG 이미지 업로드와 비공개 저장
- Hugging Face 모델 검색·제작사 아이콘·계열·LLM/VLM 표시, 모델 선택·다운로드
- 설정에서 Hugging Face 로그인 링크·읽기 토큰 연결 및 해제
- CUDA에서 LLM/VLM **LoRA와 4-bit NF4 QLoRA** 학습
- 단일 GPU FIFO 큐, 진행률·실제 손실·GPU 메모리·로그
- 체크포인트 저장 후 일시정지, optimizer/RNG 상태를 포함한 재개, 취소와 재시도
- 학습 전후 held-out assistant-token loss, perplexity와 실제 생성 응답
- 어댑터 가중치 ZIP 및 실험 JSON/CSV 다운로드
- 로그인·CSRF·LAN 보기/제어 권한, 직접 HTTPS 접속, 설정의 한국어/English 선택

**데모 실험도 남아 있습니다.** 실행 목록의 `Real GPU / 실제 GPU`와 `Demo / 데모` 표시를 확인하세요. 데모 손실·진행률·체크포인트는 합성이며 실제 GPU 학습과 별도로 동작합니다.

## 검증 모델 및 모델 선택

| 모델 | 종류 | 학습 | 라이선스 |
|---|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | LLM | LoRA / QLoRA | Apache-2.0 |
| HuggingFaceTB/SmolVLM-256M-Instruct | VLM | LoRA / QLoRA | Apache-2.0 |
| HuggingFaceTB/SmolLM2-135M-Instruct | LLM | LoRA | Apache-2.0 |
| google/flan-t5-small | LLM · 인코더·디코더 | LoRA / QLoRA | Apache-2.0 |
| facebook/bart-large-cnn | LLM · 인코더·디코더 | LoRA / QLoRA | MIT |

Qwen과 SmolVLM은 기본 모델입니다. 나머지는 Hub에서 추가 다운로드해 실제 GPU 학습을 검증했습니다. **모델 → 검색**에서 전체 Hub 모델 저장소를 검색·선택하고 제작사, 모델 계열, LLM/VLM 또는 기타 작업 유형, 파라미터 수, 라이선스, 설치 여부를 확인할 수 있습니다. 제작사·계열·유형 필터, 그룹 표시, 페이지 추가 조회와 정확한 저장소 ID 조회를 제공합니다. 유형·계열은 모델 이름이 아닌 Hub 작업·아키텍처 메타데이터를 사용하며 정보가 없으면 미확인으로 표시합니다.

LLM은 디코더 전용 모델과 인코더·디코더 모델을 모두 지원합니다. **LLM 구조 → 인코더·디코더**로 T5·FLAN-T5·BART·mT5 같은 계열을 찾을 수 있습니다. 번역·요약 모델도 인코더·디코더 목록 또는 정확한 ID로 조회할 수 있습니다. 인코더에는 질문과 대화 이력, 디코더 정답에는 마지막 assistant 응답만 사용합니다. LoRA 대상과 저장·재개 경로도 모델 구조에 맞게 선택합니다.

선택과 학습 가능 여부는 구분합니다. 현재 Transformers가 원격 코드 없이 지원하는 LLM/VLM의 safetensors 모델을 다운로드한 후 학습할 수 있습니다. GGUF, GPTQ/AWQ 가중치, 기타 작업 모델과 지원하지 않는 아키텍처는 사유를 표시합니다. 모델별 processor·토크나이저와 VRAM은 워커에서 추가 확인하므로 검색 목록이 학습 성공을 보장하지 않습니다. VLM은 레코드당 이미지 한 장을 지원하며, 다중 GPU·별도 원격 워커는 지원하지 않습니다.

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

CLI는 기본 모델 두 개를 준비합니다. 추가 모델은 대시보드에서 선택하고 **모델 다운로드**를 누릅니다. 다운로드 용량과 상태·취소를 표시하며 정확한 commit revision을 기록합니다. 학습 워커는 이후 **로컬 safetensors만** 읽으며 모델 다운로드와 원격 코드를 실행하지 않습니다. 인터넷 접속은 라이브러리 설치·Hub 검색·계정 연결·모델 다운로드 때 필요합니다. 설치된 모델의 GPU 학습은 로컬 파일만 사용합니다.

앱만 실행하거나 데모를 보려면 Python 3.10 이상의 `python3 server.py`로 시작할 수 있습니다. 실제 학습에는 전용 `.venv`와 `--enable-training`이 필요합니다. 검증한 환경은 Ubuntu 24.04.5, RTX 3060 12 GB, 드라이버 595.91.07, PyTorch 2.8.0+cu128입니다. 설치된 CUDA Toolkit 13.2와 PyTorch의 CUDA 12.8 wheel runtime은 별개입니다.

## 첫 실행과 학습

1. 서버 PC에서 `http://127.0.0.1:8765`를 엽니다. 초기 `admin/admin`으로 로그인하고 고유한 강한 비밀번호로 변경합니다. 초기 계정은 LAN에서 사용할 수 없습니다.
2. 설정 → **표시 언어(Display language)**에서 한국어 또는 English를 선택합니다. 브라우저별로 저장됩니다.
3. **데이터셋**에서 JSONL을 검증·저장하고 train/validation을 분할합니다. 중복이 양쪽에 겹치면 원본을 정리해야 실제 학습을 시작할 수 있습니다.
4. VLM은 저장된 데이터셋 카드의 이미지 업로드에서 `images/파일이름.png`와 일치하는 PNG/JPEG를 올립니다.
5. **새 실험**에서 Dataset → Base model → Method → Hyperparameters → Review → Launch 순서로 설정합니다. 설치된 모델·저장된 분할을 고르고, 미설치 모델은 **모델**에서 검색·지원 여부·접근 조건을 확인한 뒤 다운로드합니다.
6. Review의 **설정 사전 검사(dry-run)**와 **실제 학습 검사**를 각각 확인하고 Launch에서 **실제 GPU 학습 시작**을 누릅니다. **데모만 큐에 추가**는 별도의 합성 실행입니다. 설정 변경 시 검사 결과는 다시 확인해야 합니다.
7. 왼쪽 explorer에서 실행을 선택하면 중앙 학습 곡선, 오른쪽 자원·읽기 전용 설정, 하단 **로그/체크포인트/평가/설정**이 같은 실행을 표시합니다. 저장 후 일시정지·재개·취소는 서버가 제공한 상태와 허용 조작을 따릅니다. 완료 후 평가 응답과 체크포인트를 확인합니다.

최대 스텝은 optimizer 업데이트 상한입니다. 데이터 수와 epochs로 계산한 업데이트가 먼저 끝나면 그 시점에 완료됩니다. Gradient accumulation은 마이크로 배치를 모아 한 번 업데이트합니다. 최종 assistant 응답 토큰만 학습 대상으로 사용하며, context를 넘는 입력은 조용히 잘라내지 않고 거부합니다.


## Hugging Face 계정 연결

설정의 Hugging Face 카드에서 **Hugging Face 로그인**으로 공식 웹사이트에 로그인하고 **읽기 토큰 발급**에서 `Read` 또는 필요한 저장소의 읽기 권한을 가진 토큰을 만듭니다. 토큰을 카드에 입력하고 **계정 연결**을 누르면 사용자 이름이 표시됩니다. 공식 OAuth 로그인이 아닌 개인 액세스 토큰 연결입니다. 공개 모델은 연결 없이 검색·다운로드할 수 있습니다. 접근 제한 모델은 해당 모델 페이지에서 이용 조건에 동의하거나 제작사의 접근 승인을 받아야 합니다.

토큰은 `data/huggingface/account.json`에 소유자만 읽을 수 있는 권한 `0600`으로 저장됩니다. 브라우저 저장소·API 응답·실험/다운로드 작업 기록에는 저장하지 않습니다. **계정 연결 해제**는 이 파일을 삭제하며, Hugging Face 토큰 자체를 폐기하려면 공식 토큰 설정에서 별도로 폐기합니다. 다운로드 중에는 먼저 취소해야 연결을 해제할 수 있습니다.

## 데이터와 저장 범위

JSONL은 UTF-8 텍스트 128 KiB / 1000행 / 50개 데이터셋까지 지원합니다. LLM은 instruction/input/output 또는 messages 형식, VLM은 messages와 images 배열을 사용합니다. [샘플](docs/samples/)과 [초보자 안내](docs/beginner-guide.md)를 참고하세요.

이미지는 PNG/JPEG 각 2 MB / 16 megapixels, 학습 snapshot 전체 128 MB까지 허용하며 워커에서 최대 384×384로 축소합니다. 모델별 processor의 이미지 토큰 비용은 실제 context 검사에 포함합니다. 최대 batch 4, accumulation 32, LoRA rank 32, context 2048, epochs 20, max steps 2000입니다. 실제 VRAM 요구량은 설정과 이미지에 따라 달라지며 OOM일 때 오류로 종료합니다.

계정·JSONL은 기존 `data/` SQLite에, 모델·이미지·학습 상태·가중치는 `data/training/`에 저장됩니다. 재시도는 원래 작업의 데이터 snapshot과 최신 checkpoint를 보존합니다. 재시작으로 중단된 작업은 실패로 표시하고 사용자가 재시도할 수 있습니다. 체크포인트 ZIP은 adapter/tokenizer/processor와 설정이며 기본 모델 전체 가중치와 비공개 optimizer 파일은 포함하지 않습니다.

## HTTPS LAN 배포

[배포 가이드](docs/deployment.md)와 [LAN/인증](docs/lan-access.md)을 따르세요. 학습 서비스는 `.venv/bin/python server.py --enable-training`으로 실행합니다. 기존 설치의 서비스·디렉터리 이름을 유지해도 데이터와 계정은 호환됩니다.

## Workbench UI

선택한 실험이 작업 공간의 중심입니다. 오른쪽 inspector는 접을 수 있고 하단 console 높이를 조절할 수 있습니다. 모바일에서는 Run / Inspector / Console을 전환합니다. Datasets / Models / Experiments / Artifacts / Compare / Environment / Access settings에서 기존 기능에 접근합니다.

실측 GPU 값, 예상 VRAM, 합성 Demo loss와 UI fixture 값은 출처를 구분합니다. 결측 loss는 0으로 바꾸지 않으며 차트는 원본 optimizer step을 표시합니다. GPU 정보는 서버 전체 자원으로 실행마다 독립 측정한 값이 아닙니다.

2026-10-07 UI 개편: Python 140개(137 통과·3 skip), DOM 55개, i18n 및 실제 격리 브라우저 73개 검사 통과. before/after 19개 PNG와 한계는 [UI 최종 보고서](docs/ui-redesign/FINAL_REPORT.md), [검증](docs/ui-redesign/VALIDATION.md), [rollback](docs/ui-redesign/ROLLBACK.md)에 있습니다. 이 UI 검증은 실제 GPU 학습·다운로드를 실행하지 않았습니다. 안전한 실제 앱 fixture는 `python3 tools/ui_fixture_server.py --port 18765`로 실행합니다.

## 검증

2026-10-04 RTX 3060에서 네 가지 실제 GPU 경로를 각각 10 optimizer steps 실행했습니다.

| 경로 | 학습 전 검증 손실 | 학습 후 검증 손실 |
|---|---:|---:|
| LLM LoRA | 3.8124 | 2.5632 |
| LLM QLoRA | 3.7137 | 2.3686 |
| VLM LoRA | 3.9072 | 3.5259 |
| VLM QLoRA | 3.6372 | 3.2435 |

이 수치는 작은 **합성 데이터의 파이프라인 검사**입니다. 실제 업무 데이터에서의 품질·일반화 성능을 보장하지 않습니다. LLM checkpoint 재개와 어댑터 ZIP도 확인했습니다. Python 130개 테스트, DOM 39개, i18n 테스트가 통과했습니다. 전체 증거와 브라우저 확인 범위는 [검증 기록](docs/validation.md)에 있습니다.

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
