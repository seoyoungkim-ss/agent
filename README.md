# 사내 카페테리아 운영 관리 홈페이지

기획 배경과 상세 요구사항은 [`docs/PRD.md`](docs/PRD.md)를 참조한다.

## 구성

| 디렉토리 | 설명 | 배포 대상 |
|---|---|---|
| `backend/` | FastAPI + PostgreSQL(pgvector) API 서버, 배치 집계, 분석 로직 | 사내 Linux 서버 (Docker) |
| `frontend/` | React + TypeScript 대시보드 (홈/분석/시뮬레이션/Agent 채팅) | `backend`가 정적 파일로 함께 서빙 |
| `ingestion-tool/` | 나스카(DRM)로 보호된 취식 로그·주간 식단표를 xlwings로 열어 파싱 후 백엔드에 전송 | 운영자 **Windows PC** (별도 배포, Docker 대상 아님) |
| `docs/PRD.md` | 요구사항 정의서 (기획/DB 설계/기술 스택 결정 포함) | - |

## 로컬에서 실행하기 (Docker)

```bash
cp .env.example .env   # 값 채우기 (INGEST_API_TOKEN 등)
docker compose up -d --build
# http://localhost:8000 에서 대시보드 확인, http://localhost:8000/docs 에서 API 문서
```

## 개발 모드로 실행하기

```bash
# 1) DB (로컬 PostgreSQL + pgvector 확장 필요)
# 2) 백엔드
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # DATABASE_URL 등 채우기 — 이 예시는 backend/.env 용이 아니라
                       # 참고용이며 backend/app/config.py의 기본값을 확인할 것
alembic upgrade head
python -m app.seed.run_seed_holidays
uvicorn app.main:app --reload

# 3) 프론트엔드 (별도 터미널)
cd frontend
npm install
npm run dev   # http://localhost:5173, /api는 vite.config.ts가 백엔드로 프록시
```

## 데이터 수집 (운영자 PC, Windows)

`ingestion-tool/README.md` 참조 — 나스카 DRM 때문에 실제 Excel을 통해서만 파일을
열 수 있어, 이 도구만 Windows에 별도로 설치해 운영자가 수동 실행한다.

## 테스트

```bash
cd backend && source .venv/bin/activate && pytest -q            # 37 tests
cd ingestion-tool && source .venv/bin/activate && pytest -q     # 18 tests
cd frontend && npm run build                                    # 타입체크 + 빌드
```
