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
| 메뉴 food_vector 자동 태깅(규칙→LLM→관리자수동) | `app/services/food_vector_tagging.py` | `_KEYWORD_RULES`(같은 파일) | 6.1 |
| 코너 코어층 × 메뉴 동반 선택 쌍 비교 | `app/services/corner_core_layer.py`, `app/services/menu_affinity.py`(`compute_top_menu_pairs`) | `min_visit_count`/`min_share`/`min_co_count`(API 파라미터) | 6.2 |
| 취향 군집(K-means) + 자동 라벨링 | `app/services/taste_clustering.py` | `DEFAULT_TASTE_CLUSTER_K`(`scheduler.py`), `_LABEL_DEVIATION_THRESHOLD`(같은 파일) | 6.1 |
| 메뉴 동반 선택 경향성(lift) | `app/services/menu_affinity.py` | `min_co_count` 파라미터 | 6.1 |
| 시뮬레이션(what-if) | `app/api/simulation.py` (`what_if`) | 파일 상단 `_WEATHER_MULTIPLIER`, `_HISTORY_WINDOW` | 7.1 |
| 혼잡도(대기시간) 예측 | `app/api/simulation.py` (`congestion_forecast`) | 같은 파일 | 7.2 |
| 월간 VOE 클러스터링 | `app/services/voe_clustering.py` | `max_clusters` 파라미터 | 5.2 / 8 |
| 주간 식단표 파싱(메인/부찬 분리) | `ingestion-tool/parsing/weekly_menu_parser.py` | `split_cell_into_items()` | 2.2 / 9.2 |
| 식당취식정보(POS) 파싱 | `ingestion-tool/parsing/meal_transaction_parser.py` | `_REQUIRED_HEADERS` | 2.1 (실측 스키마) |
| 맛평가 리스트 파싱 | `ingestion-tool/parsing/taste_eval_parser.py` | `_HEADER_NAMES` | 2.1 (실측 스키마) |
| 취식기록 ↔ 맛평가 병합(조인) | `ingestion-tool/parsing/merge.py` | `merge_transactions_with_taste()` | 9.2 |
| 식사구분 어휘 정규화(중식↔점심 등) | `ingestion-tool/models.py` (`MEAL_TYPE_ALIASES`) | 같은 파일 | - |
| 취식 로그 ↔ 메뉴 연결 | `app/api/ingest.py` (`ingest_meal_log`) | - | 6.1/6.3 전제조건 |
| 본사/계열사/기타 분류 | `app/services/company_classification.py` (`classify_division`) | `COMPANY_DIVISION_MAP` (같은 파일) | 6.1 |
| 배치 스케줄 주기 | `app/scheduler.py` | 같은 파일 (cron 표현식) | 9.3 |
| 전체 취식 데이터 원본 엑셀 다운로드(기간 선택) | `app/api/dashboard.py` (`meal_log_export`) | - (순수 조회, 계산 없음) | - |
| 월간 VOE 고정 분류(맛/간/위생/서비스) | `app/services/voe_category.py` | `_CATEGORY_KEYWORDS`(같은 파일), `VOE_CATEGORIES` | 5.2/5.3 |
| 코너별 식수 요약(홈 화면) | `app/api/analysis.py` (`corner_analysis` 재사용) | - (신규 계산 없음) | - |

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
사번별로 그 사람이 먹은 메뉴들의 `food_vector`를 단순 평균(`numpy.mean`). 이 필터는
`MenuMaster.food_vector.isnot(None)`이므로, **아직 태깅 안 된(NULL) 메뉴는 자동으로
제외**된다(에러 없이 조용히 빠짐 — 태깅 진행 상황을 확인하려면 아래 목록 API를 본다).

**`food_vector`는 어떻게 채워지는가 — 3단계 태깅 파이프라인 (PRD 6.1)**:
파일: `backend/app/services/food_vector_tagging.py`, 연동: `backend/app/services/master_data.py::get_or_create_menu`

1. **규칙 기반(즉시, 신메뉴 인입 시)** — `tag_food_vector_from_name(menu_name)`이
   메뉴명에 포함된 키워드(`_KEYWORD_RULES` 딕셔너리, 예: "매운"→spicy, "국/탕/찌개"→
   soup_based)로 10차원 벡터를 만든다. 키워드가 하나라도 걸리면(`matched_any=True`)
   `food_vector`를 채우고 `food_vector_source="규칙기반"`으로 표시한다. 하나도 안
   걸리면 `food_vector`를 `NULL`로 남겨 2·3단계를 기다린다.
   **튜닝 지점**: `_KEYWORD_RULES` 딕셔너리에 키워드만 추가/수정하면 됨.
2. **LLM 보강(관리자 트리거)** — `POST /api/analysis/menus/tag-with-llm`을 호출하면
   `run_llm_food_vector_tagging()`이 `food_vector IS NULL`인 메뉴만 골라 사내 LLM에게
   "이 메뉴의 매운맛/단맛/...을 0~1로 평가해줘" 프롬프트를 보내고, 응답을
   `_parse_llm_vector_response()`로 파싱해 채운다(성공 시 `food_vector_source="LLM추정"`).
   응답 형식이 깨지거나 10개 차원이 다 안 나오면 그 메뉴는 건너뛰고 다음 배치 때 재시도.
   사내 LLM 미설정 환경(로컬 개발)에서는 `InternalLLMClient`의 모의 응답이 이 형식으로
   파싱되지 않으므로 실제로는 0건 태깅됨 — 배선만 검증됨.
3. **관리자 수동 조정(언제든 가능)** — `PUT /api/analysis/menus/{menu_id}/food-vector`
   (프론트: `AnalysisPage.tsx`의 `MenuFoodVectorAdminSection`, 메뉴 4분면 탭 하단)로
   10개 값(0.0~1.0)을 직접 입력하면 `food_vector_source="MANUAL"`(관리자수동)로
   잠긴다. 1·2단계 배치는 둘 다 `food_vector IS NULL`인 메뉴만 대상으로 하므로,
   한 번이라도 값이 채워진 메뉴(수동이든 규칙/LLM이든)는 자동으로 재태깅 대상에서
   빠진다 — 별도의 "잠금 확인" 로직이 없어도 이 필터 하나로 보호됨.
   목록 조회는 `GET /api/analysis/menus/food-vectors?untagged_only=`.

`taste_profile.py::cosine_similarity`도 정의만 돼 있고 아직 어떤 API에서도 호출하지
않는다 (추후 "취향 비슷한 사람이 고른 메뉴 추천" 같은 기능에 쓰라고 만들어둔 유틸).

**테스트**: `backend/tests/test_food_vector_tagging.py`(순수 함수, 5개),
`test_api_ingest_and_analysis.py`의 `test_menu_food_vector_auto_tagged_by_rule_on_ingest`,
`test_menu_food_vector_stays_untagged_when_no_rule_matches`,
`test_list_menu_food_vectors_endpoint`, `test_update_menu_food_vector_manual_override`,
`test_tag_menus_with_llm_leaves_untagged_when_llm_unconfigured`.

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
def employee_key(transaction_employee_id: str, mapping: dict[str, str] | None = None) -> str:
    employee_id = transaction_employee_id.strip()
    if mapping and employee_id in mapping:
        return mapping[employee_id]
    return employee_id
```

**가정 확인 현황** (merge.py 맨 위 docstring에도 적어둠):
1. ✅ **확인됨 (사용자, 2026-07-28) + 매핑 기능 추가 (2026-07-29)**: 맛평가의
   Knox ID와 취식기록의 사원번호가 문자열 그대로 매칭되는 건 **A사 인원뿐**이다.
   B/C/D사·기타 인원은 애초에 두 ID 체계가 다르므로, 매핑 없이는 그 인원의 취식
   행이 맛평가와 매칭 안 되고 "미평가"로 남는다(버그 아님).
   운영자가 실제로 사번↔Knox ID 매핑을 로컬 CSV로 관리하기로 하면서, 이를 위한
   경로가 새로 생겼다:
   - **파일**: `ingestion-tool/parsing/employee_mapping.py::load_employee_mapping(path)` —
     `{사번: knox_id, ...}`를 반환. 확장자로 csv/엑셀을 자동 판별한다:
     - `.csv`는 표준 `csv` 모듈로 직접 읽는다. **UTF-8과 CP949(한글 Windows
       Excel의 CSV 저장 기본 인코딩)를 순서대로 시도**하고 — Excel에서 CSV로
       저장하면 UTF-8이 아니라 CP949가 기본값이라 `UnicodeDecodeError`가 나기
       쉬웠던 문제(2026-07-29 실사용 중 발견)를 이렇게 해결했다. 둘 다 실패하면
       "xlsx로 저장해보라"는 안내와 함께 `RuntimeError`.
     - `.xlsx`/`.xls`는 `io_excel.read_used_range()`(xlwings)로 그리드를 읽은
       뒤 `_parse_mapping_grid()`(순수 함수, 헤더 이름으로 컬럼 찾음)로 파싱한다.
       엑셀은 내부적으로 유니코드라 인코딩 문제 자체가 없어, CSV 인코딩이 계속
       말썽이면 이 형식을 권장한다. 엑셀이 순수 숫자 사번/Knox ID를
       `12345678.0`처럼 float로 자동 변환해 넘기는 경우도 `_clean_cell()`에서
       정수 문자열로 되돌려 처리한다.
     - 경로가 비었거나 파일이 없으면 빈 dict(매핑 미사용, 에러 아님).
   - **설정**: `config.json`의 `employee_mapping_path` (csv/xlsx 아무 확장자,
     또는 환경변수 `INGEST_EMPLOYEE_MAPPING_PATH`) — `ingestion-tool/
     config.py::ToolConfig`.
   - **적용**: `cli.py`의 `_cmd_meal_log`가 `load_employee_mapping()`으로 읽은
     dict를 `merge_transactions_with_taste(..., employee_mapping=mapping)`에
     넘기고, `employee_key()`가 사번을 매핑에서 찾으면 knox_id로 치환해서 비교한다.
     매핑에 없는 사번(A사 등)은 원래대로 사번 그대로 비교하므로 기존 A사 동작은
     안 바뀐다.
   - **테스트**: `ingestion-tool/tests/test_employee_mapping.py`(CSV
     UTF-8/CP949/BOM/공백/빈값/디코딩실패, xlsx 그리드 파싱 — 헤더 순서 무관,
     엑셀 float 자동변환, 헤더 없음), `test_merge.py`의
     `test_employee_mapping_resolves_mismatched_ids`,
     `test_employee_mapping_missing_entry_falls_back_to_employee_id`.
2. ⚠️ **아직 미확인**: 메뉴명 매칭은 "화면표시명(한글)" 기준이다(코드성 메뉴명이
   아니라). 두 값이 실제로도 문자열이 정확히 같은지(공백, 표기 차이 등) 실물
   데이터로 검증 필요.
3. ⚠️ **아직 미확인**: 식사구분 어휘가 다르다 — 취식기록 "중식", 맛평가 "점심".
   `models.py`의 `MEAL_TYPE_ALIASES` 딕셔너리에서 정규화하므로, 다른 표기(예: "런치")가
   또 나오면 여기에 한 줄만 추가하면 된다.
4. ✅ **확인 및 수정됨 (2026-07-29, 실사용 중 발견)**: 매핑 파일을 정상 로드해도
   맛평가 매칭률이 0%였던 문제 — 원인은 `meal_transaction_parser.py`/
   `taste_eval_parser.py`의 `_clean()`이 엑셀의 숫자 자동인식을 처리 안 해서였다.
   사원번호/Knox ID처럼 순수 숫자 값을 엑셀이 자동으로 숫자로 인식하면 셀 값이
   `"12345678"`이 아니라 `12345678.0`(float)로 넘어오는데, 그대로 문자열화하면
   `"12345678.0"`이 돼서 텍스트로 저장된 다른 쪽 파일의 `"12345678"`과 달라져
   조인 키가 영구히 안 맞았다(화면상으로는 둘 다 "12345678"로 보여서 육안으로는
   못 잡음). `employee_mapping.py`의 `_clean_cell()`(같은 문제를 매핑 파일 쪽에서
   먼저 발견해 고쳤던 것)과 동일하게, 정수값 float이면 `str(int(value))`로
   변환하도록 두 파서의 `_clean()`을 고쳤다. **사원번호/Knox ID뿐 아니라 `_clean()`을
   거치는 모든 필드에 적용**되므로 비슷한 숫자형 컬럼이 또 있어도 안전하다.
   테스트: `test_meal_transaction_parser.py::
   test_numeric_employee_id_from_excel_autoformat_not_left_with_decimal`,
   `test_taste_eval_parser.py::
   test_numeric_knox_id_from_excel_autoformat_not_left_with_decimal`.

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
| `taste_clustering.py` (군집/라벨링) | `backend/tests/test_taste_clustering.py` (6개, 순수 함수) |
| `menu_affinity.py` (동반 선택 lift) | `backend/tests/test_menu_affinity.py` (8개, 순수 함수) |

```bash
cd backend && source .venv/bin/activate && pytest -q
cd ingestion-tool && source .venv/bin/activate && pytest -q
python sample_data/demo_merge.py   # 실물과 비슷한 합성 파일로 전체 파이프라인 눈으로 확인
```

새 계산 로직을 추가하면(예: food_vector 자동 태깅 배치), 반드시 같은 패턴으로
(1) 순수 함수로 분리 (2) `tests/`에 단위테스트 추가를 지켜서 다음 사람이 또 이 문서
없이도 안전하게 고칠 수 있게 해두는 걸 권장한다.

---

## 15. 본사/계열사/기타 분류 (PRD 6.1)

**확정된 규칙** (사용자, 2026-07-28): 취식기록의 "회사" 원문 기준으로
- `삼성전자` → 본사
- `삼성SDI`, `삼성에스원`, `삼성SDS` → 계열사
- 그 외 전부(지리산, 제일원, (주)아이원 등) → 기타

**파일**: `backend/app/services/company_classification.py`
```python
COMPANY_DIVISION_MAP: dict[str, Division] = {
    "삼성전자": Division.HEADQUARTERS,
    "삼성SDI": Division.AFFILIATE,
    "삼성에스원": Division.AFFILIATE,
    "삼성SDS": Division.AFFILIATE,
}
def classify_division(company_name): ...  # 없으면 기타
```
**분류 매핑을 바꾸려면 이 딕셔너리만 고치면 된다** — ingestion-tool(운영자 PC)은
원문 회사명만 그대로 실어 보내고 분류는 백엔드가 하므로, 매핑이 바뀌어도 운영자
PC의 실행 파일을 다시 배포할 필요가 없다.

**중요**: 계열사(B/C/D)라도 화면에는 "계열사"라는 라벨이 아니라 **실제 회사명을
그대로 보여줘야 한다**(사용자 요구사항). 이를 위해 `employee_master`에
`division`(집계용 대분류)과 `company_name`(원문, 표시용) 두 컬럼을 같이 저장한다
— 계열사 집계는 `division`으로 묶어서 보되, 개별 표시가 필요한 화면에서는
`company_name`을 쓰면 된다.

**PRD 6.1 "본사/계열사/기타 구분 일간/주간/월간 식수" 화면 (완료)**: `GET
/api/analysis/divisions?period_start&period_end&granularity=daily|weekly|monthly
&classification=평일|주말+공휴일`(`app/api/analysis.py::division_analysis`)이
`daily_division_stats`를 기간 버킷(일/주/월)별로 묶어서 반환한다. 주간 버킷은
그 주의 월요일 날짜, 월간은 `YYYY-MM`을 라벨로 쓴다(`_period_bucket()`). 프론트는
`frontend/src/pages/AnalysisPage.tsx`의 `DivisionAnalysisSection`(분석 탭 →
사용자 분석 서브탭 맨 위)이 본사/계열사/기타를 각각 categorical 색상(series-1/2/3,
고정 순서)의 막대로 그린다.

**데이터 흐름**: `ingestion-tool/models.py`의 `ParsedMealLogRow.company_name`
(취식기록의 "회사" 원문) → `merge.py`가 그대로 옮김 → `upload.py`가 JSON에 포함 →
`backend/app/schemas/ingest.py`의 `MealLogRowIn.company_name` → `app/services/
master_data.py::get_or_create_employee(db, employee_id, company_name)`이 매번
최신 값으로 `division`/`company_name`을 갱신.

**테스트**: `backend/tests/test_company_classification.py`(5개, 순수 함수),
`backend/tests/test_api_ingest_and_analysis.py::
test_meal_log_ingest_classifies_division_from_company_name`(API 엔드투엔드로
실제 DB에 반영되는지 확인).

---

## 16. 취향 군집 + 메뉴 동반 선택 경향성 (PRD 6.1, 사번 검색 없이 전체 경향 보기)

사번 1건씩 조회하는 것만으로는 "사람들 취향에 전체적으로 어떤 경향이 있는지" 알 수
없다는 문제의식에서, 개인 취향 벡터(6.1)를 기반으로 두 가지를 추가했다 —
① 비슷한 취향끼리 그룹으로 묶어 요약하는 **군집(clustering)**, ② 특정 메뉴를 먹는
사람이 다른 어떤 메뉴도 잘 먹는지 보는 **동반 선택 경향성(co-occurrence)**. PRD 6.1의
"떡볶이 먹는 사람은 짜장면도 잘 먹는다" 예시는 사실 ①(취향 벡터의 평균적 유사성)
보다 ②(실제 메뉴 조합의 통계적 연관성)로 더 직접 확인된다.

### 16.1 취향 군집 (K-means + 규칙 기반 라벨링)

**파일**: `backend/app/services/taste_clustering.py`

```python
def cluster_vectors(vectors, k) -> ClusteringResult:  # sklearn KMeans 얇은 래퍼, 순수 함수
def generate_cluster_label(centroid, global_mean, ...) -> str:  # 규칙 기반 라벨링, 순수 함수
def compute_taste_clusters(db, k=5, min_total_employees=None) -> int:  # DB 오케스트레이션
```

- **군집화**: `employee_taste_profile.profile_vector`(전체) 를 `sklearn.cluster.KMeans`로
  `k`개(기본 5, `scheduler.py`의 `DEFAULT_TASTE_CLUSTER_K`)로 나눈다.
- **라벨링**: VOE 클러스터링(월간, 자유 텍스트)과 달리 food_vector는 이미 구조화된
  수치라 **사내 LLM 없이 결정론적 규칙으로 라벨을 만든다** — 그 그룹의 centroid가
  전체 평균보다 `_LABEL_DEVIATION_THRESHOLD`(기본 0.12, 0~1 스케일 기준) 이상 튀는
  차원을 최대 `_LABEL_MAX_DIMENSIONS`(기본 2)개 뽑아 "매운맛·단백질 선호형"처럼
  합성한다. 튀는 차원이 없으면 "균형형". **라벨 스타일을 바꾸려면 이 두 상수와
  `FOOD_VECTOR_LABELS_KO`(`food_vector.py`, 차원 영문↔한글 매핑)만 고치면 된다.**
- **군집별 부가 정보**: 그 군집에 속한 사번들의 `meal_log`를 다시 조회해서 대표
  메뉴 top5(`Counter`), 주 이용 코너(최빈값), 평균 만족도(`TASTE_SCORE_POINTS` 평균)를
  같이 저장한다 — 표본 보정(6.3.1)은 적용하지 않은 단순 평균이다.
- **표본 부족 가드**: 전체 프로필 수가 `min_total_employees`(기본 `k*2`) 미만이면
  아무것도 안 하고 0을 반환한다 (`/api/analysis/users/taste-clusters/recompute`는
  이때 400을 응답).
- **재계산 시 기존 결과 정리**: `employee_taste_profile.cluster_id`를 먼저 전부
  NULL로 돌린 뒤 `taste_cluster` 테이블을 지우고 다시 쓴다 — monthly_voe_cluster와
  같은 "매번 통째로 다시 쓰기" 패턴.
- **배치**: 매월 1일 03:30(`scheduler.py::run_monthly_taste_clustering`). VOE
  클러스터링(03:00)과 30분 간격을 둔 것뿐, 서로 의존관계는 없다.
- **API**: `GET /api/analysis/users/taste-clusters`(목록), `POST .../recompute?k=5`,
  그리고 개인 조회(`GET .../users/{employee_id}/taste-profile`)에도
  `cluster_label` 필드가 같이 내려간다.
- **프론트**: `frontend/src/pages/AnalysisPage.tsx`의 `TasteClusterSection` — 군집×
  차원(10개) 히트맵(시퀀셜 blue, `SEQUENTIAL_BLUE_RAMP`) + 표. 사용자 분석 서브탭
  맨 위(구분별 식수 아래, 개인 검색 위)에 있다.

**⚠️ pgvector 응답 타입 주의**: `TasteCluster.centroid_vector`/`EmployeeTasteProfile.
profile_vector`를 API로 내려줄 때 `list(...)`만 쓰면 원소가 `numpy.float32`로 남아
FastAPI JSON 인코딩이 깨진다(실제로 이 기능 만들다가 걸림 — `test_taste_clusters_
recompute_and_list` 테스트로 잡음). 반드시 `[float(x) for x in vector]`로 순수
파이썬 float으로 변환할 것 (`app/api/analysis.py` 두 곳 참고).

### 16.2 메뉴 동반 선택 경향성 (lift)

**파일**: `backend/app/services/menu_affinity.py`

```python
def compute_menu_affinity(employee_menus: dict[str, set[str]], target_menu, min_co_count=3, top_n=10) -> list[MenuAffinityResult]
def build_employee_menu_sets(db, period_start, period_end) -> dict[str, set[str]]
```

- 장바구니 분석(market-basket analysis)의 **lift** 지표를 그대로 쓴다:
  `lift(A,B) = co_count(A,B) * total_employees / (count(A) * count(B))`.
  1보다 크면 "우연보다 자주 같이 나옴", 1에 가까우면 무관, 1보다 작으면 오히려
  같이 잘 안 나옴.
- `build_employee_menu_sets`는 사번별로 그 기간에 **먹어본 메뉴명의 집합**을
  만든다(빈도 무시, 존재 여부만) — `compute_menu_affinity`는 이 집합만 있으면
  DB 없이도 순수 함수로 테스트 가능.
- `min_co_count`(기본 3)로 표본이 너무 적은 우연한 쌍을 걸러낸다.
- **API**: `GET /api/analysis/menu-affinity/{menu_name}?period_start&period_end
  &min_co_count&top_n` — 대상 메뉴를 아무도 안 먹었으면 404.
- **프론트**: `AnalysisPage.tsx`의 `MenuAffinitySection` — 메뉴 4분면 탭 하단에
  검색창 + 표(동반 인원, lift).

**튜닝 지점**: `min_co_count`를 올리면 결과가 더 보수적(확실한 연관만)이 되고,
`top_n`은 화면에 몇 개 보여줄지. lift 계산식 자체를 바꿀 일은 거의 없겠지만,
바꾸려면 `compute_menu_affinity` 하나만 고치면 됨(호출부는 결과 리스트 형태만 안다).

**테스트**: `backend/tests/test_taste_clustering.py`(6개), `backend/tests/
test_menu_affinity.py`(8개) — 둘 다 순수 함수라 DB 없이 빠르게 검증 가능.
API 엔드투엔드는 `test_api_ingest_and_analysis.py::
test_taste_clusters_recompute_and_list`, `::test_menu_affinity_finds_co_occurring_menu`.

## 17. 전체 취식 데이터 원본 엑셀 다운로드 (기간 선택)

**파일**: `backend/app/api/dashboard.py`의 `meal_log_export()`

- 집계/가공 없이 `meal_log`를 `employee_master`(구분·회사명) + `corner_master`
  + `menu_master`(메뉴 없으면 outer join)와 그대로 조인해 행 단위로 xlsx에 쓴다.
  계산 로직이 아니라 순수 조회+포맷이라 튜닝 지점은 없음.
- 기간 필터는 `[period_start, period_end]`를 **양끝 포함**으로 해석: 내부적으로는
  `period_end + 1일`을 배타적 상한으로 써서(`eaten_at < period_end+1일 00:00`)
  `eaten_at`에 시각이 있어도 종료일 하루 전체가 포함되게 한다. 다른 기간 필터들
  (`aggregation.py`, `menu_affinity.py` 등)도 같은 패턴을 쓰므로 여기만 다르게
  바꾸면 일관성이 깨진다.
- **API**: `GET /api/dashboard/meal-log/export?period_start&period_end` →
  `취식일시·사번·구분·회사명·식사구분·코너·메뉴·맛평가·의견` 9개 컬럼 xlsx.
- **프론트**: `HomePage.tsx`의 "전체 취식 데이터 다운로드 (기간 선택)" 카드 —
  시작일/종료일 `<input type="date">` 두 개 + 다운로드 버튼(다른 export와 동일하게
  `<a href=... download>` 패턴, 별도 fetch 코드 없음).
- **테스트**: `test_api_ingest_and_analysis.py::
  test_meal_log_export_returns_xlsx_for_selected_period` — xlsx를 openpyxl로 다시
  읽어 헤더/행수/기간 밖 데이터 제외를 검증(테스트 전용 의존성이므로 `openpyxl`은
  `requirements-dev.txt`에만 있고 운영 `requirements.txt`에는 없음 — 운영에는
  xlsxwriter로 "쓰기"만 하면 되므로 필요 없음).

## 18. 코너 코어층 × 메뉴 동반 선택 쌍 비교 (PRD 6.2)

PRD 6.2 원문에 "코너별 코어층 분석 (해당 코너를 반복적으로 선택하는 사번 그룹의
특성)"이라고만 정의돼 있고 실제 구현은 없던 항목이다. "가장 흔한 취향(메뉴) pair를
코어층 분류랑 엮어서 확인"하고 싶다는 요청에 맞춰, 이번에 코어층 정의와 전체 메뉴
쌍 랭킹을 함께 구현했다.

### 18.1 코어층 분류

**파일**: `backend/app/services/corner_core_layer.py`

```python
def classify_corner_core_layer(
    employee_corner_counts: dict[str, dict[int, int]],  # {사번: {corner_id: 방문횟수}}
    corner_id: int,
    *,
    min_visit_count: int = 3,
    min_share: float = 0.3,
) -> list[CoreLayerResult]
def build_employee_corner_counts(db, period_start, period_end) -> dict[str, dict[int, int]]
```

- 어떤 코너의 코어층 = (a) 그 코너 방문 횟수 ≥ `min_visit_count` **그리고** (b) 그
  코너가 그 사람 전체 방문 중 차지하는 비중(`corner_share`) ≥ `min_share`를 **모두**
  만족하는 사번. AND 조건인 이유: 방문횟수만 보면 "여기저기 다 자주 가는
  헤비유저"가 모든 코너의 코어층으로 잘못 잡히고, 비중만 보면 표본이 아주 적은
  사람(1번 방문해서 그게 100%)이 섞여 들어온다.
- `build_employee_corner_counts`는 기간 내 `meal_log`를 사번×코너별로 카운트만
  한다(메뉴는 안 봄) — `menu_affinity.py::build_employee_menu_sets`와 동일한
  `[period_start, period_end+1일 배타적상한]` 기간 필터 패턴을 그대로 따른다.

### 18.2 전체 메뉴 쌍 랭킹 (대상 메뉴 고정 없이)

**파일**: `backend/app/services/menu_affinity.py`의 `compute_top_menu_pairs`

```python
def compute_top_menu_pairs(
    employee_menus: dict[str, set[str]], *, min_co_count: int = 2, top_n: int = 10
) -> list[MenuPairResult]
```

- 기존 `compute_menu_affinity`는 대상 메뉴 하나를 지정해야만 그 메뉴와 동반되는
  메뉴 목록을 볼 수 있다. 이 함수는 대상 메뉴 없이 **가장 흔한 메뉴 쌍 자체의
  전체 랭킹**을 낸다(사번별 메뉴 집합에서 `itertools.combinations`로 모든 쌍을
  세는 market-basket 방식).
- **정렬 기준이 기존 함수와 다름**: `co_count`(동반 인원 수) 내림차순이 1차,
  `lift`는 2차/참고용. "가장 흔한"이라는 표현 그대로 co_count를 우선한 것 —
  lift를 1차로 쓰면 표본 1~2명짜리 우연한 조합이 최상위로 튀어나올 수 있다.
- `min_co_count` 기본값도 `compute_menu_affinity`(3)와 다르게 2로 낮췄다 — 이
  함수는 코어층처럼 표본이 작은 부분집합에서 자주 호출되므로 3으로 두면 결과가
  자주 비어버리기 때문.
- 계산 비용: 사번마다 그 사람이 먹은 메뉴 수의 조합(C(n,2))을 전부 세므로 한
  사람이 아주 많은 메뉴를 먹었다면(수백 종) 느려질 수 있다 — 현재 규모(기간 내
  메뉴 종류 수십~백 단위)에서는 문제없음.

### 18.3 교차 비교 엔드포인트

**API**: `GET /api/analysis/corners/{corner_id}/core-layer-menu-pairs
?period_start&period_end&min_visit_count&min_share&min_co_count&top_n`
(`backend/app/api/analysis.py::corner_core_layer_menu_pairs`)

- 코너 코어층(`core_employee_ids`)과 **그 여집합**(`non_core` = 그 기간에 어떤
  메뉴든 먹은 사람 중 코어층이 아닌 사람 전체, "모든 사람"이 아님)을 나눠서 각각
  독립적으로 `compute_top_menu_pairs`를 돌린다.
- 응답 형태: `{corner_id, corner_name, core_layer: {employee_count,
  min_visit_count, min_share, top_pairs}, non_core: {employee_count, top_pairs}}`.
  기존 `analysis.py` 관례대로 별도 pydantic 응답 모델 없이 dict 그대로 반환.
- **주의**: `lift`는 각 그룹(코어층/나머지) **내부 모집단** 기준으로 따로
  계산되므로, 두 그룹의 lift 수치를 직접 비교하면 안 된다. 그룹 간 비교엔
  `co_count`(동반 인원 수)만 쓴다 — API 설명(docstring)과 프론트 안내 문구에도
  명시했다.
- 존재하지 않는 `corner_id`는 404.
- **프론트**: `AnalysisPage.tsx`의 `CornerCoreLayerSection` — "코너별 분석" 탭에
  기존 코너 통계 카드 아래로 추가. 코너 선택은 `/analysis/corners` 응답을 재사용한
  `SegmentedControl`, `min_visit_count`/`min_share`(%) 숫자 입력 2개, 결과는
  코어층/나머지 `Table` 두 개를 `grid-cols-2`로 나란히 배치(이중축 차트 등 새
  시각화는 안 만듦 — 랭킹 비교엔 표가 적합하다는 이 앱의 dataviz 원칙).

**튜닝 지점**: `min_visit_count`/`min_share`는 코어층 기준 자체를 바꾸는
파라미터(API 호출 시 넘김, 코드 수정 불필요). 코어층 정의 로직 자체를 바꾸려면
`classify_corner_core_layer` 하나만 고치면 됨.

**테스트**: `backend/tests/test_corner_core_layer.py`(6개, 순수 함수),
`backend/tests/test_menu_affinity.py`의 `compute_top_menu_pairs` 관련 5개(순수
함수). API 엔드투엔드는 `test_api_ingest_and_analysis.py::
test_corner_core_layer_menu_pairs_splits_core_and_non_core`(반복 방문 그룹과
가끔 방문 그룹을 인입해 실제로 코어층/나머지가 갈리고 각자 다른 메뉴 쌍이 나오는지
검증), `::test_corner_core_layer_menu_pairs_unknown_corner_returns_404`.

## 19. 월간 VOE 고정 분류 (맛/간/위생/서비스) — 홈 현황 화면용 (PRD 5.2/5.3)

리더 보고용으로 홈 화면을 개편하면서, 매달 라벨이 바뀌는 기존 K-means VOE
클러스터(10절 참고, 코드는 그대로 살아있음) 대신 **고정된 분류**로 훑어볼 수
있는 뷰를 추가했다.

**파일**: `backend/app/services/voe_category.py`

```python
VOE_CATEGORIES = ["맛", "간", "위생", "서비스"]
OTHER_CATEGORY = "기타"

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "맛": ("맛있", "맛없", "맛나", "노맛", "존맛", "밍밍", "느끼"),
    "간": ("짜요", "짜네", "짜서", "너무짜", "싱거워", "싱겁", "간이"),
    "위생": ("위생", "청결", "머리카락", "이물질", "벌레", "곰팡이", "상했", "냄새나"),
    "서비스": ("불친절", "친절", "서비스", "응대", "대기시간", "줄이길", "직원"),
}

