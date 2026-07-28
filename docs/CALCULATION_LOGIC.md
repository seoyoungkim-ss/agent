# 계산 로직 맵 — 나중에 수정할 때 여기부터 봐야 함

이 문서는 이 저장소를 사내 폐쇄망으로 반입한 뒤(더 이상 이 세션/외부로 파일을 꺼낼 수
없는 환경에서) 로컬 코딩 도구로 계산/분석 로직을 고치려 할 때, **어느 파일의 어느
함수를 건드려야 하는지**를 한 곳에 모아둔 지도다. 각 항목은 (1) 무엇을 계산하는지
(2) 정확한 위치 (3) 관련 상수/설정값이 어디 있는지 (4) 고치면 어디까지 영향이 퍼지는지
(5) 지금 알려진 한계(추정치/휴리스틱 여부)를 담는다.

새 코딩 도구(다른 LLM/사람)가 이 문서만 보고도 맥락 없이 작업을 이어갈 수 있게, 함수
시그니처와 상수 값을 그대로 인용했다 — 코드가 바뀌면 이 문서도 같이 갱신할 것.

---

## 0. 전체 지도 (한눈에 보기)

| 계산 영역 | 핵심 파일 | 상수/설정 위치 | PRD 절 |
|---|---|---|---|
| 평일/휴일 분류 | `app/services/holidays.py` | `app/seed/holidays_2025_2026.py` | 3.1 |
| 맛평가 5점 환산 | `app/models/enums.py` (`TASTE_SCORE_POINTS`) | 고정값(코드 내) | 6.3.1 |
| 표본 수 보정(베이지안) | `app/services/menu_performance.py` (`compute_menu_score`) | `app/config.py` | 6.3.1 |
| 메뉴 빈도 지표 | `app/services/menu_performance.py` (`compute_menu_frequency`) | - | 6.3.2 |
| 식수 하락 원인 진단 | `app/services/menu_performance.py` (`diagnose_headcount_decline`) + `app/services/aggregation.py` (`_trend`) | `aggregation.py` 상단 `_FLAT_TOLERANCE` | 6.3.3 |
| 메뉴 4분면 분류 | `app/services/menu_performance.py` (`classify_menu_quadrant`) + `app/services/aggregation.py` (`aggregate_menu_performance`의 threshold 계산) | - | 6.3.4 |
| 코너별 통계(피크타임 서브속도 포함) | `app/services/aggregation.py` (`aggregate_daily_stats`) | `app/config.py` (`peak_time_start/end`) | 6.2 |
| 개인 취향 벡터 | `app/services/taste_profile.py`, `app/services/food_vector.py` | `food_vector.py` (`FOOD_VECTOR_DIMENSIONS`) | 6.1 |
| 시뮬레이션(what-if) | `app/api/simulation.py` (`what_if`) | 파일 상단 `_WEATHER_MULTIPLIER`, `_HISTORY_WINDOW` | 7.1 |
| 혼잡도(대기시간) 예측 | `app/api/simulation.py` (`congestion_forecast`) | 같은 파일 | 7.2 |
| 월간 VOE 클러스터링 | `app/services/voe_clustering.py` | `max_clusters` 파라미터 | 5.2 / 8 |
| 주간 식단표 파싱(메인/부찬 분리) | `ingestion-tool/parsing/weekly_menu_parser.py` | `split_cell_into_items()` | 2.2 / 9.2 |
| 식당취식정보(POS) 파싱 | `ingestion-tool/parsing/meal_transaction_parser.py` | `_REQUIRED_HEADERS` | 2.1 (실측 스키마) |
| 맛평가 리스트 파싱 | `ingestion-tool/parsing/taste_eval_parser.py` | `_HEADER_NAMES` | 2.1 (실측 스키마) |
| 취식기록 ↔ 맛평가 병합(조인) | `ingestion-tool/parsing/merge.py` | `merge_transactions_with_taste()` | 9.2 |
| 식사구분 어휘 정규화(중식↔점심 등) | `ingestion-tool/models.py` (`MEAL_TYPE_ALIASES`) | 같은 파일 | - |
| 취식 로그 ↔ 메뉴 연결 | `app/api/ingest.py` (`ingest_meal_log`) | - | 6.1/6.3 전제조건 |
| 배치 스케줄 주기 | `app/scheduler.py` | 같은 파일 (cron 표현식) | 9.3 |

