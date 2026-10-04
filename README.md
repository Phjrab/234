# Forge Fine-tuning Dashboard

LLM/VLM 로컬 파인튜닝의 데이터 준비와 실험 흐름을 확인하는 대시보드 프로토타입입니다. Python 표준 라이브러리와 HTML/CSS/JavaScript를 사용하며 **한국어와 English**를 지원합니다.

> **실제 학습은 미구현입니다.** 실험 진행률·손실·학습 GPU pulse·체크포인트는 합성 데이터입니다. JSONL 검증·저장·분할·내보내기, 설정 dry-run, 실제 서버/GPU 진단과 인증된 HTTPS 접속은 동작합니다.

## 설치

앱 소스는 현재 [Draft PR #1](https://github.com/Phjrab/forge-finetune-dashboard/pull/1)의 `feature/local-finetune-dashboard` 브랜치에 있습니다. 아래 명령으로 해당 브랜치를 설치하세요. Python 3.10 이상이 필요하며 앱 실행에 CUDA나 PyTorch는 필요하지 않습니다.

```bash
git clone --branch feature/local-finetune-dashboard https://github.com/Phjrab/forge-finetune-dashboard.git
cd forge-finetune-dashboard
python3 server.py
```

서버 PC에서 `http://127.0.0.1:8765`를 열고 초기 `admin/admin`으로 로그인한 다음 고유한 강한 비밀번호로 변경합니다. 초기 계정은 로컬 설정 전용이며 LAN에서는 사용할 수 없습니다.

설정 → 표시 언어(Display language)에서 한국어 또는 English를 선택합니다. 언어는 해당 브라우저에 저장되며 사용자 데이터와 JSON 식별자는 번역하지 않습니다.

## 기능과 문서

- JSONL LLM/VLM 데이터셋 검증·저장·재현 가능한 분할·내보내기
- LoRA/QLoRA 설정 프리셋과 휴리스틱 메모리 위험 경고
- 합성 실험 대기열·일시정지·재개·취소·재시도와 결과 비교
- 실제 서버 OS/Python/디스크/NVIDIA GPU 진단
- 인증·세션·CSRF·LAN 보기/제어 권한과 직접 HTTPS 접속

[상세 README](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/README.md) · [초보자 안내](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/beginner-guide.md) · [Ubuntu 배포](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/deployment.md) · [LAN/인증](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/lan-access.md) · [검증 기록](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/validation.md)

## 검증

2026-10-04 Ubuntu 24.04 / RTX 3060 12 GB에서 Python 93개, frontend DOM 35개와 언어 테스트가 통과했습니다. 별도 컴퓨터에서 HTTPS API와 Chromium 데스크톱/모바일, 한국어/영어 전환을 확인했습니다. CUDA 13.2 커널도 별도로 검증했지만 PyTorch/모델 호환성과 실제 학습을 보장하지 않습니다. 일반 브라우저의 자체 서명 인증서 신뢰 등록과 WSL2 배포는 별도 확인이 필요합니다.

프로젝트 이름은 **Forge Fine-tuning Dashboard**, 저장소 이름은 **forge-finetune-dashboard**입니다. 공개 저장소에 비밀번호·인증서/개인 키·런타임 DB·실제 데이터셋을 넣지 마세요.
