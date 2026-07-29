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

**테스트**: `ingestion-tool/tests/test_merge.py`의
`test_diagnose_match_failure_by_evaluation_*` 6개 — 전체 일치, ID/메뉴명
불일치 격리, 매핑 적용, 매칭 없음, 그리고 취식기록이 훨씬 많아도 카운트가
맛평가 건수를 못 넘는지 확인하는 케이스.