def classify_voe_categories(comment: str) -> list[str]:
    ...  # 부분일치, 다중 라벨(한 코멘트가 여러 분류에 동시에 속할 수 있음)
```

- `food_vector_tagging.py`(15절)와 같은 키워드-규칙 컨벤션이다 — 짧은 문자열
  부분일치로 태깅. 차이는 메뉴명(단일 개념, 짧음)이 아니라 자유 문장(여러 주제를
  동시에 언급 가능)을 다루므로 **단일 벡터가 아니라 다중 라벨 리스트**를 반환한다.
- 어떤 분류에도 안 걸리면 호출부(`voe_by_category` 엔드포인트)가 "기타"로
  집계한다.
- **⚠️ 키워드셋은 초기 초안이다.** 실제 코멘트 데이터를 보면서
  `_CATEGORY_KEYWORDS` 딕셔너리만 계속 보강하면 된다 — 다른 코드 안 건드려도 됨.

**API**: `GET /api/dashboard/voe-by-category?period=YYYY-MM-DD`
(`backend/app/api/dashboard.py::voe_by_category`) — `period`는 해당 월의 아무
날짜(월초로 정규화, `voe_clusters`와 동일 관례). 그 달 `meal_log.comment`
전체를 분류해 **고정 순서**(맛→간→위생→서비스→기타)로 반환한다 — count로
정렬하지 않는 이유는 매달 카드 위치가 안 바뀌어야 리더가 매번 다시 안 훑어봐도
되기 때문. 응답에 `total_comments`(집계 대상 전체 코멘트 수, 다중 라벨이라
카테고리별 count 합계보다 작을 수 있음)와 각 분류의 원본 코멘트 목록(취식일시·
코너명 포함)이 그대로 담긴다.

**프론트**: `HomePage.tsx`의 VOE 분류 카드 — 5개 타일(맛/간/위생/서비스/기타)
클릭하면 그 아래 해당 분류 코멘트 표가 펼쳐지는 클릭-확장 패턴
(`AnalysisPage.tsx`의 `MenuFoodVectorEditor`와 동일한 UI 컨벤션).

**⚠️ 기존 K-means VOE 클러스터 기능은 삭제되지 않았다.** `voe_clustering.py`,
스케줄러의 `run_monthly_voe_clustering`, `monthly_voe_cluster` 테이블,
`GET /dashboard/voe-clusters` 엔드포인트 전부 그대로 남아있고 매달 계속
계산된다 — **다만 홈 화면(HomePage.tsx)에서 노출만 빠졌다.** 나중에 "이 달엔
무슨 새로운 주제가 나왔나" 같은 탐색용으로 다른 화면에 다시 노출시키고 싶으면
`api.voeClusters()`(이미 `client.ts`에 있음)를 그대로 쓰면 된다.

**튜닝 지점**: `_CATEGORY_KEYWORDS`만 고치면 분류 정확도를 조정할 수 있다.
분류 자체를 5개보다 늘리거나 줄이려면 `VOE_CATEGORIES` 리스트만 바꾸면 됨(응답
순서도 이 리스트 순서를 그대로 따름).

**테스트**: `backend/tests/test_voe_category.py`(6개, 순수 함수 — 단일/다중
라벨 매칭, 매칭 없음, 전체 카테고리가 키워드 규칙에 다 있는지). API
엔드투엔드는 `test_api_ingest_and_analysis.py::
test_voe_by_category_groups_comments_into_fixed_categories`,
`::test_voe_by_category_multi_label_comment_counted_in_both_categories`.

## 20. 코너별 식수 요약 — 홈 현황 화면 (신규 계산 없음)

홈 화면에 새로 추가한 "코너별 식수 (선택한 주)" 카드는 새 계산 로직이 아니라
기존 `GET /api/analysis/corners?period_start&period_end`(6절)를 **선택된 주
(월~일) 범위로 좁혀서** 재사용한 것이다. 만족도·피크타임 서브속도 등은
"분석" 탭에만 남기고, 홈 화면에는 코너명/식수 2개 컬럼만 간략히 표시한다
(`HomePage.tsx`).

## 21. 맛평가 매칭 실패 진단 (`ingestion-tool --debug-sample`) — 취식기록 기준 진단의 함정

실제 6개월치 운영 데이터를 적재하는 과정에서 맛평가 매칭률이 비정상적으로
낮게(0%로) 표시되는 문제가 있었다. 원인을 좁히기 위해
`ingestion-tool/parsing/merge.py`에 진단 함수 두 개를 두고 있다.

**문제의 근원**: `cli.py`가 원래 출력하던 매칭률(`matched / len(rows)`)의
분모는 **전체 취식기록 행 수**(예: 449,022행)였다. 그런데 맛평가는 응답률이
낮은 게 정상이라 애초에 존재하는 맛평가 자체가 훨씬 적다(예: 1,690건). 즉
"매칭률 0%"로 보였던 것도 사실은 852/1,690 ≈ 50%가 맞고 있었는데, 분모를
잘못 잡아서 아주 작은 숫자로 보인 것 — 실제 버그가 없었는데도 있는 것처럼
보인 사례다.

- **`diagnose_match_failure_by_evaluation(transactions, evaluations,
  employee_mapping=None)`** — **맛평가 건수를 분모로** 진단한다. 조인 키 4개
  필드(ID/날짜/식사구분/메뉴명) 중 하나씩 빼고 다시 세되, 맛평가 한 건씩을
  기준으로 세므로 **모든 카운트가 `total_evaluations`를 절대 못 넘는다.**
  이게 신뢰할 수 있는 신호라 CLI가 우선 출력한다.
- **`diagnose_match_failure(transactions, evaluations, employee_mapping=None)`**
  — 취식기록 건수를 분모로 진단한다(원래 있던 함수). **⚠️ 함정**: 같은 날 같은
  인기메뉴를 먹은 사람이 수백 명이면, ID 필드 하나만 무시해도 "그 날 그 메뉴를
  먹은 아무 취식기록"이 전부 매칭 후보로 잡혀 숫자가 실제보다 크게 부풀려진다
  (예: 실측에서 `match_without_id`가 58,365로 나왔지만, 이는 "58,365건이 ID만
  고치면 매칭된다"는 뜻이 아니라 "취식기록 중 그만큼이 같은 날짜/식사구분/
  메뉴명을 가진 것"에 가깝다). 참고용으로만 보조 출력한다.

두 함수 모두 순수 함수(파일 I/O 없음)로 `parsing/merge.py`에 있고,
`cli.py::_print_match_diagnosis()`가 A(맛평가 기준, 우선)/B(취식기록 기준,
참고)를 순서대로 출력한다. `--debug-sample`을 붙이면 이 진단 다음에 원본 조인
키 샘플(`repr()`)도 출력한다 — 사용법은 README "맛평가 매칭률이 이상하게
낮거나 0%면" 절 참고.

**필드별 값 비교 샘플 — `sample_field_mismatches()`**: 진단 A로 원인 필드가
좁혀진 뒤, 실제 값이 어떻게 다른지 눈으로 봐야 할 때를 위한 함수다. 아직 안
맞은 맛평가마다 "그 필드(ID/날짜/메뉴명)만 빼면 매칭되는 취식기록 후보"를
찾아 그 필드의 값을 (맛평가 값, 취식기록 값) 쌍으로 반환한다(필드당 최대 n건,
기본 5). 예를 들어 ID가 원인으로 잡혔다면 `('12345678', '012345678')`처럼
실제 자릿수/공백 차이가 그대로 드러난다 — 매핑 파일 누락인지, 자릿수 포맷
차이인지 바로 구분할 수 있다. `cli.py::_print_field_mismatch_samples()`가
"진단 C"로 출력한다.

**실사용 사례(2026-07)**: 실측 데이터(총 맛평가 1,690건)에서 진단 A 결과가
전부 일치 851건, ID만 무시 1,283건, 날짜만 무시 892건, 식사구분만 무시
851건(=전부 일치와 동일 → 식사구분은 원인이 전혀 아님, 재확인됨), 메뉴명만
무시 1,155건으로 나왔다. 즉 미매칭 839건 중 **ID 단독 원인 432건(1283-851),
메뉴명 단독 원인 304건(1155-851), 날짜 단독 원인 41건(892-851)**으로 좁혀져
ID(사번↔Knox ID 매핑 누락/포맷 차이 가능성)와 메뉴명이 주된 원인으로 확인됐다
(나머지 ~62건은 두 필드 이상이 동시에 다른 경우 — 필드 하나만 빼서는 안 잡힘).

**테스트**: `ingestion-tool/tests/test_merge.py`의
`test_diagnose_match_failure_by_evaluation_*` 6개(전체 일치, ID/메뉴명 불일치
격리, 매핑 적용, 매칭 없음, 취식기록이 훨씬 많아도 카운트가 맛평가 건수를 못
넘는지) + `test_sample_field_mismatches_*` 5개(필드별 값 비교 샘플).

## 22. 과거 기간 일괄 적재 후 홈/분석 화면에 데이터가 안 보이는 문제 — `daily-stats/recompute`

**증상(2026-07 실사용)**: 취식 데이터를 6개월치 한꺼번에 적재한 뒤, 홈 화면의
"주간 식수 추이"가 0으로 나오고 "코너별 식수"·분석 탭의 "코너별 분석"/
"본사·계열사·기타" 섹션이 전부 "데이터가 없습니다"로 표시됐다.

**원인**: `daily_corner_stats`/`daily_division_stats`는 `meal_log`에서 직접
집계하는 게 아니라 **배치 재계산 테이블**이다(PRD 4.3). 이 재계산은
`app/scheduler.py::run_daily_batch`가 **매일 새벽 2시에 "어제" 하루치만**
호출한다(`aggregate_daily_stats(db, yesterday)`, 6절 참고). 즉 `meal_log`에
과거 데이터를 한꺼번에 넣어도, 그 날짜들에 대한 배치 집계는 스케줄러가 알아서
채워주지 않는다 — 앞으로의 매일 새벽 배치는 "그날그날의 어제"만 채우므로,
이미 지나간 과거 구간은 영원히 비어 있는 채로 남는다.

**⚠️ 함정**: 홈 화면의 "주간 식수 추이"(`GET /dashboard/weekly-summary`)는
요청한 기간의 날짜마다 행을 만들고 집계가 없으면 `headcount: 0`을 채워
넣으므로(20절 이전 `_compute_weekly_summary` 참고), 데이터 개수(`length`)만
보면 "데이터가 있는 것처럼" 보인다 — 실제로는 전부 0인 빈 껍데기다. 그래서
프론트엔드 쪽 "데이터 없음" 판정은 `weekly.data.length === 0`이 아니라
**`totalHeadcount === 0`**으로 해야 한다(`HomePage.tsx`). 반면
`GET /analysis/corners`/`GET /analysis/divisions`는 애초에 `daily_corner_stats`/
`daily_division_stats`에 있는 행만 반환하므로 진짜로 빈 배열이 온다.

**해결**: `POST /analysis/daily-stats/recompute?period_start&period_end`
(`backend/app/api/analysis.py::recompute_daily_stats`) — 기존
`aggregate_daily_stats(db, date)`(하루 단위 함수)를 기간 내 날짜마다 반복
호출해 그 구간 전체를 한 번에 채운다. 응답은 `{"days_processed": N}`.
프론트엔드 3곳(`HomePage.tsx`의 주간 식수 추이/코너별 식수 카드,
`AnalysisPage.tsx`의 본사·계열사·기타 섹션과 코너별 분석 탭)에 "데이터가
없습니다" 상태일 때 "최근 180일 배치 집계 재계산" 버튼을 노출해, 운영자가
과거 데이터 일괄 적재 후 별도 설명 없이도 바로 이 버튼으로 채울 수 있게 했다
(`api.recomputeDailyStats()` — `recomputeMenuPerformance()`와 같은 컨벤션).
`menu_performance_stats`는 이미 `POST /analysis/menu-performance/recompute`가
있었지만(기간 전체를 한 번에 계산하는 방식이라 이 문제가 없었음), 일별 통계
쪽엔 이런 수동 재계산 경로가 없었던 게 이번에 드러난 공백이다.

**테스트**: `backend/tests/test_api_ingest_and_analysis.py::
test_daily_stats_recompute_backfills_range_for_corner_and_home_views`(기간
내 여러 날짜를 한 번에 채우고 corners/divisions 양쪽에서 값이 맞는지),
`::test_daily_stats_recompute_rejects_inverted_range`(period_end <
period_start면 400).

## 23. Take Out 코너명 정규화, 그린미트 정렬, 코너별 점유율/추이 (2026-07)

실사용 코너별 분석 화면을 검토하며 나온 네 가지 개선을 한 번에 반영했다.

**Take Out 코너 통합**: 취식기록의 "코너" 컬럼 원문이 `Take Out R`/`Take Out
M`/`Take Out L`(단말기별로 나뉨, 사용자 확인)로 세 가지가 들어온다. 정규화 없이
그대로 `get_or_create_corner()`에 넘기면 서로 다른 코너 3개가 생긴다.
`app/services/master_data.py`의 `_normalize_corner_name()`이 이 세 이름을
`TAKE_OUT_CORNER_NAME = "Take Out"`로 합친다 —
`company_classification.classify_division()`과 같은 이유로(원문 데이터를 가진
백엔드에만 매핑을 두면, ingestion-tool을 재배포하지 않고도 규칙을 바꿀 수
있다) 정규화는 백엔드 전용이다. **이미 적재된 데이터는 이 코드 변경으로
자동으로 합쳐지지 않는다** — 배포 전에 이미 별도 코너 3개로 나뉘어 쌓인
`meal_log`/`weekly_menu_plan`/`daily_corner_stats`가 있다면, 1회성 스크립트
`python -m app.maintenance.merge_take_out_corners`(`backend/app/maintenance/
merge_take_out_corners.py`)로 병합해야 한다. 이 스크립트는:
1. 별칭 코너(`TAKE_OUT_ALIASES`에 해당)를 찾아 정식 "Take Out" 코너로
   `meal_log.corner_id`/`weekly_menu_plan.corner_id`를 재배정
2. 별칭 코너에 쌓인 `daily_corner_stats`는 지움(정식 코너 기준으로 다시 계산
   해야 하므로)
3. 별칭 `corner_master` 행 삭제

실행 후 `POST /analysis/daily-stats/recompute`(21절)로 `daily_corner_stats`를
다시 계산해야 코너별 분석에 정확한 값이 뜬다. 이미 병합됐으면 조용히
종료하므로(idempotent) 여러 번 실행해도 안전하다.

**Take Out 제외 범위**: 착석 취식이 아니라 가져가는 형태라 "혼잡도/만족도"
류의 분석과는 안 맞는다는 게 사용자 판단이다. `GET /analysis/corners`(6절)에
`exclude_take_out` 쿼리 파라미터를 추가해 — 홈 화면("코너별 식수")은 생략
(기본 `false`, Take Out 포함), 분석 탭(코너별 분석 표·차트, 코어층 동반선택
비교)은 `true`로 호출해 제외한다. 같은 엔드포인트를 공유하므로 필터 로직도
한 곳뿐이다.

**그린미트 항상 마지막 정렬**: 그린미트(다이어트식)는 매니아층만 이용하는
코너라, 식수만으로 다른 코너와 나란히 순위 매기면 화면 맨 위/중간에 끼어들어
어색하다(실측에서 식수 2위인데도 항상 맨 아래여야 함). `GET /analysis/corners`
응답을 `sorted(key=lambda r: (is_diet_corner, -headcount_total))`로 정렬해
그린미트를 항상 마지막 행으로 보낸다. 이 엔드포인트 하나를 홈/분석 탭이
공유하므로 정렬도 자동으로 양쪽에 적용된다(`HomePage.tsx`의 코너별 식수
표에 있던 클라이언트 쪽 `.sort()`는 제거 — 백엔드 정렬을 신뢰).

**코너별 점유율 (신규)**: 기존엔 없던 기능. `AnalysisPage.tsx`의
`CornerAnalysisTab`이 이미 받아온 `query.data`(Take Out은 이미 제외됨)에서
`is_diet_corner`와 `corner_name === "미캠회관(전골)"`(니치 코너라 일반 코너
경쟁 비교에서 제외 — 사용자 확인)를 한 번 더 걸러 파이/도넛 차트로 그린다.
새 백엔드 로직 없이 프론트에서 이미 있는 데이터로 계산(`headcount_total`
비율).

**코너별 만족도/피크타임 서브 추이 (신규)**: `GET /analysis/corners/trend`
(`corner_analysis_trend`)를 신설했다. 기존 `/analysis/corners`는 코너당 1행
(전체 기간 집계, 막대그래프·표·점유율 파이차트용)이라 응답 모양이 다르므로
합치지 않고 별도 엔드포인트로 뒀다 — `division_analysis`(6.1절)처럼 항상
`period`가 있는 모양으로 통일하려면 기존 소비자(홈 화면)가 깨진다.
`period_bucket()`(6.1절, 기존 재사용)으로 주간/월간 버킷을 만들고
`(period, corner_id)`별로 만족도/피크타임을 집계한다. 응답:
`{period, corner_id, corner_name, is_diet_corner, headcount,
avg_taste_score, avg_peak_throughput_per_min}[]`. 프론트는 코너별
꺾은선그래프 2개(만족도, 피크타임 서브)를 그리며, **색은 코너 인기 순위가
아니라 `corner_id` 기준으로 고정**한다(dataviz 스킬: "색은 개체를 따라가야
하고 순위를 따라가면 안 된다" — 기간에 따라 어느 코너가 몇 등이든 같은 코너는
항상 같은 색). 코너 최대 8개까지 대응하려고 `index.css`의 categorical
팔레트를 `--series-4`~`-8`까지 확장했다(dataviz 스킬 참조 팔레트 그대로,
`validate_palette.js`로 라이트/다크 둘 다 통과 확인).

**테스트**: `backend/tests/test_master_data.py`(Take Out 별칭 3개가 같은
코너로 합쳐지는지), `backend/tests/test_maintenance_merge_corners.py`(백필
스크립트가 기존에 갈라진 코너를 병합·재배정하고 idempotent한지),
`test_api_ingest_and_analysis.py::test_corner_analysis_merges_take_out_
aliases_and_excludes_on_request`, `::test_corner_analysis_sorts_green_meat_
last_regardless_of_headcount`, `::test_corner_analysis_trend_groups_by_
period_and_corner`.

## 24. Take Out 4번째 별칭, 사번 ".0" 정규화, 전체 메뉴 동반선택, 홈 코너별 추이 (2026-07)

**Take Out 4번째 별칭 — "선택형 Take out"**: 23절에서 다룬 R/M/L 외에 "선택형
Take out"이라는 코너명도 같은 Take Out을 가리킨다는 게 추가로 확인됐다.
`TAKE_OUT_ALIASES`(`app/services/master_data.py`)에 추가만 하면 되도록
설계해뒀으므로 이 항목만 넣었다 — 정규화(`_normalize_corner_name`)와 백필
스크립트(`merge_take_out_corners.py`)는 모두 이 집합을 그대로 참조해 자동
반영된다.

**사번 ".0" 표기 — 백엔드 신뢰 경계에도 정규화 추가**: ingestion-tool의
파서 쪽 `_clean()`(엑셀 숫자 자동변환 방지)은 이미 고쳐뒀지만, 그 수정 이전에
이미 적재된 데이터나 다른 경로로 들어오는 값까지 막으려고 백엔드 저장
직전(`get_or_create_employee`, `app/services/master_data.py`)에도
`normalize_employee_id()`로 한 번 더 정규화한다("12345678.0" → "12345678",
숫자가 아닌 값은 그대로 둠). 이미 적재된 데이터를 정리하려면
`python -m app.maintenance.normalize_employee_ids`(신규, `merge_take_out_
corners.py`와 같은 컨벤션 — idempotent, meal_log/employee_taste_profile
재배정 후 안내 메시지 출력)를 1회 실행한다.

**코너 구분 없는 전체 메뉴 동반선택 비교**: `build_employee_menu_sets()`/
`compute_top_menu_pairs()`(`menu_affinity.py`)는 원래도 코너에 종속되지 않는
순수 함수였다(코어층 비교에서만 코어/비코어로 미리 나눠서 넘겼을 뿐) — 이걸
그대로 재사용해 `GET /analysis/menu-pairs/top`을 추가했다. 프론트
(`AnalysisPage.tsx`의 `CornerCoreLayerSection`)에 코너 탭들 앞에 "전체" 탭을
추가해 이 엔드포인트를 호출한다 — 코어/비코어 구분 없이 표 하나만 보여준다.

**코너별 만족도/피크타임 서브 추이 — 하나의 큰 그래프 + 토글**: 처음엔
막대그래프 옆에 항상 2개를 나란히 작게 보여줬는데 가독성이 떨어진다는 피드백
(2026-07)으로, "평균 만족도"/"피크타임 서브" 토글 버튼 2개(`Button` 컴포넌트
재사용, `variant`로 활성 표시)로 바꿨다. 최소 하나는 항상 켜져 있어야 하고
(둘 다 끄는 건 막음), 켠 것만 전체 폭(377px 높이)으로 크게 그린다 — 만족도
(0~5점)와 서브속도는 단위가 달라 여전히 한 차트에 두 축으로 합치지 않는다
(anti dual-axis 원칙 유지).

**홈 화면 "코너별 주간 식수 추이"**: 기존엔 "주간 식수 추이" 막대그래프 아래
날짜·구분·식수만 있는 단순 표였는데, 이를 코너별 스택 막대그래프로 교체했다
(`HomePage.tsx`). `GET /analysis/corners/trend`에 `granularity="daily"`를
새로 허용해(기존엔 weekly/monthly만) 선택한 주의 7일치를 코너별로 가져온다.
Take Out은 제외하지 않는다(홈 화면은 "취식 수 추이" 맥락이라 21절 규칙대로
유지). 색은 `cornerSummary.data`(이미 백엔드에서 그린미트 항상 마지막 정렬로
옴)의 corner_id 기준으로 고정해, `AnalysisPage.tsx`의 코너별 파이/추이
차트와 같은 색 안정성 원칙을 따른다.

**테스트**: `test_master_data.py`에 "선택형 Take out" 별칭 케이스와
`normalize_employee_id`/`get_or_create_employee` 정규화 테스트 추가,
`test_maintenance_normalize_employee_ids.py`(신규, 병합·idempotent 검증),
`test_api_ingest_and_analysis.py::test_top_menu_pairs_ignores_corner_and_
covers_whole_population`.

## 25. 월간 VOE 고정 분류를 LLM 기반으로 전환 — `voe_category_llm.py` (2026-07)

19절에서 만든 맛/간/위생/서비스 고정 분류는 원래 키워드 문자열 부분일치
규칙(`voe_category.py`)으로 계산했다. 실사용 피드백으로 "LLM이 키워드를 뽑고
그 키워드로 카테고리를 매기는 방식"으로 바꿔달라는 요청이 들어와
`voe_category_llm.py`(신규)를 추가했다. **고정 카테고리 자체(맛/간/위생/
서비스+기타)는 그대로 유지한다** — 19절에서 이 기능을 만든 이유 자체가
"매달 라벨이 바뀌는 K-means 클러스터(8절/`voe_clustering.py`)와 달리 리더가
매달 같은 틀로 훑어보게 하려는 것"이었으므로, 카테고리를 LLM이 자유롭게
바꾸게 하면 그 취지가 깨진다. 바뀐 건 "그 카테고리에 넣을지 말지 판단하는
방법"뿐이다(문자열 매칭 → LLM 판단 + 근거 키워드).

**저장 방식 — 왜 매번 계산하지 않고 누적 저장하는가**: `voe_clustering.py`의
`cluster_monthly_voe()`와 같은 이유다 — 매번 홈 화면을 열 때마다 LLM을 부르면
느리고 비용도 든다("누적이니 저장해두고 해", 사용자 확인). `meal_log`에
`voe_categories`(`ARRAY(String(16))`)/`voe_keywords`(`ARRAY(String(64))`) 두
컬럼을 추가했다(마이그레이션 `56b07f7edb3b`) — `comment_embedding` 컬럼과 같은
패턴으로 코멘트 하나하나에 배치 계산 결과를 직접 얹어둔다. 매달 새벽
스케줄러(`app/scheduler.py::run_monthly_voe_category_classification`, 지난달
치를 03:15에 실행 — `monthly_voe`(03:00)와 5분 텀을 둬 순서를 명확히 함)가
`classify_monthly_voe_via_llm()`을 돌려 채운다. 이번 달 데이터를 배치를
기다리지 않고 반영하려면 `POST /dashboard/voe-by-category/recompute?period=
YYYY-MM-01`(수동 트리거, 홈 화면의 "이번 달 재계산" 버튼)을 쓴다.

**LLM 호출 — 배치 프롬프트**: 코멘트 하나마다 LLM을 부르면 요청 수가 너무
많아지므로, `_BATCH_SIZE=30`개씩 묶어 한 프롬프트에 번호를 매겨 넣고
"번호. 카테고리: A,B | 키워드: k1,k2" 형식으로 한 번에 응답받는다
(`_classify_batch`). 응답 파싱(`_parse_batch_response`)은
`voe_clustering.py::_summarize_cluster`처럼 관대하게 처리한다 — 형식이 어긋난
줄은 조용히 건너뛰고, 카테고리 이름이 4개 고정 목록에 없으면 버리고, 못 찾은
번호는 빈 카테고리로 남겨 호출부가 "기타"로 대체한다.

**`voe_by_category` 엔드포인트의 하이브리드 읽기**: `meal_log.voe_categories`가
채워져 있으면(그 달 배치가 이미 돌았으면) 그 값을 그대로 쓰고, `NULL`이면(아직
배치 전 — 예: 이번 달이거나 이 기능 도입 이전 과거 데이터) 그 코멘트 하나만
기존 규칙 기반(`classify_voe_categories`)으로 그때그때 계산해 대체한다 —
한쪽이 비어 있다고 전체가 깨지지 않는다.

**사내 LLM 미설정 시**: `classify_monthly_voe_via_llm()`이 규칙 기반으로
대체 저장한다(배선 검증용, `voe_keywords`는 `None`으로 남음) — 다른 LLM
기능들(`voe_clustering.py`, `food_vector_tagging.py`)과 같은 컨벤션.

**테스트**: `test_voe_category_llm.py`(신규) — 배치 응답 파싱(정상/형식
어긋남/모르는 카테고리 걸러내기), LLM 미설정 시 규칙 기반 대체 저장.
`test_api_ingest_and_analysis.py::test_voe_by_category_prefers_stored_llm_
categories_over_rule_based`, `::test_voe_by_category_recompute_falls_back_
to_rules_when_llm_unconfigured`.

## 26. 사번 ".0" 분리로 생긴 중복 취식 기록 — `dedupe_meal_log.py` (2026-07)

**증상**: 실사용 데이터를 다운로드해 보니 맛평가·의견이 전부 비어 있었다
(0건). ingestion-tool의 `--debug-sample` 진단(21절)으로는 맛평가 1,690건 중
851건이 정상적으로 매칭됐다는 게 이미 확인된 상태라, 매칭 자체는 문제가 아니었다.

**원인**: 사번이 "12345678"/"12345678.0"으로 갈라져 있던 동안(24절 이전),
같은 취식 기록이 서로 다른 시점에 **두 번 따로 적재**됐다 — 한 번은 맛평가가
매칭된 상태로, 한 번은 안 된 상태로(또는 그 반대). `meal_log`는 append-only라
자연 중복 방지가 없으므로, 사번 표기가 다르면 완전히 다른 기록으로 보여 그냥
둘 다 쌓인다. `normalize_employee_ids.py`(24절)로 사번을 합치고 나면, 그제서야
"같은 사번·같은 일시·같은 식사구분·같은 코너·같은 메뉴"인 완전한 중복이 같은
사번 아래 드러난다 — 이 중 하나가 우연히 맛평가가 없는 쪽이었고, 다운로드한
데이터가 그 미매칭 사본에 치우쳐 있어 "맛평가가 전부 비어있다"처럼 보였다.

**해결**: `app/maintenance/dedupe_meal_log.py`(신규) — `(사번, 취식일시,
식사구분, 코너, 메뉴)` 조합이 완전히 같은 행이 여러 개면 하나만 남긴다.
맛평가(`taste_score`)가 있는 행을 우선 남겨서, 중복 제거 과정에서 실제 평가
데이터를 잃지 않게 한다(동점이면 먼저 적재된 행). **`normalize_employee_ids.py`
를 먼저 실행해 사번을 합친 뒤에 이 스크립트를 돌려야 한다** — 사번이 안 합쳐진
상태에서는 중복이 같은 그룹으로 안 잡힌다. 실행 후엔 다른 백필 스크립트들과
마찬가지로 배치 집계(`daily-stats/recompute`, `menu-performance/recompute`)를
다시 계산해야 한다.

**테스트**: `test_maintenance_dedupe_meal_log.py`(신규) — 완전 중복 제거하며
맛평가 있는 쪽 우선 보존, 코너가 다르면(진짜 다른 기록) 안 지움, idempotent.

## 27. 메뉴 4분면에서 테이크아웃 플레이스홀더 메뉴 제외 (2026-07)

**"선택형 Take out"**, **"(포장)메디쏠라"** 두 메뉴명은 테이크아웃 특성상(현장에서
가져가는 형태라 세부 메뉴를 정확히 못 남김) 4분면 비교에 안 맞는 플레이스홀더성
메뉴로 확인됐다(사용자 확인). 26절의 코너 제외 원칙과 동일하게 — 표시에서만
숨기지 않고 **`aggregate_menu_performance()`의 중앙값(수요/만족도 임계값) 계산
자체에서 제외**한다. `app/services/aggregation.py::EXCLUDED_QUADRANT_MENU_NAMES`에
등록된 메뉴명의 `menu_id`를 `meal_log` 조회 필터에서 미리 빼(`notin_`), 다른
정상 메뉴들의 4분면 분류(수요/만족도 중앙값)가 이 두 메뉴 때문에 왜곡되지
않게 한다.

**테스트**: `test_api_ingest_and_analysis.py::
test_menu_performance_recompute_excludes_take_out_placeholder_menus`.

## 28. 홈 화면 "메뉴 하이라이트" — 만족도 급상승/급하락, 신메뉴 초기 반응 (2026-07)

PRD 5.3의 "이슈 알림 배너"/"신메뉴 트래커" 아이디어를 메뉴 단위로 구현했다.
홈 화면의 기존 "코너별 식수(선택한 주)" 표를 대체한다(코너별 식수는 이미
"코너별 주간 식수 추이" 꺾은선그래프로 볼 수 있어 중복이었음).

**비교 기준**: "이번 주 vs 지난 주" 같은 달력 주 단위 비교가 아니라, **메뉴별로
"그 메뉴가 마지막으로 나온 주" vs "그 바로 전에 나온 주"**를 비교한다(사용자
확인) — 메뉴가 매주 나오는 게 아니라서, 달력 주 비교는 최근 안 나온 메뉴를
"변화 없음"으로 잘못 볼 수 있다.

**구현**: `app/services/menu_highlights.py`(신규, 순수 함수 — `menu_performance.
py`와 같은 컨벤션):
- `week_start(date)`: 그 날짜가 속한 주의 월요일.
- `compute_menu_satisfaction_trends()`: `{menu_id: {주 월요일: [그 주 평가
  목록]}}`을 받아, 등장한 주가 2개 이상인 메뉴만 대상으로 마지막 두 주를
  `compute_menu_score()`(6.3.1절, 베이지안 축소 — 표본 작은 주도 자연스럽게
  완화되므로 별도 최소건수 컷 불필요)로 계산해 델타를 낸다. 델타가 진짜
  양수/음수인 메뉴만 각각 "급상승"/"급하락" 후보에 넣고(변화 없는 메뉴는
  어느 쪽에도 안 들어감), 델타 크기 상위 3개씩(기본값) 반환.
- `compute_new_menu_reactions()`: `WeeklyMenuPlan.is_new_menu=True`(메뉴 최초
  등장 시 한 번만 찍힘, 24절 이전 확인)이고 최근 30일 이내 등장한 메뉴의
  평가건수·`compute_menu_score` 결과.

**엔드포인트** `GET /dashboard/menu-highlights`(`app/api/dashboard.py`) — 저장
없이 요청 시점에 `meal_log`를 바로 집계한다(180일 롤링 윈도우, 6.3절
`menu_performance_stats`와 같은 범위지만 별개 목적이라 그 테이블은 안 건드림).
전역 평균(`global_avg_score`)은 이 180일 윈도우의 평가 전체로 한 번만 계산해
급상승/급하락/신메뉴 계산 모두에 공유한다.

**프론트**: `HomePage.tsx`의 "메뉴 하이라이트" 카드 — 급상승/급하락/신메뉴
3열, 각 최대 3개(신메뉴는 개수 제한 없음).

**테스트**: `test_menu_highlights.py`(신규, 순수 함수 4개 — 주 시작일 계산,
급상승/급하락 감지, top_n 제한, 신메뉴 평가 0건 처리), `test_api_ingest_and_
analysis.py::test_menu_highlights_detects_rising_menu_and_new_menu_reaction`
(엔드투엔드).

## 29. 사내 LLM 게이트웨이 확인 — 논스트리밍, OpenAI 호환 응답 (2026-07)

`llm_client.py`는 원래 실제 스펙이 확정 안 된 상태라 OpenAI 호환
chat-completions **스트리밍(SSE)** 형식을 가정하고 구현돼 있었다. 실사용
중 사내 LLM 게이트웨이의 실제 호출 코드를 확인한 결과:
- Base URL이 `.../v1`로 끝나고, 응답 바디가 `data["choices"][0]["message"]`
  형태 — **응답 형식은 OpenAI 호환**이 맞다.
- 단, `requests.post()`로 **한 번에 전체 응답**을 받는 방식이라 **스트리밍은
  지원하지 않는다**(`stream: true`를 보내면 게이트웨이가 이를 해석 못 하거나
  무시할 가능성).

그래서 `chat_stream()`을 스트리밍 요청 대신 **일반 POST 한 번 + 전체 응답
파싱**으로 바꾸고, 응답 텍스트(`message.content`)를 단어 단위로 잘라 순차
`yield`한다 — 호출부(`app/api/chat.py`의 Agent 채팅 SSE, `chat_complete()`를
쓰는 `voe_clustering.py`/`food_vector_tagging.py`/`voe_category_llm.py`)는
전부 이 async generator 인터페이스만 보고 동작하므로 **아무 데도 안 고쳐도
된다** — 미설정 시 모의(mock) 응답이 이미 단어 단위로 yield하던 것과 같은
패턴을 실제 호출에도 그대로 적용한 것뿐이다.

`embed()`(임베딩, `voe_clustering.py`의 K-means에서만 씀)는 아직 사내
게이트웨이에서 확인 안 됨 — 필요해지면 같은 방식으로 확인 후 고치면 된다.

**테스트**: `test_llm_client.py`(신규) — `httpx.MockTransport`로 실제 HTTP
호출 없이 검증: 요청 바디에 `stream` 필드가 없는지, URL이
`{base_url}/chat/completions`인지, 인증 헤더가 `Bearer {api_key}`인지,
응답의 `message.content`가 단어 단위로 쪼개져 yield되는지, `chat_complete()`가
그 조각들을 다시 합쳐 원문을 복원하는지.

**추가 수정(2026-07)**: `is_configured`가 `base_url`과 `api_key`를 **둘 다**
요구해서, 인증이 필요 없는 사내 API(실사용 확인 — 별도 인증 없는 내부망 전용
API)를 쓰는 경우 `api_key`가 비어있다는 이유만으로 계속 모의 응답으로
빠지는 문제가 있었다. `is_configured`는 이제 `base_url`만 확인하고,
`api_key`가 비어있으면 `Authorization` 헤더 자체를 안 보낸다
(`_auth_headers()`).

**테스트 추가**: `test_is_configured_does_not_require_api_key`,
`test_is_configured_false_without_base_url`,
`test_chat_stream_omits_auth_header_when_api_key_not_set`.

## 30. 메뉴 4분면 — 코너별 클릭-확장 보드로 재구성 (2026-07)

메뉴 수가 많아지면서 "메뉴 4분면" 탭의 표 하나에 모든 메뉴를 나열하면 훑어보기
어려워졌다(실사용 피드백). `GET /analysis/menu-performance` 응답에
`corner_name`을 추가했다 — `menu_performance_stats`엔 코너 정보가 없으므로
다른 소스에서 붙여야 한다. (⚠️ 이 절 최초 구현은 `weekly_menu_plan` 기준이었으나
32절에서 `meal_log` 기준으로 바뀌었다 — 아래는 최신 상태.)

**프론트**(`MenuQuadrantTab`): 기존 하나의 큰 `<Table>`을 코너별로 묶어
(`Map<corner_name, rows>`, 메뉴 개수 내림차순 정렬) 클릭하면 펼쳐지는 아코디언
보드로 바꿨다 — `HomePage.tsx`의 VOE 카테고리 타일과 같은 클릭-확장 컨벤션.
산점도 차트는 그대로 전체 메뉴를 한 번에 보여준다(차트는 표만큼 "너무 많아
못 보는" 문제가 없어서 그대로 둠).

**테스트**: `test_menu_performance_recompute_and_read`에 `corner_name` 확인
추가("제육볶음"이 실제 취식된 코너인 "한식"으로 나오는지).

---

## 31. 코너별 카드 보드로 재구성 — 메뉴 4분면 + 음식벡터 관리 (2026-07)

30절에서 "메뉴 4분면"을 코너별로 묶긴 했지만 여전히 **세로로 쌓인 전체 폭
아코디언 목록**이라, 코너가 여러 개면 한눈에 훑어보기 어렵다는 후속 피드백이
있었다. 또 "메뉴 음식벡터 관리" 섹션은 아직 전혀 코너별로 안 묶여 모든 메뉴가
구분 없이 나열돼 있어 메뉴가 늘수록 페이지 스크롤이 계속 길어졌다.

**백엔드**: `GET /analysis/menus/food-vectors`(`list_menu_food_vectors`,
`app/api/analysis.py`)에 `corner_name`을 추가했다. 30절과 같은 헬퍼
(`_corner_id_by_menu_from_meal_log`, 32절 참고)를 기간 필터 없이 호출해
그 메뉴가 전체 기간에서 가장 많이 찍힌 코너를 붙인다.

**프론트**(`AnalysisPage.tsx`): 두 섹션이 "코너별로 묶기 → 목록/카드 →
클릭 확장"을 반복하므로 공용 헬퍼로 정리했다.
```tsx
function groupByCorner<T extends { corner_name: string | null }>(rows: T[]): [string, T[]][]
// corner_name ?? "코너 미배정" 기준으로 묶고, 그룹 크기 내림차순 정렬
function CornerCardGrid({ groups, selected, onSelect }): JSX.Element
// HomePage.tsx의 VOE 카테고리 타일과 같은 카드 스타일(테두리 박스, 굵은 코너명
// + 개수, 선택 시 강조 테두리/배경) — grid-cols-2 sm:grid-cols-5
```
- **`MenuQuadrantTab`**: 세로 아코디언 목록을 `CornerCardGrid` + 그 아래 단일
  펼침 테이블로 교체(상태는 기존 `expandedCorner` 재사용, 렌더링만 변경).
- **`MenuFoodVectorAdminSection`**: `expandedCorner` 상태를 새로 추가하고
  `groupByCorner`로 묶어 `CornerCardGrid`를 렌더링, 선택된 코너의
  `MenuFoodVectorEditor` 목록만 그 아래에 보여준다("미태깅 메뉴만 보기"
  체크박스는 카드 그리드 위에 그대로 두고, 필터링은 그룹핑 **전에** 적용).
  코너를 선택 안 하면 메뉴 목록이 아예 안 보여 스크롤이 짧아진다.

두 섹션 모두 카드 그리드 자체는 완전히 독립적인 컴포넌트 상태를 가지므로
("메뉴 4분면"에서 "한식" 카드를 펼쳐도 "음식벡터 관리"의 "한식" 카드는
안 펼쳐짐), 같은 코너명이 페이지에 두 번 나와도 서로 간섭하지 않는다.

**테스트**: `test_list_menu_food_vectors_endpoint`에 `corner_name` 확인 추가
(제육볶음 → "한식", 모듬과일 → "분식", 계란후라이(취식 기록 없음) → `null`).

---

## 32. "메뉴 4분면 전체가 코너 미배정" 버그 — corner_name 소스를 `weekly_menu_plan`
→ `meal_log`로 교체 (2026-07)

**증상**: 실사용 중 메뉴 4분면/음식벡터 관리의 코너 카드가 "코너 미배정"
하나에 전체 메뉴가 다 몰리고, 실제 코너 카드(한식/일품/그린미트 등)는 하나도
안 생기는 현상이 보고됨.

**원인**: 30·31절의 `corner_name` 계산이 `weekly_menu_plan` 테이블을 기준으로
그 메뉴의 최근 배치 코너를 찾는 방식이었다. 그런데 `weekly_menu_plan`은
운영자가 **취식기록/맛평가(`meal-log`)와는 완전히 별도로** "주간 식단표" 파일을
`ingestion-tool weekly-menu` 명령으로 업로드해야만 채워지는 테이블이다
(`backend/app/api/ingest.py`의 `/ingest/weekly-menu`와 `/ingest/meal-log`는
서로 다른 엔드포인트, 서로 다른 소스 파일). 실제 운영에서는 매일/과거 일괄
`meal-log`만 계속 적재하고 `weekly-menu`는 업로드하지 않았거나 극히 일부
기간만 업로드했을 가능성이 높다 — 그러면 `weekly_menu_plan`이 비어 있거나
조회 기간과 안 겹쳐서, **모든** 메뉴의 `corner_id_by_menu` 조회가 실패하고
`corner_name: null`로 떨어진다(멀쩡한 데이터가 있어도 이 조인 하나 때문에
전체가 미배정으로 보임).

**수정**: `corner_name`을 `weekly_menu_plan`이 아니라 **`meal_log`에서 그
메뉴가 실제로 가장 많이 찍힌 코너(최빈값)**로 다시 계산하도록 바꿨다.
`meal_log.corner_id`는 POS 취식기록 원본에 이미 실려 있는 값이라
(`ingest_meal_log`에서 `row.corner_name`으로 매번 채워짐) `meal-log`
적재만으로 항상 채워지고, `weekly-menu` 업로드 여부와 무관하다 — 운영
워크플로우가 실제로 뭘 하는지에 의존하지 않는 더 견고한 소스다.

**파일**: `backend/app/api/analysis.py::_corner_id_by_menu_from_meal_log`
```python
def _corner_id_by_menu_from_meal_log(
    db: Session, period_start: dt.date | None = None, period_end: dt.date | None = None
) -> dict[int, int]:
    query = db.query(MealLog.menu_id, MealLog.corner_id, func.count().label("cnt")).filter(
        MealLog.menu_id.isnot(None)
    )
    if period_start is not None and period_end is not None:
        ...  # [period_start, period_end] 양끝 포함 (17절과 같은 +1일 배타 상한 패턴)
    rows = query.group_by(MealLog.menu_id, MealLog.corner_id).order_by(func.count().desc()).all()
    corner_id_by_menu: dict[int, int] = {}
    for menu_id, corner_id, _cnt in rows:
        corner_id_by_menu.setdefault(menu_id, corner_id)  # count 내림차순이라 최빈 코너가 먼저 잡힘
    return corner_id_by_menu