---

## 1. 평일 / 주말+공휴일 분류

**파일**: `backend/app/services/holidays.py`

- `is_weekend(date) -> bool`: ISO 요일 6(토)/7(일) 체크
- `HolidayService.is_holiday(date)`: 주말이거나 `holiday_calendar` 테이블에 해당 날짜가 있으면 휴일
- `HolidayService.classify(date) -> DayClassification`: `"평일"` / `"주말+공휴일"` 반환

**건드릴 상황**: 회사 자체 휴무일(창립기념일 등)을 추가하고 싶으면 코드가 아니라
**DB에 행을 추가**하면 된다 (`HolidayCalendar` 모델, `holiday_type=COMPANY_OFF`).
로직 자체를 바꿀 일은 거의 없다.

**⚠️ 알려진 한계**: `backend/app/seed/holidays_2025_2026.py`에 있는 설날/추석/부처님오신날과
그로부터 파생된 대체공휴일 날짜는 제가 계산한 **추정치**다. 파일 맨 위 주석에 어떤 날짜가
불확실한지 표시해뒀다. 사내 반입 전에 공공데이터포털 특일정보나 인사팀 공식 캘린더로
재검증하고, 틀린 값이 있으면 `HOLIDAY_SEED` 리스트에서 해당 튜플만 고치면 된다
(재시딩은 `python -m app.seed.run_seed_holidays` — 이미 있는 날짜는 건너뛰므로, 날짜를
**고치려면** 먼저 DB에서 그 행을 지우거나 직접 UPDATE해야 한다).

---

## 2. 맛평가 5점 환산 + 표본 수 보정 (PRD 6.3.1)

**점수 매핑** — `backend/app/models/enums.py`
```python
TASTE_SCORE_POINTS = {
    TasteScore.DELICIOUS: 5,   # 맛남
    TasteScore.NORMAL: 3,      # 보통
    TasteScore.NEEDS_IMPROVEMENT: 1,  # 개선
}
```
이 매핑 자체를 바꾸면(예: 5/3/1 → 다른 스케일) `menu_performance.py`의 `compute_menu_score`,
`taste_profile.py`, `aggregation.py`의 `aggregate_daily_stats`/`aggregate_menu_performance`
전부 자동으로 새 스케일을 쓴다(다 이 딕셔너리를 참조하므로) — **여기 한 곳만 고치면 된다.**

**베이지안 축소 공식** — `backend/app/services/menu_performance.py::compute_menu_score`
```python
adjusted_score = n/(n+m) * raw_score + m/(n+m) * global_avg_score
```
- `n` = 그 메뉴의 평가 건수
- `m` = 신뢰 기준 평가건수, **`app/config.py`의 `menu_score_shrinkage_m` (기본 20)**
- `global_avg_score`는 호출부(`aggregation.py::aggregate_menu_performance`)에서 그 기간
  전체 로그의 평균으로 계산해서 넘겨준다 (`statistics.fmean(all_scores)`)
- `low_sample_threshold`(기본 10, `app/config.py`)보다 평가 건수가 적으면
  `is_low_sample=True` → 4분면에서 자동으로 "표본부족" 처리됨

**건드릴 상황**:
- `m`, `low_sample_threshold` 값 튜닝 → `backend/.env`에 `MENU_SCORE_SHRINKAGE_M=30` 처럼
  추가하면 됨 (코드 수정 불필요, pydantic-settings가 읽음)
- 보정 공식 자체를 바꾸고 싶으면 → `menu_performance.py`의 `compute_menu_score` 함수만
  수정. 이 함수는 순수 함수라 DB 없이 `backend/tests/test_menu_performance.py`로 바로
  검증 가능 (`test_low_sample_menu_is_pulled_toward_global_average` 등 6개 테스트).

**영향 범위**: 이 값은 `menu_performance_stats.adjusted_score` 컬럼에 저장되고 →
`/api/analysis/menu-performance`, `/api/dashboard/menu-history/{menu_name}` API →
프론트 홈 화면 메뉴 이력 표, 분석 탭 4분면 차트/표에 전부 반영된다.

