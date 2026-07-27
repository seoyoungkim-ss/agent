# 사내망 배포 가이드

`docs/PRD.md` 9.4/9.5에서 정한 대로, 이 저장소는 **두 부분으로 나눠서** 사내에 배포한다.

1. **웹 대시보드** (`backend/` + `frontend/`) — 사내 **Linux 서버**에 Docker로 배포
2. **데이터 수집 도구** (`ingestion-tool/`) — 나스카(DRM) 때문에 운영자 **Windows PC**에 별도 배포

둘은 별개의 배포 대상이니 순서를 헷갈리지 말 것. 아래는 각각의 절차다.

---

## 0. 사전 준비물

| 구분 | 필요한 것 |
|---|---|
| 웹 대시보드 서버 | Linux 서버 1대, Docker + Docker Compose 설치, 이 Git 저장소에 접근 가능 |
| 운영자 PC | Windows, Excel(+나스카 클라이언트) 설치, Python 3.11+ (또는 배포받은 .exe) |
| 공통 | 사내망에서 GitHub(또는 이 저장소가 올라간 사외 Git 호스트)에 접근 가능한지 확인 |

---

## 1. 코드 다운로드 (사내망 서버)

사내망이 사외 Git에 직접 접근 가능한지(프록시 경유 포함)에 따라 두 가지 방법이 있다.

### 방법 A — 사내망에서 git 명령이 바로 되는 경우
```bash
git clone https://github.com/seoyoungkim-ss/agent.git
cd agent
git checkout claude/cafeteria-management-homepage-uekoiv   # 또는 main에 머지된 뒤라면 main
```

### 방법 B — 사내망이 완전 폐쇄망이라 git이 안 되는 경우
1. 인터넷이 되는 PC에서 저장소를 zip으로 다운로드 (GitHub 페이지의 "Code → Download ZIP" 또는 `git clone` 후 압축)
2. 사내 반입 승인된 방식(USB, 사내 파일 전송 시스템 등)으로 사내망 서버에 전달
3. 서버에서 압축 해제

이후 업데이트할 때도 같은 방식(A는 `git pull`, B는 새 zip을 받아 교체)을 반복한다.

---

## 2. 웹 대시보드 실행 (사내 Linux 서버)

```bash
cd agent
cp .env.example .env
```

`.env` 파일을 열어 값을 채운다:

| 변수 | 설명 |
|---|---|
| `POSTGRES_PASSWORD` | DB 비밀번호 — 반드시 기본값(`change-me`)에서 변경 |
| `INGEST_API_TOKEN` | ingestion-tool이 API 호출 시 쓰는 토큰 — 임의의 긴 문자열로 설정 (아래 4단계에서 운영자 PC 설정에도 **동일하게** 넣어야 함) |
| `INTERNAL_LLM_BASE_URL` / `INTERNAL_LLM_API_KEY` | 사내 LLM API 연동 정보. 비워두면 Agent 채팅/월간 VOE 클러스터링이 모의(mock) 응답으로 동작 |
| `APP_PORT` | 대시보드를 열 포트 (기본 8000) |

값을 채웠으면 실행:

```bash
docker compose up -d --build
```

최초 실행 시 자동으로 처리되는 것 (`backend/docker-entrypoint.sh`):
- DB 스키마 마이그레이션 적용 (Alembic)
- 휴일 마스터 데이터 시딩 (2025~2026년, 이미 있으면 건너뜀)
- API 서버 + 빌드된 프론트엔드 정적 파일 서빙 시작

### 접속 확인
- 대시보드: `http://<서버 IP>:8000`
- API 문서: `http://<서버 IP>:8000/docs`
- 헬스체크: `http://<서버 IP>:8000/health` → `{"status":"ok"}`

### 상태 확인 / 로그
```bash
docker compose ps
docker compose logs -f app
docker compose logs -f db
```

### 흔한 문제
- **컨테이너가 계속 재시작됨**: `docker compose logs app`으로 마이그레이션/DB 연결 오류 확인. `.env`의 `INGEST_API_TOKEN`이 비어있으면 시작 시 오류가 난다(필수값).
- **대시보드는 뜨는데 화면이 텅 비어 있음**: 정상이다 — 아직 데이터가 하나도 없기 때문. 3단계(ingestion-tool)로 데이터를 넣어야 홈/분석 화면에 내용이 채워진다.
- **포트 충돌**: `.env`의 `APP_PORT`를 다른 포트로 변경 후 `docker compose up -d --build` 재실행.

### 코드 업데이트 시
```bash
git pull   # 또는 새 zip으로 교체
docker compose up -d --build
```
DB 데이터는 Docker volume(`cafeteria_db_data`)에 남아있으므로 재빌드해도 유지된다.

### 완전히 초기화하고 싶을 때 (주의: 데이터 삭제됨)
```bash
docker compose down -v
```

---

## 3. 데이터 수집 도구 설치 (운영자 Windows PC)

전체 저장소를 받았다면 그 중 `ingestion-tool/` 폴더만 있으면 된다. 이 PC에는
**Excel + 나스카가 설치돼 있어야 한다** (DRM 때문에 실제 Excel로 열어야 파일을 읽을 수 있음).

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
  "backend_base_url": "http://<2단계에서 띄운 서버 IP>:8000/api",
  "api_token": "<.env의 INGEST_API_TOKEN과 동일한 값>"
}
```

### 사용법
새 주간 식단표/취식 로그 파일을 받을 때마다 실행:
```powershell
python cli.py weekly-menu "C:\식단표\2026-07-27_주간식단표.xlsx" --week-start 2026-07-27
python cli.py meal-log "C:\취식로그\mealdata.xlsx"
```
전송 전 파싱 결과(행 수, 경고)를 보여주고 `y`를 입력해야 실제로 서버에 전송된다.

### Python 없이 실행 파일(.exe)로 배포하고 싶다면
```powershell
pip install pyinstaller
pyinstaller --onefile --name cafeteria-ingest cli.py
```
`dist/cafeteria-ingest.exe`를 `config.json`과 함께 운영자 PC에 배포한다. 자세한 내용은
`ingestion-tool/README.md` 참조.

> ⚠️ 수동 실행형 도구다. 실행을 놓치면 데이터 공백이 생기니, 새 파일을 받을 때마다
> 실행하는 것을 운영 체크리스트에 넣어두는 것을 권장한다.

---

## 4. 배치 작업이 실제로 도는지 확인하기

배치(일별 집계, 메뉴 성과 재계산, 월간 VOE 클러스터링)는 서버 안 APScheduler가 자동으로
새벽 시간대에 돈다(`backend/app/scheduler.py`). 데이터를 막 넣은 직후 분석 탭에 아무것도
안 보이면, 배치를 기다리지 않고 수동으로 한 번 트리거해서 바로 확인할 수 있다:

```bash
curl -X POST "http://<서버 IP>:8000/api/analysis/menu-performance/recompute?period_start=2026-01-01&period_end=2026-07-27"
curl -X POST "http://<서버 IP>:8000/api/analysis/users/taste-profile/recompute"
```

---

## 요약 체크리스트

- [ ] 사내 Linux 서버에 저장소 다운로드
- [ ] `.env` 작성 (`INGEST_API_TOKEN` 필수, 사내 LLM 정보는 선택)
- [ ] `docker compose up -d --build` 실행 후 `/health` 확인
- [ ] 운영자 Windows PC에 `ingestion-tool/` 설치, `config.json`에 서버 주소/토큰 입력
- [ ] 취식 로그/주간 식단표로 한 번 테스트 전송
- [ ] 대시보드에서 데이터 확인
