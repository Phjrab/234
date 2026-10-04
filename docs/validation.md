# Forge Fine-tuning Dashboard · 검증 기록

2026-10-04 Ubuntu 배포와 다른 LAN 컴퓨터의 Chromium에서 확인했습니다. PASS는 아래에 적힌 범위에서 통과했다는 뜻입니다. 학습 지표와 체크포인트는 계속 합성이며 실제 학습 워커는 미구현입니다.

| 항목 | 결과 | 범위 |
|---|---|---|
| Python 백엔드 | PASS | unittest 93개: 상태 전이, 영속성, 데이터셋, 인증, 임시 루프백 HTTP |
| 프런트엔드 | PASS | DOM 스텁 35개, i18n 테스트, 3개 JS 문법 검사 |
| Python 소스 | PASS | 서버/시뮬레이터/어댑터/인증/워크스페이스/미리보기 컴파일 |
| 실제 HTTPS API | PASS | 인증, 데이터 준비, 설정 검사, 모의 실행 제어, 내보내기와 재시작 후 영속성 |
| 실제 Chromium UI | PASS | 로그인, 화면 이동, 데이터 준비와 다운로드, 데스크톱/모바일 표시 |
| 한국어/영어 | PASS | 즉시 전환, 재접속 유지, 탭 동기화, 미저장 입력 보존, JSON 식별자 보존, 모바일 가로 넘침 없음 |
| 언어 설정의 부작용 | PASS | 권한/비밀번호 API 쓰기 없음, JavaScript 오류 없음 |
| Ubuntu LAN 배포 | PASS | systemd 서비스, 사설 IP HTTPS, 별도 컴퓨터에서 접속 |
| 실제 GPU/CUDA | PASS | RTX 3060 12 GB 탐지, CUDA 13.2 커널 실행. 학습 라이브러리 검증은 아님 |
| 오프라인 미리보기 | PASS | 합성 데이터의 읽기 전용 렌더링, 번들에 i18n 포함, 로컬 브라우저 확인 |
| 일반 브라우저 인증서 신뢰 | 미확인 | 운영체제/브라우저 신뢰 저장소 등록은 별도 사용자 설정 |
| WSL2 배포 | 미확인 | 검증 호스트는 native Ubuntu |
| 전체 키보드 접근성과 실제 1시간 세션 만료 | 미확인 | 일부 DOM/API 단위 검사는 있으나 완전한 브라우저 수동 검증은 없음 |
| PyTorch/모델 호환성, 실제 학습/평가/가중치 | 미구현/미검증 | 모델 다운로드와 실제 학습 워커 없음 |

## 인증서 검증 방식

HTTPS API 검사는 배포 서버의 공개 인증서를 명시적으로 로드해 체인·유효기간·IP를 검증했습니다. 격리된 Chromium 검사는 해당 인증서의 정확한 SPKI 핀을 사용했습니다. 모든 인증서 오류를 무시하는 전역 설정은 사용하지 않았습니다. 이 테스트는 사용자의 일반 브라우저 신뢰 등록을 대신하지 않습니다.

## 자료와 재현

[JSON 기록](validation.json), [배포 가이드](deployment.md), [한국어 설정 데스크톱](screenshots/settings-korean-desktop.png), [한국어 설정 모바일](screenshots/settings-korean-mobile.png)을 참고하세요. 스크린샷은 설정 화면이며 계정 비밀번호나 실제 데이터셋을 포함하지 않습니다.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py simulator.py adapter.py auth.py workspace.py tools/build_preview.py
node --check static/app.js
node --check static/i18n.js
node --check static/workspace.js
node tests/test_frontend.js
node tests/test_i18n.js
python3 tools/build_preview.py
```

DOM 스텁은 CSS/실제 브라우저 검사를 대체하지 않습니다. `offline-preview.html`은 서버·인증·GPU 없이 렌더링하는 합성 fixture입니다. 데이터 저장과 실행 제어는 거부합니다.

2026-10-03 빌드 환경의 브라우저 차단 기록은 과거의 도구 제한입니다. 위 표는 이후 실제 배포 검증으로 갱신한 결과입니다. 호스트별 방화벽/인증서/라이브러리 구성에 따라 새 설치에서는 다시 확인해야 합니다.