```
`menu_performance`(기간 필터 적용)와 `list_menu_food_vectors`(기간 필터
없음) 둘 다 이 헬퍼를 공유한다. 어떤 메뉴가 그 기간에 `meal_log`로 한 번도
취식되지 않았으면(예: 부찬만 있고 실제로 안 팔린 메뉴) 여전히
`corner_name: null`(코너 미배정)로 남는다 — 이건 정상 동작이다.

**⚠️ 참고**: `weekly_menu_plan`은 이제 corner_name 계산에는 안 쓰이지만,
`ingest_meal_log`의 "메뉴명이 없는 소스는 그 날 그 코너의 메인 메뉴로 간주"
폴백 로직(12절)에는 여전히 쓰인다 — 완전히 안 쓰는 테이블이 된 건 아니다.

**테스트**: 30·31절의 관련 테스트를 `meal_log` 기준 동작에 맞게 갱신
(`test_list_menu_food_vectors_endpoint`가 "코너에서 실제로 취식된 메뉴만
그 코너로 잡히고, 취식 기록이 없는 메뉴는 미배정으로 남는지" 확인).

---

## 33. 메뉴 동반 선택 쌍에서도 테이크아웃 플레이스홀더 메뉴 제외 (2026-07)

27절에서 "선택형 Take out"/"(포장)메디쏠라"를 **메뉴 4분면**(`aggregate_menu_performance`)
에서만 제외했는데, "코너별 분석"의 코어층 × 메뉴 동반 선택 쌍(18절)과 메뉴
동반 선택 경향성(16.2절)에는 그 제외가 안 걸려 있어서 "코너별 분석에서 메뉴
쌍에 선택형 Take out이 계속 나온다"는 후속 피드백을 받았다 — 원인은 두 기능이
같은 소스 함수를 안 쓰고 있었다는 것.

**원인 상세**: 코어층 메뉴 쌍(`corner_core_layer_menu_pairs`), 전체 메뉴 쌍
(`top_menu_pairs`), 메뉴 동반 선택 검색(`menu_affinity`) 셋 다
`menu_affinity.py::build_employee_menu_sets`(사번별 "먹어본 메뉴명 집합")를
공유하는데, 이 함수는 `EXCLUDED_QUADRANT_MENU_NAMES`(당시 `aggregation.py`에만
있던 상수)를 몰랐다.

**수정**:
1. 제외 목록을 `aggregation.py`에서 `master_data.py`로 옮기고
   `PLACEHOLDER_MENU_NAMES`로 이름을 바꿨다(더 이상 "4분면 전용"이 아니라
   메뉴 단위 통계 전반에서 재사용하는 상수이므로) — Take Out 별칭 상수
   (`TAKE_OUT_ALIASES`)와 같은 파일에 둔 것도 "테이크아웃 관련 정규화/제외
   규칙은 다 여기 모여있다"는 일관성을 위해서다.
2. `build_employee_menu_sets`가 사번-메뉴 집합을 만들 때 `PLACEHOLDER_MENU_NAMES`에
   속한 메뉴명은 애초에 집합에 안 넣도록 필터를 추가했다 — 이 함수 하나만
   고치면 이걸 호출하는 3개 API(코어층 쌍/전체 쌍/동반 선택 검색)에 전부
   자동으로 반영된다.

**파일**: `backend/app/services/master_data.py`(`PLACEHOLDER_MENU_NAMES` 정의),
`backend/app/services/aggregation.py`(`EXCLUDED_QUADRANT_MENU_NAMES` 대신
`PLACEHOLDER_MENU_NAMES` import), `backend/app/services/menu_affinity.py`
(`build_employee_menu_sets` 필터 추가).

**테스트**: `test_top_menu_pairs_excludes_take_out_placeholder_menus`,
`test_corner_core_layer_menu_pairs_excludes_take_out_placeholder_menus`
(둘 다 `backend/tests/test_api_ingest_and_analysis.py`).

**⚠️ 새 플레이스홀더 메뉴명이 또 발견되면**: 이제 `master_data.py`의
`PLACEHOLDER_MENU_NAMES` 집합 한 곳만 추가하면 4분면 + 메뉴 동반 선택 쌍
전부에 자동 반영된다(예전처럼 여러 파일을 따로 고칠 필요 없음).

---

## 34. 사내 LLM 연동 — 프록시 우회 + 모델명 기본값 (2026-07)

29절에서 스트리밍/인증 문제를 고쳤는데도 실사용 중 "network error"가 계속
남아있었다. 원인은 서버 환경에 pip 설치용 `HTTP_PROXY`/`HTTPS_PROXY`가
걸려 있었던 것 — `httpx.AsyncClient`는 기본(`trust_env=True`)으로 이
환경변수를 읽어 **모든** 요청을 그 프록시로 보내는데, 이 프록시는 인터넷행
트래픽용이라 인트라넷 전용인 사내 LLM 게이트웨이는 거치지 못해 연결이
실패한다.

**수정**: `backend/app/services/llm_client.py`의 `chat_stream()`/`embed()`
두 곳 모두 `httpx.AsyncClient(timeout=60.0, trust_env=False)`로 바꿔 프록시
환경변수를 무시하고 직접 접속하게 했다. (참고: 프론트엔드↔백엔드 사이의
`localhost` 호출이 같은 프록시를 타서 생기는 문제는 코드가 아니라 서버
환경변수 `NO_PROXY=localhost,127.0.0.1` 추가로 해결하는 별개 사안 —
`docs/DEPLOYMENT.md` 3절에 기록.)

**모델명 기본값**: `app/config.py`의 `internal_llm_chat_model` 기본값을
`"internal-chat"`(플레이스홀더)에서 실사용 확인된 `"thinkingcap"`으로
바꿨다. `.env`에 `INTERNAL_LLM_CHAT_MODEL`을 안 넣어도 이 기본값이 쓰인다.

**테스트**: `test_llm_client.py`에 `test_chat_stream_bypasses_proxy_env_vars`,
`test_embed_bypasses_proxy_env_vars` 추가 — 패치된 `AsyncClient` 생성자에
전달된 kwargs를 캡처해 `trust_env=False`가 실제로 넘어가는지 확인.

---

## 35. 분석/현황 UI 개선 7건 — 위치 이동·관계도·Take Out 제외·툴팁·메뉴별 처리량·요일표시 (2026-07)

### 35.1 메뉴 동반 선택 경향성 위치 이동

`MenuAffinitySection`(독립적인 메뉴명 검색 — 코너 파라미터 없음)을 "메뉴
4분면" 탭에서 "코너별 분석" 탭의 `CornerCoreLayerSection` 바로 아래로
옮겼다(`frontend/src/pages/AnalysisPage.tsx`). 렌더 위치만 바뀌었고 컴포넌트
로직은 그대로다.

### 35.2 코너 코어층 × 메뉴 동반 선택 쌍 — 관계도(네트워크 그래프)

기존 표(lift/동반 인원 나열)는 그대로 두고, 그 위에 ECharts `graph`
시리즈(force layout)로 관계도를 추가했다(`buildMenuPairGraphOption`,
`AnalysisPage.tsx`). 표는 정확한 수치 조회용으로 남기고 관계도는 "누가
누구와 자주 엮이는지"를 한눈에 보는 용도 — 툴팁은 enhance일 뿐 값 자체는
표로도 항상 접근 가능하게 유지했다(dataviz 가이드).

- 노드 크기 = 그 메뉴가 관련된 쌍들의 `co_count` 합에 비례
- 엣지 굵기/불투명도 = `lift`에 비례
- 색상: "전체" 모드는 `--accent` 단색, 코너 선택 모드는 코어층
  `--series-1`(파랑)/나머지 `--series-2`(주황) — 기존 두 표의 `grid-cols-2`
  레이아웃과 동일하게 나란히 배치, 카테고리 팔레트 순서 그대로 재사용(새
  색 검증 불필요)

### 35.3 취향 군집 요약에서 Take Out 제외

**파일**: `backend/app/services/taste_clustering.py::compute_taste_clusters`

27절(4분면)·33절(메뉴 동반선택 쌍)에서 쓰던 `master_data.py`의
`PLACEHOLDER_MENU_NAMES`/`TAKE_OUT_CORNER_NAME`을 그대로 재사용해, 클러스터의
`top_menus`/`dominant_corner` 집계에서 Take Out 관련 값을 제외했다:
```python
menu_counter = Counter(
    name for l in logs
    if (name := menu_names.get(l.menu_id)) and name not in PLACEHOLDER_MENU_NAMES
)
corner_counter = Counter(
    name for l in logs
    if (name := corner_names.get(l.corner_id)) and name != TAKE_OUT_CORNER_NAME
)
```
순환 임포트 없음(`master_data.py`는 `taste_clustering.py`를 참조하지 않음).

**테스트**: `test_taste_clusters_exclude_take_out_from_dominant_corner_and_
top_menus`(`test_api_ingest_and_analysis.py`) — 사번당 Take Out 방문(2회)이
한식 방문(1회)보다 많게 구성해, 제외 규칙이 없으면 `dominant_corner`가
"Take Out"으로 잘못 나오는 걸 확실히 잡아내도록 함.

### 35.4 차트 툴팁 소수점 2자리

`Table` 컴포넌트엔 호버 툴팁이 없다 — 이 앱에서 "마우스를 올리면 숫자가
나오는" 곳은 ECharts 차트 툴팁뿐이다. 공용 헬퍼 `formatTooltipNumber`/
`axisTooltipFormatter`를 `AnalysisPage.tsx`·`HomePage.tsx` 각각에 추가하고
(페이지 간 로컬 헬퍼 중복은 `isoDaysAgo`처럼 기존 컨벤션), 포맷터 없이
원본 값을 그대로 보여주던 axis-trigger 툴팁 전부에 적용했다. 기존
`.toFixed(1)` 쓰던 곳(4분면 산점도 "1회 제공당 식수", 코너 요약 표의
"피크타임 분당 서브")도 `.toFixed(2)`로 통일해 자릿수를 맞췄다.

⚠️ 참고: axis-trigger 툴팁의 헤더(날짜)는 ECharts `axisValueLabel`이
함수형 `axisLabel.formatter`를 항상 반영하지는 않아 원본 ISO 날짜로 표시될
수 있음(값 자체는 정상적으로 2자리 반올림됨) — 표시값 정확도에는 영향
없는 사소한 표기 차이.

### 35.5 코너별 "메뉴 있는 날 피크타임 서브속도" 비교

**파일**: `backend/app/services/menu_throughput.py`(신규)

`aggregate_daily_stats`(6절)는 코너/식사구분 단위로만 피크타임 처리량을
계산해 메뉴 연관성을 볼 수 없었다. `meal_log`엔 이미 `menu_id`가 있으므로
(32절 "meal_log를 신뢰" 원칙과 동일하게, `weekly_menu_plan` 별도 업로드에
의존하지 않음) 새 컬럼 없이 계산 가능:

```python
def build_corner_daily_throughput(db, corner_id, period_start, period_end, settings=None) -> list[DayThroughput]:
    # 코너의 날짜별로: peak 구간 count/분(aggregate_daily_stats와 동일 계산 방식) +
    # 그날 그 코너 meal_log의 최빈 menu_id("그날의 대표 메뉴")