---

## 3. 메뉴 빈도 지표 (PRD 6.3.2)

**파일**: `backend/app/services/menu_performance.py::compute_menu_frequency`

입력: 등장 날짜 리스트, 총 식수, 평가건수. 등장횟수(`set()`으로 같은 날 중복 제거),
평균 재등장 간격(연속 등장일 차이의 평균), 평가율(`evaluation_count/total_headcount`)을
계산한다. 특별한 상수 없음 — 로직을 바꾸려면 이 함수만.

---

## 4. 식수 하락 원인 진단 (PRD 6.3.3)

**2x2 매트릭스** — `backend/app/services/menu_performance.py::diagnose_headcount_decline`
```
점유율↓ + 만족도↓        → 메뉴 자체 만족도 이슈
점유율↓ + 만족도 유지/상승 → 경쟁 메뉴 대체 가능성
점유율 유지/상승 + 만족도↓ → 잠재 이탈 위험
점유율 유지/상승 + 만족도 유지/상승 → 외부 요인(전체 식수 변동)
```
`TrendDirection`(상승/유지/하락)을 입력받는 순수 함수. **"상승/유지/하락"을 실제로
판정하는 로직**은 별도 파일에 있다:

**추세 판정** — `backend/app/services/aggregation.py::_trend`
```python
_FLAT_TOLERANCE = 0.05  # ±5% 이내 변화는 "유지"로 취급
```
이전 기간 대비 ±5% 안이면 "유지", 그 밖이면 상승/하락. **이 5% 기준을 바꾸고 싶으면
`aggregation.py` 맨 위 `_FLAT_TOLERANCE` 상수 하나만 고치면 된다.**

**호출 경로**: `aggregation.py::diagnose_menu_decline(db, menu_id, recent_period, prior_period)`
→ `/api/analysis/menu-performance/{menu_id}/decline-diagnosis` API. 두 기간 모두
`menu_performance_stats`에 미리 recompute돼 있어야 동작한다(내부에서 DB 재계산 안 하고
저장된 두 행을 비교만 함).

---

## 5. 메뉴 4분면 분류 (PRD 6.3.4)

**분류 자체** — `backend/app/services/menu_performance.py::classify_menu_quadrant`
```python
high_demand = demand >= demand_threshold
high_satisfaction = satisfaction >= satisfaction_threshold
# High+High=인기메뉴, High+Low=개선시급, Low+High=숨은강자, Low+Low=퇴출후보
# evaluation_count < low_sample_threshold 면 무조건 "표본부족"
```

**기준선(threshold) 계산** — `backend/app/services/aggregation.py::aggregate_menu_performance`
안에서 그 기간에 등장한 **모든 메뉴의 중앙값(median)**으로 계산한다:
```python
demand = freq.total_headcount / freq.appearance_count   # 1회 제공당 평균 식수
demand_threshold = statistics.median(demand_values)      # 모든 메뉴의 median
score_threshold = statistics.median(score_values)         # 모든 메뉴의 median
```

**⚠️ 프론트에도 같은 계산이 한 번 더 있음**: `frontend/src/pages/AnalysisPage.tsx`의
`median()` 함수가 4분면 산점도에 점선(기준선)을 그리기 위해 **같은 median 로직을
클라이언트에서 다시 계산**한다. 서버가 이미 계산해서 `quadrant_label`로 저장해주므로
점 색깔 자체는 서버 값을 그대로 쓰지만(`quadrant` 필드), **점선 위치는 프론트가 독자적으로
재계산**한다. 두 로직(서버의 median 계산 vs 프론트의 median 계산)이 다른 방식으로
바뀌면 "점 색깔과 점선 위치가 안 맞는" 상황이 생길 수 있다 — **기준선 계산 방식을 바꾸면
두 군데(`aggregation.py`의 median 부분, `AnalysisPage.tsx`의 `median()` 함수) 모두
고쳐야 함.**

---

## 6. 코너별 통계 · 피크타임 서브속도 (PRD 6.2)

**파일**: `backend/app/services/aggregation.py::aggregate_daily_stats`

- 피크타임 구간: `app/config.py`의 `peak_time_start`(기본 `"11:40:00"`) /
  `peak_time_end`(기본 `"12:00:00"`) — **`.env`에 `PEAK_TIME_START=11:30:00`처럼
  넣으면 코드 수정 없이 바뀐다.**
