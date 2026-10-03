# Forge · Local fine-tuning dashboard

LLM/VLM 로컬 파인튜닝을 준비하고 실험 상태를 살펴보는 **실행 가능한 프로토타입**입니다. Python 표준 라이브러리와 HTML/CSS/JavaScript만 사용합니다.

> **실제 학습은 아직 구현되지 않았습니다.** 학습 실행·손실·GPU pulse·로그·체크포인트는 합성 시뮬레이션입니다. 실제 기능은 데이터셋 검증/저장/분할/내보내기, 설정 검증, 환경 진단, 인증과 접근 설정입니다. 12 GB는 기본 VRAM 계획 가정이며 사용자 RTX 3060의 측정값이 아닙니다.

## 빠른 시작 · Ubuntu / WSL2

Python 3.10 이상이 필요합니다. Python 패키지, CUDA, PyTorch, 모델 다운로드는 필요하지 않습니다.

```bash
git clone https://github.com/Phjrab/local-finetune-dashboard.git
cd local-finetune-dashboard
python3 server.py
```

현재 코드는 draft PR에서 개발됩니다. main에 아직 앱이 없다면 [draft PR](https://github.com/Phjrab/local-finetune-dashboard/pull/1)의 실제 head branch를 체크아웃한 뒤 실행하세요.

1. 같은 컴퓨터에서 http://127.0.0.1:8765 를 엽니다
2. 처음에는 ID admin / 비밀번호 admin 으로 **로컬에서만** 로그인합니다
3. Access settings에서 현재 비밀번호를 입력하고 고유한 강한 새 비밀번호로 변경합니다
4. 설정 완료 후 데이터와 데모 제어가 열립니다. 종료는 Ctrl+C입니다

새 비밀번호는 최소 12자이며 20자 미만이면 문자 종류 3개 이상, 서로 다른 문자 6개 이상이 필요합니다. 초기 비밀번호는 LAN에서 사용할 수 없습니다. 새 비밀번호와 실제 계정 정보를 저장소에 넣지 마세요.

다른 포트가 필요하면 `python3 server.py --port 8766`을 사용합니다. `--no-worker`는 자동 모의 진행을 끄고 API/설정 제어만 유지하는 테스트 모드입니다.

## 화면별 기능

| 화면 | 구현된 기능 | 범위/제한 |
|---|---|---|
| Home | 현재 running/paused 작업, 진행률, 손실, GPU pulse, 오류 | 학습/GPU 수치 합성, 과거 실험은 Experiments에서 확인 |
| Experiments | LLM/VLM 필터, 시작/일시정지/재개/취소/재시도, 로그/구성/체크포인트 탭 | 단일 모의 GPU, FIFO 자동 대기열, 체크포인트는 가상 메타데이터 |
| Datasets | JSONL 붙여넣기/파일 입력, LLM/VLM 스키마 검사, 오류 줄 번호, 미리보기, 저장, seed 기반 분할, JSONL 내보내기 | 128 KiB 텍스트/1000행/50개 데이터셋. 이미지 파일 접근/업로드 없음 |
| Training setup | 작은 LoRA/QLoRA 프리셋, 기본/접힌 고급 설정, dry-run, 명시적 VRAM 가정, 메모리 위험 경고, 설정 내보내기 | 휴리스틱이며 모델 호환성/학습 가능성 보장 아님. 실제 실행 없음 |
| Compare | 두 실험의 합성 손실 곡선/설정/eval loss 비교, JSON/CSV 내보내기 | 실제 평가/생성 결과 비교 아님. CSV는 수식 실행을 방지하도록 문자열 보호 |
| Environment | 서버 호스트의 실제 Python/OS/디스크 조회, 설치된 nvidia-smi의 읽기 전용 GPU 탐지 | 현재 서버 VM의 진단. 미래 사용자 학습 컴퓨터의 상태가 아님 |
| Access settings | 로그인, 초기 비밀번호 변경, LAN/view/control 설정, 로그아웃 | 로컬 우선, 실제 LAN 리스너 시작은 별도 명시적 실행 필요 |

모바일은 상단 화면 선택 메뉴를 사용합니다. 모든 기능을 한 화면에 펼치지 않았으며 학습 고급 옵션은 접어서 볼 수 있습니다. 실제 브라우저 레이아웃 검증은 현재 환경에서 막혀 있으므로 아래 검증 기록을 확인하세요.

### 데이터 준비

LLM은 instruction/input/output 또는 user/assistant 메시지를 지원합니다. VLM은 messages와 `images:["images/example.png"]` 같은 상대 경로 **라벨**을 지원합니다. 절대 경로, 상위 경로 이동, URL은 거부합니다. 이미지 존재/크기/내용은 검사하지 않습니다.

가져온 JSONL 텍스트는 서버의 로컬 SQLite에 실제 저장됩니다. 분할은 seed와 비율이 같으면 재현 가능하며 원본 행을 보존합니다. 중복이 양쪽 분할에 남으면 평가 누출 경고를 표시하므로 원본을 정리한 뒤 실제 평가에 사용해야 합니다. 스키마 통과가 내용 정확성/라이선스/토큰 길이 검증을 의미하지 않습니다.

### 데모 실행과 실패 처리

대기 작업은 모의 GPU가 비면 FIFO로 자동 시작됩니다. Pause는 시뮬레이터만 멈추고 슬롯을 유지합니다. Retry는 원본 이력을 보존한 새 작업이며 OOM 주입 설정도 복사합니다. 주입 OOM을 없애려면 오류의 Review training recipe를 눌러 설정을 검토하고 정상 데모 시나리오로 새 실행을 만드세요. 실제 GPU 메모리를 고치거나 훈련 프로세스를 재시작하는 기능이 아닙니다.

## LAN 접속 · 선택 사항

LAN access / remote view / remote control의 **저장 기본값은 모두 ON**입니다. 그러나 초기 비밀번호 상태에서는 실제 원격 접근은 모두 OFF이며, 비밀번호 변경 후에도 기본 루프백 리스너에서는 원격 접근이 열리지 않습니다. 설정 화면에서 저장값과 실제 적용 상태를 구분해 보여줍니다.

사용자 학습 컴퓨터에서 로컬 설정을 완료한 다음에만 별도 LAN 실행을 선택하세요. LAN은 인증과 직접 private-IP TLS를 기본 요구합니다. HTTP 예외는 명시적 위험 동의 플래그이며 비밀번호/쿠키/데이터를 가로챌 수 있습니다. 인증 없는 LAN, 공용 인터넷 공개, 임의 reverse proxy/tunnel, 자동 방화벽/라우터 변경은 지원하지 않습니다.

자세한 실행 조건, TLS, Ubuntu/WSL2 주의점은 [LAN 가이드](docs/lan-access.md)를 참고하세요. 이 개발 작업에서 VM의 LAN 포트나 방화벽을 열지 않았고 실제 계정/비밀번호를 생성하지 않았습니다.

## 검증 결과와 남은 확인

정확한 상태와 증거/차단 원인/사용자 로컬 확인 절차는 [검증 매트릭스](docs/validation.md)와 [JSON 기록](docs/validation.json)에 있습니다.

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node --check static/workspace.js
node tests/test_frontend.js
```

Node는 프런트엔드 소스 검사 때만 필요합니다. 앱 실행에는 필요하지 않습니다. DOM 스텁 테스트는 실제 브라우저·CSS·모바일·키보드 동작 검증을 대신하지 않습니다.

`docs/offline-preview.html`은 합성 fixture를 넣은 읽기 전용 미리보기입니다. 학습, 인증 변경, 데이터 저장, API 제어는 동작하지 않습니다. 이를 실제 서버 통합 검사나 브라우저 통과로 표시하지 않습니다.

## 처음 시작한다면

[초보자 가이드](docs/beginner-guide.md)의 Data → Model → Config → Demo run → Compare 순서를 따라 작은 합성 샘플로 시작하세요. Datasets 화면의 접힌 형식 안내에 필수 필드, 지원하지 않는 형식과 다운로드 가능한 샘플이 있습니다. Training setup의 용어 도움말과 오류의 다음 행동/기술 상세를 함께 사용하세요.

## 실제 학습으로 확장할 때

[어댑터 계약](docs/adapter-contract.md)과 [데이터/설정 API](docs/workspace-api.md)에 준비 구조를 정리했습니다. `adapter.py`는 실행되지 않는 타입 계약입니다.

미구현: 실제 학습 워커, PyTorch/Transformers/PEFT/TRL 연동, 모델/데이터 다운로드, 실제 체크포인트 파일/가중치, 생성 평가, 인증된 별도 원격 워커, 다중 GPU 스케줄러. 어떤 설정이나 LAN 권한도 실제 학습을 자동 시작하지 않습니다.

사용자 RTX 3060의 실제 VRAM부터 확인한 뒤 모델 크기, 양자화, 컨텍스트, 이미지 해상도와 배치 크기를 정해야 합니다. 12 GB 가정으로 모델 적합성을 보장하지 않습니다.

- 학습 전용 PC라면 native Ubuntu가 Linux 도구를 한 환경에서 관리하는 선택입니다. 재설치 전 백업/드라이버 호환성을 확인하세요
- Windows를 유지한다면 Ubuntu on WSL2를 검토하세요. [Microsoft GPU 가이드](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute)를 따르세요
- WSL2에서는 Windows NVIDIA 드라이버를 사용하며 WSL 안에 Linux NVIDIA 디스플레이 드라이버를 별도 설치하지 마세요. [NVIDIA 공식 WSL 가이드](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)를 참고하세요

## 저장과 공개 저장소

data/ 안의 실행 상태, 인증 해시/설정, 데이터셋 SQLite는 버전 관리에서 제외합니다. 서버를 다시 시작해도 상태는 남지만 로그인 세션은 사라집니다. 초기화하려고 인증 데이터베이스까지 무심코 지우면 초기 계정 설정으로 돌아갈 수 있으니 사용자 데이터 백업/복구 결정은 직접 검토하세요.

공개 저장소에는 합성 샘플과 소스만 포함합니다. 실제 데이터셋, 비밀번호, 토큰, 모델, TLS 인증서/개인 키, 실행 DB, 로그를 커밋하지 마세요. [보안 범위](docs/security.md)를 확인하세요.