def compute_menu_throughput_summary(days, *, min_day_count=2) -> MenuThroughputSummary:
    # 순수 함수 — 대표 메뉴별 평균 처리량 + 전체 평균(baseline).
    # day_count < min_day_count인 메뉴는 표본 부족으로 제외(4분면 low_sample과 동일 사상)
```
`build_corner_daily_throughput`(DB 오케스트레이션) + `compute_menu_
throughput_summary`(순수 함수) 분리는 이 리포지토리의 기존 컨벤션.

**API**: `GET /analysis/corners/{corner_id}/menu-throughput?period_start&
period_end&min_day_count=2`(`analysis.py`) — `avg_throughput` 오름차순(느린
메뉴 먼저)으로 반환, `overall_avg_throughput`이 기준선.

**프론트**: `CornerCoreLayerSection`의 코너 선택 상태를 그대로 재사용 —
코어층/나머지 표 아래에 가로 막대차트(`buildMenuThroughputOption`) 추가.
느린 메뉴가 위로 오게 `yAxis.inverse: true`, `markLine`으로 기준선 점선,
기준선보다 느리면 `--warning`, 아니면 `--good`(기존 `QuadrantBadge`가 쓰는
상태색 재사용 — 막대 자체가 상태를 표시하므로 별도 범례 불필요).

**테스트**: `test_menu_throughput.py`(순수 함수 4개),
`test_corner_menu_throughput_sorts_slowest_menu_first`/
`test_corner_menu_throughput_unknown_corner_returns_404`
(`test_api_ingest_and_analysis.py`).

### 35.6·35.7 홈 현황 주간 차트 — 요일 표시 + 주말/공휴일 빨간색

`_compute_weekly_summary`(22절, `backend/app/api/dashboard.py`)는
`start_date`(항상 그 주 월요일)부터 하루씩 증가시키며 반환해 **이미
월→일 순서**였다(정렬 버그 없음, 코드 확인). 다만 x축 라벨이 "MM-DD"만
보여줘 순서가 눈에 안 띄고, 주말/공휴일도 막대 색(범례)만 다를 뿐 날짜
자체는 구분이 없었다.

`frontend/src/pages/HomePage.tsx`에 `weekdayLabel(dateIso)`(요일 접미사
추가)와 `classificationByDate` 맵을 추가해, "주간 식수 추이"·"코너별 주간
식수 추이" 두 차트의 `xAxis.axisLabel`에 함수형 `formatter`(요일 표시)와
`color`(주말/공휴일이면 `--critical`, 아니면 기본 텍스트색) 콜백을 붙였다.
`xAxis.data`는 `.slice(5)`로 미리 자르지 않고 원본 ISO 날짜를 그대로
유지해야 `classificationByDate.get(value)` 조회가 맞아떨어진다.

**테스트**: 프론트 전용 시각적 변경이라 별도 단위테스트 없음 — Playwright
스크린샷으로 x축이 "07-27(월)"~"08-02(일)" 순서로 나오고 토/일이 빨간색인
것을 확인.

---

## 36. 홈 "개선 포인트" 카드 + 주간 식단표(주찬/부찬) 고도화 (2026-07)

식당 관리자 관점에서 "지금 뭘 손봐야 하는지"를 바로 보여주는 홈 카드와,
주간 식단표(주찬/부찬 구조)를 실제로 검토·수정·활용하는 기능 묶음.

### 36.1 홈 "개선 포인트" 카드 — 혼잡도/만족도/VOE

**파일**: `backend/app/services/improvement_points.py`(신규)

세 함수 모두 **이미 계산된 API 응답을 인자로 받는 순수 함수**다 — 새 DB
쿼리나 통계 재계산 없이 기존 값을 재해석만 한다:
```python
def select_congestion_points(corners: list[dict], *, top_n=2) -> list[ImprovementPoint]
def select_satisfaction_points(menu_rows: list[dict], *, top_n=2) -> list[ImprovementPoint]
def select_voe_points(current: dict, prior: dict | None, *, top_n=1) -> list[ImprovementPoint]
```
- **혼잡도**: `corner_analysis`(`analysis.py`) 응답에서 `headcount_total`이
  median 이상인 코너 중 `avg_peak_throughput_per_min`이 median보다 낮은
  코너를 "혼잡" 후보로 뽑는다 — 4분면 분류(`classify_menu_quadrant`)가
  쓰는 "전체 median 기준" 사상을 코너 레벨에 그대로 적용.
- **만족도**: `menu_performance`(`analysis.py`) 응답에서 `quadrant ==
  "개선시급"`(수요 높은데 만족도 낮음)인 메뉴를 `share_of_traffic`
  내림차순으로.
- **VOE**: 이번 달과 지난달의 `_compute_voe_by_category` 결과를 비교해
  건수 증가폭이 가장 큰 카테고리(지난달 데이터 없으면 이번달 최다
  카테고리로 대체). "기타"는 원인 진단 근거로 부적합해 제외.

**`dashboard.py`**: 기존 `voe_by_category` 라우트의 내부 로직을
`_compute_voe_by_category(db, period)`로 분리해(기존 `_compute_weekly_
summary` 패턴과 동일) 이번달/지난달 두 번 호출할 수 있게 했다. 신규
`GET /api/dashboard/improvement-points?period_start&period_end`가
`corner_analysis`/`menu_performance`(둘 다 `analysis.py`에서 직접
import해 재사용 — 별도 서비스 레이어로 안 뽑고 route 함수를 그대로
호출)를 db와 함께 직접 호출해 위 세 함수에 넘긴다.

**프론트**: `HomePage.tsx`의 StatTile 행 바로 아래, 가장 먼저 보이는
자리에 "개선 포인트" 카드 추가 — 항목마다 점(`--warning`/`--critical`)
+ title(굵게) + detail(회색 작은 글씨) 한 줄.

### 36.2 신메뉴 추적 강화 — 도입 후 경과일

**파일**: `backend/app/services/menu_highlights.py::compute_new_menu_reactions`

`NewMenuEntry`에 `days_since_introduction: int` 필드 추가(그 메뉴가
`weekly_menu_plan`에 처음 나온 `plan_date`부터 오늘까지) — 정렬 기준도
메뉴명 알파벳순에서 **경과일 오름차순(최신 도입 먼저)**으로 바꿨다.
`dashboard.py::menu_highlights`가 `_new_menu()` 직렬화에서
`needs_attention = days_since_introduction >= 7 and evaluation_count ==
0`을 계산해 함께 내려준다 — 도입 후 일주일이 지나도록 평가가 하나도
없으면 "반응 없음" 신호.

**프론트**: `HomePage.tsx`의 "신메뉴 반응" 표에 "도입 후 경과일" 컬럼
추가, `needs_attention`이면 `--warning` 색으로 "N일 · 반응 없음" 강조.

### 36.3 주간 식단표 검토/관리 화면 (2.0)

운영 전제(사용자 확인, 2026-07): 식당에서 주간 식단표를 **2주 전에
전달**, 관리자는 **1주 전까지** 개선의견을 낼 수 있음. 같은 메인메뉴는
항상 같은 부찬을 받음(36.4의 조합 분석 전제). 원본 파일이 셀 병합 등으로
자동 파싱(메인/부찬 위치 추정)이 틀리기 쉬워 **관리자가 직접 확인·수정
저장하는 기능이 필수**로 요구됨.

**스키마 변경** (`8f3c9a1e5d21_add_role_source_and_weekly_menu_feedback.py`):
- `WeeklyMenuPlan.role_source` 컬럼 추가 — 신규 enum `MenuRoleSource`
  (`app/models/enums.py`, `FoodVectorSource`와 완전히 동일한 3값 패턴:
  `RULE="규칙기반"`/`LLM="LLM추정"`/`MANUAL="관리자수동"`). 기존 행은
  전부 규칙기반으로 백필.
- 신규 테이블 `weekly_menu_feedback`(`id, plan_date, corner_id, comment,
  created_at`) — 관리자가 남기는 개선의견, 마감과 무관하게 항상 저장.

**서비스**: `backend/app/services/weekly_menu_review.py`
```python
def feedback_deadline(plan_date: dt.date) -> dt.date:  # plan_date - 7일, 순수 함수
def group_weekly_menu_rows(rows, *, today) -> list[WeeklyMenuSlot]  # 순수 함수
def build_weekly_menu_slots(db, period_start, period_end, *, today=None) -> list[WeeklyMenuSlot]
def set_menu_role(db, plan_id, menu_role) -> WeeklyMenuPlan | None  # role_source="관리자수동"으로 잠금
def add_feedback(db, plan_date, corner_id, comment) -> WeeklyMenuFeedback
def list_feedback(db, period_start, period_end) -> list[WeeklyMenuFeedback]
```
`group_weekly_menu_rows`는 `(plan_date, corner_id, meal_type)` 단위로
메인/부찬을 묶는다. ⚠️ **한 슬롯에 MAIN이 두 개 이상 섞이는 데이터
정합성 문제**가 생기면(방지 로직은 아래 참고), 첫 번째로 만난 MAIN만
`main`에 남기고 **나머지는 조용히 버리지 않고 `sides`에 넣어 화면에서
보이게 한다**(데이터 유실 방지 — 테스트로 고정: `test_group_weekly_
menu_rows_keeps_extra_main_in_sides_instead_of_dropping`).

`set_menu_role`이 어떤 행을 MAIN으로 바꿀 때, **같은 슬롯에 이미 MAIN인
다른 행이 있으면 자동으로 SIDE로 내린다**(내려간 행도 이 조작의 결과이니
같이 MANUAL로 표시) — 실사용 검증 중 이 자동 강등이 없으면 "화면엔 새로
고른 메인이 보이는데 `_planned_main_menu_id`(36.6절)는 여전히 옛날
메인을 반환하는" 불일치가 실제로 재현됐다(같은 슬롯에 MAIN 행이 2개
남아 각 쿼리가 서로 다른 행을 먼저 집었기 때문 — 테스트:
`test_update_weekly_menu_role_to_main_demotes_previous_main`). 위
`group_weekly_menu_rows`의 "여분 MAIN을 sides로" 처리는 이 자동 강등이
있어도 혹시 모를 다른 경로(예: LLM 재분류 응답 파싱 오류)로 슬롯에 MAIN이
2개 남는 경우에 대비한 이중 안전장치다.

**API** (`analysis.py`): `GET /weekly-menu`(슬롯 목록 + 마감/역할출처),
`PUT /weekly-menu/{plan_id}/role`(수동 수정, MANUAL 잠금 + 기존 메인
자동 강등),
`POST /weekly-menu/feedback` + `GET /weekly-menu/feedback`(개선의견
등록/조회).

**프론트**: `AnalysisPage.tsx`에 새 서브탭 "주간 식단표 관리" 추가.
주 선택기(`weeklyMondayOf`/`weeklyAddDays`, `HomePage.tsx`의
`mondayOf`/`addDays`와 동일 패턴을 이 파일에 로컬로 복제 — 기존
`isoDaysAgo` 중복 컨벤션과 동일) + `CornerCardGrid`(31절)로 코너를 고르면
날짜별 카드에 메인/부찬 목록(역할 드롭다운으로 즉시 수정 가능,
"관리자수동" 아니면 "(자동분류·규칙기반)" 같은 옅은 텍스트 표시) + 마감
배지("D-N" 또는 "마감") + 개선의견 입력창을 보여준다.

### 36.4 LLM 기반 주찬/부찬 일괄 재분류 (2.1)

**파일**: `backend/app/services/weekly_menu_role_llm.py`(신규)

`food_vector_tagging.py`의 "규칙 → LLM 보강" 패턴을 그대로 따른다.
`source_row_raw`(같은 셀에서 나온 원본 항목들, 메인/부찬 행 전부 동일
문자열 보관)가 같은 행들을 `(plan_date, corner_id, meal_type,
source_row_raw)` 기준으로 묶어 LLM에게 "메인: OO / 부찬: OO, OO" 형식
응답을 요청·파싱한다:
```python
async def classify_menu_roles_via_llm(llm_client, menu_names: list[str]) -> dict[str, MenuRole] | None
async def reclassify_weekly_menu_roles(db, llm_client, period_start, period_end) -> int
```
`reclassify_weekly_menu_roles`는 **`role_source != MANUAL`인 행만**
쿼리에 포함시킨다 — MANUAL 잠긴 행이 그룹에서 빠지면 그룹 크기가
1이 될 수도 있는데, 그 경우 "재분류할 게 없다"고 보고 건너뛴다(그룹
최소 2개 필요). 즉 관리자가 고친 행은 간접적으로도 보호된다.

**API**: `POST /analysis/weekly-menu/reclassify-roles-with-llm?
period_start&period_end` — 36.3 화면의 "일괄 자동 분류(LLM)" 버튼.

### 36.5 부찬 조합별 만족도 비교 + 영양 균형 프록시 (2.2/2.3)

**전제**: 같은 메인메뉴는 항상 같은 부찬을 받는다(확인됨) → `meal_log`는
개인이 어떤 부찬을 받았는지 모르지만, **날짜 단위로 비교**하면 된다 —
같은 메인 메뉴가 다른 날 다른 부찬과 나왔을 때 그 날짜의 평균 만족도를
조합별로 묶어 비교.

**파일**: `backend/app/services/menu_combination.py`(신규)
```python
def build_side_combos_for_main_menu(db, main_menu_id, period_start, period_end) -> list[ComboDay]
    # weekly_menu_plan에서 main_menu_id가 MAIN인 (날짜,코너,식사구분)마다
    # 같은 슬롯의 SIDE 메뉴들 + 그 날짜 그 코너의 main_menu_id meal_log 평균 만족도
def compute_combo_satisfaction_summary(days, *, min_day_count=1) -> list[ComboSummary]
    # 순수 함수 — 부찬 조합(frozenset)별로 그룹핑, 만족도 내림차순(평가 없는 조합은 맨 뒤)
def compute_combo_nutrition_profile(menu_ids, food_vectors) -> dict[str, float]
    # 순수 함수 — 조합 메뉴들의 food_vector(7절, 매운맛/단백질/채소 비중 등 0~1
    # 프록시) 차원별 평균. ⚠️ 실제 칼로리/영양성분 DB가 없으므로 "영양 균형
    # 추정치"일 뿐 — 실측 아님, 응답에도 이 취지를 설명 문구로 남김.
```
**API**: `GET /analysis/menu-combinations/{menu_name}?period_start&
period_end` — `menu-affinity/{menu_name}`과 같은 이름 기반 경로 컨벤션
(meal_log 기반 함수들과 달리 이 기능은 menu_id 기준 내부 계산이지만,
검색 UX를 맞추기 위해 API 경로만 이름으로 노출).

**프론트**: "메뉴 4분면" 탭에 `MenuComboSection` 추가(`MenuAffinitySection`과
같은 검색창 UI 패턴, 자리는 가깝지만 목적이 달라 — 부찬 조합 vs 개인
동반 선택 — 별도 섹션 유지) — 메인 메뉴명 검색 → 조합별 카드(부찬 목록,
등장일수, 평균 만족도, 영양 프로필 태그).

### 36.6 혼잡도 예측에 실제 계획 메뉴 반영 (2.5)

**현재 한계**: `simulation.py`의 `congestion_forecast`/`what_if`는 코너
단위 과거 평균(`_HISTORY_WINDOW=8`)만 보고 그날 실제로 무슨 메뉴가
나오는지 전혀 몰랐다. `what_if`의 `new_menu_corner_id`는 "신메뉴가
있다더라" 수준의 플래그였고 배수는 고정 1.15(v0 임의값).

**신규 헬퍼** (`simulation.py`):
```python
def _planned_main_menu_id(db, corner_id, meal_type, target_date) -> int | None
    # weekly_menu_plan에서 그 날짜·코너·식사구분의 MAIN 메뉴 조회, 없으면 None(폴백)
def _menu_popularity_multiplier(db, corner_id, menu_id) -> float | None
    # 그 메뉴의 최근 menu_performance_stats.share_of_traffic ÷ 같은 기간
    # 그 코너 소속 메뉴들의 평균 share_of_traffic (코너 소속은
    # analysis.py::_corner_id_by_menu_from_meal_log 재사용 — 32절과 동일 원칙)