- 서브속도(분당 처리량) = 피크타임 구간 취식 로그 수 / 구간 분(分)
  ```python
  peak_minutes = (peak_end - peak_start).total_seconds() / 60
  throughput = peak_count / peak_minutes
  ```
- 코너별 평균 만족도는 `TASTE_SCORE_POINTS`로 환산한 원점수 평균(표본 보정 **없음** —
  4분면과 달리 코너 단위 통계는 보정을 적용하지 않는다. 필요하면 여기에도
  `compute_menu_score`류 로직을 적용하도록 확장 가능).

**조식/석식도 같은 피크타임 창을 씀**: 현재 `peak_time_start/end`는 식사구분과 무관하게
전역 값 하나다. 조식/석식 피크타임이 다르면(예: 조식은 8시대) `aggregate_daily_stats`에서
`meal_type`별로 다른 피크 구간을 쓰도록 분기 처리를 추가해야 한다 — 지금은 그 분기가 없다.

---

## 7. 개인 취향 벡터 (PRD 6.1)

**차원 정의** — `backend/app/services/food_vector.py`
```python
FOOD_VECTOR_DIMENSIONS = ["spicy","sweet","salty","sour","oily",
                          "protein","carb","fried","soup_based","vegetable_ratio"]
```
**계산** — `backend/app/services/taste_profile.py::compute_employee_taste_profiles`:
사번별로 그 사람이 먹은 메뉴들의 `food_vector`를 단순 평균(`numpy.mean`).

**⚠️ 가장 중요한 미해결 지점**: `menu_master.food_vector`는 **어디서도 자동으로
채워지지 않는다.** 지금은 전부 `NULL`이라, 이 취향 벡터 기능은 값이 하나도 안 나온다.
매운맛/단백질 등 특성을 메뉴마다 입력하는 화면이나 일괄 업로드 기능이 없다 —
이 값을 채우는 방법(수기 입력 화면 추가, 엑셀 업로드 API 추가, 혹은 사내 LLM으로 메뉴명
보고 자동 태깅하는 배치 추가 등)을 별도로 만들어야 6.1 기능이 실제로 동작한다.
가장 빠른 임시 방법은 `menu_master` 테이블에 직접 SQL로 값을 채우는 것.

`taste_profile.py::cosine_similarity`도 정의만 돼 있고 아직 어떤 API에서도 호출하지
않는다 (추후 "취향 비슷한 사람이 고른 메뉴 추천" 같은 기능에 쓰라고 만들어둔 유틸).

---

## 8. 시뮬레이션(what-if) — 날씨/신메뉴/사내행사 (PRD 7.1)

**파일**: `backend/app/api/simulation.py`

```python
_HISTORY_WINDOW = 8   # 최근 같은 평일/휴일 분류 8회 평균을 baseline으로 사용
_WEATHER_MULTIPLIER = {
    Weather.SUNNY: 1.00,
    Weather.RAIN: 0.90,
    Weather.HEATWAVE: 0.95,
    Weather.COLDWAVE: 0.95,
}
# what_if() 안에서:
if payload.has_company_event: multiplier *= 0.90
if payload.new_menu_corner_id == corner.corner_id: multiplier *= 1.15
predicted = baseline * multiplier
```

**⚠️ 전부 v0 추정치다.** 실제 날씨-식수 상관관계 데이터가 없어서 제가 임의로 넣은
배수다. 이 값들은 실측 데이터가 쌓이면 회귀모델(lightgbm 등)로 교체하는 게 목표라고
코드 주석에도 명시해뒀다 (`note` 필드로 API 응답에도 "v0 휴리스틱"이라고 표시됨).

**튜닝하려면**: `_WEATHER_MULTIPLIER` 딕셔너리 값만 바꾸면 된다. `_HISTORY_WINDOW`(몇 회
평균을 baseline으로 볼지)도 상수 하나. 진짜 회귀모델로 바꾸려면 이 함수(`what_if`) 전체를
갈아엎어야 함 — `daily_corner_stats` 테이블에 이미 날씨/행사 여부를 남기는 컬럼이 없으므로,
모델을 학습하려면 먼저 그 컬럼들을 추가해서 과거 데이터를 태깅해야 한다(현재 스키마엔
날씨 이력이 없음).

