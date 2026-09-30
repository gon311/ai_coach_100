# GCP 서비스 구축·운영 증빙

## 확인 목적

이 문서는 AI 체력 코치의 Google Cloud Compute Engine 구축과 서비스 배포·서빙 담당 근거를 공개 저장소에서 확인할 수 있도록 요약한 기록입니다. 원본 증빙은 2026년 9월 27일 수집한 `ai-coach-evidence-20260927` 폴더이며, 해당 GCP 운영 계정은 팀장 이다겸이 관리했습니다.

원본에는 개인 이메일과 외부 접속 IP가 포함되어 있어 공개 저장소에는 올리지 않고, 파일명·검증값과 역할 판단에 필요한 사실만 기록합니다.

## 증빙에서 확인한 사실

| 원본 파일 | 확인한 내용 |
|---|---|
| `01-vm-description.yaml` | 2026년 9월 27일 `ai-coach-1` Compute Engine 인스턴스가 생성됐으며 증빙 수집 시점에 `RUNNING` 상태였음 |
| `02-gcp-audit-log.json` | 이다겸의 GCP 운영 계정이 인스턴스 생성과 네트워크 태그 설정 작업을 수행한 감사 로그 |
| `03-gcp-audit-summary.txt` | 인스턴스 생성과 태그 설정의 시각·작업 주체·API 메서드를 요약한 기록 |
| `vm-logs/04-ai-fitness-web-journal.txt` | `ai-fitness-web.service` 기동, FastAPI 애플리케이션 시작 완료, Uvicorn의 `127.0.0.1:8501` 실행, `/api/health` 및 실제 서비스 요청의 HTTP 200 응답 |
| `vm-logs/05-vm-boot-history.txt` | 2026년 9월 27일 VM 생성 직후의 부팅 이력과 재부팅 기록 |
| `vm-logs/06-login-reboot-history.txt` | GCP 커널에서의 시스템 부팅·실행 상태 기록 |
| `vm-logs/07-service-file-stat.txt` | `/etc/systemd/system/ai-fitness-web.service`가 2026년 9월 27일 생성·수정된 파일 메타데이터 |

위 기록은 이다겸이 GCP VM을 만들고, 애플리케이션을 systemd 서비스로 구성해 FastAPI 서버를 기동하고, 상태 확인과 실제 요청 응답까지 점검한 **GCP 구축·배포·서빙 담당자**라는 역할 근거로 사용합니다. 애플리케이션 기능 코드 전체의 단독 작성 근거로 확대 해석하지 않습니다.

## 원본 무결성 확인값

| 파일 | SHA-256 |
|---|---|
| `01-vm-description.yaml` | `dfc43ff41ea908261a3ea20b8ed56e56ce8f6292d809b48ae85b40f8db4f9f4e` |
| `02-gcp-audit-log.json` | `1e5d7f3a17b4fa75367fea2437e0104dfde4064e7441d749a620dd1aa1107858` |
| `03-gcp-audit-summary.txt` | `6eb0cf85b33336d6152ca59ebec2f6274870ce7fa9b8859446777cc662ed1a26` |
| `vm-logs/04-ai-fitness-web-journal.txt` | `ca9a916c40f650f7a1c91cc4893f630dd6fdf6ac5638298393191e154c4c5a0d` |
| `vm-logs/05-vm-boot-history.txt` | `2916c9832f27c6d9cbbd1bdc3f91739b8add73e2eed4a078e5e4791db9513c72` |
| `vm-logs/06-login-reboot-history.txt` | `56371214705450727ac066eae2a49f518193baff915474be59bbdf587cd7028b` |
| `vm-logs/07-service-file-stat.txt` | `a023552fc648ba78e8a37137fdb02c1a376156be942c17efabccb50ac5efac74` |

## 저장소에서 연결되는 구현

- `apps/api/src/fitness_web_server.py`: GCP에서 실행한 FastAPI 웹 애플리케이션
- `apps/api/scripts/server.sh`: Linux 환경의 로컬 모델·웹 서버 통합 기동 스크립트
- `apps/api/scripts/START_AI_FITNESS.sh`: 서비스 시작 진입점
- `apps/api/scripts/STOP_AI_FITNESS.sh`: 서비스 종료 진입점
- `docs/frontend/assets/service-landing-live.png`: GCP 배포 서비스의 실제 랜딩 화면
- `docs/frontend/assets/service-recommendation-live.png`: 배포 서비스의 운동 추천 화면