```
- **`congestion_forecast`**: 코너별로 계획 메뉴를 찾아 `menu_popularity_
  multiplier`를 baseline(코너 평균 식수)에 곱한다 — `expected_wait_
  minutes`도 이 보정된 예측치 기준으로 재계산. 계획이 없으면(주간
  식단표 미입력 기간) 기존처럼 코너 평균만 사용 — **폴백 유지, 에러
  아님**.
- **`what_if`**: 신규 선택 필드 `planned_menu_id`. 이미 성과 데이터가
  있으면(`menu_performance_stats`) 4분면(quadrant)별 배수를 쓴다:
  ```python
  _MENU_QUADRANT_MULTIPLIER = {
      POPULAR: 1.20, HIDDEN_GEM: 1.10, NEEDS_IMPROVEMENT: 1.05,
      REMOVAL_CANDIDATE: 1.00, LOW_SAMPLE: 1.15,
  }
  ```
  성과 데이터가 아예 없으면(진짜 신메뉴) 기존 고정값(1.15,
  `_DEFAULT_NEW_MENU_MULTIPLIER`)으로 폴백 — `new_menu_corner_id`만
  주고 `planned_menu_id`를 안 주면 기존 동작 그대로 유지(하위 호환).

**⚠️ 참고**: 두 엔드포인트 다 `weekly_menu_plan`에 그 날짜(며칠~2주 앞)가
미리 업로드돼 있어야 효과가 있다 — 과거분만 있으면 계획 메뉴를 못 찾아
기존 동작과 동일.

**테스트**: `test_congestion_forecast_adjusts_for_planned_menu_
popularity`, `test_what_if_uses_quadrant_multiplier_for_planned_menu_
with_performance_data`(둘 다 `test_api_ingest_and_analysis.py`) — 코너
평균 대비 특정 메뉴의 share_of_traffic 비율로 예측치가 실제로 달라지는지
숫자로 고정.

## 37. 신메뉴 수동 지정 + 주간 식단표 관리 화면 재설계(메인 강조 + 예측 패널) (2026-07)

실사용 피드백 두 가지를 반영했다: (1) "신메뉴 반응"의 자동판정(`is_new_menu`)이
인제스트 순서에 따라 깨지기 쉽고 30일이 지나면 강제로 빠져서, 관리자가 직접
추가/해제할 수 있게 해달라는 요청. (2) 주간 식단표 관리 화면에서 코너 하나를
펼치면 메인 1개 + 부찬 여러 개가 완전히 같은 스타일로 나란히 나와 "5~6개
메뉴"처럼 보이는 문제 — 메인을 시각적으로 강조하고, 그 메인메뉴가 그동안
어땠는지/이번에 나오면 어떻게 될지를 보여주는 예측 패널을 추가했다.

### 37.1 신메뉴 수동 지정

**스키마**: `MenuMaster`에 `new_menu_override: bool | None`(None=자동판정
따름, True=강제 노출, False=강제 제외), `new_menu_marked_on: date | None`
(override=True로 설정한 시점 = 도입일 기준) 추가
(`c1a2f6e9b3d4_add_new_menu_override_to_menu_master.py`).

**API**: `PUT /api/analysis/menus/new-menu-status` `{menu_name, is_new}` —
`food_vector_source`/`role_source`와 같은 "규칙 위에 관리자 수동 오버라이드"
패턴이지만, 대상 스키마가 이미 있는 3단계 enum이 아니라 단순 override라서
별도 enum 없이 nullable bool로 처리했다. `menu_name`으로 조회하는 이유는
프론트가 이미 `GET /menu-combinations/{menu_name}`에서 menu_id 없이
menu_name만 들고 있는 지점이 있어 그 컨벤션을 그대로 재사용하기 위함.

**`dashboard.py::menu_highlights`**: 기존 자동판정(최근 30일
`is_new_menu=True`)으로 dict를 만든 뒤, `new_menu_override IS NOT NULL`인
`MenuMaster` 행을 추가로 반영한다 — `True`는 30일 창과 무관하게 계속
노출(해제 전까지), `False`는 자동판정으로 떴어도 강제로 뺀다. 수동으로 추가된
메뉴의 코너명은 `weekly_menu_plan`이 아니라 `_corner_id_by_menu_from_meal_log`
(meal_log 최빈 코너, 32절과 동일 이유 — weekly_menu_plan은 누락되기 쉬움)로
찾는다. 응답에 `is_manual` 필드를 추가해 프론트가 "관리자 지정" 배지를
붙인다.

**프론트**: `HomePage.tsx` "신메뉴 반응" 표 위에 메뉴명 입력 + "신메뉴로 등록"
버튼, 각 행에 "신메뉴 아님으로 표시" 버튼을 추가했다.

**테스트**: `test_new_menu_status_manual_add_bypasses_auto_window`(meal-log로만
생긴 메뉴는 자동판정에 절대 안 걸리는데 수동 등록하면 뜨는지),
`test_new_menu_status_manual_remove_hides_auto_detected_menu`,
`test_new_menu_status_unknown_menu_name_404s`(모두
`test_api_ingest_and_analysis.py`).

### 37.2 주간 식단표 슬롯 카드 — 메인 강조 + 부찬 요약 (37.4에서 격자표로 재작성됨)

최초 버전은 슬롯 카드 헤더 아래에 메인메뉴명을 배경 칩으로 강조하고
`CornerCardGrid`(코너 카드 클릭 → 그 주 날짜별 카드가 세로로 쌓임)를 그대로
썼다. 실사용 피드백(2026-07): 카드 배지 스타일이 과하고("촌스럽다"), 코너를
클릭해야만 그 주 날짜별 카드를 볼 수 있어 요일 간 비교가 안 됨 — 이 구조는
37.4에서 코너×요일 격자표로 전면 교체됐다. 역할 수정 기능을 "수정" 토글
뒤로 접는 아이디어 자체는 격자표에서도 유지된다(37.4 참고).

### 37.3 예측 패널 — 버튼 클릭 시에만 계산

쿼리 여러 번 + LLM 호출이 슬롯 펼칠 때마다 자동으로 몰리면 느려지므로
(사용자 확인), 슬롯 카드에 "예측 보기" 버튼을 두고 클릭 시에만
`GET /api/analysis/weekly-menu/{plan_id}/predicted-impact`를 호출한다.

**신규 서비스** `backend/app/services/weekly_menu_prediction.py`:

- **기존 만족도/식수**: 그 메뉴의 가장 최근 `MenuPerformanceStats` 행
  (`adjusted_score`, `total_headcount`, `evaluation_count`).
- **이 조합(메인+부찬)의 과거 성적**: `menu_combination.py`를 확장해
  `ComboDay`/`ComboSummary`에 `headcount`/`avg_headcount`를 추가했다(기존엔
  만족도만 있었음 — `build_side_combos_for_main_menu`가 이미 그 날짜의
  meal_log를 훑고 있어서 `taste_score.isnot(None)` 필터를 없애고 평가
  여부와 무관하게 전체 행 수를 식수로, 그중 평가된 것만 만족도 평균으로
  집계하도록 바꿨다). 지금 이 슬롯의 실제 부찬 구성(`frozenset`)과 정확히
  일치하는 `ComboSummary`만 골라 보여준다 — 부찬이 하나라도 다르면
  "이 정확한 조합의 과거 이력 없음".
- **예상 점유율/식수(숫자 계산)**: `simulation.py`의 기존 baseline(코너별
  최근 8회 headcount 평균)·`_menu_popularity_multiplier`(식수 점유율
  배수)·`_planned_main_menu_id` 로직을 그대로 재사용하되, 사용자가 명시적
  요청한 "코너 분당 서브 수(처리량)도 고려"를 반영하기 위해
  `menu_throughput.py::compute_menu_throughput_summary`에서 뽑은 "이
  메뉴의 평균 처리량 ÷ 코너 전체 평균 처리량" 비율을 추가 신호로 넣었다.
  두 신호(식수 점유율 배수, 처리량 비율)를 **기하평균**으로 합성한다
  (`combine_menu_multiplier`, 순수 함수) — 신호가 하나만 있으면 그것만,
  둘 다 없으면 기존 `_DEFAULT_NEW_MENU_MULTIPLIER`(1.15)로 폴백. 이 코너의
  `predicted_headcount = baseline × 합성배수`, 나머지 코너들은
  `congestion_forecast`와 동일하게(baseline × 각자의 계획 메뉴 배수, 계획
  없으면 baseline 그대로) 계산해서, `predicted_share = 이 코너 ÷ 전체 합`
  으로 정규화한다(`compute_predicted_share`, 순수 함수).
- **코어층/코너간 경쟁(정성 코멘트만)**: 이 코드베이스엔 코어층→식수 영향이나
  교차-코너 경쟁을 숫자로 바꾸는 확정 공식이 없다(코어층 분류는 직원 집합
  분류만 있고, 18절의 코어층×메뉴쌍 비교는 서술적 분석일 뿐 예측에 안
  쓰임 — 2026-07 확인, 사용자도 정성 코멘트 방식에 동의). 그래서 이
  둘은 실제 신호(코어층 vs 비코어층 각각 이 메뉴를 먹어본 인원 수 —
  `compute_core_layer_menu_signal`, 순수 함수; 같은 날 다른 코너가
  `POPULAR` 4분면 메뉴를 내는지)를 LLM 프롬프트에 사실로만 넣고,
  "사실에 없는 숫자를 지어내지 말 것"을 명시해 2~3문장 서술로만
  받는다(`llm_client.chat_complete`, 이미 있는 짧은 호출용 헬퍼).
  `llm_client.is_configured`가 False면(로컬/테스트 환경) 위 숫자들을
  그대로 조립한 템플릿 문장으로 폴백.

**순환 임포트 주의**: `simulation.py`가 `analysis.py`의
`_corner_id_by_menu_from_meal_log`를 가져다 쓰는데, 이 예측 서비스는
`analysis.py`의 신규 엔드포인트에서 호출되므로 모듈 최상단에서
`simulation.py`를 임포트하면 `analysis → weekly_menu_prediction →
simulation → analysis` 순환이 생긴다. `compute_predicted_impact` 함수
**안에서** `from app.api.simulation import ...`를 하는 지연 임포트로
피했다(호출 시점엔 세 모듈 다 이미 로드가 끝난 뒤라 문제없음).

**API**: `GET /api/analysis/weekly-menu/{plan_id}/predicted-impact` — `plan_id`가
없거나 그 행이 메인메뉴가 아니면(부찬 행이거나 잘못된 id) 404.

**테스트**: `test_weekly_menu_prediction.py`(순수 함수: `combine_menu_
multiplier`의 기하평균/폴백, `compute_predicted_share`의 정규화,
`compute_core_layer_menu_signal`의 카운트), `test_menu_combination.py`에
`avg_headcount` 집계 테스트 추가,
`test_weekly_menu_predicted_impact_returns_prediction_and_fallback_comment`
(`test_api_ingest_and_analysis.py`, 엔드투엔드 + 부찬 행/존재하지 않는
id에 대한 404 확인).

**검증**: Playwright로 실사용 시나리오 확인 — 홈에서 신메뉴 수동 등록 시
"(관리자 지정)" 배지가 붙고 표에 즉시 반영됨, 주간 식단표 관리에서 슬롯이
메인 강조 칩 + 부찬 요약으로 보이고 "수정" 토글로 기존 정정 기능이 그대로
동작함, "예측 보기" 클릭 시에만 쿼리+LLM(미설정 시 폴백 문장)이 실행되고
기존 만족도/조합 이력/예상 식수·점유율이 표시됨.

### 37.4 주간 식단표 — 코너×요일 격자표로 재구성 + 전체 예측 비교 (2026-07)

37.2/37.3 배포 직후 실사용 피드백: (1) 카드 배지("N개 메뉴"류) 스타일이
과하다, (2) 코너 카드를 클릭해야 그 주 날짜별 카드가 세로로 쌓이는 구조라
"이번 주 전체를 한눈에" 보거나 요일 간 비교가 안 된다, (3) 예측(점유율/식수)도
슬롯 하나씩 클릭해야 해서 요일별 비교가 불가능하다. 화면 구조 자체를
코너×요일 격자표(스프레드시트)로 바꿨다.

**프론트** (`frontend/src/pages/AnalysisPage.tsx`, `WeeklyMenuReviewTab`
전면 재작성): `CornerCardGrid` + 클릭-확장 대신 직접 그리는 `<table>` —
행은 코너(이름 가나다순), 열은 `selectedMonday`부터 6일(월~토, 일요일
없음 — ingestion-tool의 6일 운영 전제와 동일). 각 셀은 그 코너·그 날짜의
메인메뉴명(중간 굵기 텍스트)과 부찬 한 줄(작은 회색 텍스트)만 보여준다 —
색 배경 배지 없이 타이포그래피 위계로만 구분해 37.2의 "촌스럽다" 피드백을
반영. 셀을 클릭하면 그 슬롯이 선택되고(표 아래 하나의 상세 패널만
렌더링), 다른 셀을 클릭하면 선택이 바뀌면서 "수정"/"예측 보기" 상태는
자동으로 닫힌다 — 그렇지 않으면 셀을 옮겨 다닐 때마다 이전 슬롯의 LLM
상세 호출이 새 슬롯에 대해 재발화되는 문제가 생긴다. 상세 패널의 역할
수정(`WeeklyMenuRoleRow`)과 예측 보기(`PredictedImpactPanel`)는 컴포넌트를
그대로 재사용 — API/로직 변경 없음.

**"전체 예측 비교" 버튼** — `GET /api/analysis/weekly-menu/predicted-impact-
summary?period_start&period_end`를 한 번 호출해 그 주 전체 메인메뉴 슬롯의
예상 점유율/식수를 받아 `plan_id → 결과` 맵으로 저장하고, 격자의 각 셀에
메뉴명 아래 "점유율 42.9%" 같은 작은 보조 텍스트로 얹는다 — 요일 간·코너
간 점유율을 격자 전체에서 한 번에 비교할 수 있다. 버튼을 안 누르면 기존과
동일(메뉴명만 보임), LLM 코멘트가 들어간 상세는 여전히 셀 클릭 후 "예측
보기"를 눌러야만 나온다(37.3과 동일 원칙 — 격자 전체에 LLM을 다 돌리면
느려짐).

**백엔드** (`backend/app/services/weekly_menu_prediction.py`): 기존
`compute_predicted_impact` 하나가 숫자 계산 + LLM 호출을 다 하던 걸
`compute_predicted_numbers(db, plan_id)`(LLM 없이 기존 만족도/식수, 조합
이력, 예상 점유율/식수 + `plan_id`/`plan_date`/`corner_id`/`corner_name`/
`menu_id`/`menu_name` 식별 필드까지 계산)와 `compute_predicted_impact(db,
llm_client, plan_id)`(위 함수를 호출한 뒤 코어층/경쟁 사실 수집 + LLM
코멘트만 얹음, `{**numbers, "summary_comment": ...}`)로 분리했다. 신규
`compute_predicted_numbers_for_period(db, period_start, period_end)`는 그
기간의 메인메뉴 슬롯 전체에 대해 `compute_predicted_numbers`를 반복
호출한다(LLM 없어 상대적으로 빠름, 그래도 버튼 클릭 시에만 실행). 상세
엔드포인트(`GET /weekly-menu/{plan_id}/predicted-impact`)의 응답 스키마는
그대로라(단, `plan_id`/`plan_date` 등 식별 필드가 최상위에 추가됨) 기존
프론트 상세 패널·테스트에 영향 없음. `plan_date`/`meal_type`은 서비스
계층에선 원본 파이썬 타입(date/enum)을 반환하고, `analysis.py`의
`_serialize_predicted_numbers` 헬퍼가 두 엔드포인트(상세/요약) 공통으로
JSON 직렬화한다(이 레포의 서비스/API 계층 분리 컨벤션).

**테스트**: `test_weekly_menu_predicted_impact_summary_returns_numbers_
without_llm_call`(`test_api_ingest_and_analysis.py`) — 요약 엔드포인트가
`summary_comment` 없이 숫자만(plan_date/meal_type 직렬화 포함) 돌려주는지
확인. 기존 `test_weekly_menu_predicted_impact_returns_prediction_and_
fallback_comment`는 리팩터링 후에도 그대로 통과(응답 스키마 하위호환).

**검증**: Playwright로 격자표가 배지 없이 코너×요일로 보이는지, 셀 클릭
시 하단에 수정/예측 상세 패널이 뜨고 기존 역할 수정이 그대로 되는지,
"전체 예측 비교" 클릭 시 격자 각 셀에 점유율이 한 번에 채워지는지 확인.

### 37.5 "전체 예측 비교" 가시화 — 히트맵/도넛/추이차트/헤드라인/혼잡 배지 (2026-07)

37.4의 "전체 예측 비교"가 셀에 작은 텍스트만 얹어 눈에 잘 안 띈다는 피드백 +
"식단표 밑에 점유율 도넛 그래프 같은 걸 고민해달라"는 요청. dataviz 스킬을
로드해 이미 이 코드베이스에 있는 전례를 그대로 재사용했다(새 색 규칙을
만들지 않음):

- **격자 히트맵**: `TasteClusterSection`의 `SEQUENTIAL_BLUE_RAMP`(단일 색상
  3-스톱, sequential magnitude 인코딩)를 그대로 가져와 `shareToBackground
  (share, maxShare)`(순수 함수, 선형보간)로 셀 배경을 칠한다 — 그 주
  `predicted_share` 최댓값 기준 정규화. 배경이 진해지면(정규화 값 > 0.55)
  텍스트를 흰색으로 전환해 대비를 지킨다. 점유율 숫자 텍스트는 그대로 유지
  (배경 추가일 뿐 정보 손실 없음 — 스킬의 "표/범례 병행" 원칙과 같은 취지).
- **요일 선택형 도넛**: `CornerAnalysisTab`의 `shareOption`(`type:"pie",
  radius:["45%","70%"]`)과 `cornerColor`(코너를 `corner_id` 오름차순으로
  `var(--series-N)` 고정 배정 — "색은 순위가 아니라 개체를 따라간다")를
  그대로 재사용. `SegmentedControl`(`components/ui.tsx`)로 월~토 하나를
  고르면 그 날짜의 `predictedByPlanId` 항목들을 코너별로 묶어 도넛 슬라이스로
  그린다.
- **요일별 점유율 추이 라인차트**: 같은 `cornerColor`를 시리즈 색으로 재사용,
  x축은 월~토, 코너별 1개 시리즈 — 시리즈 2개 이상은 범례 필수(스킬 규칙)라
  범례를 켰다. 그 코너가 안 나온 날은 `null`로 끊어(`connectNulls:false`)
  실제로 계획이 없는 날과 점유율 0을 혼동하지 않게 했다.
- **이번 주 예상 인기 메뉴 헤드라인**: `predictedByPlanId` 중
  `predicted_share` 최댓값 행을 `StatTile`(`components/ui.tsx`)로 표시 —
  "단일 헤드라인" job(스킬의 폼 선택 기준)이라 차트가 아니라 숫자 하나로
  처리.
- **혼잡 예상 코너 하이라이트 배지**: 사용자가 "피크타임 분당 서브수
  고려한 혼잡도 예측도 해달라"고 추가 요청 — `weekly_menu_prediction.py::
  compute_predicted_numbers`가 배수 합성용으로 이미 계산해두던
  `throughput_entry`(이 메뉴의 평균 분당 처리량)/`throughput_summary.
  overall_avg_throughput`(코너 전체 평균, 메뉴별 데이터 없을 때 폴백)을
  그대로 재사용해 `expected_wait_minutes = predicted_headcount ÷ 실효
  처리량`을 추가 쿼리 없이 계산했다(`prediction` dict에 필드 추가).
  프론트는 그 주 전체 `expected_wait_minutes`의 **중앙값**보다 높은 셀에
  `--warning` 색 라벨("⚠ 혼잡 예상 · 대기 ~N분")을 붙인다 — 색만이 아니라
  아이콘+텍스트 포함(스킬의 status color 규칙), 임계치는 그 주 데이터
  기준 상대값이라 별도 설정 없이 맥락에 맞게 움직인다. `PredictedImpact
  Panel`(상세 패널)에도 "예상 대기시간" 한 줄을 추가했다.

**파일**: `backend/app/services/weekly_menu_prediction.py`(필드 1개 추가,
쿼리 추가 없음), `frontend/src/pages/AnalysisPage.tsx`(`shareToBackground`/
`hexToRgb` 신규 헬퍼, 기존 `median` 재사용, 격자 셀 스타일링, "이번 주
예측 요약" 카드 신규).

**테스트**: `test_predicted_impact_computes_expected_wait_minutes_from_
peak_time_throughput`(과거 이틀치 피크타임 취식기록 + daily-stats
recompute로 baseline을 만든 뒤 `expected_wait_minutes > 0` 확인),
기존 두 predicted-impact 테스트에 `expected_wait_minutes` 필드 존재/기본값
None 확인 추가.

**검증**: Playwright로 "전체 예측 비교" 클릭 후 격자 셀 배경이 점유율에
따라 진해지고 진한 셀은 흰 텍스트로 바뀌는지, 요일을 바꾸면 도넛이 그
날짜 코너 구성으로 바뀌는지(예: 07-28은 일품 96.78%/한식 3.22%처럼 그
날 실제 비율과 일치), 추이 라인차트에 코너별 선이 나오는지, 헤드라인
StatTile이 실제 최고 점유율 행을 가리키는지 확인.

### 37.6 혼잡 예상 대기시간 — "총 서빙시간"에서 "피크 초과분"으로 재설계 (2026-07)

37.5의 "혼잡 예상 · 대기 ~N분"이 `predicted_headcount ÷ 피크타임 분당
처리량`으로 계산됐는데, 사용자가 "어떤 로직인지 모르겠다"고 지적했다 —
실제로는 "그 코너 전체 예상 식수를 쭉 서빙하는 데 걸리는 총 시간"이라
비현실적으로 큰 값(예: 66분)이 나왔다. 개인이 줄 서서 기다리는 시간이
아니었던 것.

**사용자가 확정한 파라미터**: 피크타임을 11:40~12:00(20분)에서
**11:40~12:20(40분)**으로 늘리고, **중식 전체 시간대는 11:20~13:00
(100분)**이라고 알려줬다 — 이 두 구간이 있으면 "피크타임에 실제로 얼마나
몰리는지"를 실측할 수 있다.

**새 공식** — "피크타임 처리 용량을 넘는 초과분만 대기로 본다":
```
peak_share_ratio = 그 코너의 (피크타임 취식 건수 합) ÷ (중식 전체시간대 취식 건수 합)   # 실측
expected_peak_arrivals = predicted_headcount × peak_share_ratio   # 예상 식수 중 피크에 몰릴 인원
peak_capacity = effective_throughput × peak_window_minutes(40분)  # 피크타임 처리 가능 인원
overflow = max(0, expected_peak_arrivals − peak_capacity)
expected_wait_minutes = overflow ÷ effective_throughput
```
수요가 피크 용량 안에 들면 0분(혼잡 없음), 넘치면 그 초과분을 마저
처리하는 데 걸리는 시간만 나와 훨씬 직관적이다. `peak_share_ratio`를
실측할 데이터가 아직 없는 코너(신규 등)는 시간 비례
(`peak_window_minutes ÷ meal_window_minutes` = 40/100 = 0.4)로 폴백한다(v0,
문서화).

**파일**:
- `backend/app/config.py`: `peak_time_end` "12:00:00"→"12:20:00", 신규
  `meal_period_start`("11:20:00")/`meal_period_end`("13:00:00").
- `backend/app/services/menu_throughput.py`: `window_minutes(start, end)`
  (순수함수 — 기존 `build_corner_daily_throughput`의 인라인 `peak_minutes`
  계산도 이걸로 교체해 중복 제거), `build_corner_daily_peak_share`(신규 —
  기존 `build_corner_daily_throughput`과 같은 "전체 행을 가져와 파이썬에서
  시각 비교" 방식으로 코너의 (피크 건수, 전체 중식시간대 건수) 합계를 센다
  — 새 SQL 시간추출 방식 안 씀), `compute_peak_share_ratio`(순수함수).
- `backend/app/services/weekly_menu_prediction.py`: `compute_expected_
  wait_minutes`(신규 순수함수, 위 공식)로 기존 나눗셈 한 줄을 교체.
  `compute_predicted_numbers`가 이미 구해둔 `effective_throughput`은 그대로
  재사용, `peak_share_ratio`만 추가로 계산(추가 쿼리 1건).

**프론트**: 계산 로직 자체는 그대로 소비(`prediction.expected_wait_
minutes` 필드 의미 불변, 히트맵/배지 렌더링 로직 안 건드림) — 사용자가
"일반인도 알아듣기 쉽게 표기해달라"고 요청해 `CONGESTION_EXPLANATION`
상수(1문장, "혼잡 예상 배지는 피크타임에 처리 가능한 인원보다 예상 식수가
많을 때 그 초과 인원을 처리하는 데 걸리는 예상 추가 시간입니다")를
"이번 주 예측 요약" 카드 캡션과 격자 배지의 `title` 툴팁 양쪽에 공유해서
표시한다.

**회귀 확인**: `peak_time_end`를 12:00→12:20으로 늘려도 기존 테스트 중
그 사이 시각에 걸린 assertion이 없어(13시·11:52 등만 사용) 195개 전체
테스트 그대로 통과.

**테스트**: `test_menu_throughput.py`에 `window_minutes`/`compute_peak_
share_ratio` 단위테스트 추가. `test_weekly_menu_prediction.py`에
`compute_expected_wait_minutes`의 핵심 3케이스(용량 안=0, 초과=양수 정확한
값, 데이터 없음=None)를 직접 고정 — 이 공식은 여러 신호가 얽혀 있어
엔드투엔드 픽스처로 특정 초과 시나리오를 억지로 만들기보다 순수함수
단위테스트로 정확히 검증하는 쪽을 택했다(기존 엔드포인트 테스트는 배선만
확인하도록 `> 0` → `>= 0`으로 완화, 0도 유효한 결과이므로).

---

## 38. 실사용 버그·개선 9건 일괄 처리 (2026-07)

실제로 화면을 쓰면서 나온 버그 신고/개선 요청 9가지를 한 라운드에 처리했다.
서로 독립적인 항목이라 하나씩 정리한다.

### 38.1 홈 화면 일요일 제외

`HomePage.tsx`가 `sundayOfSelected = addDays(selectedMonday, 6)`(월~일 7일)
범위로 `weeklySummary`/`cornerAnalysisTrend`를 호출했는데, `end_date`를 안
넘기면 백엔드 `_compute_weekly_summary`(`dashboard.py`)가 `start_date+6일`을
기본값으로 써서 일요일도 `headcount:0`으로 채워 반환했다 — 식당이 일요일에
운영을 안 하는데도 차트에 0건짜리 막대가 노출됨. `saturdayOfSelected =
addDays(selectedMonday, 5)`(월~토 6일)로 바꾸고 `end_date`를 명시적으로
넘기도록 수정(주간 식단표 관리 탭은 이미 6일이라 손 안 댐). 백엔드는 범용
범위 순회라 변경 없음.

### 38.2 신메뉴 하이라이트 — 메인메뉴만

`dashboard.py::menu_highlights`가 신메뉴 판정 시 `WeeklyMenuPlan.menu_role`
필터가 없어 부찬도 섞여 나왔다. 자동판정 쿼리에 `menu_role == MenuRole.MAIN`
조건 추가. 관리자 수동 override(`MenuMaster.new_menu_override`)는
`weekly_menu_plan`에 한 번도 MAIN으로 등장한 적 없는 메뉴(=부찬으로만 쓰인
메뉴)만 걸러낸다 — `weekly_menu_plan`에 아예 등장한 적 없는 메뉴(취식기록
으로만 존재, 예: 관리자가 POS 신메뉴를 손으로 등록하는 경우)는 역할을 판단할
근거가 없으므로 그대로 통과시킨다(기존 테스트 `test_new_menu_status_
manual_add_bypasses_auto_window`가 이 케이스를 이미 검증).

### 38.3 원산지 정보 제거 — 메인메뉴명만으로 매칭

`(우육:호주산)`이 셀 전체가 아니라 `"우삼겹구이(우육:호주산)"`처럼 메뉴명에
바로 붙어 들어오면 기존 `_INGREDIENT_ANNOTATION_PATTERN`(셀 전체 일치만
봄)이 못 걸렀다. 취식기록/맛평가에는 원산지 정보가 없어 이런 이름은 절대
매칭이 안 됐다.
- `ingestion-tool/parsing/weekly_menu_parser.py`: `_strip_origin_annotation`
  (순수함수, `\s*\([^()]*:[^()]*\)\s*$` 반복 제거)을 `split_cell_into_items`
  안에서 각 항목에 적용.
- `backend/app/services/master_data.py::get_or_create_menu`: 같은 정규화를
  한 번 더 방어적으로 적용(`_normalize_menu_name`) — 파싱 경로가 아닌 다른
  경로로 원산지 붙은 이름이 들어와도 항상 같은 `MenuMaster` row로 모이게
  한다.
- **범위**: 앞으로 새로 업로드하는 주간 식단표부터 정상 동작. 이미 DB에
  들어간 과거 중복 메뉴(원산지 붙은 것과 안 붙은 것 두 row)는 이번엔 정리
  안 함(재업로드 시 자연히 새 이름으로 정리됨).

### 38.4 `&미니우동` 코너 미배정 버그

`"제육볶음&미니우동"`이 셀 안에서 줄바꿈으로 감싸져
`"제육볶음\n&미니우동"`처럼 들어오면, 줄바꿈 분리 패턴(`_ITEM_SPLIT_
PATTERN`)이 이를 두 항목으로 쪼개 `"&미니우동"`이라는 조각난 메뉴명이
별도(부찬) 항목으로 생성됐다 — 이 이름은 취식기록의 실제 메뉴명과 절대
안 맞아 "코너 미배정"으로 떨어짐. `split_cell_into_items`에서 분리 후
후처리: `&`로 시작하는 조각은 독립 항목으로 안 보고 바로 앞 항목에
이어붙인다(`items[-1] += part`). 마찬가지로 과거 오염 데이터는 이번엔 정리
안 함.

### 38.5 메뉴 4분면 — 분류 기준 설명 + 화면에서 조절

기존엔 백엔드가 `statistics.median()`으로 계산한 수요/만족도 기준값을
그대로 받아 쓰기만 했다(조절 지점 없음, 기준이 뭔지 설명도 없음). 사용자
결정: **화면에서만** 조절(백엔드/DB 안 건드림). `frontend/src/pages/
AnalysisPage.tsx::MenuQuadrantTab`에 두 슬라이더(수요/만족도 기준값, 초기값
= 서버가 준 median)를 추가해 `classifyQuadrantClient()`(백엔드
`classify_menu_quadrant`와 동일한 규칙을 프론트에서 재현)로 **클라이언트
사이드 재분류**를 한다. 단, 표본부족(`evaluation_count < low_sample_
threshold`) 판정은 서버 값을 그대로 쓴다 — 조절 대상이 아님. 산점도
markLine과 확장 테이블의 4분면 배지 둘 다 이 재분류 결과를 쓴다. 상단에
"가로축/세로축이 기준값보다 큰지 작은지로 네 가지로 나눈다"는 설명 캡션도
추가.

### 38.6 코너 확장 테이블 — 정렬 + 4분면 체크 필터

같은 `MenuQuadrantTab`의 코너 클릭 확장 테이블(메뉴/등장횟수/평가건수/
만족도)에 정렬이 전혀 없었다. 4개 컬럼 헤더 클릭 시 오름/내림차순 토글
(`sortKey`/`sortDir` 로컬 state)을 추가. 4분면 범례를 클릭-토글 가능한
체크박스처럼 바꿔(`visibleQuadrants: Set<string>`) 선택된 분류만 산점도와
테이블에 보이게 필터링 — 38.5의 클라이언트 재분류 결과와 자연스럽게
연동된다.

### 38.7 코너별 분석 — 다른 코너 동반선택쌍 별도 섹션

`/corners/{corner_id}/core-layer-menu-pairs`는 원래도 코너 무관하게 코어층
전체 메뉴 집합에서 쌍을 계산했다(버그 아님) — 문제는 같은 코너 조합과
다른 코너 조합이 화면에서 구분 없이 섞여 나와, 같은 코너 조합이 워낙 흔해
다른 코너 조합이 top_n 안에 거의 안 잡혔다는 것. 각 페어 메뉴에
`corner_a`/`corner_b`(취식기록 최빈 코너, `_corner_id_by_menu_from_meal_
log` 재사용)를 붙이고, 후보 풀을 `top_n × 20`(최소 200)으로 넉넉히 넓혀
계산한 뒤 `corner_a != corner_b`인 것만 걸러 별도 `cross_corner_pairs`
필드로 반환(기존 `top_pairs` 필드는 그대로 — 하위호환). 프론트
`CornerCoreLayerSection`에 "다른 코너 조합 Top N" 표를 코어층/나머지 각각
아래에 추가, 코너 조합을 `A ↔ B` 태그로 표시.

### 38.8 음식벡터 관리 — 캠퍼스 메인메뉴 평균 레이더 차트 (신규 기능)

`food_vector`의 10차원(매운맛/단맛/짠맛/신맛/기름진맛/단백질/탄수화물/
튀김/국물/채소)은 사람이 이름 붙인 해석 가능한 속성이라, 임의 임베딩과
달리 차원축소 없이 레이더 차트로 바로 보여줄 수 있다.
- `backend/app/services/food_vector.py`: `compute_average_food_vector`
  (순수함수, 축별 산술평균), `describe_average_bias`(순수함수 —
  `taste_clustering.py::generate_cluster_label`과 같은 "중립값(0.5) 대비
  뚜렷이 튀는 차원 1~2개 추출" 방식, 임계값 0.12 동일하게 재사용해 "매운맛·
  국물 쪽으로 치우쳐 있습니다" 같은 한 줄 설명을 만든다).
- `backend/app/api/analysis.py`: `GET /menus/food-vectors/average` — `weekly_
  menu_plan`에 MAIN으로 한 번이라도 등장한 menu_id만(부찬 제외)
  `food_vector IS NOT NULL`인 것을 모아 평균·설명·표본수 반환.
- 프론트: "음식벡터 관리" 탭 최상단에 `CampusAverageFoodVectorSection`
  신규 — ECharts radar(평균 벡터 vs 중립 기준 0.5 두 시리즈 겹쳐 그림) +
  편향 설명 캡션.

### 38.9 홈 개선포인트 — VOE 주관식 주된 내용 요약

기존 `select_voe_points`(순수함수)는 카테고리별 **건수**만 보고 "어떤
카테고리가 늘었다/많다"는 제목만 만들었다 — 무슨 내용인지는 알 수 없었다.
`ImprovementPoint`에 `voe_category` 필드를 추가(선택된 카테고리를 그대로
들고 다님, 여전히 순수함수 — DB/LLM 접근 없음). DB 오케스트레이션 레이어
(`dashboard.py::improvement_points`, 이제 `async def`)에서 그 카테고리의
원문 코멘트(`_compute_voe_by_category`가 이미 모아둔 `comments`)를 최대 10건
뽑아 신규 `summarize_voe_comments(llm_client, category, comments)`
(`improvement_points.py`, `weekly_menu_prediction.py`의 `_build_summary_
prompt`/`_fallback_summary` 패턴 재사용)에 넘겨 1~2문장 요약을 만들고,
`voe_summary` 필드로 응답에 붙인다. LLM 미설정 시 폴백은 원문 예시 한 건을
그대로 인용(`"'위생' 관련 코멘트 예시: "..." 등 (사내 LLM 미설정 — 원문
예시만 표시)"`). 프론트 `HomePage.tsx`는 `voe_summary`가 있으면 인용구
스타일로 detail 아래에 덧붙여 보여준다.