---

## 9. 혼잡도(대기시간) 예측 (PRD 7.2)

**파일**: `backend/app/api/simulation.py::congestion_forecast`
```python
expected_wait_minutes = baseline_headcount / avg_throughput  # avg_throughput은 6번의 피크타임 서브속도
```
아주 단순한 나눗셈 휴리스틱. `_HISTORY_WINDOW`(위와 동일, 8회) 평균을 씀. 코너 조합을
바꿔가며 분산 효과를 비교하는 전용 최적화 로직은 아직 없고, 프론트에서 `/what-if`를
여러 시나리오로 반복 호출해서 비교하는 방식으로 v0를 구성했다 (`SimulationPage.tsx` 참고).

---

## 10. 월간 VOE 클러스터링 (PRD 5.2 / 8)

**파일**: `backend/app/services/voe_clustering.py`
- `cluster_monthly_voe(db, period_month, llm_client, max_clusters=5)`: 사내 LLM으로
  코멘트를 임베딩 → `KMeans(n_clusters=min(5, 댓글수))`로 군집화 → 각 군집의 대표 코멘트
  (centroid에 가장 가까운 것) + LLM에게 라벨/키워드 요청(`_summarize_cluster`)
- 클러스터 개수(`max_clusters=5`)는 `run_monthly_voe_clustering`(스케줄러) 호출부나
  함수 시그니처에서 숫자만 바꾸면 됨

**의존성**: `app/services/llm_client.py`의 `InternalLLMClient.embed()` / `chat_complete()`.
사내 LLM 엔드포인트가 OpenAI 호환 `/chat/completions`, `/embeddings` 스펙이 아니면
`llm_client.py`의 요청/응답 파싱 부분을 그 스펙에 맞게 고쳐야 한다 (지금은 OpenAI 포맷을
가정하고 짰음 — PRD 10번 "확인 필요 사항"에도 적어둔 부분).

---

## 11. 주간 식단표 파싱 — 메인/부찬 분리 (PRD 2.2 / 9.2)

**파일**: `ingestion-tool/parsing/weekly_menu_parser.py`

```python
_ITEM_SPLIT_PATTERN = re.compile(r"[\n\r]+|[,/·]")

def split_cell_into_items(raw_text):
    parts = [p.strip() for p in _ITEM_SPLIT_PATTERN.split(raw_text)]
    return [p for p in parts if p]
# 호출부(parse_weekly_menu_grid)에서: 첫 번째 항목=메인, 나머지=부찬
```

**⚠️ 실제 식단표 파일로 검증 안 된 가정이다.** 줄바꿈/쉼표/슬래시/가운뎃점으로 나누고
"첫 항목=메인"이라 가정했는데, 실제 파일의 셀 구조가 다르면(예: 메인이 항상 마지막 줄에
있다거나, 구분자가 다르다거나) 이 함수만 고치면 된다 — `ingestion-tool/tests/
test_weekly_menu_parser.py`에 합성 그리드로 만든 테스트가 있으니, 실제 파일 샘플을
보고 이 테스트 데이터부터 실제 구조로 바꿔서 돌려보는 걸 추천.

**헤더 위치 가정**: `parse_weekly_menu_grid`의 기본 인자
`meal_type_col=0, corner_col=1, first_day_col=2` — 실제 표의 열 순서가 다르면 호출부
(`cli.py`)에서 이 인자들을 넘기도록 고치면 된다.

**병합 셀 forward-fill**: `_forward_fill_column()` — 조/중/석식·코너명 컬럼에서 빈 값을
윗값으로 채우는 로직. 병합 방식이 다른 표(예: 코너명이 병합 안 되고 매 행에 반복 기재됨)면
이 함수를 안 써도 되므로 호출부에서 조건 분기 추가.

---

## 12. 취식기록 ↔ 맛평가 병합 (실측 스키마로 교체됨)

PRD 작성 시점엔 `mealdata.csv` 한 파일에 취식일자/사번/식구분/코너/맛평가/의견이
전부 있다고 가정했었다. **실제로는 두 개의 별도 파일**이고(사용자가 스크린샷으로 확인),
컬럼도 훨씬 많다:

