# ingestion-tool

사내 카페테리아 홈페이지의 데이터 수집 도구. `docs/PRD.md` 9.2 참조.

## 왜 별도 도구인가

사내 보안 프로그램(나스카 등 DRM)이 걸려 있어 `mealdata.csv`와 주간 식단표(xlsx)
모두 pandas/openpyxl 같은 라이브러리로 원문을 직접 열 수 없다. DRM은 실제
Excel 애플리케이션이 파일을 열 때만 복호화하므로, 이 도구는 **xlwings로 실제
Excel을 구동**해 셀 값을 읽은 뒤, 정제된 데이터만 백엔드로 전송한다.

이 때문에 이 도구는 **Excel + 나스카가 설치된 Windows PC에서만** 동작한다
(`io_excel.py`가 xlwings/COM에 의존). `parsing/` 아래의 순수 파싱 로직은
Linux/Mac에서도 단위 테스트가 가능하도록 분리되어 있다.

## 설치 (운영자 PC, Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
# config.json을 열어 backend_base_url / api_token을 채운다
```

## 사용법

```powershell
# 주간 식단표 (그 표가 나타내는 주의 월요일 날짜를 --week-start로 지정)
python cli.py weekly-menu "C:\식단표\2026-07-20_주간식단표.xlsx" --week-start 2026-07-20

# 취식 로그
python cli.py meal-log "C:\취식로그\mealdata.xlsx"
```

두 명령 모두 전송 전 파싱 결과(행 수, 코너/식사구분별 집계, 샘플, 경고)를
보여주고 `y`를 입력해야 백엔드로 전송한다. `--yes`를 주면 확인 없이 바로 전송한다.

> ⚠️ 수동 실행형 도구다. 새 식단표/취식 로그를 받을 때마다 운영자가 직접
> 실행해야 하며, 실행을 놓치면 데이터 공백이 생긴다. 주간 단위 체크리스트로
> 실행 여부를 관리하는 것을 권장한다.

## 단일 실행 파일(.exe)로 배포하기

운영자 PC에 Python이 없어도 실행할 수 있도록 PyInstaller로 묶는다:

```powershell
pip install pyinstaller
pyinstaller --onefile --name cafeteria-ingest cli.py
```

`dist/cafeteria-ingest.exe`를 `config.json`과 함께 운영자 PC에 배포한다.

## 메뉴표 파싱 규칙 (조정 필요할 수 있음)

- 1번째 컬럼(조/중/석식), 2번째 컬럼(코너명)은 병합 셀을 위→아래로 forward-fill한다.
- 요일 셀 안 텍스트는 줄바꿈(`\n`) 또는 `/`, `,`, `·` 로 항목을 분리하고,
  **첫 번째 항목을 메인, 나머지를 부찬**으로 가정한다 (`parsing/weekly_menu_parser.py`
  의 `split_cell_into_items`). 실제 식단표로 검증한 뒤 필요하면 이 규칙만 수정하면 된다.

## 테스트 (Linux/Mac 개발 환경에서도 가능)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```
