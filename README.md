# Forge Fine-tuning Dashboard

**한국어/English를 지원하는 로컬 LLM·VLM GPU 파인튜닝 대시보드**입니다. 데이터셋 준비부터 실제 LoRA/QLoRA 학습, 체크포인트와 평가까지 제공합니다.

앱 소스는 현재 [PR #1](https://github.com/Phjrab/forge-finetune-dashboard/pull/1)의 `feature/local-finetune-dashboard` 브랜치에 있습니다. 기본 브랜치에는 이 설치 안내가 있으므로 아래 명령으로 앱 브랜치를 선택하세요.

## 기능

- JSONL 검증·저장·재현 가능한 train/validation 분할과 VLM 이미지 업로드
- CUDA에서 Qwen 0.5B LLM / SmolVLM 256M VLM의 LoRA·4-bit QLoRA 학습
- 단일 GPU 대기열, 실제 손실과 GPU 측정, checkpoint 일시정지·재개·취소·재시도
- held-out 평가와 생성 응답, adapter 가중치 ZIP, 실험 JSON/CSV 다운로드
- 한국어/영어 언어 설정, 로그인·CSRF·권한과 직접 HTTPS LAN 접속

기존 데모 실험은 별도의 `Demo` 표시와 합성 지표를 유지합니다. 실제 학습은 `Real GPU / 실제 GPU`로 구분됩니다.

## 설치 · Ubuntu + NVIDIA GPU

```bash
git clone --branch feature/local-finetune-dashboard https://github.com/Phjrab/forge-finetune-dashboard.git
cd forge-finetune-dashboard
sudo apt-get install python3-venv
python3 -m venv .venv
.venv/bin/pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.venv/bin/pip install -r requirements-training.txt
.venv/bin/python tools/download_models.py --root data/training/models
.venv/bin/python server.py --enable-training
```

서버 PC에서 `http://127.0.0.1:8765`를 열고 초기 `admin/admin`으로 로그인한 다음 고유한 강한 비밀번호로 변경합니다. 초기 계정은 로컬 설정 전용입니다. 설정에서 한국어를 선택하고, 데이터셋 저장·분할 → 학습 설정 → **실제 GPU 학습 시작** 순서로 진행하세요.

준비/데모만 실행하려면 `python3 server.py`를 사용할 수 있습니다. 실제 학습은 전용 환경과 `--enable-training`이 필요합니다. 모델 다운로드는 운영자 도구가 수행하며 워커는 준비된 로컬 모델만 읽습니다.

[상세 README](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/README.md) · [초보자 안내](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/beginner-guide.md) · [배포](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/deployment.md) · [검증 기록](https://github.com/Phjrab/forge-finetune-dashboard/blob/feature/local-finetune-dashboard/docs/validation.md)

## 검증과 범위

Ubuntu 24.04.5 / RTX 3060 12 GB / PyTorch 2.8.0+cu128에서 LLM/VLM LoRA·QLoRA를 각각 10 optimizer steps 실행해 실제 손실·checkpoint·가중치·생성을 확인했습니다. HTTPS 웹 UI에서도 LLM 40-step, VLM 10-step 학습과 저장 후 재개·취소·다운로드를 검증했습니다. 서비스 중단 후 33-step checkpoint에서 retry가 100-step까지 완료됐습니다. Python 108개, DOM 37개와 i18n 테스트가 통과했습니다.

합성 데이터로 학습 흐름을 검증한 결과이며 실제 업무 데이터 품질을 보장하지 않습니다. 지원 모델은 위의 두 개입니다. 다중 GPU, 원격 worker와 임의 모델/실행 명령은 지원하지 않습니다.

공개 저장소에 비밀번호·토큰·인증서/개인 키·실제 데이터·모델 가중치·runtime DB를 넣지 마세요. 프로젝트 이름은 **Forge Fine-tuning Dashboard**, 저장소 이름은 **forge-finetune-dashboard**입니다.
