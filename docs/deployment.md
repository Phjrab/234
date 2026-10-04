# Forge Fine-tuning Dashboard · Ubuntu 배포

앱 실행에는 Python 3.10 이상만 필요합니다. CUDA와 PyTorch는 필수 의존성이 아닙니다. CUDA를 설치해도 이 프로토타입이 실제 학습을 수행하지는 않습니다.

## 설치와 최초 설정

[README](../README.md)의 브랜치 설치 명령을 사용하고, 먼저 서버 PC의 루프백에서 초기 비밀번호를 변경하세요. 이후 [LAN 가이드](lan-access.md)에 따라 해당 PC의 사설 IP가 SAN에 포함된 인증서와 개인 키를 준비합니다. 개인 키와 인증 데이터는 공개 저장소 밖에 보관하세요.

## systemd 예시

아래의 `YOUR_USER`, `YOUR_PRIVATE_IP`, 디렉터리와 인증서 경로를 실제 설치에 맞게 바꾸세요. `/etc/systemd/system/forge-finetune-dashboard.service`에 저장하는 예시입니다.

```ini
[Unit]
Description=Forge Fine-tuning Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/forge-finetune-dashboard
ExecStart=/usr/bin/python3 /home/YOUR_USER/forge-finetune-dashboard/server.py --lan --host YOUR_PRIVATE_IP --port 8765 --tls-cert /home/YOUR_USER/.config/forge-finetune-dashboard/server-cert.pem --tls-key /home/YOUR_USER/.config/forge-finetune-dashboard/server-key.pem
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now forge-finetune-dashboard.service
sudo systemctl status forge-finetune-dashboard.service
```

다른 LAN 컴퓨터에서 `https://YOUR_PRIVATE_IP:8765`로 접속합니다. 자체 서명 인증서를 쓰는 경우 인증서의 지문과 IP를 확인하고 신뢰 등록을 별도로 완료하세요. 필요한 경우 해당 사설 네트워크만 허용하는 방화벽 규칙을 운영자가 설정합니다.

## 기존 설치와 이름 변경

2026-10-04 검증한 기존 설치는 `local-finetune-dashboard` 디렉터리와 systemd 서비스 이름을 유지합니다. GitHub 이름과 화면 브랜드 변경은 이 경로나 저장된 계정·데이터셋·브라우저 `forge.*` 설정을 초기화하지 않습니다. 새 설치는 위의 새 이름을 사용할 수 있습니다.

갱신 전 `data/`와 인증 자료를 별도 보호된 위치에 백업하고 실행 중인 서비스를 재시작하세요. 서버 재시작은 로그인 세션을 종료합니다. 인증서·개인 키·실제 데이터·비밀번호를 배포 문서나 커밋에 포함하지 마세요.

## 검증한 호스트

Ubuntu 24.04.5, Python 3.12.3, NVIDIA RTX 3060 12 GB, 드라이버 595.91.07, CUDA Toolkit 13.2에서 설치와 CUDA 커널 실행을 확인했습니다. 대시보드 HTTPS 로그인·환경 진단·한국어/영어 전환도 검증했습니다. PyTorch 버전 호환성, 모델 다운로드와 실제 파인튜닝은 검증 범위에 포함되지 않습니다.
