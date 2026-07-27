# 사내망 배포 가이드 (Docker 미사용 / 완전 초기 설치 기준)

`docs/PRD.md` 9.4/9.5에서 정한 대로, 이 저장소는 **두 부분으로 나눠서** 배포한다.

1. **웹 대시보드** (`backend/` + `frontend/`) — 사내 **Linux 서버**에 직접 설치 (지금은 Docker 미사용)
2. **데이터 수집 도구** (`ingestion-tool/`) — 나스카(DRM) 때문에 운영자 **Windows PC**에 별도 설치

이 문서는 서버에 **아무것도 안 깔려있는 상태(완전 초기)** 를 기준으로, PostgreSQL 설치부터
순서대로 설명한다. Docker는 나중에 필요해지면 저장소에 이미 있는 `docker-compose.yml`로
전환할 수 있으니 맨 아래 부록을 참고한다.

---

## 0. 사전 준비물

| 구분 | 필요한 것 |
|---|---|
| 웹 대시보드 서버 | Linux 서버 1대 (Ubuntu/Debian 계열 기준으로 설명, root 또는 sudo 권한), 이 Git 저장소에 접근 가능 |
| 운영자 PC | Windows, Excel(+나스카 클라이언트) 설치, Python 3.11+ (또는 배포받은 .exe) |
| 공통 | Python 3.11+, Node.js 20+ (프론트엔드는 **빌드할 때만** 필요, 운영 중엔 불필요) |

---

## 1. 코드 다운로드 (사내망 서버)

사내망이 사외 Git에 접근 가능한지에 따라 방법이 갈린다.

### 방법 A — 사내망에서 git 명령이 되는 경우
```bash
git clone https://github.com/seoyoungkim-ss/agent.git
cd agent
git checkout claude/cafeteria-management-homepage-uekoiv   # main에 머지됐다면 main
```

### 방법 B — 완전 폐쇄망이라 git이 안 되는 경우
인터넷 되는 PC에서 zip으로 받아 사내 반입 승인 절차(USB, 사내 파일 전송 시스템 등)로
서버에 옮긴 뒤 압축을 푼다. 이후 업데이트도 같은 방식(A는 `git pull`, B는 새 zip 교체)을
반복한다.

---

## 2. PostgreSQL 설치 + pgvector 확장 + DB 생성 (완전 처음부터)

### 2-1. PostgreSQL 설치
```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "SELECT version();"   # 설치 확인
```
설치된 메이저 버전을 확인해둔다 (예: `psql (PostgreSQL) 16.x` → 버전은 16).
```bash
sudo -u postgres psql -c "SHOW server_version;"
```

### 2-2. pgvector 확장 설치
메뉴 취향 벡터(6.1), VOE 임베딩(8) 저장에 필요한 확장이다. **위에서 확인한 PostgreSQL
버전 번호**를 아래 `<PGVER>` 자리에 넣는다 (예: 16).
```bash
sudo apt-get install -y postgresql-<PGVER>-pgvector
```
> apt 저장소에 해당 패키지가 없다면(오래된 배포판 등) 소스 빌드가 필요하다:
> ```bash
> sudo apt-get install -y git build-essential postgresql-server-dev-<PGVER>
> git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector
> cd /tmp/pgvector && make && sudo make install
> ```

### 2-3. 서비스 계정 및 DB 생성
```bash
sudo -u postgres psql <<'EOF'
CREATE USER cafeteria WITH PASSWORD '여기에_강한_비밀번호로_변경';
CREATE DATABASE cafeteria OWNER cafeteria;
\c cafeteria
CREATE EXTENSION IF NOT EXISTS vector;
EOF
```
확인:
```bash
sudo -u postgres psql -d cafeteria -c "\dx"   # vector 확장이 목록에 보이면 성공
```

