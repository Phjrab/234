# Forge · Local fine-tuning dashboard

로컬 LLM/VLM 파인튜닝 모니터링을 위한 작고 실행 가능한 **데모 프로토타입**입니다.
Python 표준 라이브러리 + HTML/CSS/JavaScript로 동작합니다. Node, CUDA, PyTorch, 모델 파일은 실행에 필요하지 않습니다.

> **현재 실제 학습 기능은 없습니다.** 모든 실행, 손실, 로그, 체크포인트, GPU 수치는 합성 데이터입니다. GPU를 감지하거나 사용하지 않으며 모델/데이터셋을 다운로드하지 않습니다. 화면의 RTX 3060 / 12 GB는 **데모 가정**이며 사용자 GPU의 실제 VRAM을 확인한 결과가 아닙니다.

## 빠른 시작 · Ubuntu / WSL2

Python 3.10 이상이 필요합니다. 별도 Python 패키지는 필요하지 않습니다.

```bash
git clone https://github.com/Phjrab/234.git local-finetune-dashboard
cd local-finetune-dashboard
python3 server.py
```

브라우저에서 **http://127.0.0.1:8765** 를 엽니다. 종료는 `Ctrl+C`입니다.
다른 프로세스가 포트를 사용하면 `python3 server.py --port 8766`으로 변경할 수 있습니다.
WSL2 안에서 서버를 실행하는 경우 Windows 브라우저에서도 localhost 주소를 사용할 수 있는지 확인하세요. 이 프로토타입은 루프백 주소에만 바인딩하며 LAN/인터넷 공개를 지원하지 않습니다.

## 사용할 수 있는 기능

- LLM/VLM 실행 목록, 필터, 실행별 손실/eval loss/학습률/진행률
- 합성 GPU VRAM, 온도, 사용률 표시와 명확한 DEMO 표기
- 새 데모 실행 설정과 시작/일시정지/재개/취소
- 실패/취소된 실행을 새 실행으로 재시도; 기존 이력 보존
- OOM 실패 시나리오, 가상 체크포인트, 로그 및 구성 보기
- SQLite에 실행 상태 보존; 서버 재시작 후 복원
- 2초 주기 API 갱신, 반응형 데스크톱/모바일 화면
- 단일 모의 GPU. 실행/일시정지 중인 실험은 슬롯을 예약하고 슬롯이 비면 대기 실행을 FIFO 순서로 자동 시작

데모의 `Pause`는 시뮬레이터를 멈춥니다. 실제 훈련 프로세스 일시정지를 구현했다고 뜻하지 않습니다. 체크포인트는 **메타데이터만 존재**하며 학습된 가중치 파일은 생성하지 않습니다.

