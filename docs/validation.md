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
| 일반 브라우저 자체 서명 인증서 신뢰 | PASS | macOS 기본 SSL 인증서 검증 성공. Safari 새 탭에서 경고 없이 보안 HTTPS 접속 확인 |
| WSL2 및 다른 GPU/라이브러리 조합 | 미확인 | 검증은 native Ubuntu / 위의 고정 버전 |
| 주요 키보드 흐름 | PASS | 로그인 Tab/Enter, 실험 Enter/Space, 탭 방향키/Home/End, 갱신 후 행·로그 포커스, 모달 이름/Escape/포커스 복귀 |
| 세션 만료 경계·재로그인 | PASS | 격리된 실제 HTTP/Chromium에서 인증 시계를 주입: 3599초 200 → 3600초 401, 로그인 창 표시와 재로그인 200. 운영 설정은 3600초 유지 |
| Safari 네이티브 언어 메뉴 | PASS | Space로 메뉴 열기, 방향키/Enter로 영어·한국어 선택, 한국어 복귀 확인 |
| WCAG A/AA 자동 검사 | PASS | axe-core: 로그인, 7개 화면, 상세 탭, 모바일을 포함한 16개 화면의 위반 0. 보조 텍스트·차트 대비, 입력 경계와 포커스 표시 보완 |
| 실제 1시간 세션 대기 | PASS | 운영 HTTPS에서 시계 주입 없이 원본 쿠키 유지: 3590초 HTTP 200 → 3605초 HTTP 401. 로그인 창 표시와 재로그인 HTTP 200 확인 |
| 전체 보조기술 감사 | 미실행 | Safari 접근성 트리의 이름·역할은 확인. VoiceOver/NVDA 전체 시나리오와 수동 WCAG 적합성 인증은 별도 |
| 다중 GPU·원격 worker·full fine-tuning | 미지원 | 로컬 GPU의 네이티브 Transformers 모델 LoRA/QLoRA 지원. 모델 크기는 실제 VRAM에 제한됨 |
| 업무 데이터 품질 benchmark | 미검증 | 사용자 업무 데이터와 별도 평가 suite는 사용하지 않음 |

## HTTPS 방식과 자료

Python HTTPS API 검사는 정확한 공개 인증서의 체인·기간·IP를 검증했습니다. 격리된 Chromium은 해당 인증서의 **정확한 SPKI 핀**을 사용하며 전역 certificate-error 무시는 사용하지 않습니다. 일반 브라우저 신뢰 등록을 대신하지 않습니다. 현재 Mac은 기본 SSL 인증서 검증이 성공하며, Safari 새 탭에서도 경고 없는 보안 접속을 확인했습니다. 테스트 Chromium과 curl/Node 같은 독립 신뢰 저장소는 macOS 신뢰 설정과 다를 수 있습니다.

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
node --check tools/verify_browser.js
```

실제 GPU 검증에는 README의 venv·모델 준비·`--enable-training` 설치가 필요합니다. CI 단위 테스트는 모델을 받거나 GPU를 학습하지 않습니다. DOM 스텁과 오프라인 미리보기는 실제 브라우저/GPU 통합 검사를 대체하지 않습니다.

## 선택적 실제 브라우저 검사

검사 도구는 로그인 및 검사 종료 시 로그아웃만 수행하며 데이터셋·학습·서버 설정은 변경하지 않습니다. 언어 선택은 격리된 브라우저 저장소에 적용합니다. 비공개 JSON 파일에 `url`, `username`, `password`를 넣고 파일 접근 권한을 제한하세요. 비밀번호를 명령줄에 넣지 마세요.

```bash
npm install --prefix /tmp/forge-browser-check playwright @axe-core/playwright
NODE_PATH=/tmp/forge-browser-check/node_modules /tmp/forge-browser-check/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/forge-browser-check/node_modules node tools/verify_browser.js \
  --credentials /PRIVATE/credentials.json --report /PRIVATE/a11y-report.json