같은 방식으로 테스트용 DB도 하나 더 만들어두면(선택) `pytest` 실행 시 개발 DB를
건드리지 않는다:
```bash
sudo -u postgres psql -c "CREATE DATABASE cafeteria_test OWNER cafeteria;"
sudo -u postgres psql -d cafeteria_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

---

## 3. 백엔드 설치 및 마이그레이션

```bash
cd agent/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`.env` 파일 생성 (`backend/.env`, 저장소에는 커밋되지 않음):
```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql+psycopg://cafeteria:여기에_2-3에서_설정한_비밀번호@localhost:5432/cafeteria
INGEST_API_TOKEN=임의의_긴_랜덤_문자열_생성
INTERNAL_LLM_BASE_URL=
INTERNAL_LLM_API_KEY=
EOF
```
- `INGEST_API_TOKEN`: ingestion-tool(운영자 PC)이 API 호출 시 쓰는 토큰. 예: `openssl rand -hex 24`로 생성.
- `INTERNAL_LLM_BASE_URL` / `INTERNAL_LLM_API_KEY`: 사내 LLM 연동 정보. 비워두면 Agent 채팅/월간 VOE 클러스터링이 모의(mock) 응답으로 동작한다.

DB 스키마 적용 + 휴일 마스터 데이터 시딩:
```bash
alembic upgrade head
python -m app.seed.run_seed_holidays
```

---

## 4. 프론트엔드 빌드

프론트엔드는 **운영 중에는 Node가 필요 없다** — 한 번 정적 파일로 빌드해서 백엔드가
그 파일을 서빙하게만 하면 된다.

```bash
cd ../frontend
npm install
npm run build      # frontend/dist 생성
```

백엔드가 이 빌드 결과를 찾게 하려면 `backend/.env`에 절대경로로 한 줄만 추가하면 된다
(`pydantic-settings`가 `.env`를 읽어 `app/config.py`의 `frontend_dist_dir` 값으로 반영한다):
```bash
echo "FRONTEND_DIST_DIR=$(realpath dist)" >> ../backend/.env   # frontend/ 안에서 실행한 경우
```

---

## 5. 서버 실행

### 5-1. 빠르게 확인만 해보고 싶을 때 (foreground)
```bash
cd ../backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
브라우저에서 `http://<서버 IP>:8000` 접속 → 대시보드가 보이면 성공.
`http://<서버 IP>:8000/health` → `{"status":"ok"}`.

Ctrl+C로 끄면 서버도 같이 종료된다 (터미널 붙어있는 동안만 유지).

### 5-2. 상시 구동 (systemd) — 운영에는 이 방식을 권장
```bash
sudo tee /etc/systemd/system/cafeteria-backend.service > /dev/null <<EOF
[Unit]
Description=사내 카페테리아 운영 관리 백엔드
After=network.target postgresql.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cafeteria-backend
sudo systemctl status cafeteria-backend
```
이렇게 하면 서버가 재부팅돼도 자동으로 다시 뜬다. 배치 작업(일별 집계, 월간 VOE
클러스터링)도 이 프로세스 안에서 APScheduler가 알아서 도니 별도 cron이 필요 없다.

로그 확인:
```bash
journalctl -u cafeteria-backend -f
```

### 5-3. 방화벽
사내 방화벽에서 8000번 포트(또는 원하는 포트)를 서버 내부망에 열어준다:
```bash
sudo ufw allow 8000/tcp   # ufw를 쓰는 경우
```

---

## 6. 데이터 수집 도구 설치 (운영자 Windows PC)

저장소 중 `ingestion-tool/` 폴더만 있으면 된다. 이 PC에는 **Excel + 나스카가 설치돼
있어야 한다** (DRM 때문에 실제 Excel로 열어야 파일을 읽을 수 있음).

```powershell
cd ingestion-tool
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
```

`config.json`을 열어 값을 채운다:
```json
{
  "backend_base_url": "http://<3~5단계에서 띄운 서버 IP>:8000/api",
  "api_token": "<backend/.env의 INGEST_API_TOKEN과 동일한 값>"
}
```

