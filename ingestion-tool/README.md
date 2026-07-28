# ingestion-tool

사내 카페테리아 홈페이지의 데이터 수집 도구. `docs/PRD.md` 9.2 참조.

## 왜 별도 도구인가

사내 보안 프로그램(나스카 등 DRM)이 걸려 있어 취식 관련 파일들과 주간 식단표(xlsx)
모두 pandas/openpyxl 같은 라이브러리로 원문을 직접 열 수 없다. DRM은 실제
Excel 애플리케이션이 파일을 열 때만 복호화하므로, 이 도구는 **xlwings로 실제
Excel을 구동**해 셀 값을 읽은 뒤, 정제된 데이터만 백엔드로 전송한다.

## 취식 데이터는 파일 2개를 합쳐서 만든다

당초 계획과 달리 취식 데이터는 한 파일이 아니라 **① 식당취식정보(POS 결제 로그)**
와 **② 맛평가 리스트**, 두 개로 나뉘어 나온다. ①에는 누가 언제 어느 코너에서
뭘 먹었는지가, ②에는 그 식사에 대한 맛평가/의견이 있고, 둘을 사번(①)/Knox
ID(②) + 날짜 + 식사구분 + 메뉴명으로 매칭해서 합친다. 정확한 컬럼과 매칭 가정은
`docs/CALCULATION_LOGIC.md` 12번 항목, 실제 조인 로직은 `parsing/merge.py`
참고.

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

# 취식 로그 = 식당취식정보 + 맛평가 리스트, 두 파일을 함께 넘긴다
python cli.py meal-log "C:\취식기록\transactions.xlsx" "C:\맛평가\taste_eval.xlsx"
```

두 명령 모두 전송 전 파싱/병합 결과(행 수, 맛평가 매칭률, 샘플, 경고)를
보여주고 `y`를 입력해야 백엔드로 전송한다. `--yes`를 주면 확인 없이 바로 전송한다.

> ⚠️ 수동 실행형 도구다. 새 식단표/취식 데이터를 받을 때마다 운영자가 직접
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

## 취식 데이터 파싱/병합 규칙 (조정 필요할 수 있음)

- 취식기록의 사원번호가 비어 있는 행(관측된 사례: 협력사 직원)은 건너뛴다 —
  개인 단위 분석에서 빠진다는 뜻이므로 실제로 맞는 정책인지 확인 필요.
- 맛평가와의 조인 키는 `(사번/Knox ID, 취식 날짜, 식사구분, 메뉴명)`이다. Knox ID와
  사원번호가 같은 값 체계라고 가정하고 있다 — 다르면 `parsing/merge.py`의
  `employee_key()`에 변환 로직을 추가해야 한다.
- 메뉴명은 취식기록의 "화면표시명(한글)" 기준으로 맞춘다(코드성 "메뉴명" 아님).
- 식사구분 어휘 차이(취식기록 "중식" ↔ 맛평가 "점심")는 `models.py`의
  `MEAL_TYPE_ALIASES`에서 정규화한다.

자세한 배경은 `docs/CALCULATION_LOGIC.md` 12번 항목 참고.

## 합성 테스트 파일로 파이프라인 미리 확인하기

`sample_data/`에 실제 파일과 같은 구조의(DRM 없는) 합성 xlsx 샘플과, 그걸
파싱+병합해서 결과를 출력하는 스크립트가 있다. Excel 없이도(Linux 포함) 바로
돌려볼 수 있다:

```bash
python sample_data/generate_samples.py   # 샘플 xlsx 2개 생성
python sample_data/demo_merge.py         # 파싱 → 병합 → 콘솔 출력
```

## 테스트 (Linux/Mac 개발 환경에서도 가능)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```
