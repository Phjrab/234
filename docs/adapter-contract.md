# Forge · 로컬 GPU 학습 워커와 API

`training.py`는 영속적인 단일 GPU supervisor, `train_worker.py`는 소유한 CUDA 자식 프로세스입니다. `adapter.py`의 이벤트 타입은 외부 어댑터를 작성할 때 참고할 수 있는 계약이며 실행 구현은 위 두 파일에 있습니다.

## 실행 구조

인증된 브라우저 → JSON API → 검증된 데이터 snapshot/큐 → 고정 Python 워커 → 설치된 PyTorch/Transformers/PEFT.

서버에서 `--enable-training`과 전용 Python 환경을 사용합니다. 기본 output/model root는 `data/training` / `data/training/models`이며 CLI에서 운영자가 바꿀 수 있습니다. 브라우저는 경로나 실행 명령을 제공하지 못합니다. 기본 모델은 CLI로, 추가 Hub 모델은 인증된 대시보드 다운로드로 revision을 고정하고, 워커는 `local_files_only=True`, `trust_remote_code=False`, offline 환경에서 safetensors를 읽습니다.

## API

모든 읽기는 로그인과 보기 권한, 모든 쓰기는 로그인·동일 Origin·CSRF·해당 권한을 요구합니다.

| 요청 | 기능 |
|---|---|
| `GET /api/training` | 활성 상태, GPU, 설치 모델/revision, 지원 범위와 제한 |
| `POST /api/training/preflight` | 정규화된 학습 config 검사, 데이터 분할·중복·이미지·디스크 검사; GPU 학습 미실행 |
| `POST /api/training/runs` | 같은 config로 실제 작업 생성, 원본 데이터/이미지 snapshot, FIFO 큐 |
| `GET /api/runs/train-ID` | 실제 실행 상태와 측정 지표 |
| `POST /api/runs/train-ID/start` | 큐가 비어 있을 때 즉시 시작 |
| `POST /api/runs/train-ID/pause` | checkpoint 저장 후 worker 종료 요청 |
| `POST /api/runs/train-ID/resume` | 저장한 optimizer/RNG/scaler 상태에서 같은 실행 재개 |
| `POST /api/runs/train-ID/cancel` | 종료 요청, 실제 process exit 후 canceled 표시 |
| `POST /api/runs/train-ID/retry` | 원래 snapshot과 최신 checkpoint를 보존한 새 실행 |
| `GET /api/runs/train-ID/export?format=json\|csv` | `mode: real_training`, `synthetic: false`인 기록 |
| `GET /api/runs/train-ID/artifacts/checkpoint-NNNNNN` | adapter/tokenizer/processor/config ZIP; optimizer 파일 제외 |
| `POST /api/datasets/dataset-ID/images` | `{label: "images/name.png", content_base64: "..."}`로 참조 PNG/JPEG 업로드 |

`train-ID`의 실제 형식은 `train-` 뒤 12자리 소문자 hex입니다. Action 본문은 빈 JSON 객체입니다. 기존 `/api/runs` 생성은 데모로 유지되며 실제 생성은 `/api/training/runs`입니다. Hub 검색·계정·다운로드 API는 [모델 카탈로그 API](huggingface-api.md)를 참고하세요.

## 상태와 소유권

`queued → running → completed | failed | canceled`, pause는 `running → pausing → paused`, cancel은 실행 중 `canceling`을 거칩니다. 요청 접수만으로 종료 완료를 표시하지 않습니다. 저장 후 worker 종료를 확인한 뒤 paused, 프로세스 exit를 확인한 뒤 terminal로 바꿉니다. 중단된 서비스는 작업을 failed로 남기고 자동으로 이력을 초기화하거나 성공으로 표시하지 않습니다.

한 supervisor가 한 CUDA device(0)의 작업 하나를 실행합니다. paused 작업은 순서를 보존하며 재개하거나 취소하기 전 다음 작업을 실행하지 않습니다. 큐/상태는 SQLite, 데이터/이미지는 생성된 run 디렉터리의 불변 snapshot입니다. 호스트 파일 잠금을 자식에 전달하며 Linux parent-death signal과 systemd control-group 종료로 고아 워커를 제한합니다. 강제 취소는 이 supervisor가 가진 정확한 Popen 프로세스에만 적용합니다.

## 실제 학습과 평가

LoRA는 q_proj/v_proj가 있는 모델에서 기존 attention 설정을 사용하며, 다른 native 아키텍처는 PEFT all-linear 설정을 사용합니다. 채팅 템플릿이 없는 LLM은 역할·본문 형식의 기본 텍스트 템플릿을 사용합니다. QLoRA는 NF4 4-bit/double quantization 기본 가중치를 사용합니다. 고정 base model은 학습하지 않습니다. 최종 assistant 응답의 토큰만 label로 사용하고 prompt/padding을 -100으로 마스킹합니다. 원본 row는 epochs마다 seed로 shuffle하며 batch와 accumulation 그룹을 재현할 수 있습니다. 마지막 불완전 accumulation 그룹은 실제 마이크로 배치 수로 나눕니다.

실제 sequence 길이와 이미지 tensor를 검사한 후 업데이트합니다. 최대 context 초과는 실패로 표시하고 조용히 잘라내지 않습니다. AdamW, gradient clipping, 선형 learning-rate 감소와 CUDA mixed precision을 사용합니다. max steps는 epochs가 만드는 update plan의 상한입니다.

held-out 데이터로 학습 전후 assistant-token cross entropy와 perplexity를 계산합니다. 첫 validation 예제에서 greedy 응답을 생성합니다. 작은 합성 검증은 학습 파이프라인의 동작만 확인하며 실제 모델 품질을 보장하지 않습니다. 전용 모델 평가 suite나 업무 데이터 benchmark는 포함하지 않습니다.

## 파일과 이벤트

워크스페이스는 임의 경로나 symlink escape를 거부합니다. JSONL/이미지는 업로드한 내용만 사용합니다. private worker traceback 로그는 서버 호스트에만 저장합니다. 인증정보/모델 토큰은 frontend와 실험 metadata에 포함하지 않습니다.

워커의 bounded JSONL 이벤트는 run ID, 증가하는 sequence, metric/log/checkpoint/evaluation/status payload를 갖습니다. supervisor는 교차 작업·중복 sequence·비유한 metric·미확인 checkpoint 경로를 거부하고 offset을 영속화합니다. GPU 수치는 nvidia-smi의 실제 측정이며 측정 실패는 null로 표시합니다. 데모는 계속 simulated=true입니다.

체크포인트는 adapter safetensors, tokenizer/processor, 설정/revision과 private optimizer/RNG/scaler state를 저장합니다. 완료된 디렉터리를 원자적으로 등록하며 ZIP은 등록된 checkpoint만 최대 256 MB로 내보냅니다. 기본 모델 snapshot은 ZIP에 포함하지 않습니다. 별도 inference 환경에서 기본 모델과 `PeftModel.from_pretrained`로 어댑터를 로드할 수 있습니다.

미지원: 현재 Transformers가 지원하지 않는 모델 아키텍처, LLM/VLM 이외의 작업, GGUF/GPTQ/AWQ 가중치, 사용자 shell 명령, remote Python code, 다중 GPU, 원격 worker, base model 전체 fine-tuning, streaming/대형 datasets와 전용 inference serving endpoint.