**파일 요약**:

| 항목 | 파일 |
|---|---|
| 38.1 | `frontend/src/pages/HomePage.tsx` |
| 38.2 | `backend/app/api/dashboard.py` |
| 38.3 | `ingestion-tool/parsing/weekly_menu_parser.py`, `backend/app/services/master_data.py` |
| 38.4 | `ingestion-tool/parsing/weekly_menu_parser.py` |
| 38.5, 38.6 | `frontend/src/pages/AnalysisPage.tsx` (`MenuQuadrantTab`) |
| 38.7 | `backend/app/api/analysis.py`, `frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx` |
| 38.8 | `backend/app/services/food_vector.py`, `backend/app/api/analysis.py`, `frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx` |
| 38.9 | `backend/app/services/improvement_points.py`, `backend/app/api/dashboard.py`, `frontend/src/api/client.ts`, `frontend/src/pages/HomePage.tsx` |

**검증**: 신규/변경 pytest 전부 통과(백엔드 206개, ingestion-tool 78개),
프론트 `tsc -b && vite build` 클린, uvicorn+vite 띄운 뒤 Playwright로 실
데이터 기준 스크린샷 확인(일요일 미노출, 슬라이더로 4분면 재분류·정렬·
필터 동작, 레이더 차트 렌더, VOE 요약 인용구 노출, 다른 코너 조합 섹션
노출).

## 39. 식당 AX 대시보드 개선 12개 항목 (2026-07)

사용자가 화면을 실사용하며 정리한 대규모 개편 요청 12개를 우선순위 배치
([1,2,3,4] → [6,7,8] → [5,9] → [10,11] → [12])로 처리했다. 데이터 정의가
모호한 지점은 사용자가 지정한 기준을 그대로 따랐고, 유일하게 실사용
판단이 필요했던 4분면 X축 왜곡 문제(39.6)는 사용자에게 직접 확인해 결정
했다.

### 39.1 홈 요약 카드 4개 교체 + 혼잡도 예측 버그 수정