## 동작 확인

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js  # Node가 설치되어 있을 때만 필요
node tests/test_frontend.js  # DOM 스텁 테스트; 실제 브라우저 테스트는 아님
```

API 예제:

```bash
curl http://127.0.0.1:8765/api/status
curl -X POST http://127.0.0.1:8765/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-demo","kind":"LLM","model":"demo/llm-3b","dataset":"synthetic-instructions","max_steps":30}'
```

슬롯이 비면 대기 실행은 자동으로 시작됩니다. 수동 시작하려면 생성 응답의 `run.id`를 사용해 `/api/runs/{id}/start`에 빈 JSON `{}`을 POST합니다.
이미 실행/일시정지 중인 실험이 있으면 다른 실험의 수동 시작은 409 오류로 거부됩니다.
정지된 재현 가능한 스냅샷은 `--no-worker`로 실행할 수 있습니다. 이 모드에서는 제어 상태 변경만 동작하고 자동 진행은 없습니다.

초기 샘플 상태로 되돌리려면 서버를 종료한 뒤 `data/state.sqlite3` 및 같은 이름의 `-wal`, `-shm` 파일을 삭제하고 재시작합니다. **데모 실행 이력이 삭제됩니다.** 별도 테스트 상태는 `--db /tmp/forge-demo.sqlite3`로 지정할 수 있습니다.

## 실제 로컬 학습으로 확장할 때

현재 구현된 부분과 예정된 부분을 분리했습니다. `docs/offline-preview.html`은 합성 상태를 보여주는 읽기 전용 파일 미리보기입니다. 실행 제어는 실제 서버에서만 동작합니다. 이 미리보기는 브라우저/API 통합 검증을 대신하지 않습니다.

`docs/adapter-contract.md`에 향후 로컬 학습 워커의 계약과 보안 경계를 기술했고, `adapter.py`에는 실행되지 않는 타입 계약만 있습니다.

아직 구현되지 않은 기능:

- NVIDIA GPU 자동 감지 / 실제 텔레메트리
- Hugging Face/Transformers/PEFT/TRL 또는 VLM 학습 워커
- 실제 데이터셋 파일 접근, 모델 다운로드, 가중치 체크포인트 저장
- 인증된 원격 워커 연결, 사용자 인증, 다중 GPU 스케줄링
- 메트릭 내보내기 및 원격 알림

RTX 3060의 **실제 VRAM부터 확인**한 뒤 모델 크기, 양자화, 컨텍스트 길이와 배치 크기를 정해야 합니다. 이 화면의 12 GB로 학습 가능성을 보장하지 않습니다.

### OS 선택

- 학습 전용 컴퓨터라면 네이티브 Ubuntu를 우선 검토할 수 있습니다. 드라이버/파일 시스템/프로세스 관리가 한 Linux 환경에 모이지만, 재설치 전 데이터 백업과 설치 호환성 확인이 필요합니다
- Windows를 계속 쓴다면 Ubuntu on WSL2가 Linux 기반 학습 도구를 쓰는 실용적인 선택입니다. 지원 Windows 버전 및 최신 NVIDIA Windows 드라이버 등은 [Microsoft 공식 GPU 가이드](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute)에서 확인하세요
- WSL2에서는 GPU 드라이버가 Windows에서 제공되므로 WSL 안에 별도 Linux NVIDIA 디스플레이 드라이버를 설치하지 마세요. 설치/지원 제약은 [NVIDIA CUDA on WSL 공식 가이드](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)와 [NVIDIA WSL 안내](https://developer.nvidia.com/cuda/wsl)를 따르세요

이 저장소 실행 자체에는 GPU 드라이버나 CUDA 설치가 필요하지 않습니다. 실제 학습 설치 명령은 아직 제공하지 않으며 사용자의 로컬 환경을 확인한 다음 별도 워커에서 검증해야 합니다.

## 안전한 기본값

기본 바인딩은 `127.0.0.1`; 루프백 외 주소는 거부합니다. 같은 origin의 JSON 요청만 브라우저에서 허용하고, Host 검사/본문 크기 제한/정적 경로 검증/보안 헤더를 적용합니다. 임의 shell 명령 입력이나 실제 작업 실행 API는 없습니다. 로컬 신뢰 사용자만을 위한 데모이며 악성 로컬 소프트웨어를 방어하는 인증 시스템이 아닙니다.

`data/`, 가상 환경, 토큰, 데이터셋, 로그 파일을 공개 저장소에 올리지 마세요. 이 저장소의 샘플은 합성 데이터만 포함합니다. 상세 제한은 `docs/security.md`를 참고하세요.

## 구성

```text
server.py                 루프백 HTTP API / 정적 파일 서버
simulator.py              합성 실행 상태 머신 / SQLite 저장
adapter.py                향후 워커 타입 계약 (실행 구현 없음)
static/                   의존성 없는 반응형 UI
tests/                    표준 unittest 백엔드/API 검증
docs/adapter-contract.md  실제 학습 확장 계획과 이벤트 계약
docs/sample-run.json      합성 실행 설정 예제
docs/validation.json      검증 내역
tests/test_frontend.js    DOM 스텁 기반 렌더링/핸들러 테스트
```
