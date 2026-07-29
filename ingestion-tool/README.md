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
# (사번↔Knox ID 매핑이 필요하면 employee_mapping_path도 — 아래 "사번↔Knox ID
#  매핑" 절 참고)
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

맛평가 매칭률이 이상하게 낮거나 0%면(날짜/메뉴명/식사구분/사번은 다 맞아 보이는데도
안 되는 경우가 실제로 있었음 — 엑셀이 숫자만 있는 사번/Knox ID를 "12345678.0"으로
자동변환하는 문제 등), `--debug-sample`로 진단할 수 있다:
```powershell
python cli.py meal-log "transactions.xlsx" "taste_eval.xlsx" --debug-sample
```
세 가지를 출력한다:
1. **자동 진단 A — 맛평가 기준(정확한 신호, 우선 확인)** — 조인 키 4개 필드
   (ID/날짜/식사구분/메뉴명) 중 하나씩 빼고, **맛평가 건수를 분모로** 다시
   세어본다. 예: "ID만 무시하고 매칭: 480건"인데 "전부 일치: 0건"이면
   ID(사번/Knox ID)가 원인. 화면에 뜬 숫자만 읽어서 알려줘도 원인을 좁힐 수
   있다(사내망이라 복붙이 안 되는 환경 고려). 맛평가는 응답률이 낮아 취식기록
   보다 훨씬 적은 게 정상이라(예: 취식기록 45만 건에 맛평가 1,700건), 이 진단은
   모든 카운트가 맛평가 건수를 못 넘으므로 신뢰할 수 있는 신호다.
2. **자동 진단 B — 취식기록 기준(참고용)** — 같은 방식이지만 취식기록 건수를
   분모로 센다. **주의**: 같은 날 같은 인기메뉴를 먹은 사람이 수백 명이면,
   ID 하나만 무시해도 그 사람들이 전부 "매칭 후보"로 잡혀 숫자가 실제보다 훨씬
   부풀려질 수 있다 — 이 값만 보고 "ID가 원인"이라 단정하지 말고 진단 A를
   우선 봐야 한다.
3. **원본 샘플** — 취식기록/맛평가 양쪽에서 각각 5건씩(숫자 지정 가능,
   `--debug-sample 10`) 조인 키를 `repr()`로 그대로 출력한다 — 자동 진단으로
   원인 필드를 좁힌 뒤, 실제 값이 어떻게 다른지(공백, 타입 차이 등) 확인할 때
   쓴다.

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
- 맛평가와의 조인 키는 `(사번/Knox ID, 취식 날짜, 식사구분, 메뉴명)`이다. **A사
  인원은 사번==Knox ID**라 그대로 매칭되지만, 다른 회사는 값 체계가 달라 매핑이
  필요하다 — 아래 "사번↔Knox ID 매핑" 절 참고.
- 메뉴명은 취식기록의 "화면표시명(한글)" 기준으로 맞춘다(코드성 "메뉴명" 아님).
- 식사구분 어휘 차이(취식기록 "중식" ↔ 맛평가 "점심")는 `models.py`의
  `MEAL_TYPE_ALIASES`에서 정규화한다.

자세한 배경은 `docs/CALCULATION_LOGIC.md` 12번 항목 참고.

## 사번↔Knox ID 매핑 (A사 외 인원 맛평가 매칭용)

A사가 아닌 회사(계열사/기타)는 취식기록의 사번과 맛평가의 Knox ID가 서로 다른 값
체계라, 매핑 없이는 그 인원의 맛평가가 전부 "미평가"로 남는다(에러는 아니고
조용히 매칭만 안 됨).

운영자가 로컬에 매핑 파일을 직접 만들어두면 자동으로 적용된다. **CSV와 xlsx 둘 다
지원**한다(확장자로 자동 판별). 헤더는 "사번"/"knox_id" 두 컬럼이 필수(순서 무관):

```csv
사번,knox_id
12345678,abcd1234
87654321,wxyz9999
```
CSV로 저장할 때 **한글 Windows Excel의 기본 인코딩(CP949)과 UTF-8을 둘 다
자동으로 시도**하므로 대부분 그대로 되지만, 그래도 인코딩 에러
(`UnicodeDecodeError`)가 나면 **xlsx로 저장해서 쓰는 게 가장 확실하다** — 엑셀
파일은 내부적으로 유니코드라 이런 인코딩 문제 자체가 없다.

`config.json`에 그 파일 경로를 지정한다(csv/xlsx 아무 확장자나):
```json
{
  "backend_base_url": "...",
  "api_token": "...",
  "employee_mapping_path": "C:\\매핑\\employee_mapping.xlsx"
}
```
(또는 환경변수 `INGEST_EMPLOYEE_MAPPING_PATH`로도 지정 가능 — `config.json`보다
우선함)

이 파일은 `.gitignore`에 등록돼 있어(`ingestion-tool/employee_mapping.csv`)
저장소 안에 둬도 커밋되지 않는다. 파일이 없거나 경로가 비어 있으면 그냥 매핑 없이
동작한다(A사만 다루는 환경이면 필요 없음). 매핑 로직은 `parsing/
employee_mapping.py`(로드 — csv는 표준 csv 모듈, xlsx는 `io_excel.read_used_range`
재사용), `parsing/merge.py`의 `employee_key()`(적용) 참고.

## 사내 SSL 검사로 업로드가 막힐 때 (SSL certificate verify 에러)

사내망이 프록시/보안 소프트웨어로 트래픽을 가로채면서 자체 인증서를 쓰는 경우,
백엔드 전송 시 `SSL certificate verify` 계열 에러가 날 수 있다. **가장 안전한
해결책은 그 사내 루트 인증서를 Windows/Python 신뢰 저장소에 설치하는 것**이다 —
IT팀에 인증서 파일(.crt/.pem)을 요청하면 된다.

그게 당장 어렵고 IT팀이 검증 비활성화를 승인한 경우에만, `config.json`에
`"verify_ssl": false`를 추가하면 된다:
```json
{
  "backend_base_url": "...",
  "api_token": "...",
  "verify_ssl": false
}
```
(또는 환경변수 `INGEST_VERIFY_SSL=false`) 이 값이 꺼져 있으면 실행할 때마다
"SSL 인증서 검증이 비활성화된 상태" 경고가 출력된다. **사내망 안에서만 통신하는
`backend_base_url`에 한해서만** 이렇게 쓰는 걸 전제로 한다 — 외부 인터넷 주소에는
이 설정을 켜둔 채로 쓰지 않는다.

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