`simulation.py::congestion_forecast`의 `expected_wait_minutes` 계산이
`weekly_menu_prediction.py`에서는 이미 고쳐진(피크 초과분만 대기로 보는)
공식으로 바뀌었는데, 이 엔드포인트만 옛 방식("예상 식수 전체를 처리하는
총 시간")이 그대로 남아있었다 — 새 카드를 얹는 김에 `compute_expected_
wait_minutes`/`compute_peak_share_ratio`/`build_corner_daily_peak_share`
(기존 순수함수·헬퍼)로 교체해 같이 고쳤다. 응답에 `expected_peak_
headcount = predicted_headcount × peak_share_ratio`(코너별 피크타임 실제
몰릴 인원)를 신규 필드로 추가 — 홈의 "오늘 예상 총 식수"는 전체 코너
`predicted_headcount` 합, "최고 혼잡 예상 코너"는 이 값이 최댓값인 코너.
"금주 메뉴 과거 VOE"는 이번 주 메인메뉴 목록에 대해 프론트에서 `Promise.
all`로 `menu-history`를 병렬 호출해 이력 있는 메뉴 수를 세는 v0 구현(트래픽
적은 화면이라 배치 엔드포인트 신설은 과설계로 판단해 보류).

### 39.2~39.4 문구·그래프 형태 변경

"개선 포인트" → "개선 필요 포인트"로 문구 변경 + 내부 로직 설명 문단 삭제
(39.2). 주간 식수 추이 막대→꺾은선(39.3, 포인트별 색은 `data: {value,
itemStyle:{color}}[]` 형태로 유지). 코너별 주간 추이는 Take Out/미캠회관
(전골)/그린미트를 범례 맨 뒤로 재정렬하고 `legend.selected`로 기본 OFF —
클릭해서 켜야 보임(39.4, 이 프로젝트에서 `legend.selected` 첫 사용 사례).

### 39.5 금주 메뉴 VOE 상세 화면 + 주관식 VOE 서브탭 신설

신규 화면 `WeeklyMenuVoeDetailPage.tsx`(라우팅은 `App.tsx`의 숨은 탭
`"weekly-voe"` — 네비게이션 바엔 없고 홈 카드 클릭으로만 진입) — 이번 주
메인메뉴별 아코디언에 좌측 점수 이력(`menu-history`), 우측 코멘트 원문
(신규 `GET /dashboard/menu-comments/{menu_name}`, `MealLog` 조인)을
나란히 보여준다.

분석 탭 "주관식 VOE" 서브탭(`VoeAnalysisTab`)엔 기존 홈에 있던 "월간 VOE
분류"(카테고리 고정, `voe-by-category`)를 그대로 옮기고, **이미 백엔드엔
다 구현돼 있었지만 어느 화면에도 안 붙어있던 죽은 기능**이던 `voe-
clusters`(K-means 자유형 클러스터, `MonthlyVoeCluster`)를 새로 연결했다.
수동 재계산 트리거가 없어(voe-by-category엔 있는데 비대칭) `POST /
dashboard/voe-clusters/recompute`를 신규 추가. 홈 화면의 "월간 VOE 분류"
섹션은 제거(1번 카드로 요약 대체).

### 39.6 메뉴별 분석(구 메뉴 4분면) — X축 왜곡을 버블 크기로 시각화

X축(1회 제공당 평균 식수)은 제공 횟수가 적은 메뉴일수록 하루치 우연한
결과가 평균을 크게 흔든다는 문제가 있었다. 세 가지 방식(임계값 이하 회색
처리 / 최소 표본 미달 시 숨김 / 버블 크기로 표본수 시각화)을 사용자에게
제시했고, **버블 크기 방식**으로 확정했다. `MenuQuadrantTab`의
`scatterData`에서 `symbolSize`를 `appearance_count` 기반 제곱근 스케일로
바꾸고(`buildMenuPairGraphOption`의 기존 버블 스케일 패턴 재사용), 최소
표본(최근 3회 미만) 메뉴는 점선 테두리+낮은 불투명도로 추가 구분. 탭
이름도 "메뉴 4분면" → "메뉴별 분석"으로 변경.

### 39.7~39.8 코너별 분석 — 듀얼축 통합 그래프 + 표 기본 숨김

기존 "누적 식수"/"평균 만족도" 막대 그래프 두 개를 하나의 **월간 기간축
듀얼축 꺾은선**으로 통합했다(`cornerAnalysisTrend(granularity="monthly")`
가 이미 코너·월별 `headcount`/`avg_taste_score`를 함께 반환하므로 백엔드
신규 엔드포인트 없이 프론트 차트 구성만 변경). `yAxis: [{식수}, {만족도,
min:0,max:5}]`, 코너당 "{코너명} 식수"(`yAxisIndex:0`)/"{코너명} 만족도"
(`yAxisIndex:1`) 두 시리즈로 나눠 범례 클릭으로 개별 ON/OFF 가능(39.7).
지표명 "누적 식수" → "월간 식수". 하단 상세 표는 `useState(false)` +
토글 버튼으로 기본 숨김(39.8).

### 39.9 서브그래프 — 월 주차별 표시 + 메인메뉴 툴팁

"코너별 만족도·피크타임 서브속도 추이" 서브그래프에 `trendGranularity`
옵션을 `"weekly-of-month"`로 확장 — 월 선택기(`<input type="month">`)로
고른 달의 `cornerAnalysisTrend(granularity="daily")`를 그대로 받아
**프론트에서** 날짜를 주차로 그룹핑(`Math.ceil(dayOfMonth/7)`)해 "1주차"~
"5주차" 라벨을 붙인다 — 백엔드 `granularity` enum에 새 값을 추가하는 대신
프론트 재집계로 구현해 `_period_bucket`(analysis.py) 등 기존 집계 로직에
영향이 없게 했다. 그래프 포인트 hover 시 그날의 코너별 메인메뉴를 툴팁에
추가로 표시하기 위해 신규 `GET /analysis/corners/main-menu-by-date`
(`weekly_menu_plan`의 MAIN 역할만 코너·날짜별로 매핑해 반환)를 추가하고,
프론트가 이 맵을 `tooltip.formatter`에서 날짜+코너로 조회해 `(메인:
메뉴명)`을 덧붙인다.

### 39.10 코너 코어층/메뉴 동반선택쌍 — 두 개의 독립 화면으로 분리

기존엔 코어층(방문 빈도·비중 기준)과 메뉴 동반선택쌍(장바구니 분석)이 한
Card 안에 섞여 있었다. 사용자 지시대로 목적이 다른 두 분석을 완전히
분리했다(`AnalysisPage.tsx`의 `CornerLoyaltySection`/
`MenuPairAnalysisSection`, 이전의 단일 `CornerCoreLayerSection`을 대체).

**코너 코어층(10-1)** — 기존 판정 기준(①방문 횟수·비중이 유의미하게
높음, `classify_corner_core_layer`)에 신규 기준(②같은 메인메뉴가 여러
코너에서 동시 제공된 날에도 이 코너를 고르는 패턴)을 **AND로 합치지 않고
나란히 보여주는 방식**으로 추가했다(AND로 합치면 기존 코어층 정의가
깨짐). 신규 `corner_core_layer.py::classify_menu_controlled_corner_
preference(rows)`: 입력은 `(plan_date, menu_id, corner_id)` 튜플 목록 —
`build_menu_controlled_meal_log_rows(db, period_start, period_end)`(신규
DB 헬퍼)가 `weekly_menu_plan`에서 같은 (날짜, 메뉴)가 2개 이상 corner_id로
MAIN 제공된 "경합 상황"을 찾고, 그 조합에 해당하는 `meal_log` 행만
필터링해 넘긴다. 코너별로 `contested_occasions`(경합 상황에서의 전체
선택 수)와 `chosen_count`(그 코너가 선택된 수)를 **모든 경합 이벤트에
걸쳐 분자·분모를 누적**해 집계한다(이벤트 단위 단순 평균이 아니라 참여
인원 비례 가중 — 참여자가 많은 이벤트가 자연히 더 크게 반영됨).
`preference_ratio = chosen_count / contested_occasions`를 "메뉴 동일
상황에서도 이 코너 선택 비율"로 화면에 노출, 경합 상황이 없으면(개발
DB처럼 표본이 희소하면) "데이터 없음"을 명확히 표시.

**메뉴 동반 선택 쌍(10-2)** — `menu_affinity.py`가 이미 반환하던 `lift`
기준 정렬 옵션을 프론트에 노출(`sortKey: "co_count"|"lift"`, 기존
`co_count` 우선 정렬 대신 사용자가 고를 수 있게). "자명한 조합"(예:
부대찌개-참치김치찌개처럼 같은 카테고리) 판정은 신규 `menu_affinity.py::
is_obvious_pair(vector_a, vector_b, threshold=0.85)` — 두 메뉴의
`food_vector`(10차원) 코사인 유사도(`taste_profile.py::cosine_
similarity` 재사용)가 0.85 이상이면 자명한 조합으로 플래그. 벡터가 없는
메뉴는 `None`(판정 불가, 화면에서 필터링 대상 아님). API 응답(`/analysis/
corners/{id}/core-layer-menu-pairs`, `/analysis/menu-pairs/top`)의 각
페어에 `is_obvious_pair` 필드를 추가하고, 프론트는 기본으로 자명한 조합을
숨겨(체크박스로 켜야 보임) "부대찌개 선호자가 떡볶이도 유의미하게
선호한다" 같은 비자명한 연관관계가 lift 순으로 먼저 보이게 한다.

### 39.11 Agent 채팅 데이터 그라운딩

`InternalLLMClient`(`llm_client.py`)는 tool calling을 지원하지 않는 순수
텍스트 in/out 클라이언트라, "질문을 규칙 기반으로 분류 → 관련 데이터
사전 조회 → system 메시지로 주입" 방식으로 그라운딩했다(신규
`backend/app/services/chat_grounding.py`).

- `route_categories(message) -> list[str]`: 순수함수, 키워드 매칭만으로
  카테고리 목록을 정한다(혼잡/피크/대기→`congestion`, 만족도/평가/점수→
  `satisfaction`, voe/의견/불만/코멘트/후기→`voe`, 식수/몇명/인원→
  `headcount`, 신메뉴/새메뉴→`new_menu`). 한 메시지에 여러 카테고리가
  매칭될 수 있고, 하나도 안 맞으면 빈 리스트.
- `build_grounded_context(db, user_message) -> str`: 매칭된 카테고리마다
  전용 포맷터가 **기존 라우트 함수를 그대로 재호출**해서 데이터를 조회한다
  (새 쿼리 로직을 만들지 않음) — `congestion_forecast`(오늘 중식 피크
  예상), `corner_analysis`(최근 30일 코너별 만족도), `_compute_voe_by_
  category`(이번 달 카테고리별 건수+대표 코멘트 최대 2건), `_compute_
  weekly_summary`(이번 주 일자별 식수), `menu_highlights`(최근 신메뉴
  반응). 매칭 카테고리가 없으면 기본 종합 요약(최근 7일 식수 상위 3개
  코너 + 이번 달 VOE 상위 카테고리)으로 대체.
- 조회 결과는 "이 데이터에 근거해서만 답하고, 없는 내용은 추측하지 말고
  데이터가 없다고 답하라"는 지시문과 함께 system 메시지로 만들어
  `payload.messages` 맨 앞에 삽입한다(`chat.py::chat_stream`). LLM
  호출(`chat_stream`) 자체는 기존과 동일한 스트리밍 프로토콜이라 프론트
  변경은 없음.

### 39.12 UI 스타일 가이드 일괄 적용

전체 항목 완료 후 마지막에 한 번에 적용(중간에 바꾸면 배치별 diff가
섞여 리뷰가 어려워짐):
- `Card` 제목을 `text-[13px] font-medium` → `text-[15px] font-semibold`
  (색도 `ink-secondary` → `ink`)로 키워, 페이지 대제목(`text-lg font-
  semibold`)과 섹션 제목의 위계를 더 뚜렷하게 구분.
- `StatTile`에 optional `tone?: "good"|"warning"|"critical"` prop 추가 —
  값 텍스트 자체엔 색을 넣지 않고(기존 `QuadrantBadge`와 동일한 "색은
  점에만 싣는다" 규칙 유지) 라벨 옆 점(dot) + 왼쪽 강조 테두리로만
  상태를 표시한다. 상태를 실제로 나타내는 지표에만 적용(예: 홈의 "최고
  혼잡 예상 코너" 카드에 `tone="warning"`) — 모든 StatTile에 임의로
  씌우지 않음.
- 분석 탭들의 최상위 컨테이너 spacing이 `space-y-4`로 다른 페이지
  (홈/시뮬레이션/VOE 상세, `space-y-6`)와 어긋나 있던 것을 통일
  (`AnalysisPage.tsx`의 `UserAnalysisTab`/`CornerAnalysisTab`/`WeeklyMenuReviewTab`/
  `VoeAnalysisTab`/`AnalysisPage` 최상위 및 "메뉴별 분석" 탭 묶음 wrapper).

**파일 요약**:

| 항목 | 파일 |
|---|---|
| 39.1 | `backend/app/api/simulation.py`, `frontend/src/pages/HomePage.tsx` |
| 39.2~39.4 | `frontend/src/pages/HomePage.tsx` |
| 39.5 | `backend/app/api/dashboard.py`, `frontend/src/pages/WeeklyMenuVoeDetailPage.tsx`(신규), `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/App.tsx` |
| 39.6 | `frontend/src/pages/AnalysisPage.tsx`(`MenuQuadrantTab`) |
| 39.7, 39.8 | `frontend/src/pages/AnalysisPage.tsx`(`CornerAnalysisTab`) |
| 39.9 | `backend/app/api/analysis.py`, `frontend/src/pages/AnalysisPage.tsx` |
| 39.10 | `backend/app/services/corner_core_layer.py`, `backend/app/services/menu_affinity.py`, `backend/app/api/analysis.py`, `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/api/client.ts` |
| 39.11 | `backend/app/services/chat_grounding.py`(신규), `backend/app/api/chat.py` |
| 39.12 | `frontend/src/components/ui.tsx`, `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/AnalysisPage.tsx` |

**검증**: 신규/변경 pytest 전부 통과(백엔드 228개), 프론트 `tsc -b &&
vite build` 클린, uvicorn+vite 띄운 뒤 Playwright로 실 데이터 기준
스크린샷 확인(홈 카드 4개 + 혼잡 경고 톤, 꺾은선 전환, 범례 기본 OFF,
4분면 버블 크기, 코너별 듀얼축 통합 그래프, 표 접기/펼치기, VOE 상세
화면, 주관식 VOE 서브탭, 코어층/동반선택쌍 분리 화면에서 코너 전환·정렬
토글·자명 조합 필터 동작, Agent 채팅이 200 응답 + system 메시지에 실제
데이터 주입 확인, 통일된 카드 제목/여백). 구현 도중 `CornerLoyaltySection`의
`selectedCornerId` 초기값이 `corners` prop이 비어있는 첫 렌더 시점에
고정되어 버려(부모 쿼리가 비동기로 나중에 채워짐) 코너 선택 상태가
영원히 `null`로 남는 버그를 Playwright 스크린샷 비교 중 발견 — `useEffect`
로 `corners`가 채워지면 첫 코너를 선택하도록 동기화해 수정.

## 40. 실사용 피드백 라운드 — 버그 2건·패밀리데이 신설·수정 7건 (2026-07)

지난 라운드 배포 후 실사용 중 나온 피드백을 처리했다: VOE 클러스터링 500
에러, Agent 채팅이 실제 데이터가 있어도 "데이터 없음"으로 답변 거부하던
버그, "패밀리데이"(매월 21일이 있는 주의 금요일, 출근 자율) 신규 분류,
그 외 홈/분석 화면 수정 7건.

### 40.1 VOE 클러스터링 500 에러 — 원인 재현 실패, 방어 로직 추가

코드 리뷰·시딩 데이터 재현 모두 500을 재현하지 못했다(표본부족·NOT NULL
제약은 이미 방어돼 있었음, sklearn 1.5 KMeans로 직접 검증). 가장 그럴듯한
원인은 실제 사내 LLM 임베딩 게이트웨이 호출 실패(타임아웃/인증/응답
스키마 불일치)인데, `cluster_monthly_voe`(`voe_clustering.py`)에 예외
처리가 전혀 없어 어떤 예외든 그대로 500으로 노출됐다. 방어책: (1)
`np.array(embeddings)`로 넘기기 전 임베딩 개수/차원 일치를 검증해 명확한
`ValueError`를 던지게 함(불일치 시 numpy가 알아보기 힘든 에러를 던지는
문제 방지), (2) 클러스터 라벨 요약(`_summarize_cluster`) 호출 실패는
클러스터링 자체(KMeans 배정)를 실패시키지 않고 "미분류"로 폴백, (3)
`dashboard.py::recompute_voe_clusters` 엔드포인트에서 예외를 502 +
상세 메시지로 감싸 원인 진단이 가능하게 함. `test_voe_clustering.py`
신규(이 경로에 테스트가 전혀 없었음).

### 40.2 Agent 채팅 그라운딩 — 월/랭킹 파싱 추가

`chat_grounding.py`가 데이터 **종류**(식수/만족도/voe 등)만 라우팅하고
**기간**(몇 월)·**의도**(top N/순위)는 전혀 파싱하지 않아 "6월 식수
top3"/"6월 가장 많이 먹은 메뉴" 같은 질문에 항상 "이번 주"만 보거나
아예 매칭되는 카테고리가 없어 데이터 없음으로 답했다. 순수함수
`_extract_month_range`("N월"/"지난달"/"이번달" 파싱, 이번 달보다 큰
달이면 작년으로 간주), `_extract_top_n`("top3"/"상위 3"/"3위" 파싱),
`_wants_ranking`(랭킹 의도 키워드 매칭)을 추가하고 모든 포매터를
`(db, message)` 시그니처로 통일했다. 신규 카테고리 `menu_ranking`
("많이 먹은", "인기 메뉴" 등 구문 매칭) + 신규 백엔드 엔드포인트
`GET /analysis/menus/top-by-headcount`(임의 기간을 `meal_log`에서
그 자리에서 집계 — `menu_performance`는 사전 recompute된 정확히 일치
하는 기간만 조회 가능해 채팅처럼 즉석 질의에 못 씀).

### 40.3 패밀리데이 — 3단계 분류로 앱 전체 확장

`holidays.py::DayClassification`에 `FAMILY_DAY = "패밀리데이"` 추가.
판정: `family_day_of_month(year, month)` — 그 달 21일이 속한 주(월~일)의
금요일(`21일 + (5 - 21일.isoweekday())`일). 공휴일과 겹치면 공휴일 우선.
`is_holiday` 컬럼(`DailyCornerStats`/`DailyDivisionStats`)은 boolean이라
3단계를 못 담는다 — `family_day_dates_in_range(start, end)`로 기간 내
패밀리데이 날짜 집합을 계산해 `analysis.py::_apply_classification_filter`
(신규 공통 헬퍼, `division_analysis`/`_load_corner_stats`가 공유)가
"패밀리데이"는 `stat_date IN (...)`, "평일"은 그 집합을 `NOT IN`으로
추가 제외해 더는 평일 버킷에 안 섞이게 한다. 시뮬레이션 baseline(최근
8회 이력 평균, `simulation.py::_fetch_classification_history`)도 패밀리
데이가 월 1회뿐이라 `is_holiday=False` 풀에서 훨씬 넓게(400개) 스캔한
뒤 Python에서 `is_family_day()`로 걸러 8개를 모은다(평일 이력도 같은
풀에서 패밀리데이만 제외, 스캔 폭은 32개로 충분). `dashboard.py::_compute_
weekly_summary`/`simulation.py::what_if`는 `HolidayService.classify()`
확장만으로 자동 반영(코드 변경 불필요). 프론트는 `Classification` 타입에
`"패밀리데이"` 추가 + 모든 분류 필터 `SegmentedControl`/`Legend`에 3번째
옵션, 홈 화면 차트 색상은 `var(--series-3)`로 구분.

### 40.4 홈 화면 — Take Out 제외, 토요일 기본 숨김

"최고 혼잡 예상 코너"(`HomePage.tsx`) reduce에 `corner_name !== "Take
Out"` 필터 추가(착석 취식이 아니라 혼잡도 개념과 안 맞음 — `corner_
analysis`의 `exclude_take_out`과 같은 이유). "오늘 예상 총 식수"는 그대로
유지(사용자가 최고 혼잡 코너만 명시). "주간 식수 추이"/"코너별 주간 식수
추이"는 토요일이 평일과 규모가 달라 같은 라인에 섞으면 오해하기 쉽다 —
`showSaturday` state(기본 `false`)로 두 차트 전용 `chartWeeklyData`를
필터링(누적 식수 스탯 타일은 영향 없음, 원본 `weekly.data` 그대로 사용),
버튼으로 토글.

### 40.5 주간 식단표 히트맵 — 색상 대비 재설계 (dataviz 스킬 적용)

기존 `useLightText = share/maxShare > 0.55`라는 share 비율 임의 컷오프가
실제 배경색 명도와 무관해, 컷오프 아래(전체 셀 절반 이상)에서 회색
(`--ink-muted`)·노란색(`--warning`, 밝은 배경 대비 1.79:1로 사실상 안
보임) 텍스트가 연한 파란 배경 위에 그대로 남았다. WCAG 상대 명도/대비
공식(`AnalysisPage.tsx::relativeLuminance`/`wcagContrast`, dataviz 스킬
`validate_palette.js::contrast`와 동일 공식)으로 흰색/기본잉크(`var(--ink)`)
중 실제 대비가 높은 쪽을 선택하도록 교체(`useLightTextOn`). 혼잡 경고
(`⚠ 혼잡 예상`)는 색(`--warning`)만으로 신호하지 않는다 — dataviz 스킬
원칙(상태색은 항상 아이콘+라벨과 함께)에 따라 ⚠ 이모지가 아이콘 역할을
하고 텍스트는 본문과 같은 대비색을 쓰게 변경.

### 40.6 메뉴별 분석 — 조식/중식/석식 필터

`MenuPerformanceStats`(`/menu-performance`가 읽는 테이블)는 끼니 구분
없이 통합 집계라 스키마 마이그레이션 없이는 끼니별로 못 나눈다 —
`aggregate_menu_performance`(aggregation.py)와 동일한 순수함수 체인
(`compute_menu_score`/`compute_menu_frequency`/`compute_share_of_traffic`/
`classify_menu_quadrant`)을 재사용하되 `MealLog` 쿼리에 `meal_type`
필터를 추가해 그 자리에서 계산만 하고 저장하지 않는 신규 엔드포인트
`GET /analysis/menu-performance/by-meal-type`을 추가(기존 엔드포인트는
그대로 유지). 수요/만족도 중앙값도 그 meal_type 내에서 다시 계산한다.
`MenuQuadrantTab`에 조식/중식/석식 `SegmentedControl` 추가, "전체" 선택
시에만 "재계산" 버튼 노출(끼니별 모드는 저장 대상이 없음).

### 40.7 코너별 분석 — 범례 단순화 (코너명만)

`combinedTrendOption`의 식수/만족도 두 시리즈가 "{코너} 식수"/"{코너}
만족도"로 범례가 2배였다 — 두 시리즈의 `name`을 코너명 하나로 통일하면
ECharts가 자동으로 한 범례 항목에 묶어 같이 토글한다. 두 시리즈 구분은
`series.id`(`"{코너}::headcount"`/`"{코너}::satisfaction"`)로 유지하고,
이 차트 전용 툴팁 포매터(`combinedTrendTooltipFormatter`)가 `seriesId`로
"식수"/"만족도" 라벨을 붙여 렌더한다.

### 40.8 코너 코어층 — 메뉴 통제 선호도 버그 수정 + 코너간 비교 뷰

**버그**: `corner_core_layer.py::build_menu_controlled_meal_log_rows`가
"경합 상황"(같은 날 같은 메뉴가 2개 이상 코너에서) 판정을 `meal_log`가
아니라 `weekly_menu_plan`의 `MenuRole.MAIN` 행에서만 찾았다 —
`weekly_menu_plan`은 이미 다른 곳(`_corner_id_by_menu_from_meal_log`
주석)에서 "누락되기 쉬워 안 쓴다"고 명시된 소스라, 계획표에 없거나
MAIN이 아닌 SIDE로 잘못 분류된 코너는 실제 `meal_log`에 데이터가 있어도
조용히 빠졌다. 수정: `weekly_menu_plan` 의존을 완전히 제거하고
`meal_log`에서 직접 (날짜, menu_id)별 서로 다른 corner_id 수를 세어
경합 여부를 판정 — 실제 취식 사실을 근거로 삼는 쪽이 더 정확하다.
회귀 테스트(`test_menu_controlled_preference_detects_contested_menu_
without_weekly_menu_plan`)는 `/ingest/weekly-menu`를 아예 호출하지
않고도 정확한 비율이 나오는지 확인한다.

**비교 뷰**: 신규 슬림 엔드포인트 `GET /analysis/corners/core-layer-
summary` — 기존 `corner_core_layer_menu_pairs`처럼 코너 하나씩 개별
호출/쿼리하지 않고 `build_employee_corner_counts`(전체 코너를 이미 한
번에 스캔함)를 한 번만 호출한 뒤 `classify_corner_core_layer`만 코너별로
루프(메뉴 쌍 계산 생략, 비교 목적이라 가벼움). `CornerLoyaltySection`
상단에 전체 코너 비교 표(코너명/코어 이용자/유동층)를 추가.

### 40.9 피크타임 서브속도 — 코너별/메뉴별 비교 연계

`CornerAnalysisTab`의 코너별 피크타임 서브속도 추이(전체 코너 라인차트)와
`CornerLoyaltySection`의 메뉴별 피크타임 막대(선택된 코너 1개)가 완전히
분리된 코너 선택 상태를 각자 가지고 있었다 — `selectedCornerId`를
`CornerAnalysisTab`으로 끌어올려 `CornerLoyaltySection`은 props(`selectedCornerId`/
`onSelectCorner`)로 받게 바꾸고, "피크타임 서브" 섹션에 "코너별 비교"
(기존 라인차트)/"메뉴별 비교"(코너 선택 컨트롤 + 막대차트, `corner-menu-
throughput` 쿼리키가 `CornerLoyaltySection`과 동일해 React Query 캐시가
자동으로 중복 요청을 막음) 모드 토글을 추가했다. 코너를 어느 쪽에서
바꾸든 두 섹션이 같은 코너를 가리킨다.

**파일 요약**:

| 항목 | 파일 |
|---|---|
| 40.1 | `backend/app/services/voe_clustering.py`, `backend/app/api/dashboard.py`, `backend/tests/test_voe_clustering.py`(신규) |
| 40.2 | `backend/app/services/chat_grounding.py`, `backend/app/api/analysis.py`(신규 `top-by-headcount`) |
| 40.3 | `backend/app/services/holidays.py`, `backend/app/api/analysis.py`, `backend/app/api/simulation.py`, `frontend/src/api/client.ts`, `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/AnalysisPage.tsx` |
| 40.4 | `frontend/src/pages/HomePage.tsx` |
| 40.5 | `frontend/src/pages/AnalysisPage.tsx`(`WeeklyMenuReviewTab`) |
| 40.6 | `backend/app/api/analysis.py`(신규 `menu-performance/by-meal-type`), `frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx`(`MenuQuadrantTab`) |
| 40.7 | `frontend/src/pages/AnalysisPage.tsx`(`CornerAnalysisTab`) |
| 40.8 | `backend/app/services/corner_core_layer.py`, `backend/app/api/analysis.py`(신규 `corners/core-layer-summary`), `frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx`(`CornerLoyaltySection`) |
| 40.9 | `frontend/src/pages/AnalysisPage.tsx`(`CornerAnalysisTab`, `CornerLoyaltySection`) |

**검증**: 신규/변경 pytest 전부 통과(백엔드 265개), 프론트 `tsc -b &&
vite build` 클린, uvicorn+vite 띄운 뒤 Playwright로 실 데이터 기준
스크린샷 확인(패밀리데이 필터가 홈 차트에서 3색으로 분리되고 필터링
시 정확히 그 날짜만 남음, 히트맵 모든 셀 텍스트 대비 확인, 메뉴별 분석
끼니 필터 전환, 코너별 분석 범례가 코너명 하나씩만 뜨고 툴팁이 식수/
만족도를 정확히 구분, 코너 코어층 비교 표에 전체 코너가 한 번에
나오고(우연히 40.8 버그 수정 전엔 "데이터 없음"이던 메뉴 통제 선호도가
"43%, 271건 중 117건"으로 실데이터가 나오는 것도 이때 확인됨), 피크타임
서브속도 코너별/메뉴별 모드 전환 시 코너 선택이 두 섹션에서 일치).

## 41. 주간 식수 추이 — 조식/중식/석식 체크 필터 (2026-07)

`daily_division_stats`/`daily_corner_stats`는 이미 `(stat_date, division|
corner_id, meal_type)` 단위로 끼니별 행을 따로 저장하는데(6.2절), 홈
화면의 "주간 식수 추이"/"코너별 주간 식수 추이"는 그동안 이 행들을
끼니 구분 없이 항상 다 더해서만 보여줬다. 요청은 체크박스로 조식/중식/
석식을 골라 보고, 여러 개를 체크하면 그만큼 합산되게 해달라는 것.

**백엔드**: `dashboard.py::_compute_weekly_summary`와
`analysis.py::_load_corner_stats`(이 둘이 각각 `GET /dashboard/weekly-
summary`, `GET /analysis/corners`, `GET /analysis/corners/trend`의
공통 조회 함수)에 `meal_types: list[MealType] | None` 파라미터를
추가해 `meal_type.in_(meal_types)` 필터를 얹었다. 값을 생략하면(빈
리스트/`None`) 기존과 동일하게 전체 합산 — 하위호환.

**주의(Query 기본값 함정)**: `corner_analysis`(`GET /analysis/corners`)
는 FastAPI 라우트일 뿐 아니라 `chat_grounding.py`/`dashboard.py`에서
평범한 파이썬 함수로도 직접 호출된다. 이런 직접 호출 경로에서는
FastAPI가 `Query(default=None, ...)`를 실제 `None`으로 풀어주지
않고 `Query` 객체 자체가 그대로 인자에 들어온다 — 이 객체는 `bool()`이
참이라 `if meal_types:` 분기를 타서 `.in_(Query객체)`가 SQLAlchemy
`ArgumentError`로 터진다. 이미 있던 `classification`/`exclude_take_out`
파라미터는 우연히 비교 연산(`==`)에만 쓰여 이 문제가 드러나지 않았을
뿐, 같은 함정을 안고 있다. 해결: `meal_types`는 `Query(...)` 래퍼 없이
plain `None` 기본값으로 선언(다른 곳(`corner_analysis_trend`, `weekly_
summary`)은 직접 호출되지 않아 `Query(...)`를 그대로 둬도 안전함을
확인 후 유지).

**프론트**: `HomePage.tsx`에 `mealTypeFilter: MealType[]` state(기본값
3개 전부 체크 — 기존 "전체 합산" 동작과 동일)와 체크박스 3개를 분류
`SegmentedControl` 옆에 추가. 최소 1개는 항상 체크돼 있어야 하며(다
끄면 "필터 없음"과 구분이 안 돼 혼동되므로 `toggleMealType`이 마지막
1개는 해제를 무시), `weekly`/`cornerTrend` 두 쿼리 모두 `mealTypeFilter`를
쿼리키에 포함해 체크 조합이 바뀔 때마다 새로 조회한다. `qs()` 헬퍼
(`api/client.ts`)는 배열 값을 반복 쿼리 파라미터(`meal_types=조식&
meal_types=중식`)로 직렬화하도록 확장했다.

**검증**: 신규 pytest 2건(`test_weekly_summary_filters_by_meal_types`,
`test_corner_analysis_trend_filters_by_meal_types` — 조식만/조식+중식
합산/미필터 3가지 케이스 확인) 포함 전체 267개 통과, 프론트 `tsc -b &&
vite build` 클린. uvicorn 재시작 후(코드 수정이 실행 중이던 구 프로세스에
반영 안 돼 있었던 걸 재시작으로 확인) Playwright로 실 데이터 기준 확인:
해당 주는 실제로 전부 중식 데이터라 조식만 체크 시 누적 식수가
488→0으로, 중식+석식 체크 시 488 그대로 나오는 것을 확인.

**파일 요약**: `backend/app/api/dashboard.py`, `backend/app/api/analysis.py`,
`backend/tests/test_api_ingest_and_analysis.py`, `frontend/src/api/client.ts`,
`frontend/src/pages/HomePage.tsx`.

## 42. 홈 패밀리데이 월별 추이 · 메뉴별 분석 4분면 재설계 · 코너별 분석 그래프 재구성 (2026-07)

프론트엔드만 수정한 라운드(백엔드 변경 없음 — 기존 엔드포인트가 이미 필요한
데이터를 다 제공했다).

### 42.1 홈 — 패밀리데이 선택 시 월별 추이

패밀리데이는 한 주에 최대 하루뿐이라 "주간 식수 추이"에 평일과 나란히
그려봐야 비교가 안 된다는 피드백 — 패밀리데이를 선택하면 "주간 식수 추이"
카드 안에 월별 패밀리데이끼리의 식수 추이를 추가로 보여준다.
`HomePage.tsx`에 `familyDayTrend` 쿼리(`classification === "패밀리데이"`일
때만 활성화)를 추가했는데, 새 엔드포인트 없이 이미 있던
`GET /analysis/divisions`(`api.divisionAnalysis`, 40.3절에서 이미
`classification=패밀리데이` 필터를 지원하도록 확장됨)를 `granularity=
monthly`, 최근 1년 범위로 호출해 재사용했다 — 본사/계열사/기타별로 오는
행을 프론트에서 월(period) 기준으로 합산해 하나의 라인차트로 그린다.

### 42.2 메뉴별 분석 — 4분면 산점도 → 분면별 막대 패널

기존엔 전체 메뉴를 한 좌표평면에 산점도(원)로 겹쳐 그렸는데, 메뉴 수가
많아지면 원끼리 다 겹쳐 어떤 메뉴인지 구분이 안 된다는 피드백. 산점도 +
markLine 대신 분면(인기메뉴/숨은강자/개선시급/퇴출후보/표본부족)마다 별도
패널을 만들어 가로 막대 그래프로 그린다(`buildQuadrantBarOption`,
`AnalysisPage.tsx`) — y축 자체가 메뉴명(카테고리 축)이라 항상 이름이
막대 옆에 붙고, 막대끼리는 절대 겹치지 않는다. 막대 길이=수요(1회 제공당
평균 식수), 막대 끝 라벨=만족도. 분면별로 수요 내림차순 정렬 후 "표시
개수" 선택(5/10/20/전체, `quadrantLimit` state)만큼 잘라서 보여준다 —
이 개수 제한은 다섯 분면 모두에 동일하게 적용(분면별 개별 설정은 UI
복잡도 대비 실익이 적어 배제). 최근 {LOW_APPEARANCE_THRESHOLD}회 미만
제공된 메뉴는 막대 투명도를 낮춰(0.45) 표본이 적다는 걸 계속 구분한다
(기존 산점도의 점선 테두리 표현을 막대 opacity로 대체). 기존 분면 토글
(범례 클릭으로 특정 분류만 보기), 기준값 슬라이더, 코너별 상세 표는
그대로 유지.

### 42.3 코너별 분석 — 그래프 재구성

**이용자 수 & 만족도 통합**: 기존엔 "월간 식수·만족도 통합 그래프"(항상
월간 고정)와 "코너별 만족도·피크타임 서브속도 추이"(주간/월간/주차별
선택 가능, 만족도만 표시)가 따로 있어 화면에 비슷한 성격의 그래프가 두
번 나왔다. 이제 "코너별 이용자 수 · 만족도 추이" 하나로 합치고, 기존에
아래쪽 그래프에서만 되던 기간 단위 선택(주간/월간/주차별)을 그대로
적용한다 — `cornerAnalysisTrend`가 이미 코너·기간별 headcount와
avg_taste_score를 함께 반환하므로 새 쿼리 없이 기존 `activePeriods`/
`activeByCorner`(주간·월간·주차별 공용으로 이미 있던 변수)를 그대로 재사용.
이로써 이전에 있던 `monthlyTrendQuery`(항상 월간 고정 별도 쿼리)는
제거됐다 — 중복 쿼리가 없어져 더 단순해짐.

**피크타임 서브속도 & 점유율 통합**: 기존엔 "코너별 점유율"이 (선택 기간
전체 누적 기준) 파이차트로 서브속도 추이와 완전히 분리돼 있었다. 이제
"피크타임 서브속도 · 코너별 점유율 추이"로 합쳐 기간별(주간/월간/주차별)
꺾은선 듀얼축 그래프 하나로 그린다 — 왼쪽 축=피크타임 분당 서브, 오른쪽
축=점유율(%). 점유율은 새 엔드포인트 없이 프론트에서 그때그때 계산한다:
공유 대상 코너(Take Out·그린미트·미캠회관(전골) 제외 — 기존 파이차트와
동일한 착석 취식 코너만 비교) 기준으로 기간별 헤드카운트 합계를 구하고
(`periodShareTotals`), 코너별 헤드카운트/합계×100을 점유율 시리즈로 쓴다.
"코너별 비교"(이 통합 그래프)/"메뉴별 비교"(선택 코너의 메뉴별 막대,
기존 그대로) 토글은 유지.

두 통합 그래프 모두 식수·만족도(또는 서브속도·점유율) 두 시리즈가 범례
단순화를 위해 코너명 하나를 공유하므로(40.7절과 동일한 이유),
`seriesId`(`"{코너}::headcount"` 등)로 지표를 구분하는 툴팁 포매터
(`buildMetricTooltipFormatter`)를 공용화해 재사용했다. 만족도 전용
`평균 만족도` 표시/숨김 토글 버튼은 이제 항상 함께 보여주므로 제거.

**검증**: 신규 pytest 없음(백엔드 무변경, 기존 267개 그대로 통과 확인).
프론트 `tsc -b && vite build` 클린. uvicorn+vite로 Playwright 확인: 홈에서
패밀리데이 선택 시 월별 추이(2026-07, 3명)가 실제로 나타남, 메뉴별
분석에서 인기메뉴/숨은강자/개선시급/표본부족 4~5개 패널이 겹침 없이
메뉴명과 함께 표시되고 "표시 개수" 10개로 잘렸음을 확인(퇴출후보는
"해당 없음"으로 정상 표시), 코너별 분석에서 이용자수·만족도 듀얼축
그래프 1개와 피크타임서브속도·점유율 듀얼축 그래프 1개(그린미트 제외
4개 코너)가 각각 통합돼 나오는 것을 확인.

**파일 요약**: `frontend/src/pages/HomePage.tsx`,
`frontend/src/pages/AnalysisPage.tsx`(`MenuQuadrantTab`, `CornerAnalysisTab`).

### 42.4 메뉴별 분석 4분면 — 막대 → 점(산점도)으로 재수정 + 코너명 표기

42.2에서 막대 그래프로 바꿨더니 "막대 말고 점으로 보여달라"는 재요청.
분면별 패널 분리(겹침 완화 효과의 핵심)는 그대로 유지하되, 각 패널
내부를 막대 대신 원래 방식인 산점도(x=수요, y=만족도)로 되돌렸다
(`buildQuadrantScatterOption`, `buildQuadrantBarOption` 대체). 분면당
항목 수가 이미 5~20개로 적어(42.2 표시개수 제한 유지) 전체를 한 좌표에
욱여넣던 이전 버전보다는 겹침이 훨씬 덜하다. 추가로 "메뉴 보여줄 때
코너명도 같이 표기해달라"는 요청 반영 — 같은 메뉴명이 여러 코너에서
나올 수 있어(`MenuPerformanceRow.corner_name`) 점 옆 라벨과 툴팁 모두
"메뉴명 (코너명)" 형식으로 통일했다. 그래도 가까운 점끼리 라벨이 겹칠
수 있어 ECharts 6 `labelLayout: { moveOverlap: "shiftY" }`로 세로 방향
자동 밀어내기를 적용했다(완전한 겹침 방지는 아니고 완화).

**검증**: 프론트 `tsc -b && vite build` 클린. Playwright로 실 데이터
확인 — 인기메뉴/숨은강자/개선시급/표본부족 패널 모두 점으로 표시되고
각 점 옆에 "메뉴명 (코너명)"(예: "돼지불고기 (한식)", "짜장면 (분식)")이
붙어 있음을 확인.

**파일 요약**: `frontend/src/pages/AnalysisPage.tsx`(`MenuQuadrantTab`).

## 43. 4분면 라벨 겹침 완화 + 분류 로직 확장(만족도 추세·메뉴 로열티) (2026-07)

42.4에서 라벨을 항상 붙이게 했지만 분면 하나에 점이 몰리면(표본부족 등)
여전히 겹쳐서 못 읽는다는 재피드백, 그리고 4분면 분류 로직 자체에 대한
개선 요청 2건 — (1) 개선시급/퇴출후보가 "직전 대비 만족도 하락"도
반영했으면 함, (2) 식수가 낮아도 그 메뉴만 꾸준히 찾는 고정 고객이 있으면
퇴출후보로 몰지 말 것.

### 43.1 라벨 겹침 — hideOverlap + 정렬 + 동적 높이

`buildQuadrantScatterOption`(`AnalysisPage.tsx`)의 `labelLayout`에 기존
`moveOverlap: "shiftY"`와 함께 `hideOverlap: true`를 추가했다 — 밀어내기로
안 되면 아예 숨겨서(겹쳐서 못 읽는 것보다 일부만 보이는 게 낫다) 가독성을
확보한다. `hideOverlap`은 데이터 배열 뒤쪽 요소의 라벨을 먼저 숨기므로,
표본이 더 믿을만한(제공 횟수가 많아 원이 큰) 점의 라벨이 우선 살아남도록
`appearance_count` 내림차순으로 정렬해 넘긴다. 패널 높이도 320px 고정에서
`Math.max(280, Math.min(560, 60 + limited.length * 22))`로 항목 수에 따라
늘어나게 바꿔 점이 많은 분면에 세로 공간을 더 준다.

### 43.2 4분면 분류 — 만족도 추세 + 메뉴 로열티 반영

**핵심 설계 결정(사용자 확인)**: 로열티(고정 고객) 판정 기준은 "그 메뉴가
나온 횟수 대비 그 사람이 실제로 주문한 비율" — 코너 코어층
(`corner_core_layer.py::classify_corner_core_layer`)의 "전체 방문 대비
이 코너 비중" 방식은 메뉴 단위에서는 안 맞는다(메뉴는 코너와 달리 가끔만
나와 비중이 항상 작게 나옴).

- `TrendDirection` enum을 `app/services/menu_performance.py`에서
  `app/models/enums.py`로 옮겼다(`menu_performance_stats.satisfaction_trend`
  컬럼에 저장되므로 다른 DB 저장 enum과 같은 자리에 둠 — `menu_performance.py`
  는 하위호환을 위해 그대로 재수출).
- `aggregation.py`의 private `_trend`를 `menu_performance.py::compute_trend`
  (순수함수)로 공개 이전 — 만족도 추세뿐 아니라 기존 `diagnose_headcount_
  decline`의 점유율 추세에도 그대로 재사용.
- 신규 `MenuLoyaltyResult`/`classify_menu_loyalty`(`menu_performance.py`,
  순수함수) — 코너 코어층과 같은 이중 임계값 구조(절대 주문횟수 AND 비율)
  지만 분모가 "그 메뉴가 나온 횟수"(`menu_appearance_count`)다. 기본값
  `min_order_count=2`, `min_order_ratio=0.5`(설정 가능,
  `config.py::menu_loyalty_min_order_count/ratio`). 이 조건을 만족하는
  직원이 `menu_loyalty_min_employees`(기본 2)명 이상이어야
  `has_loyal_following=True`.
- `classify_menu_quadrant`에 `satisfaction_trend`/`has_loyal_following`
  키워드 인자 추가(기본값 없음, 호출부가 명시적으로 넘기게 강제):
  ```python
  satisfaction_ok = satisfaction >= satisfaction_threshold and satisfaction_trend != TrendDirection.DOWN
  if high_demand:
      return POPULAR if satisfaction_ok else NEEDS_IMPROVEMENT
  if has_loyal_following:
      return HIDDEN_GEM  # 만족도와 무관하게 우선
  return HIDDEN_GEM if satisfaction_ok else REMOVAL_CANDIDATE
  ```
  만족도가 기준 이상이어도 하락 추세면 "양호"로 인정하지 않아 개선시급/
  퇴출후보로 조기 경보되고, 로열티 신호는 저수요 분면(퇴출후보 vs
  숨은강자)에서만 만족도보다 우선한다 — 이미 고수요인 메뉴는 로열티와
  무관하게 만족도 기준대로 분류된다("식수가 낮아도"라는 사용자 전제가
  고수요 분면엔 적용되지 않으므로).
- **만족도 추세 계산**(`aggregation.py::compute_menu_satisfaction_trends`,
  공개 함수 — `analysis.py::menu_performance_by_meal_type`에서도 재사용):
  호출부의 `period_start`/`period_end`가 무엇이든 상관없이 항상
  `period_end` 기준 최근/직전 `menu_trend_window_days`일(기본 30일)을
  비교한다(패밀리데이처럼 표본이 희소한 경우와 무관하게 항상 같은 기준).
  두 구간 중 하나라도 평가가 없으면 "유지"로 본다(보수적 기본값, 잘못된
  하락 판정 방지). 쿼리 1번만 추가(menu_id/taste_score/eaten_at, 두
  구간을 합친 범위를 한 번에 가져와 파이썬에서 나눔).
- **로열티 계산**: `employee_menu_counts`(사번별 메뉴별 주문횟수)는 새
  쿼리 없이 이미 읽어둔 `logs`/`by_menu`에서 바로 집계한다 —
  `aggregate_menu_performance`/`menu_performance_by_meal_type` 둘 다 이미
  기간 전체 `MealLog`를 한 번에 읽어두므로 무료로 얻는다.
- **저장**: `menu_performance_stats`에 `satisfaction_trend`(nullable
  enum)/`has_loyal_following`(bool, default False) 컬럼 추가(마이그레이션
  `d6ad762b4b92`) — `quadrant_label`처럼 같은 recompute 시점에 계산해
  저장해야 프론트가 슬라이더로 기준값을 바꿀 때도 서버 재조회 없이 즉시
  재분류를 미러링할 수 있다(`classifyQuadrantClient`가 이 두 값을 그대로
  받아 백엔드와 동일한 분기를 탐).
- 프론트: 툴팁에 "만족도 추세: 하락"/"고정 고객 있음"을 해당하는 경우만
  추가로 보여준다.

**검증**: 백엔드 신규 유닛테스트 12건(`compute_trend`, `classify_menu_
loyalty` 임계값/정렬/빈 배열, `classify_menu_quadrant`의 하락 추세
다운그레이드 2건 + 로열티 오버라이드 2건) + 통합테스트 3건(`aggregate_
menu_performance`가 로열티 있는 저수요 메뉴를 실제로 숨은강자로 분류,
직전/최근 만족도가 뚜렷이 갈리는 메뉴의 `satisfaction_trend`가 "하락"으로
저장, `menu_performance_by_meal_type` 응답에도 두 필드가 포함) 포함 전체
279개 통과. 프론트 `tsc -b && vite build` 클린. uvicorn 재시작 후(코드
변경이 기존 프로세스에 반영 안 됨) 실 데이터로 재계산 → Playwright 확인:
표본부족 패널(10개 점)에서 라벨이 이전처럼 다 겹치지 않고 일부만 자동
숨겨져 읽을 수 있음, 실 데이터에 이미 로열티 고객이 있는 메뉴 다수가
`has_loyal_following=true`로 나옴(예: 짜장면·스테이크는 숨은강자로 유지,
제육볶음처럼 고수요인 메뉴는 로열티와 무관하게 개선시급 그대로 — 로열티가
저수요 분면에서만 작동하는 설계가 실데이터에서도 의도대로 동작함을 확인).

**파일 요약**: `backend/app/models/enums.py`, `backend/app/models/stats.py`,
`backend/alembic/versions/d6ad762b4b92_*.py`(신규), `backend/app/config.py`,
`backend/app/services/menu_performance.py`, `backend/app/services/
aggregation.py`, `backend/app/api/analysis.py`, `backend/tests/
test_menu_performance.py`, `backend/tests/test_api_ingest_and_analysis.py`,
`frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx`.

## 44. "개선 필요 포인트" 카드 500 에러 수정 (2026-08)

홈 화면 "개선 필요 포인트" 카드에서 Internal Server Error 신고. 원인:
`GET /dashboard/improvement-points`(`dashboard.py::improvement_points`)가
VOE 축 포인트마다 `improvement_points.py::summarize_voe_comments`를 호출해
사내 LLM에 주관식 코멘트 요약을 요청하는데, 이 LLM 호출(`InternalLLMClient.
chat_complete` → `httpx` POST) 주변에 예외처리가 전혀 없었다 — 게이트웨이가
타임아웃/연결실패/오류응답을 내면 예외가 그대로 전파돼 카드 전체가 500으로
죽었다. `INTERNAL_LLM_BASE_URL`을 불가 도달 주소로 두고 실제로 재현 확인함
(`httpx.ConnectError` 전파 → 500).

이전 라운드에 `dashboard.py::recompute_voe_clusters`에서 이미 한 번 같은
유형의 버그를 고친 전례가 있었는데(그 수정 주석: *"이 경로는 사내 LLM
임베딩 게이트웨이 호출을 포함해 외부 의존성이 많다 — 원인 불명 500 대신
어떤 예외였는지 detail에 남겨 디버깅 가능하게 한다"*), `improvement_
points()`에는 반영이 안 돼 있었다.

**수정 방식은 그 전례와 다르게 택함**: `recompute_voe_clusters`는 POST
재계산 전용이라 실패 시 502로 명확히 알리는 게 맞지만, `improvement_
points()`는 혼잡도/만족도/VOE 세 축을 한 번에 반환하는 GET이고 VOE 요약은
그중 "있으면 좋은" 부가 정보다 — LLM 호출 하나가 실패했다고 이미 계산된
혼잡도/만족도 포인트까지 전부 못 보여주는 건 과하다. 그래서 `summarize_
voe_comments`의 LLM 호출을 `try/except Exception`으로 감싸고, 실패 시
(LLM 미설정 시와 동일하게) `_fallback_voe_summary`(원문 코멘트 예시)로
조용히 대체하는 쪽을 택했다 — 나머지 두 축은 정상 응답. 겸사겸사
`_fallback_voe_summary`의 안내 문구도 "사내 LLM 미설정"(설정은 됐지만
호출만 실패한 경우엔 부정확한 말)에서 "사내 LLM 요약 사용 불가"로
고쳤다 — 이 함수가 이제 "미설정"과 "설정했지만 실패" 두 경우 모두에
재사용되기 때문.

**조사 중 발견한 별개 버그(이번 범위 아님)**: `corner_analysis`
(analysis.py)가 라우트가 아니라 `chat_grounding.py`/`dashboard.py`에서
일반 파이썬 함수로 직접 호출되는데, `exclude_take_out` 파라미터가 여전히
`Query(default=False, ...)` 기본값이라 직접 호출 시 `Query` 객체 자체가
truthy로 들어와 항상 `exclude_take_out=True`처럼 동작한다(Take Out이
항상 제외됨, 의도한 기본값과 반대) — 크래시는 안 나는 조용한 동작
오류라 이번엔 범위에서 제외(사용자 확인). 매일 새벽 스케줄러가 집계하는
기간(어제 기준 180일)과 홈 화면이 조회하는 기간(오늘 기준 180일)이 하루
어긋나 "만족도 개선필요" 축이 조용히 빈 결과만 나올 수 있는 것도 별개
건으로 남겨둠.

**검증**: 회귀 테스트 1건 추가(`test_summarize_voe_comments_falls_back_
when_llm_call_raises` — `is_configured=True`인 클라이언트의 `chat_complete`
가 예외를 던지도록 monkeypatch, 폴백 문구로 정상 반환되는지 확인) 포함
전체 280개 통과. uvicorn을 `INTERNAL_LLM_BASE_URL=http://127.0.0.1:59999`
(불가 도달)로 띄운 채 `GET /api/dashboard/improvement-points` 재현 —
더는 500이 아니라 200으로 응답하고 VOE 포인트만 폴백 문구가 붙는 것을
확인. 정상(미설정) 상태로 재기동 후 Playwright로 홈 화면 확인 시
`improvement-points` 요청이 200이고 페이지 에러 없음.

**파일 요약**: `backend/app/services/improvement_points.py`,
`backend/tests/test_improvement_points.py`.

## 45. "전체 예측 비교"/"개선 필요 포인트" 500 재신고 — 회귀 수정 + 실제 원인 (2026-08)

사용자가 본인 uvicorn(8080)에서 "주간식단표관리 → 전체 예측 비교"와
"홈 → 개선 필요 포인트" 두 화면에서만 API 500이 뜬다고 신고(다른 화면은
정상). 두 가지를 확인했다.

**1) 확정된 회귀(코드 버그, 수정함)**: `weekly_menu_prediction.py::
compute_predicted_numbers`가 `simulation.py::_baseline_headcount`를 호출할
때 `is_holiday`(**bool**)를 넘기고 있었는데, `_baseline_headcount`의
시그니처는 이전 "패밀리데이" 라운드에서 `classification: DayClassification`
(enum)으로 바뀌었다 — `what_if`/`congestion_forecast`(simulation.py)는 그때
같이 고쳐졌지만 이 파일의 호출부는 빠졌던 것. `classification ==
DayClassification.HOLIDAY` 비교는 bool을 받아도 예외 없이 그냥 False로
평가돼(파이썬은 타입이 달라도 `==` 자체는 안 터짐) 크래시는 안 나고,
대신 **주말/공휴일/패밀리데이에 계획된 메뉴도 매번 "평일 이력"만으로
baseline을 계산하는 조용한 오류**였다 — `_baseline_headcount`가 항상
`is_holiday.is_(False)` 풀에서만 이력을 가져왔기 때문. 회귀 테스트로
재현 확인: 평일 이력(2명)과 주말(토요일) 이력(20명)을 뚜렷이 다르게
시딩하고, 실제 계획일이 토요일인 슬롯의 예측 식수를 확인하면 수정 전엔
2명(평일 이력만 사용, 틀림), 수정 후엔 20명대(주말 이력 정상 사용)로
나온다(`test_predicted_impact_uses_holiday_history_for_holiday_plan_date`).
`holiday_svc.is_holiday(plan.plan_date)` 대신 `holiday_svc.classify(plan.
plan_date)`로 교체해 `what_if`/`congestion_forecast`와 동일한 패턴으로
맞췄다.

