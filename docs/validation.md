# Forge Fine-tuning Dashboard · 실제 학습 검증

2026-10-04 Ubuntu 24.04.5 / NVIDIA RTX 3060 12 GB에서 검증했습니다. **실제 LLM/VLM LoRA·QLoRA, 체크포인트와 평가가 동작합니다.** 기존 데모 작업은 simulated=true로 유지됩니다.

## GPU 검증 결과

PyTorch 2.8.0+cu128, Transformers 4.57.1, PEFT 0.17.1, bitsandbytes 0.48.1, NVIDIA 드라이버 595.91.07을 사용했습니다. CUDA Toolkit 13.2는 별도로 설치되어 있으며 학습은 wheel의 CUDA 12.8 runtime을 사용합니다.

| 실제 경로 | optimizer steps | 학습 전 validation loss | 학습 후 validation loss | 어댑터 ZIP |
|---|---:|---:|---:|---:|
| Qwen 0.5B LoRA | 10 | 3.8124 | 2.5632 | 4,934,225 bytes |
| Qwen 0.5B QLoRA | 10 | 3.7137 | 2.3686 | 4,936,501 bytes |
| SmolVLM 256M LoRA | 10 | 3.9072 | 3.5259 | 2,594,363 bytes |
| SmolVLM 256M QLoRA | 10 | 3.6372 | 3.2435 | 2,598,656 bytes |

각 경로에서 CUDA optimizer update, 실제 validation loss, 모델 생성 응답, safetensors adapter와 checkpoint ZIP을 확인했습니다. LLM LoRA는 checkpoint로 일시정지·재개했습니다. 데이터는 합성 JSONL, VLM 이미지는 프로그램으로 만든 작은 색상 사각형입니다. **이 수치는 모델 품질이나 업무 데이터 일반화 성능을 입증하지 않습니다.**

모델 revision: Qwen `7ae557604adf67be50417f59c2c2f167def9a775`, SmolVLM `7e3e67edbbed1bf9888184d9df282b700a323964`.

## 검증 매트릭스

| 항목 | 결과 | 범위 |
|---|---|---|
| Python backend/HTTP/security/workspace | PASS | 기존 93개 + 실제 학습 supervisor/API 15개 = 108개 |
| frontend DOM/i18n/syntax | PASS | DOM 37개, i18n suite, JS 4개 문법 검사 |
| 실제 LLM/VLM LoRA/QLoRA | PASS | 위의 네 CUDA 학습 경로, 각 10 updates |
| pause/resume | PASS | 저장·worker exit 확인, optimizer/RNG에서 학습 재개 |
| 중단 후 recovery/retry | PASS | 33-step checkpoint 이후 supervisor 종료, 재시작 시 failed 보존, 새 retry가 100-step까지 완료. 불변 dataset snapshot 및 복사한 checkpoint 다운로드 확인 |
| HTTPS Chromium 학습 UI | PASS | 한국어 LLM QLoRA 40-step + VLM QLoRA 10-step 완료, 실제 평가/생성 표시와 어댑터 다운로드 |
| 이미지 업로드 | PASS | VLM에 참조 PNG 12개를 웹 UI로 업로드 후 실제 학습 |
| 실제 취소 | PASS | running → canceling → 실제 worker exit → canceled |
| 언어/화면 | PASS | 한국어/영어, 언어 변경 시 미저장 recipe 보존, 실제/합성 source 구분, 측정 GPU 문구 |
| 모바일 | PASS | Chromium 390×844 학습 패널, 가로 넘침/JS 오류 없음 |
| 오프라인 preview | PASS | 한국어, 외부 네트워크 없음, 쓰기 거부, real worker unavailable |
| 기존 API/인증/영속성 | PASS | HTTPS 로그인, secure cookie, CSRF, 준비 데이터/데모 제어, 기존 설치의 상태 보존 |
| 일반 브라우저 자체 서명 인증서 신뢰 | 승인 대기 | 현재 macOS 로그인 키체인에 공개 인증서 추가; 신뢰 설정의 OS 승인이 필요하며 기본 검증은 아직 실패 |
| WSL2 및 다른 GPU/라이브러리 조합 | 미확인 | 검증은 native Ubuntu / 위의 고정 버전 |
| 주요 키보드 흐름 | PASS | 로그인 Tab/Enter, 실험 Enter/Space, 탭 방향키/Home/End, 갱신 후 행·로그 포커스, 모달 이름/Escape/포커스 복귀 |
| 세션 만료 경계·재로그인 | PASS | 격리된 실제 HTTP/Chromium에서 인증 시계를 주입: 3599초 200 → 3600초 401, 로그인 창 표시와 재로그인 200. 운영 설정은 3600초 유지 |
| 전체 키보드·보조기술 및 실제 1시간 대기 | 미확인 | 네이티브 select 메뉴의 키보드 선택은 테스트 Chromium 환경에서 검증 불가(기본 HTML select도 동일). select 포커스와 API 옵션 선택은 확인. 스크린리더·실제 1시간 wall-clock 대기는 미실행 |
| 큰 모델·다중 GPU·원격 worker·full fine-tuning | 미지원 | 지원 범위는 README 모델 두 개의 로컬 LoRA/QLoRA |
| 업무 데이터 품질 benchmark | 미검증 | 사용자 업무 데이터와 별도 평가 suite는 사용하지 않음 |

## HTTPS 방식과 자료

Python HTTPS API 검사는 정확한 공개 인증서의 체인·기간·IP를 검증했습니다. 격리된 Chromium은 해당 인증서의 **정확한 SPKI 핀**을 사용하며 전역 certificate-error 무시는 사용하지 않습니다. 일반 브라우저 신뢰 등록을 대신하지 않습니다. 현재 클라이언트 공개 인증서는 키체인에 추가했지만 macOS 신뢰 승인 전이므로, 기본 OS 검증은 아직 신뢰 오류를 반환합니다.

[JSON 기록](validation.json), [GPU/브라우저 학습 결과](training-validation.json), [실제 평가 화면](screenshots/real-training-evaluation.png), [모바일 학습 화면](screenshots/real-training-mobile.png)을 참고하세요. 스크린샷과 기록에는 합성 데이터만 포함합니다. 실제 계정 비밀번호·쿠키·토큰·개인 키·기본 모델 가중치·runtime DB는 공개하지 않습니다.

## main 배포

앱 소스와 실제 학습 PR #1은 `main`에 병합되었습니다. README의 기본 clone 명령으로 전체 앱을 설치합니다. 기존 설치 디렉터리·서비스명은 데이터 호환성을 위해 유지할 수 있습니다. 배포 시 실행 중인 학습을 먼저 확인하고, `main`을 fast-forward한 뒤 서비스를 재시작하세요. 사용자 데이터셋이 제공되지 않아 실제 데이터 품질 benchmark는 미실행입니다.

## 재현

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py simulator.py adapter.py auth.py workspace.py training.py train_worker.py tools/build_preview.py tools/download_models.py
node --check static/app.js
node --check static/i18n.js
node --check static/workspace.js
node --check static/training.js
node tests/test_frontend.js
node tests/test_i18n.js
python3 tools/build_preview.py
```

실제 GPU 검증에는 README의 venv·모델 준비·`--enable-training` 설치가 필요합니다. CI 단위 테스트는 모델을 받거나 GPU를 학습하지 않습니다. DOM 스텁과 오프라인 미리보기는 실제 브라우저/GPU 통합 검사를 대체하지 않습니다.