```

자체 서명 서버를 격리된 Chromium에서 검사할 때는 `--certificate /PRIVATE/public-server-cert.pem`을 추가합니다. 참조 인증서의 유효 기간과 접속 호스트를 검사한 후 정확한 SPKI 핀을 사용합니다. 이는 OS 신뢰 설치와 구분되며, 전역 TLS 오류 무시는 사용하지 않습니다.

동일 명령에 `--session-expiry`를 추가하면 실제 1시간 대기를 수행합니다. 원본 쿠키를 유지한 HTTPS 요청은 인증서 체인·기간·호스트를 검증하고, 만료 후 401·로그인 창·재로그인을 확인합니다. 테스트 중 서버를 재시작하면 세션이 조기에 만료되므로 검사가 실패할 수 있습니다. 자동 접근성 검사와 주요 키보드 검증은 보조기술 전체 감사나 WCAG 적합성 인증을 대신하지 않습니다.

## 화면 문구 검증

2026-10-04, `69ad6b1`에서 한국어·영어 제목과 안내문을 기능명 중심으로 수정했습니다. HTTPS Chromium에서 5개 기능 화면의 두 언어 제목, 대시보드·로그인 제목, 데스크톱·모바일 표시, 언어 변경 시 미저장 학습 설정 유지를 확인했습니다. 브라우저 JavaScript 오류는 없었습니다. 프런트엔드 37개 테스트, 언어 테스트, 오프라인 표시 검사와 [CI](https://github.com/Phjrab/forge-finetune-dashboard/actions/runs/37199569165)가 통과했습니다.

정적 파일만 갱신하여 서비스 재시작 없이 반영했습니다. 스크린샷은 기존 합성 데이터 검증 결과를 사용하며, 이번 변경에서는 GPU 학습과 1시간 세션 검사를 다시 실행하지 않았습니다.

## Hugging Face 모델 카탈로그 검증

공식 Hub 검색·페이지 추가 조회, 제작사 아이콘, 제작사·계열·LLM/VLM 필터, 정확한 저장소 ID 조회와 기타 작업 모델의 학습 제한 표시를 확인했습니다. 토큰 오류가 기존 계정이나 대시보드 세션을 변경하지 않으며, 선택한 추가 모델은 언어 변경 후에도 유지됩니다. 새 계정 설정·목록의 데스크톱/모바일 4개 화면에서 axe-core A/AA 위반과 브라우저 JavaScript 오류는 0건입니다. Python 130개, 프런트엔드 39개, 언어 테스트가 통과했습니다.

`HuggingFaceTB/SmolLM2-135M-Instruct`를 공개 Hub에서 272,496,399 bytes 다운로드하고 revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`으로 고정했습니다. 기존 합성 LLM 데이터로 LoRA 10스텝을 실제 GPU에서 완료했으며 검증 손실은 1.0491 → 0.8832, 실제 체크포인트 4개를 저장했습니다. 실제 데이터 품질 평가 결과가 아닙니다. 실제 사용자 토큰 연결과 접근 제한·비공개 모델 다운로드는 계정이 제공되지 않아 실검증하지 않았습니다. 유효 토큰 연결·권한·비노출은 모의 Hub 응답을 사용한 단위 테스트로 확인했습니다.

[검증 JSON](huggingface-validation.json)은 공개 모델 ID·리비전, 합성 학습 지표와 검사 결과만 포함합니다. 이번 화면 스크린샷은 로컬에만 보관합니다.

## 인코더·디코더 아키텍처 확장 검증

2026-10-05, 동일한 Ubuntu / RTX 3060 환경에서 FLAN-T5와 BART의 실제 GPU 학습을 검증했습니다. 설치된 Transformers 4.57.1의 네이티브 seq2seq 구조를 지원하며, PEFT `SEQ_2_SEQ_LM`, 입력과 정답의 분리 토큰화, 개별 길이 검사, 정답 패딩 마스크, 전체 디코더 토큰 평가와 생성 결과 디코딩을 적용했습니다. SentencePiece 0.2.1을 추가했고 FLAN-T5의 느린 토크나이저도 로컬 파일로 확인했습니다.

| 모델 | 경로 | steps | 학습 전 validation loss | 학습 후 validation loss | 재개 |
|---|---|---:|---:|---:|---|
| google/flan-t5-small | LORA | 24 | 3.2812 | 2.9323 | PASS |
| google/flan-t5-small | QLORA | 10 | 3.3874 | 3.2734 | — |
| facebook/bart-large-cnn | LORA | 10 | 3.3438 | 2.7188 | — |
| facebook/bart-large-cnn | QLORA | 10 | 3.5088 | 2.7860 | — |

각 경로는 실제 optimizer update, 생성 응답, safetensors 체크포인트 4개와 어댑터 ZIP 다운로드를 완료했습니다. FLAN-T5 LoRA는 저장된 optimizer/RNG 상태에서 일시정지·재개했습니다. 레코드 12개, train 9개 / validation 3개의 합성 LLM JSONL과 batch 2를 사용했습니다. 업무 데이터 품질이나 모델별 일반화 성능은 평가하지 않았습니다.

Python 137개 테스트가 원격에서 모두 통과했습니다. 프런트엔드 39개·언어·문법 검사와 CI도 통과했습니다. 별도 CI 작업에서는 가중치 다운로드 없이 작은 T5/BART/GPT-2 모델을 구성해 LoRA 역전파, 어댑터 저장·재로딩, 생성과 GPT-2의 Conv1D 투영을 검사합니다. 기존 Qwen/SmolVLM GPU 학습과 1시간 세션 검사를 반복하지 않았습니다.

HTTPS Chromium에서 인코더·디코더 검색, 제작사 필터, T5와 요약 BART의 구조·다운로드·설치·선택, 언어 변경 시 선택 유지, 한국어 평가·생성 화면을 확인했습니다. FLAN-T5처럼 `pipeline_tag`가 없는 저장소도 `text2text-generation` 태그로 검색됩니다. 새 목록의 데스크톱·모바일 두 화면에서 가로 넘침, JavaScript 오류, axe-core A/AA 위반은 0건입니다.

[검증 JSON](architecture-validation.json), [CI](https://github.com/Phjrab/forge-finetune-dashboard/actions/runs/37251505151). 공개 기록에는 모델 ID·리비전과 합성 학습 지표만 포함합니다. 원격 호스트·계정·데이터셋 및 작업 식별자는 제외했습니다.