사용법:
```powershell
python cli.py weekly-menu "C:\식단표\2026-07-27_주간식단표.xlsx" --week-start 2026-07-27
python cli.py meal-log "C:\취식로그\mealdata.xlsx"
```
전송 전 파싱 결과를 보여주고 `y`를 입력해야 실제로 서버에 전송된다. Python 없이
쓰고 싶으면 `ingestion-tool/README.md`의 PyInstaller `.exe` 빌드 방법을 참고한다.

> ⚠️ 수동 실행형 도구다. 새 파일을 받을 때마다 실행하는 것을 운영 체크리스트에
> 넣어두는 것을 권장한다.

---

## 7. 데이터 넣은 직후 바로 확인하고 싶을 때

배치는 새벽에 자동으로 돌지만, 데이터를 막 넣은 직후 바로 확인하려면 수동으로
한 번 트리거할 수 있다:
```bash
curl -X POST "http://<서버 IP>:8000/api/analysis/menu-performance/recompute?period_start=2026-01-01&period_end=2026-07-27"
curl -X POST "http://<서버 IP>:8000/api/analysis/users/taste-profile/recompute"
```

---

## 8. 완전히 처음부터 다시 시작하고 싶을 때 (초기화)

테스트하다가 데이터를 다 지우고 깨끗한 상태로 되돌리고 싶은 경우.

### 8-1. 데이터만 지우고 스키마는 유지 (테이블 비우기)
```bash
cd backend && source .venv/bin/activate
alembic downgrade base   # 모든 테이블 삭제
alembic upgrade head     # 스키마 재생성
python -m app.seed.run_seed_holidays   # 휴일 데이터 다시 시딩
```

### 8-2. DB 자체를 통째로 삭제하고 재생성
```bash
sudo systemctl stop cafeteria-backend   # 먼저 서버 정지 (연결 중인 세션 정리)
sudo -u postgres psql <<'EOF'
DROP DATABASE IF EXISTS cafeteria;
CREATE DATABASE cafeteria OWNER cafeteria;
\c cafeteria
CREATE EXTENSION IF NOT EXISTS vector;
EOF
cd backend && source .venv/bin/activate
alembic upgrade head
python -m app.seed.run_seed_holidays
sudo systemctl start cafeteria-backend
```

### 8-3. PostgreSQL 자체를 완전히 제거하고 처음부터 (극단적인 경우)
```bash
sudo systemctl stop postgresql
sudo apt-get purge -y postgresql postgresql-contrib "postgresql-*-pgvector"
sudo rm -rf /var/lib/postgresql
```
이후 **2단계**부터 다시 진행하면 된다.

---

## 요약 체크리스트

- [ ] PostgreSQL 설치 + pgvector 확장 + `cafeteria` DB/계정 생성 (2단계)
- [ ] 저장소 다운로드 (1단계)
- [ ] `backend/.env` 작성 (`DATABASE_URL`, `INGEST_API_TOKEN` 필수)
- [ ] `alembic upgrade head` + 휴일 시딩 (3단계)
- [ ] `npm run build`로 프론트엔드 빌드 (4단계)
- [ ] systemd 서비스 등록 후 `/health` 확인 (5단계)
- [ ] 운영자 Windows PC에 `ingestion-tool/` 설치, `config.json` 작성 (6단계)
- [ ] 취식 로그/주간 식단표 한 번 테스트 전송 후 대시보드 확인

---

## 부록: 나중에 Docker로 전환하고 싶을 때

저장소에 `docker-compose.yml`과 `backend/Dockerfile`이 이미 준비되어 있다. 언제든
아래처럼 전환할 수 있다 (기존 systemd 서비스는 먼저 내린다):
```bash
sudo systemctl stop cafeteria-backend
sudo systemctl disable cafeteria-backend
cp .env.example .env   # 값 채우기 (POSTGRES_PASSWORD, INGEST_API_TOKEN 등)
docker compose up -d --build
```
단, 이 경우 DB가 컨테이너 안 PostgreSQL로 새로 생성되므로, 기존 데이터를 옮기려면
`pg_dump`/`pg_restore`로 별도 이관이 필요하다.