**① 식당취식정보(POS 결제 로그)** — 25개 컬럼. 파서: `ingestion-tool/parsing/
meal_transaction_parser.py::parse_meal_transaction_grid`. 헤더 **이름**으로 컬럼을
찾으므로 열 순서가 바뀌어도 안전하다(`_REQUIRED_HEADERS` 딕셔너리 참고). 핵심 컬럼:
일시, 부문명, 사업장명, 회사, 사원번호, 회사구분(협력사/관계사/…), 급식업체, 식당,
코너, 식구분, 포장구분, **메뉴명(코드성)**, **화면표시명(한글)(실제 표시 이름)**,
영수증번호, 구분(정상 등), 정정여부.

⚠️ **협력사 직원은 사원번호가 빈 값인 실제 사례가 있었다** (스크린샷의 이철*/김입*/
천명* — 회사구분=협력사, 사원번호 공란. 관계사인 박휘*만 사원번호=14131244로 채워져
있었음). `parse_meal_transaction_grid`는 사원번호가 없는 행을 **건너뛴다**
(`if not employee_id: continue`) — 즉 협력사 인력의 취식은 지금 구조로는 개인 단위
분석(6.1)에서 빠진다. 이게 의도된 정책인지, 협력사도 다른 식별자로 잡아야 하는지는
확인이 더 필요하다.

**② 맛평가 리스트** — `N0, 취식일자, Knox ID, 식사구분, 평가, 메뉴명, 의견, 평가의견,
IF 생성 날짜, IF 수정 날짜`. 파서: `ingestion-tool/parsing/taste_eval_parser.py`.
`취식일자`엔 **시간 정보가 없다**(날짜만). `의견`/`평가의견` 두 컬럼 중 값이 있는 걸
합쳐서 `comment`로 쓴다(`" / "`로 연결, `_summarize` 아님 — 둘 다 있으면 둘 다 남김).

**③ 병합** — `ingestion-tool/parsing/merge.py::merge_transactions_with_taste`.
조인 키는 `(사번, 취식 날짜, 식사구분, 메뉴명)` 4개 조합. 코너는 맛평가 쪽에 아예
없어서 조인 키에 못 쓴다.

```python
def employee_key(transaction_employee_id: str) -> str:
    return transaction_employee_id.strip()   # ⚠️ 아래 가정 참고
```

**가정 확인 현황** (merge.py 맨 위 docstring에도 적어둠):
1. ✅ **확인됨 (사용자, 2026-07-28)**: 맛평가의 Knox ID와 취식기록의 사원번호가
   문자열 그대로 매칭되는 건 **A사 인원뿐**이다. B/C/D사·기타 인원은 애초에 두 ID
   체계가 다르므로, 그 인원의 취식 행이 맛평가와 매칭 안 되고 "미평가"로 남는 건
   **버그가 아니라 현재 구조상 당연한 결과**다. A사 외 인원도 매칭하려면 별도 ID
   매핑 수단이 확보돼야 하고, 그때 `employee_key()`에 회사구분별 분기를 추가하면 된다.
2. ⚠️ **아직 미확인**: 메뉴명 매칭은 "화면표시명(한글)" 기준이다(코드성 메뉴명이
   아니라). 두 값이 실제로도 문자열이 정확히 같은지(공백, 표기 차이 등) 실물
   데이터로 검증 필요.
3. ⚠️ **아직 미확인**: 식사구분 어휘가 다르다 — 취식기록 "중식", 맛평가 "점심".
   `models.py`의 `MEAL_TYPE_ALIASES` 딕셔너리에서 정규화하므로, 다른 표기(예: "런치")가
   또 나오면 여기에 한 줄만 추가하면 된다.

**status 필터**: `merge_transactions_with_taste(..., only_normal_status=True)` 기본값이
`구분 != "정상"`인 행을 제외한다. "정상" 외에 어떤 값들이 있는지(취소/환불 등) 아직
확인 못 했다 — 실제 파일 받으면 `구분` 컬럼의 고유값 목록부터 확인해서 이 필터 조건을
맞게 조정할 것.