**2) 실제 500의 원인(코드 버그 아님, 별도 스크래치 DB로 재현·확정)**: 위
회귀는 `==` 비교가 안전해 크래시를 안 낸다 — 그래서 이 세션의 dev DB(이미
`alembic upgrade head` 적용됨)에서는 두 엔드포인트 모두 200으로 정상
응답했다. 진짜 500 원인을 확인하려고 별도의 1회성 스크래치 Postgres DB를
만들어 `alembic upgrade head` 후 `alembic downgrade -1`로 **바로 직전
라운드(43번 항목)에서 추가한 `d6ad762b4b92`(menu_performance_stats에
`satisfaction_trend`/`has_loyal_following` 컬럼 추가) 마이그레이션만
빠진 상태**를 재현해보니, `MenuPerformanceStats`를 조회하는 쿼리마다
`psycopg.errors.UndefinedColumn: column menu_performance_stats.
satisfaction_trend does not exist`가 그대로 전파돼 500이 났다(스크래치
DB는 확인 후 즉시 삭제). `compute_predicted_numbers`(전체 예측 비교의
숫자 계산 경로)와 `analysis.py::menu_performance`(개선 필요 포인트가
만족도 축에 쓰는 함수) 둘 다 `MenuPerformanceStats`를 조회하므로 이
설명과 정확히 들어맞는다 — **사용자가 최신 코드를 pull한 뒤 자신의
DB에는 아직 `alembic upgrade head`를 안 돌린 상태로 8080 서버를 띄운
것으로 보인다.** 코드로 고칠 수 있는 문제가 아니라 배포 절차 문제라,
사용자에게 `cd backend && alembic upgrade head`를 실행한 뒤 재기동해
달라고 안내했다.

**검증**: 신규 회귀 테스트 포함 전체 281개 통과. uvicorn 재기동 후 실제
데이터로 `GET /analysis/weekly-menu/predicted-impact-summary`, `GET
/dashboard/improvement-points` 둘 다 200 확인. Playwright로 "분석 →
주간 식단표 관리" 탭에서 "전체 예측 비교" 버튼을 실제로 클릭해 콘솔/
네트워크 에러 없이 예측 요약이 렌더되는 것과, 홈 화면 전체가 콘솔/네트워크
에러 없이 뜨는 것을 확인.

**파일 요약**: `backend/app/services/weekly_menu_prediction.py`,
`backend/tests/test_api_ingest_and_analysis.py`.

## 46. "식당 AX 대시보드 수정 스펙" — 대부분 이미 구현돼 있었음 확인 + 남은 갭 처리 (2026-08)

사용자가 홈/분석(메뉴별·코너별·사용자 분석)/VOE 탭 개편 스펙 문서를 전달.
조사 결과 상당 부분이 **이미 §39("식당 AX 대시보드 개선 12개 항목",
2026-07)·§42에서 구현돼 있었다** — 스펙 문서가 그 이전 버전으로 보인다.
항목별로 "이미 됨" / "진짜 갭" / "최근 결정과 충돌"로 나눠 처리했다.

**충돌 2건은 사용자에게 직접 확인 후 진행**:
- 메뉴별 분석 사분면(46.5): 스펙은 X=만족도/Y=수요 + 단일 차트를 요구했는데,
  기존(X=수요/Y=만족도, 분면별 패널 분리)은 39.6에서 사용자가 직접 확인해
  정한 축이고 패널 분리는 42.2/42.4에서 겹침 문제를 두 번 고친 결과였다.
  사용자 확인: "한눈에 보고 싶은 게 더 큼" → 패널 분리를 버리고 스펙대로
  단일 통합 차트로 재설계(축도 반전), 겹침 완화는 패널 분리 대신 이후
  라운드에 추가된 `labelLayout.hideOverlap`(43번, 패널 분리 이전엔 없던
  기능)에 맡긴다.
- 코너별 분석 통합 그래프(46.3): 스펙은 "이용자 수 vs 서브속도" 토글을
  요구했는데, 이미 두 고정 조합(①식수+만족도, ②서브속도+점유율) 통합
  그래프로 정리돼 있었다(42.3, 그때 비슷한 그래프 여러 개를 줄이려 이렇게
  통합함). 사용자 확인: "지표 선택형 단일 그래프로 재설계" → 두 고정
  조합 차트를 없애고 좌/우 축 지표를 사용자가 직접 고르는 단일 그래프
  하나로 대체.

### 46.1 홈 — 코너별 주간 식수 추이 툴팁

`HomePage.tsx::cornerTrendOption`에 로컬 `tooltip.formatter`(
`cornerTrendTooltipFormatter`)를 새로 추가 — 식수를 `Math.round`로 정수
표시하고, 그날 그 코너의 메인메뉴를 다음 줄에 덧붙인다. 다른 차트가
공유하는 `axisTooltipFormatter`/`formatTooltipNumber`(소수 2자리, 만족도
등에도 쓰임)는 그대로 두고 이 차트에만 로컬 포맷터를 적용했다 — 전역
포맷을 바꾸면 다른 곳의 소수 표기가 깨진다. 메뉴 매핑은 `AnalysisPage.tsx`
가 이미 쓰던 패턴(`api.cornerMainMenuByDate` → `Map<"${corner_id}|
${date}", menu_name>`)을 그대로 이식 — 신규 쿼리 1개 추가.

### 46.2 홈 — 메뉴 하이라이트 날짜 + 레이아웃

`menu_highlights.py::compute_menu_satisfaction_trends`가 내부적으로 이미
계산하던 `recent_week`(그 메뉴가 마지막으로 나온 주의 월요일)를 그동안
버리고 있었다 — `MenuTrendEntry`에 필드로 담아 `dashboard.py`
직렬화(`"date"`)에 노출만 하면 됐다(새 계산 없음). 프론트는 급상승/급하락
을 `grid-cols-2` 한 행으로, 신메뉴는 별도 행(아래)으로 재배치하고 각
항목에 "날짜"(M/D) 컬럼 추가.

### 46.3 코너별 분석 — 지표 선택형 단일 그래프

`CornerAnalysisTab`의 `headcountSatisfactionOption`(식수+만족도)과
`throughputShareOption`(서브속도+점유율) 두 함수를 없애고
`cornerMetricOption` 하나로 통합. 왼쪽/오른쪽 축 드롭다운(식수/만족도/
서브속도/점유율 중 선택, 같은 지표 중복 선택 시 자동으로 서로 교체)으로
어떤 조합이든 볼 수 있다 — `cornerAnalysisTrend`가 이미 식수/만족도/
서브속도를 한 응답에 반환하고 점유율은 기존처럼 프론트에서 파생하므로
신규 쿼리 없음. 서브속도가 축 중 하나면 "전체 평균" 회색 점선을 데이터
없는 전용 시리즈(코너별 중복 방지)에 markLine으로 표시.

### 46.4 코너별 분석 — 피크타임 서브속도 메뉴별 비교 Top5/Bottom5

`buildMenuThroughputOption`(전체 메뉴 막대)은 `CornerLoyaltySection`에서는
그대로 두고(범위 밖), `CornerAnalysisTab`의 "메뉴별 비교" 모드만 신규
`buildMenuThroughputRankingOption`(막대 색이 리스트 전체 고정)로 서브
가장 느린 Top5(`--critical`, 빨강)/가장 빠른 Top5(`--good`, 초록) 두
리스트를 나란히 보여주도록 교체 — 프론트에서 `avg_throughput` 기준 정렬
후 슬라이스만 하면 되므로 백엔드 변경 없음.

### 46.5 메뉴별 분석 — 단일 통합 사분면 차트

`buildQuadrantScatterOption`(분면별 패널 반복 렌더) → `buildUnified
QuadrantOption`(하나의 산점도) 교체. X=만족도, Y=수요로 축 반전. 분면별로
시리즈를 나눠(기존 분면 필터 버튼이 그대로 어떤 시리즈를 렌더할지 결정)
한 차트 안에 겹쳐 그리고, 배경엔 데이터 없는 전용 시리즈에 `markArea`(4개
사분면 음영+라벨)와 `markLine`(기준값 십자선)을 얹었다. 배경 음영은 순수
수요/만족도 임계값 기준이라, 만족도 추세 하락·로열티로 실제 분류가
override된 점은 점 색(진짜 분류)과 배경 음영이 어긋나 보일 수 있다 —
의도된 것으로, 툴팁에 추세/로열티 이유를 표기해 설명한다. 겹침 완화는
기존 `labelLayout: { hideOverlap: true, moveOverlap: "shiftY" }`와
`appearance_count` 내림차순 정렬 그대로 유지.

### 46.6 코너 코어층 — Take Out 제외

`corner_core_layer.py::build_employee_corner_counts`에 `exclude_corner_
ids` 키워드 인자 추가(기존 호출부는 기본값 `None`이라 영향 없음).
`analysis.py::corner_core_layer_summary`에서 Take Out corner_id를 조회해
요약 표 행 목록과 `employee_corner_counts` 분모 양쪽에서 제외 — 분모만
빼면 Take Out 자체는 안 보여도 다른 코너의 `corner_share`가 왜곡되므로
반드시 같이 빼야 한다. 그린미트/미캠회관(전골)은 스펙에 명시되지 않아
이번엔 포함 상태 유지. 회귀 테스트로 확인: Take Out 방문을 대량으로
섞어도(분모 오염 시나리오) 다른 코너의 코어층 인원수가 그대로인지 검증.

### 46.7 사용자 분석 — 라인차트 + 표 아코디언

`DivisionAnalysisSection`의 막대 시리즈를 라인(`type: "line"`)으로 교체,
하단 표를 `CornerAnalysisTab`의 `showCornerTable` 패턴과 동일하게
`useState(false)` + 토글 버튼으로 기본 접힘 처리.

### 46.8 VOE — 코너·메뉴 매핑 + 최다 코너/메뉴 요약

`_compute_voe_by_category`가 `CornerMaster`만 join하던 것에 `MenuMaster`
outer join(`MealLog.menu_id`가 nullable) 추가, 코멘트 엔트리에 `menu_name`
필드 추가. 프론트 코멘트 표는 "코너"/"코멘트" 2컬럼에서 "코너·메뉴"(
`코너명 · 메뉴명` 병합 표기)/"코멘트"로 변경. "이달의 VOE 최다 코너/메뉴"
요약 카드는 새 백엔드 집계 없이, 이미 받아온 카테고리별 코멘트를 프론트
에서 dedupe(다중 라벨로 같은 코멘트가 여러 카테고리에 겹쳐 잡히므로) 후
`corner_name`/`menu_name` 기준 tally해 최다 1건씩 뽑는다.

**검증**: 신규 회귀 테스트 3건(메뉴 하이라이트 date 필드, 코어층 Take
Out 분모 오염 방지, VOE menu_name 노출) 포함 전체 283개 통과. 프론트
`tsc -b && vite build` 클린. uvicorn+vite로 Playwright 확인 — 홈 툴팁
정수+메뉴 표시, 하이라이트 카드 2단+날짜, 메뉴별 분석 단일 사분면(배경
음영+십자선+분면별 색), 코너별 분석 지표 드롭다운 4개 조합, 서브속도
Top5/Bottom5(빨강/초록), 코어층 표에서 Take Out 행 사라짐, 사용자 분석
라인차트+표 접기, VOE "코너·메뉴" 컬럼 + "이달의 VOE 최다 코너/메뉴"
카드(그린미트 11건/닭가슴살샐러드 10건 확인) 모두 콘솔/네트워크 에러
없이 정상 렌더 확인.

**파일 요약**: `backend/app/services/menu_highlights.py`,
`backend/app/services/corner_core_layer.py`, `backend/app/api/
analysis.py`, `backend/app/api/dashboard.py`, `backend/tests/
test_api_ingest_and_analysis.py`, `frontend/src/api/client.ts`,
`frontend/src/pages/HomePage.tsx`, `frontend/src/pages/AnalysisPage.tsx`.

---

## 47. 화면을 5개 축으로 재편 — 네비게이션 교체 + 기능 강등 (2026-08)

담당자 협의에서 정한 5개 축으로 화면 구조를 바꿨다. **"기존 기능은 분석용으로
데이터는 가지고 있되 UI에 표현되는 것들을 정리한다"**는 원칙이라, 이번 작업에서
지운 것은 **화면 뿐이고 API·집계 로직은 하나도 건드리지 않았다.**

### 47.1 새 탭 구성

| 이전 | 이후 |
|---|---|
| 홈 / 분석(서브탭 5개) / 시뮬레이션 / Agent 채팅 | **현황 / 메뉴 편성·운영 / 만족도·VoE / Agent 채팅 / 관리** |

- **현황** — 요약 카드 4개, 개선 필요 포인트, 주간 식수 추이, 통합 식수 추이(1-B),
  금주 예상 식수·점유율·대기시간(1-C/1-D), **코너별 지표 비교**(분석>코너별에서 이동)
- **메뉴 편성·운영** — 주간 식단표 관리, 부찬 조합별 만족도, 메뉴 동반 선택 쌍
- **만족도·VoE** — 메뉴 4분면, 월간 VOE 분류, VOE 클러스터링
- **Agent 채팅** — 변경 없음
- **관리** — 음식벡터 관리, 전체 취식 데이터 다운로드

`weekly-voe`(금주 메뉴 과거 VOE 상세)는 이전처럼 상단 내비에 없고 현황 카드
클릭으로만 진입한다.

### 47.2 시뮬레이션 탭을 없앨 수 있었던 이유

`SimulationPage`의 what-if 카드는 제목에 "신메뉴 코너"가 있었지만 **실제 입력
컨트롤이 없었고**(호출부도 `new_menu_corner_id`를 보내지 않았다), 날짜·끼니·
날씨는 현황의 금주 예상 식수 카드가 이미 갖고 있었다. 즉 이 탭의 유일한 고유
입력은 **"사내 행사" 토글 하나**였다. 그래서 주간 래퍼
`GET /simulation/congestion-forecast/weekly`에 `has_company_event: bool = False`를
추가하고(배수 0.90 — `what_if`가 쓰던 값 그대로), 현황 카드에 체크박스를 붙여
흡수한 뒤 `SimulationPage.tsx`를 삭제했다. **`POST /simulation/what-if` API는
백엔드에 그대로 남아 있다.**

### 47.3 UI에서 내린 기능 6개 + 2개

| 대상 | 살아있는 API |
|---|---|
| 캠퍼스 평균 음식벡터 레이더 | `GET /analysis/menus/food-vectors/average` |
| 코너 코어층 | `GET /analysis/corners/core-layer-summary`, `.../core-layer-menu-pairs` |
| 취향 군집 요약 | `GET /analysis/users/taste-clusters` |
| 사용자 입맛 분석 | `GET /analysis/users/{employee_id}/taste-profile` |
| 피크타임 서브속도 메뉴별 Top5/Bottom5 | `GET /analysis/corners/{id}/menu-throughput` |
| 메뉴 동반 선택 경향성 | `GET /analysis/menu-pairs/top` |
| 사용자 분석 탭 전체 | (위 3개 + 회사구분별 식수) |
| 회사구분별 식수 **표** | `GET /analysis/divisions` |

**컴포넌트 정의는 남기지 않고 지웠다.** 정의만 남기면 TS가
"declared but never read"로 빌드를 깨기 때문이다. 되살릴 때는 git 이력에서
꺼내면 되고, 그동안 API가 죽지 않았다는 건 아래 회귀 테스트가 보증한다.

**의도적 손실 1건**: 회사구분별 식수의 **표 형태**는 사라진다. 그래프는 1-B의
통합 추이 차트가 `group_by=division` + 일/주/월 + 분류 필터로 그대로 대체하지만
숫자 표는 없다. 필요하면 통합 차트에 표 토글을 붙이는 게 다음 라운드 과제다.

### 47.4 회귀 테스트가 이번 재편의 안전장치

`test_demoted_features_keep_working_apis`(`backend/tests/
test_api_ingest_and_analysis.py`)가 강등된 기능들의 엔드포인트 + `/simulation/
what-if`까지 전부 200을 주는지 확인한다. **UI 정리 과정에서 백엔드를 같이
지워버리는 사고를 막는 게 목적**이라, 이 테스트는 화면이 아니라 API 계약을 본다.

### 47.5 관리 탭은 접근 제한이 아니다

이 앱에는 로그인/권한 체계가 없다(프론트에 인증 없음, 백엔드 인증은 `/ingest/*`
Bearer 토큰뿐). 그래서 관리 탭은 **일상 동선에서 치우는 정리 목적일 뿐 접근을
막지 않으며**, 오해를 막기 위해 화면 상단에도 그 문장을 그대로 띄운다.
개인 취향 프로필 API(`/analysis/users/{employee_id}/taste-profile`)도 협의 결정에
따라 인증 없이 열려 있고, UI에서만 내렸다 — 인증 도입 시 일괄 처리한다.

### 47.6 남은 후속 과제

- 연휴 전후 배수(0.85/0.90)는 실측 근거 없는 **v0 가정치** — 연휴 표본이 쌓이면 보정 필요
- `expected_wait_minutes` 폭주(표본 희박 코너에서 1012분) — 화면은
  `WAIT_MINUTES_PLAUSIBLE_MAX=120`으로 가렸고 근본 해결(처리량 표본 하한)은 미해결
- 2~5순위(메뉴 회전 이력·건강가든 텍스트 입력·알람·VoE 정리·채팅 그라운딩 갱신)

**파일 요약**: `backend/app/api/simulation.py`, `backend/tests/
test_api_ingest_and_analysis.py`, `frontend/src/App.tsx`, `frontend/src/pages/
HomePage.tsx`, `frontend/src/pages/AnalysisPage.tsx`, `frontend/src/pages/
SimulationPage.tsx`(삭제), `frontend/src/api/client.ts`.
