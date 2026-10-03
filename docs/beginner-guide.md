# 처음 파인튜닝을 준비하는 사람을 위한 순서

이 버전은 준비 도구와 합성 실행 시뮬레이터입니다. 실제 RTX 3060 학습은 아직 시작할 수 없습니다. 처음에는 실제 개인정보/업무 데이터를 넣지 말고 제공된 합성 샘플로 흐름을 확인하세요.

## 1. Data · 작은 예제부터

Datasets 화면의 형식 안내를 펼치고 샘플을 다운로드합니다.

- [LLM chat 샘플](samples/llm-chat.jsonl): messages 배열, user/assistant 역할, 각 메시지의 role/content 필수
- [LLM instruction 샘플](samples/llm-instruction.jsonl): instruction/output 필수, input 선택
- [VLM image + text 샘플](samples/vlm-image-text.jsonl): messages와 images 상대 라벨. 이미지 파일은 샘플에 포함되지 않고 실제로 읽지 않습니다

JSONL은 한 줄에 JSON 객체 하나입니다. JSON 배열 파일, CSV, Parquet, ZIP, 이미지 업로드는 지원하지 않습니다. UTF-8 텍스트128 KiB/1000행이 최대이며 여기에는 학습 전체 데이터를 넣기보다 작은 준비 샘플을 사용하세요.

Validate only → 줄/필드 오류 수정 → Validate & save 순서로 진행합니다. 이름과 데이터 종류를 확인한 다음 seed42와 validation 비율0.2로 분할합니다. 같은 seed/비율은 같은 분할을 만듭니다. 중복이 train/validation 양쪽에 남는다는 경고가 있으면 원본 중복을 정리해야 합니다. 현재 서버가 자동으로 내용을 좋게 만들거나 평가 누출을 해결하지는 않습니다.

## 2. Model · 호환성과 크기는 나중에 실제 확인

Training setup에서 작은 LLM/VLM 프리셋을 선택합니다. 모델 이름은 설정 라벨이며 다운로드/호환성 확인이 수행되지 않습니다. 실제 GPU VRAM, 모델 라이선스와 지원 학습 라이브러리를 향후 로컬 워커에서 확인해야 합니다.

12 GB는 기본 계획 가정입니다. 사용자의 RTX 3060이 실제로 그 VRAM을 가진다고 측정한 값이 아닙니다. 이미지 해상도/토큰 길이/옵티마이저/커널이 메모리에 영향을 주므로 휴리스틱 숫자로 학습 가능성을 보장할 수 없습니다.

## 3. Config · 적은 변경으로 시작

기본 프리셋을 먼저 dry-run하고, 고급 옵션은 필요할 때 펼칩니다.

- Batch size: 한 장치에서 한 번에 다루는 예제 수. 크게 올리면 메모리 부담이 늘 수 있습니다
- Gradient accumulation: 여러 작은 배치의 기울기를 모아 업데이트. per-step batch를 작게 유지하면서 effective batch를 키우는 방법입니다
- Learning rate: 업데이트 크기. 높으면 불안정해질 수 있고 낮으면 진행이 느릴 수 있습니다. 한 값이 모든 모델에 맞지는 않습니다
- LoRA rank: 학습하는 어댑터의 규모. 큰 rank는 메모리와 데이터 요구량을 높일 수 있습니다
- QLoRA: 양자화된 기본 모델과 LoRA 어댑터를 함께 사용하는 방식. 현재 도구가 이를 실제로 실행하는 것은 아닙니다. [Hugging Face 공식 설명](https://huggingface.co/docs/peft/developer_guides/quantization)을 참고하세요

Dry-run은 설정 모양/위험 경고를 점검하는 기능입니다. 학습, 토큰화, 이미지 검증은 하지 않습니다. 경고를 검토한 뒤 설정 JSON과 split JSONL을 저장해 미래 워커에 전달할 준비를 합니다.

## 4. Run · 먼저 합성 동작 이해

Queue demo only로 모의 작업을 만듭니다. 대기열은 모의 GPU가 비면 자동으로 시작합니다. Pause는 데모만 멈추고 슬롯을 유지하며 Cancel은 그 모의 실행을 끝냅니다. Retry는 원본을 보존한 새 작업입니다.

OOM 시나리오는 일부러 실패하게 만든 합성 상황입니다. 실제 GPU가 부족하다고 진단한 결과가 아닙니다. Retry는 주입 설정도 보존하므로 다시 실패할 수 있습니다. Review training recipe에서 배치/컨텍스트/rank를 검토하고 정상 데모 시나리오를 새로 만드세요.

## 5. Evaluate · 비교하는 습관부터

Compare에서 두 합성 실행의 train/eval loss와 구성을 비교하고 JSON/CSV를 내보냅니다. 낮은 demo eval loss는 실제 모델 품질이나 일반화 성능을 뜻하지 않습니다. 실제 평가에는 누출 없는 held-out 데이터, 도메인 목표, 생성 예시/기능 평가가 필요하며 이 버전의 실제 평가 워커는 미구현입니다.

## 오류를 볼 때

1. 어떤 단계가 실패했는지 확인합니다: 인증 / 데이터 검증 / 설정 / 데모 실행
2. 무엇이 실패했는지와 줄/필드/오류 코드를 읽습니다
3. Next step을 따르고 입력을 수정한 뒤 다시 검사합니다
4. 기술 상세/로그는 필요할 때 펼칩니다. 비밀번호/토큰/개인 데이터가 있는 자료는 공개 이슈에 붙이지 마세요

서버는 경로나 traceback을 오류 응답으로 내보내지 않습니다. 데모 로그는 합성이고 UI는 흔한 토큰 모양을 가립니다. 이것이 모든 비밀을 찾아주는 도구라는 뜻은 아닙니다.

실제 GPU 학습, 실제 브라우저 동작, 두 번째 LAN 장치 접속은 검증 매트릭스의 별도 미확인 항목입니다.