**직접 실행해서 검증하는 법**: `ingestion-tool/sample_data/`에 사용자가 보내준 실제
스크린샷 샘플을 그대로 재현한 xlsx 2개(`sample_transactions.xlsx`,
`sample_taste_eval.xlsx`)와 그걸 파싱+병합해서 결과를 출력하는 `demo_merge.py`가
있다. 이 합성 파일은 DRM이 없어서 xlwings/Excel 없이도 (openpyxl로) 바로 돌려볼 수
있다:
```bash
cd ingestion-tool && source .venv/bin/activate
python sample_data/demo_merge.py
```
실제 파일을 받으면 이 스크립트의 `read_grid()`를 실제 파일 경로로 바꿔서 그대로
재사용하면 된다 — 파싱/병합 로직 자체는 안 건드려도 됨.

**백엔드 연결**: `menu_name`이 있으면(위 파이프라인은 항상 채워서 보낸다)
`backend/app/api/ingest.py::ingest_meal_log`가 그 이름으로 바로
`menu_master`를 조회/생성해서 연결한다 — 예전의 "코너의 그날 메인 메뉴 하나로
추정" 방식보다 훨씬 정확하다. `menu_name`이 없는 경우(과거 방식 호환용)에만 예전
추정 로직으로 폴백한다.

---

## 13. 배치 스케줄 (언제 재계산되는지)

**파일**: `backend/app/scheduler.py`
```python
scheduler.add_job(run_daily_batch, "cron", hour=2, minute=0, ...)       # 매일 새벽 2시
scheduler.add_job(run_monthly_voe_clustering, "cron", day=1, hour=3, minute=0, ...)  # 매월 1일 새벽 3시
```
`run_daily_batch`가 하는 일 3가지(`aggregation.py`, `taste_profile.py` 호출):
1. `aggregate_daily_stats(어제)` — 코너/구분별 일일 통계
2. `aggregate_menu_performance(어제-180일, 어제)` — **6개월 롤링 윈도우**로 메뉴 성과 재계산
   (`MENU_PERFORMANCE_WINDOW_DAYS = 180`, `scheduler.py` 상단)
3. `compute_employee_taste_profiles()` — 취향 벡터 재계산

시간/주기를 바꾸려면 `add_job`의 `hour`/`minute`/`day` 인자만. 6개월 윈도우를 바꾸려면
`MENU_PERFORMANCE_WINDOW_DAYS` 상수.

---

## 14. 수정 후 검증 방법 (테스트 위치)

로직을 고쳤으면 관련 테스트부터 돌려서 확인할 것. 전부 DB 없이/실 DB로 돌아가게 구성돼
있음(`backend/tests/conftest.py`가 `cafeteria_test` DB를 자동으로 만들고 정리함).

| 고친 파일 | 돌려볼 테스트 |
|---|---|
| `menu_performance.py` (점수/빈도/진단/4분면) | `backend/tests/test_menu_performance.py` (21개) |
| `holidays.py` / 휴일 시드 | `backend/tests/test_holidays.py` (6개) |
| `ingest.py`, `aggregation.py`, API 전반 | `backend/tests/test_api_ingest_and_analysis.py` (37개 중 나머지, 실제 DB에 데이터 넣고 API 호출까지 검증) |
| `weekly_menu_parser.py` | `ingestion-tool/tests/test_weekly_menu_parser.py` (9개) |
| `meal_transaction_parser.py` | `ingestion-tool/tests/test_meal_transaction_parser.py` (7개) |
| `taste_eval_parser.py` | `ingestion-tool/tests/test_taste_eval_parser.py` (5개) |
| `merge.py` (조인 로직) | `ingestion-tool/tests/test_merge.py` (7개) |

```bash
cd backend && source .venv/bin/activate && pytest -q
cd ingestion-tool && source .venv/bin/activate && pytest -q
python sample_data/demo_merge.py   # 실물과 비슷한 합성 파일로 전체 파이프라인 눈으로 확인
```

새 계산 로직을 추가하면(예: food_vector 자동 태깅 배치), 반드시 같은 패턴으로
(1) 순수 함수로 분리 (2) `tests/`에 단위테스트 추가를 지켜서 다음 사람이 또 이 문서
없이도 안전하게 고칠 수 있게 해두는 걸 권장한다.
