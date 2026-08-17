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

---

## 48. 2순위 — 메뉴 편성·운영: 회전 이력 · 건강가든 · 코너별 조합 비교 (2026-08)

담당자 협의에서 정한 2순위 3개 항목을 구현했다.

### 48.1 메뉴 회전 이력 — "이 메뉴 최근에 내보내지 않았나?"

`GET /analysis/weekly-menu/rotation?period_start&period_end&lookback_days=180`

판정 로직은 `backend/app/services/menu_rotation.py`의 순수 함수
`classify_rotation(target_date, past_dates)`가 전부 갖고 있다(DB를 모른다).

**두 기준을 같이 쓴다:**

| 판정 | 조건 |
|---|---|
| 같은 날 중복 | 같은 날짜에 2번 이상 편성됨(다른 코너/끼니) |
| 재편성 과다 | 직전 편성 이후 `MIN_ROTATION_GAP_DAYS`(14일) 미만 |
| 평소보다 이름 | 14일은 넘었지만 그 메뉴의 평균 주기 × `EARLY_RATIO`(0.6) 미만 |
| 오랜만 | 평균 주기 × `LONG_ABSENT_RATIO`(2.0) 초과 |
| 적정 / 이력 없음 | 나머지 / 과거 편성 이력 없음 |

절대 기준만 쓰면 매주 나오는 김치·밥 같은 상시 부찬이 전부 경고가 되고, 상대
기준만 쓰면 이력이 1회뿐이라 평균 주기를 못 내는 메뉴를 놓친다. 그래서 둘 다 본다.

**평균 주기는 "과거끼리의 간격"으로만 낸다** — 판정하려는 이번 등장을 평균에
넣으면 그 값이 기준까지 끌어내려 자기 자신을 항상 정상으로 만드는 순환이 된다
(`test_avg_interval_excludes_the_appearance_being_judged`가 이걸 고정한다).

**과거 이력의 출처는 `weekly_menu_plan`(편성 이력)이지 `meal_log`(취식 이력)가
아니다.** "언제 또 내보낼까"를 정하는 편성 담당자 관점에선 실제로 몇 명이
먹었는지가 아니라 식단표에 몇 번 올렸는지가 기준이기 때문이다.

`MIN_ROTATION_GAP_DAYS = 14`는 구내식당 2주 사이클이라는 **운영 관행 기반
기본값이지 실측 근거가 아니다** — 담당자 피드백으로 조정할 값이다.

추가로 `find_overused_menus`가 조회 기간 안에서 3회를 넘게 편성된 메뉴를
따로 모은다. **역할(메인/부찬/건강가든)을 가로질러 센다** — 같은 나물이 어떤
날은 부찬, 어떤 날은 건강가든으로 들어가도 먹는 사람에겐 중복이라서다.

### 48.2 건강가든 — 텍스트 수기 입력

식단표 엑셀에 건강가든이 아직 안 들어온다. 담당자가 "대략 5개 종류가 반복"
이라고 해서, 정식 데이터 유입 전까지 **화면에서 텍스트로 입력**받기로 했다
(협의 결정, 2026-08).

`PUT /analysis/weekly-menu/health-garden` — `{plan_date, corner_id, meal_type,
menu_names_raw}`. 쉼표/줄바꿈/탭으로 구분하며(`parse_menu_names`), 슬롯 단위
**전체 교체**다(POST 추가가 아님 — 화면이 텍스트 상자 하나라 "지금 이 슬롯의
건강가든은 이거다"를 통째로 보내는 게 UI와 일치하고, 빈칸 저장이 곧 비우기가 된다).

**별도 테이블을 만들지 않고 `weekly_menu_plan`에 `MenuRole.HEALTH_GARDEN`으로
넣는다.** 같은 테이블에 있어야 회전 이력·중복 판정이 메인/부찬과 한꺼번에
돌아가기 때문이다(요청사항이 "메인/부찬/건강가든 **조합** 중복 최소화"였다).
데이터가 정식 유입되면 ingestion-tool이 같은 role로 적재하면 되고 화면·판정
로직은 그대로 쓸 수 있다.

다만 화면 표시와 `WeeklyMenuSlot`에서는 **부찬과 섞지 않고 따로 담는다**
(`health_garden` 필드) — 섞으면 §29의 부찬 조합별 만족도 비교가 오염된다.

마이그레이션 `e7b4c2915f30`: `MenuRole`이 `native_enum=False`라 VARCHAR 길이가
가장 긴 멤버값에서 나오는데, 기존 멤버가 "메인"/"부찬"(2자)뿐이라 컬럼이
`VARCHAR(2)`였다. "건강가든"(4자)이 안 들어가므로 8자로 넓혔다.

### 48.3 부찬 조합별 만족도 — 코너 필터

`GET /analysis/menu-combinations/{menu_name}`에 `corner_id`(선택)를 추가했다.
같은 메인이 여러 코너에서 다른 부찬과 나오면 조합이 섞여 비교가 흐려진다.

### 48.4 화면

**메뉴 편성·운영** 탭 = 주간 식단표 관리 → **메뉴 회전 이력(신규)** → 부찬 조합별
만족도 → 메뉴 동반 선택 쌍.

회전 이력 표는 **"경고만 보기"가 기본 ON**이다 — 적정/이력 없음까지 다 띄우면
한 주에 수십 줄이라 정작 봐야 할 경고가 묻힌다.

건강가든 입력은 주간 식단표의 **슬롯 상세 패널** 안에 있다(날짜·코너·끼니가
이미 정해진 자리라 입력 대상이 모호하지 않다).

### 48.5 남은 후속 과제

- `MIN_ROTATION_GAP_DAYS`(14일)·`EARLY_RATIO`(0.6)·`OVERUSE_COUNT_IN_PERIOD`(3)는
  **운영 관행 기반 기본값** — 실사용 피드백으로 보정 필요
- 건강가든이 식단표 엑셀에 정식으로 들어오면 ingestion-tool 파싱 경로 추가
  (그때 이 텍스트 입력은 보조 수단으로 남기거나 제거)
- 3순위(알람), 4순위(만족도·VoE 정리), 5순위(채팅 그라운딩 갱신)

**파일 요약**: `backend/app/services/menu_rotation.py`(신규),
`backend/app/services/weekly_menu_review.py`, `backend/app/services/
menu_combination.py`, `backend/app/models/enums.py`, `backend/app/api/
analysis.py`, `backend/alembic/versions/e7b4c2915f30_*.py`,
`backend/tests/test_menu_rotation.py`(신규), `backend/tests/
test_api_ingest_and_analysis.py`, `frontend/src/api/client.ts`,
`frontend/src/pages/AnalysisPage.tsx`.

---

## 49. 식단표 8개월치로 가능해진 분석 4종 (2026-08)

주간 식단표 엑셀 31개(8개월치)가 적재됐다. 그전까지 `weekly_menu_plan`은 최근
몇 주치뿐이라 **편성 이력 자체를 분석 대상으로 쓸 수 없었다.**

### 49.1 전제 — 편성 횟수 ≠ 취식 발생 일수

기존 "메뉴별 분석" 4분면의 X축 `appearance_count`는 `meal_log`의 **취식 발생
일수**다(`aggregation.py`의 `[r.eaten_at.date() for r in rows]`). 즉 **편성했는데
아무도 안 먹은 메뉴는 `by_menu`에 안 들어와 4분면에서 아예 사라진다.**

편성 횟수는 담당자가 **직접 통제하는 유일한 변수**다 — 만족도·식수는 결과지만
편성 횟수는 다음 주에 바꿀 수 있다. 그래서 §49.3의 화면은 `weekly_menu_plan`을
기준으로 다시 센다.

### 49.2 중복은 축이 둘이다

| 축 | 질문 | 구현 |
|---|---|---|
| 기간 내 같은 메뉴 반복 | "이 메뉴 최근에 또 내보내지 않았나" | §48 회전 이력(`menu_rotation.py`) — 유지 |
| **슬롯 내 재료·특성 중복** | "이 한 끼 구성이 겹치지 않나" | **신규 `menu_clash.py`** |

담당자 예시: 콩나물국밥(메인) + 콩나물무침(부찬) = 재료 중복 /
순두부찌개 + 매운양념 부찬 = 맛 중복 / 메인이 탄수화물인데 부찬도 탄수화물.

`GET /analysis/weekly-menu/combination-check` — 같은 (날짜, 코너, 끼니) 안에서
메인↔부찬, 부찬↔부찬 모든 쌍을 본다. 건강가든도 부찬과 함께 넣는다.

**재료 중복**은 `_INGREDIENT_TOKENS` 사전으로 메뉴명에서 식재료를 뽑아 교집합을
본다. `food_vector_tagging._KEYWORD_RULES`는 *차원*(매운맛/탄수화물) 키워드지
재료 사전이 아니라("콩나물"이 없다) 별도로 뒀다.
**한계**: 사전에 없는 재료는 못 잡는다. 1자 토큰("무")은 "무침"·"무국"에
오탐하므로 **2자 이상만** 넣는다. 이 레포의 3단계 패턴(규칙 → LLM → 수동)에서
1단계만 한 셈이고, 커버리지가 부족하면 LLM 재료 추출이 다음 단계다.

**특성 중복**은 `food_vector`를 재사용한다. 대상 차원은
`spicy/carb/fried/oily/soup_based/salty` 6개뿐이다 — **`protein`과
`vegetable_ratio`는 뺐다. 단백질이나 채소가 겹치는 건 문제가 아니라 오히려
좋다.** 겹쳐서 물리거나 영양이 쏠리는 차원만 본다. `sweet`/`sour`는 판단이
애매해 v0에서 제외했다. 임계값 0.6은 규칙 태깅(0.85/0.2 이분법)과 LLM
태깅(연속값)을 같은 기준으로 다루기 위한 값이다.

**`food_vector`가 NULL인 메뉴는 조용히 넘기지 않고 `untagged`로 따로 센다** —
태깅이 안 된 것뿐인데 "구성이 괜찮다"고 오해하면 안 된다.

화면은 회전 이력과 **한 카드로 합쳤다**(`DuplicationCheckSection`). 카드가
따로면 주 이동이 어긋나 "회전 이력은 이번 주, 조합은 지난 주"를 보게 된다.
협의 결정에 따라 `RotationFlag.SAME_DAY`(코너 간 같은 날 중복)는 프론트의 기본
경고 집합에서 뺐다 — 백엔드 판정·테스트는 그대로라 되살리려면 한 줄이다.

### 49.3 편성 빈도 × 성과 + 메뉴명 매칭 진단

`GET /analysis/menu-plan/performance` — 편성 횟수(weekly_menu_plan)와
반응(meal_log)을 교차해 감편/증편 방향을 낸다. 기준선은 **그 기간 전체의
중앙값**으로, 기존 4분면(`aggregation.py`)과 같은 방식이다 — 화면마다 다른
기준을 쓰면 담당자의 판정 감각이 어긋난다.

판정 우선순위: **취식 0 → 표본 부족 → 4분면**. 취식이 아예 없으면 만족도 비교
자체가 성립하지 않는다.

**메인메뉴만 본다.** 맛평가·취식 데이터는 그 사람이 고른 **메인** 기준이고
부찬은 취식 기록에 따로 안 남는다(담당자 확인) — 부찬을 넣으면 전부 취식 0이
되어 무의미하다.

**매칭 진단이 이 화면의 핵심 안전장치다.** 식단표 메뉴와 취식기록 메뉴는 둘 다
`get_or_create_menu(db, menu_name)`을 거치므로 이름이 같으면 자동으로 같은
`menu_id`가 되지만, 표기가 다르면 별개 메뉴가 된다(이 레포는 §3 원산지 정규화,
§4 `&미니우동` 파싱 등 표기 문제를 이미 겪었다). 응답의 `matching`이
`matched` / `plan_only`(편성됐는데 취식 0) / `log_only`를 그대로 실어 보내
담당자가 **"진짜 안 팔린 것"과 "이름이 안 맞아 매칭 실패한 것"을 직접 구분**할
수 있게 한다. 이게 없으면 감편 리스트가 매칭 실패 메뉴로 가득 찬다.

### 49.4 부찬 조합 편차 랭킹 — 검색 없이 먼저 보이게

부찬 조합 비교가 메뉴명 검색으로만 열려 "뭘 검색해야 하는지"부터 막힌다는
피드백. **조합에 따라 만족도 편차가 큰 메인메뉴**를 먼저 띄운다 — 편차가 크다 =
부찬을 바꾸면 만족도가 실제로 움직인다. 편차가 0에 가까우면 뭘 붙여도 결과가
같으니 볼 필요가 없다.

`GET /analysis/menu-combinations/spread-ranking`. `min_day_count` 기본 2인 이유:
1일짜리 조합은 그날 컨디션이 그대로 편차가 되어 랭킹 상위가 우연으로 찬다.

**성능**: 기존 `build_side_combos_for_main_menu`는 **슬롯마다 `meal_log` 쿼리를
1번씩** 던진다. 단건 상세엔 그게 더 가볍지만 기간 전체 랭킹에선 8개월 × 코너 7 ×
주 6일 = 1000+ 쿼리가 된다. 그래서 **쿼리 3개로 끝내는 `build_side_combos_bulk`**
를 따로 뒀고, 기존 단건 함수는 그대로 남겼다.

두 경로가 갈라지면 랭킹과 상세가 다른 숫자를 보여주므로
`test_bulk_combo_loader_matches_single_menu_loader`가 **동치성을 못박는다.**
이게 이 배치의 핵심 안전장치다.

⚠️ **라우트 순서 함정**: `/menu-combinations/spread-ranking`을
`/menu-combinations/{menu_name}` **뒤에** 두면 `{menu_name}`이 "spread-ranking"을
잡아먹는다(FastAPI는 선언 순서로 매칭). `/corners/list`와 같은 함정이라 이번에도
고정 경로를 먼저 선언했다.

### 49.5 코너별 레퍼토리 진단

`GET /analysis/menu-plan/repertoire` — 코너 × 역할별로 편성 슬롯 수, 고유 메뉴
종수, 상위 5개 비중, HHI(허핀달 지수).

**`top_share`와 `hhi`를 둘 다 내는 이유**: 종수가 `top_n` 이하면 `top_share`는
무조건 1.0이라 아무것도 구분 못 한다 — 바로 그 구간을 HHI가 잡는다. 반대로
종수가 많으면 `top_share`가 쏠림을 직관적으로 보여준다. 한 지표만 보면 오진한다
(`test_hhi_discriminates_where_unique_count_and_top_share_cannot`가 이걸 고정).

### 49.6 조회 기간

§49.3~49.5 화면에 기간 선택(3/6/12개월)을 붙이고 **기본 6개월**로 뒀다.
`AnalysisPage.tsx`의 `PERIOD_START`는 `isoDaysAgo(180)` 고정이라 8개월치를 볼
수단이 없었다. 기본값을 12개월로 올리진 않는다 — **적재 이전 구간은 편성 이력이
비어 있어 편성 횟수가 실제보다 적게 나온다.**

### 49.7 남은 후속 과제

- **LLM 기반 재료 추출** — 규칙 사전 커버리지가 부족할 때(3단계 패턴 2단계)
- 요일·월별 편성 패턴 히트맵, 신메뉴 정착률(이번에 안 고른 2개)
- 회전 이력 임계값(14일/0.6/3회) 실측 보정 — 8개월치가 쌓여 이제 실제 분포를
  보고 조정할 수 있다
- 3순위 알람, 4순위 만족도·VoE 정리, 5순위 채팅 그라운딩 갱신

**파일 요약**: `backend/app/services/menu_clash.py`(신규),
`backend/app/services/menu_plan_analytics.py`(신규),
`backend/app/services/menu_combination.py`, `backend/app/api/analysis.py`,
`backend/tests/test_menu_clash.py`(신규),
`backend/tests/test_menu_plan_analytics.py`(신규),
`backend/tests/test_api_ingest_and_analysis.py`,
`frontend/src/api/client.ts`, `frontend/src/pages/AnalysisPage.tsx`.

---

## 50. 성능 회귀 복구 — 홈이 "불러오는 중"에서 멈추던 문제 (2026-08)

**증상(실사용 신고)**: "데이터 불러오는 중 속도가 느리고 로딩되다가 결국 결과가
나오지 않음."

### 50.1 직접 원인 — 버튼 뒤에 있던 호출이 자동 호출로 바뀐 회귀

홈 진입 시 무조건 나가던 API 중 둘이 사실상 끝나지 않았다:

| 엔드포인트 | 비용(측정) |
|---|---|
| `/analysis/weekly-menu/predicted-impact-summary` | 슬롯 30개 기준 **1,122 쿼리 / 1,399ms** |
| `/simulation/congestion-forecast/weekly` | 코너·날짜마다 180일 스캔 반복 |

`compute_predicted_numbers_for_period`가 슬롯마다 `compute_predicted_numbers`를
부르고, 그 안에서 다시 코너 루프를 돌며 180일치 `meal_log`를 반복해서 읽는
구조다. `analysis.py`의 docstring에도 **"전체 예측 비교 버튼을 눌렀을 때만
호출한다(자동 실행 아님)"** 고 적혀 있었는데, **커밋 `60960f9`(현황 재편 —
점유율·대기시간을 홈으로 이동)에서 이 호출이 `enabled` 없이 마운트 시점 호출로
바뀌었다.** 화면을 옮기면서 원래의 호출 조건을 같이 옮기지 않은 것이 원인이다.

**조치**: 두 쿼리에 `enabled: forecastRequested` 게이트를 걸고 카드에 "예측
계산하기" 버튼을 뒀다. 카드 자리와 설명은 그대로 둬서 기능이 사라진 것으로
보이지 않게 했다. 홈 진입 시 무거운 예측 호출 **0개**(Playwright로 확인).

### 50.2 React Query 기본값이 없어 탭 전환마다 전량 재요청

`main.tsx`의 `new QueryClient()`에 옵션이 하나도 없어 `staleTime: 0`이었다 —
탭을 오갈 때마다 모든 쿼리가 다시 나갔다. 취식·식단표 데이터는 하루 1회 배치로만
갱신되므로 `staleTime: 5분`, `gcTime: 30분`, `refetchOnWindowFocus: false`로 뒀다.

### 50.3 요청 단위 캐시 — `Session.info`

예측 경로가 **같은 인자로 같은 무거운 조회를 수백 번** 반복하고 있었다. 결과가
요청 안에서 변하지 않는 것들을 `Session.info`(SQLAlchemy가 세션 스코프 저장소로
제공)에 담아 재사용한다:

| 대상 | 캐시 키 |
|---|---|
| `_corner_id_by_menu_from_meal_log` (180일 GROUP BY) | `(period_start, period_end)` |
| `build_corner_daily_throughput` / `build_corner_daily_peak_share` | `(corner_id, period_start, period_end)` |
| `_baseline_headcount` | `(corner_id, meal_type, classification)` |
| `_planned_main_menu_id` | `(corner_id, meal_type, plan_date)` |
| `_menu_popularity_multiplier` | `(corner_id, menu_id)` |
| `HolidayService` (`get_holiday_service`) | 세션당 1개 |

**캐시 수명이 요청과 정확히 같다는 게 안전성의 전제다** — `get_db`가 요청마다
세션을 새로 만들고 닫기 때문이다. 이 전제가 깨지면(예: scoped session 도입)
새로 적재한 데이터가 화면에 안 보이는 조용한 버그가 되므로,
`test_request_scoped_caches_do_not_leak_across_requests`로 못박았다.

`HolidayService`는 캐시가 **인스턴스 스코프**라 루프 안에서 `HolidayService(db)`를
새로 만들면 그 횟수만큼 `holiday_calendar`를 다시 읽는다 — 예측 경로가 실제로
그랬다. `get_holiday_service(db)`로 세션당 1개를 재사용한다.

### 50.4 예측 경로가 벌크 조합 로더를 쓰게 함

`compute_predicted_numbers`가 쓰던 `build_side_combos_for_main_menu`는 **과거
슬롯마다 `meal_log` 쿼리를 1번씩** 던진다 — 30슬롯 1,122쿼리 중 약 600이 여기서
나왔다. §49.4에서 만든 쿼리 3개짜리 `build_side_combos_bulk`를 세션 캐시와 함께
쓰도록 바꿨다. 두 경로가 같은 값을 낸다는 건
`test_bulk_combo_loader_matches_single_menu_loader`가 이미 보증한다.

### 50.5 `headcount-trend`를 SQL 집계로 전환

기간 내 취식 행을 **전부 파이썬으로 끌어와** 세고 있었다(월간 선택 시 365일치
전량). 회사구분·분류 필터도 파이썬이라 범위를 좁혀도 읽는 양이 그대로였다.

→ `GROUP BY (날짜, 코너, 끼니, 회사구분)`으로 SQL에서 집계하고, 회사구분 필터는
WHERE로 내렸다. `Division.OTHER`를 고른 경우 `employee_master`에 없는 사번
(`division IS NULL`)도 함께 잡아야 기존 outerjoin 규칙과 일치한다(§49의
`daily_division_stats` 합계 일치 조건).

분류(평일/주말+공휴일/패밀리데이) 필터는 `HolidayService.classify_range()`로
**날짜 dict를 한 번 만들어** 조회한다 — 예전엔 취식 행마다 `classify()`를 불러
같은 날짜를 그 날 취식 건수만큼 재계산했다. `classify_range`는 이미 있었지만
코드베이스 어디서도 쓰이지 않고 있었다.

### 50.6 복합 인덱스 (`b3f81c47d052`)

초기 스키마 이후 `meal_log`/`weekly_menu_plan`에 인덱스가 **하나도 추가된 적이
없고 전부 단일 컬럼**이었다. 실제 쿼리 형태에 맞춰 6개를 추가했다 —
`meal_log(corner_id, eaten_at)`, `(menu_id, eaten_at)`,
`(eaten_at, corner_id, meal_type)`, `weekly_menu_plan(plan_date, menu_role)`,
`menu_performance_stats(menu_id, period_end)`,
`daily_corner_stats(corner_id, meal_type, is_holiday, stat_date)`.

### 50.7 결과

슬롯 30개 기준 `predicted-impact-summary`: **1,122 쿼리 / 1,399ms →
364 쿼리 / 647ms** (쿼리 67% 감소). 여기에 홈 진입 시 이 호출 자체가 안 나가므로
체감 개선은 더 크다.

**남은 것**: `menu-pairs/top`의 조합 폭발(`menu_affinity.py`, O(사번 × 메뉴종수²))과
`congestion_forecast` 테이블이 있는데 아무 배치도 안 채우는 문제는 그대로다 —
예측을 배치 산출물로 옮기는 게 다음 단계다.

---

## 51. 원산지 표기가 부찬으로 저장되던 버그 — 4중 결함 (2026-08)

**증상(실사용 신고)**: "`(오징어:중국산)`, `(계육-국산)` 이런 것들은 메인메뉴
재료의 원산지인데 부찬이라고 잘못 판단하고 있다. 그리고 한 끼 구성을 판단할 때
키워드로만 봐서 **'외국산'을 '국'(국물)으로 인식**한다."

실제 파서를 돌려 재현했고, 결함이 4개였다.

### 51.1 결함 1 — 원산지 패턴이 콜론을 하드코딩

`_INGREDIENT_ANNOTATION_PATTERN`과 `_TRAILING_ORIGIN_ANNOTATION_PATTERN` 둘 다
`(.+:.+)` 형태여서 **하이픈·공백 표기를 전부 놓쳤다**. §38.3에서 원산지를
다뤘지만 그때 목표는 "메뉴명 뒤 주석 떼기"였지 "주석 줄 자체를 부찬으로 만들지
않기"가 아니었고, 그래서 콜론만 보고 있었다.

### 51.2 결함 2 — 항목 분리가 괄호를 반토막 냄 (가장 파괴적)

`_ITEM_SPLIT_PATTERN`의 `,`/`/`/`·` 분리가 괄호 안에서도 잘랐다:

```
"우삼겹구이(우육:호주산, 돈육:국내산)"
  → 메인 '우삼겹구이(우육:호주산'   ← 메인메뉴명 자체가 깨진다
  → 부찬 '돈육:국내산)'
```

**부찬 오염을 넘어 메인 이름이 깨지면 취식기록과 영영 매칭되지 않는다.**
원산지는 실무상 거의 항상 여러 재료를 쉼표로 나열하므로 이게 가장 흔한 경로였다.

→ `_split_top_level()`로 **괄호 깊이가 0일 때만** 자른다.

### 51.3 결함 3 — 백엔드 방어선이 "이중 방어"가 아니라 같은 결함의 복제

`master_data._normalize_menu_name`의 정규식이 파서와 **문자 단위로 동일**했다.
파서가 못 잡는 건 백엔드도 100% 못 잡았다.

→ 백엔드는 `app/services/menu_name.py`를 **단일 출처**로 삼는다
(`master_data`와 `food_vector_tagging`이 서로를 임포트하고 있어 어느 한쪽에 두면
순환이 된다 — 실제로 한 번 순환을 만들었다가 중립 모듈로 뺐다).
ingestion-tool과는 패키지가 분리돼 공유가 불가능하므로 복제하되,
**양쪽에 같은 `ORIGIN_CASES` 표를 두어 어긋나면 테스트가 깨지게** 했다.

### 51.4 결함 4 — `soup_based`의 `"국"`이 원산지를 삼킴 (연쇄 피해)

`_KEYWORD_RULES["soup_based"]`의 `"국"`이 **외국산·중국산·국내산·국산·미국산·
태국산에 전부 매칭**됐다. 여파가 단순 오태깅에서 끝나지 않는 게 문제다:

1. `get_or_create_menu`가 신규 메뉴 태깅 시 `food_vector`를 **NULL이 아니게** 채움
2. `run_llm_food_vector_tagging`은 `food_vector IS NULL`만 대상 → **그 행이 LLM
   보정 대상에서 영구히 빠진다.** 규칙 → LLM → 수동 3단계 안전망의 2단계가 무력화
3. `menu_clash._CLASH_DIMENSIONS`에 `soup_based`가 있어 국물 메인 + 유령 부찬이
   **확정적으로 "국물 중복" 오탐**

→ `"국"` → `"국물"`로 바꾸고 `endswith("국")` 접미어 판정을 따로 뒀다(미역국·
된장국·북어국은 그대로 잡힌다). 추가로 태깅 전에 원산지 주석을 먼저 떼어낸다.

### 51.5 판정 규칙 — 넓히되 오삭제는 막는다

구분자만 넓히면 `(오징어볶음-매운맛)` 같은 정상 이름까지 지워진다. 그래서
**괄호 안 마지막 토큰이 원산지처럼 보여야 한다**는 조건을 함께 건다:
명시 목록(`국내산/국산/외국산/수입산/원양산`) 또는 **"산"으로 끝나는 2~6자**.
`매운맛`·`얼큰한맛`·`태양초`는 안 걸린다.

`is_origin_annotation_text`(줄 전체를 버릴지)와 `strip_origin_annotation`
(뒤에 붙은 주석만 뗄지)을 나눈 이유: `우삼겹구이(우육:호주산)`을 통째로 버리면
메뉴가 사라진다. **메뉴명이 앞에 붙어 있으면 전자는 False를 준다.**

| 입력 | 결과 |
|---|---|
| `(계육-국산)` / `*돈육:국내산` | 버림 |
| `우삼겹구이(우육:호주산, 돈육:국내산)` | `우삼겹구이` |
| `오징어(중국산)` | `오징어` |
| `(오징어볶음-매운맛)` / `김치찌개(얼큰한맛)` | **보존** |

### 51.6 이미 적재된 데이터 — 정리 스크립트 + 멱등 재적재

**파서 수정은 적재 경로에만 걸리므로 기존 8개월치는 안 바뀐다.**

`app/maintenance/purge_origin_annotation_menus.py` — **기본 dry-run**,
`--apply`로만 삭제. `weekly_menu_plan` 행은 지우되 **`meal_log`는 `menu_id`만
NULL로 되돌린다**(취식 기록은 실제로 일어난 사실이라 지우면 식수 통계가 틀어진다).

그리고 `POST /ingest/weekly-menu`는 dedup 없는 `db.add`라 **그냥 재업로드하면
데이터가 2배가 된다.** `replace_existing: bool = False`를 추가해 true면 payload에
등장하는 (plan_date, corner_id, meal_type) 슬롯의 기존 행을 먼저 지운다.
**`role_source == MANUAL`인 행은 교체 대상에서 제외** — 관리자가 손으로 고친
주찬/부찬과 건강가든 수기 입력이 재업로드로 조용히 날아가면 안 된다.

**복구 순서**: ① dry-run으로 목록 확인 → ② `--apply` → ③ 식단표 재업로드
(`replace_existing=true`) → ④ 배치 집계 재계산 + `menu-performance/recompute`.

---

## 52. 화면·기준 조정 — 편성 빈도 기준, 그래프 직관성, 중복 점검 분리 (2026-08)

실사용 피드백 5건을 반영했다.

### 52.1 편성 빈도 — *간격*이 아니라 *횟수* 기준을 추가

담당자 기준: **"3개월에 2회까지는 무난한 편성"**. 기존 판정은 §48의
`MIN_ROTATION_GAP_DAYS`(직전 등장 이후 14일)뿐이라 **"14일은 넘겼지만 분기에
3번 나온다"가 안 잡혔다** — 축이 다르다.

`menu_rotation.py`에 횟수 기준을 따로 뒀다:

| 상수 | 값 | 근거 |
|---|---|---|
| `ROTATION_WINDOW_DAYS` | 90 | 담당자가 말한 "3개월" |
| `MAIN_MAX_IN_WINDOW` | 2 | "2회까지는 무난" → 3회부터 과다 |
| `SIDE_MAX_IN_WINDOW` | 6 | 부찬은 자주 돌려쓰는 게 정상(약 2주에 1회) |

`count_in_window`는 **같은 날 여러 코너에 깔린 걸 1회로 센다** — "얼마나 자주
내보내나"가 질문이라 하루에 두 코너면 하루치 노출이다(그 중복은 `SAME_DAY`가
따로 본다).

응답에 `window_count` / `window_max` / `over_frequency`를 실어 화면이 "2/2회"
처럼 보여준다.

### 52.2 중복 점검 — 메인과 부찬을 분리

담당자: **"메인메뉴가 과다 편성 되는 게 1순위 문제고, 부찬도 자주 돌려쓰면 문제"**.
회전 이력 응답에 `menu_role`이 이미 있어 백엔드 변경 없이 화면에서 나눴다 —
**메인 블록을 위에 `critical` 색으로, 부찬·건강가든을 아래에** 놓는다.
경고 카운터도 "경고 N건(메인 M건)"으로 메인을 따로 센다.

### 52.3 편성 빈도 × 성과 그래프 — "직관적이지 않음" 수정

이전 그래프는 **색만 다르고 아무 설명이 없었다.** 무엇이 바뀌었나:

- **판정별로 시리즈를 분리** → 범례가 생기고, 범례를 눌러 한 분류만 볼 수 있다.
  이전엔 시리즈 하나에 `itemStyle` 색만 달라 색의 의미를 알 방법이 없었다
- **사분면 배경 음영 + 모서리에 뜻을 적었다** — "감편 검토(자주 내는데 반응 낮음)",
  "증편 후보(드문데 반응 좋음)", "주력 유지". 중앙값 십자선만으로는 어느 쪽이
  감편인지 매번 머리로 계산해야 했다
- **점마다 메뉴명 상시 표시** + `labelLayout: {moveOverlap:"shiftY", hideOverlap:true}`
  로 겹치면 자동으로 비킨다(§42의 4분면 차트와 같은 처리라 조작감이 같다)
- y축을 만족도 실척도인 0~5로 고정 — 자동 스케일이면 점 몇 개의 미세한 차이가
  전체 높이로 확대돼 실제보다 크게 보인다

⚠️ ECharts 산점도에 `label.show: true`만 주면 **메뉴명이 아니라 숫자가 찍힌다** —
`formatter: (p) => p.name`을 명시해야 한다(실제로 한 번 놓쳤다가 화면 확인에서 발견).

### 52.4 부찬 조합 — 좋았던/나빴던 조합의 **차이**만 음영

담당자: "변화된 부분을 음영처리해서 눈에 띄게". 텍스트로 나열하면 부찬이 3~4개일 때
뭐가 달라졌는지 눈으로 못 찾는다.

순수 함수 `diffSides(best, worst) -> {onlyBest, onlyWorst, common}`으로 계산하고,
**한쪽에만 있는 부찬만 배경색으로** 칠한다(좋았던 쪽은 `--good`, 나빴던 쪽은
`--critical`). 공통 부찬은 흐린 회색이라 대비로 차이가 바로 보인다.

### 52.5 조회 기간 30/60/90일/6개월

기존 3/6/12개월 → **30일 / 60일 / 90일 / 6개월**, 기본 90일.
기본값을 90일로 둔 이유는 §52.1의 편성 기준 창(3개월)과 맞추기 위해서다 —
화면에서 보는 기간과 판정 기준의 기간이 다르면 숫자가 안 맞아 보인다.

---

## §53. LLM 분석을 새벽 배치로 옮기고 캐시로 읽는다 (2026-08)

담당자 요청 두 가지가 같은 구조를 필요로 했다.

1. 메뉴 하이라이트에 "만족도가 왜 변했는지" 원인 설명
2. 개선 필요 포인트에 편성·운영 문제 notice

둘 다 LLM이 문장을 만들어야 하는데, **화면 로드 경로에 LLM을 넣지 않았다.**

### 53.1 왜 배치인가

같은 라운드에서 "로딩되다가 결국 결과가 나오지 않는다"는 신고를 받고 §50에서
성능 회귀를 복구한 직후다. 화면 진입마다 LLM을 부르면 그 문제로 되돌아간다.
레포에 이미 같은 판단의 선례가 둘 있다 — `voe_clustering`, `voe_category_llm`은
월간 배치 산출물이고 화면은 저장된 결과만 읽는다(§25).

그래서 `llm_analysis.py`는 **계산(배치)과 조회(화면)를 완전히 분리**한다:

| | 언제 | 무엇을 |
|---|---|---|
| 쓰기 | 새벽 2시 `run_daily_batch` | LLM 호출 → `llm_analysis_cache`에 저장 |
| 읽기 | 화면 요청 | `get_cached()`로 저장된 문장만 조회 (LLM 호출 0회) |

식재료 추출(§53.4)도 같은 배치에 넣었다. 매주 식단표가 올라오며 새 메뉴가
생기는데, 관리자가 버튼을 누르는 걸 잊으면 중복 판정이 조용히 키워드 사전으로
되돌아가기 때문이다. 대상이 `ingredients IS NULL`인 행뿐이라 첫 실행 이후엔
하루 몇 건 수준이다. 즉시 반영이 필요할 때를 위해 관리 탭 버튼도 함께 둔다.

### 53.2 ⚠️ 캐시를 **기간 정확 일치로 읽지 않는다**

`get_cached`는 `(kind, subject_key)`로 찾아 `created_at DESC LIMIT 1`을 준다.
`period_start`/`period_end`는 **저장은 하되 조회 조건에 쓰지 않는다.**

§45에서 정확히 이 함정에 빠졌었다. `menu_performance_stats`를
`filter_by(period_start=..., period_end=...)`로 읽었는데,

- 배치는 `period_end = 어제` 기준으로 쓰고
- 화면은 `period_end = 오늘`로 조회한다

하루 차이로 **항상 빈 결과**가 나왔고, 에러도 안 나서 "데이터가 없나 보다"로
보였다. 여기서는 최신 1건을 주고, 어느 기간을 근거로 언제 계산했는지를 함께
내보낸다(`cause_computed_at`). 이 규칙은
`test_get_cached_returns_latest_regardless_of_period`가 고정한다.

### 53.3 LLM 실패가 다른 축을 죽이지 않게

§44의 결론을 그대로 따른다.

- 폴백 `_fallback_*()`을 따로 두고 **미설정과 호출 실패 양쪽에 재사용**한다.
  미설정 상태가 예외가 아니라 **정상 동작 경로**다 — `InternalLLMClient`는
  미설정일 때 예외가 아니라 모의 문자열을 주므로, 호출 전에 `is_configured`를
  먼저 본다.
- 폴백 문구는 **사실만 나열하고 추정하지 않는다.** 끝에
  "(자동 분석 미설정)"을 붙여 LLM이 만든 문장과 구별되게 한다 — 붙이지 않으면
  규칙이 만든 문장을 담당자가 분석 결과로 오해한다.
- 프롬프트에도 "사실에 없는 내용은 지어내지 말고, 근거가 부족하면 특정하기
  어렵다고 쓰라"고 명시한다. 사실 수집은 순수 함수가 하고 LLM은 **문장을 다듬는
  일만** 한다.

### 53.4 `menu_master.ingredients` — 3단계의 2단계를 채운다

담당자 지적: "키워드로만 보기 때문에 외국산을 '국'으로 인식한다."

근본 원인(원산지 표기가 부찬으로 들어가고 `soup_based`가 "국"에 걸리던 것)은
§51에서 고쳤다. 그 위에 레포의 3단계 패턴(규칙 → LLM → 관리자수동)을 얹는다.

`menu_clash.extract_ingredients(name, stored)`는 `stored`(=`menu_master.
ingredients`)가 있으면 그걸 쓰고, 없을 때만 이름 기반 규칙 사전으로 폴백한다.
`_INGREDIENT_TOKENS`는 손으로 늘리는 사전이라 커버리지가 구조적으로 부족했다.

`ingredients_source == 관리자수동`인 행은 **`ingredients`가 이미 차 있으므로
자동으로 보호된다** — 배치가 `IS NULL`만 대상으로 하기 때문이다. `food_vector`
태깅과 완전히 같은 안전장치라 별도 예외 처리가 없다.

### 53.5 개선 포인트에 편성 축 추가

`ImprovementPoint.axis`에 `"planning"`을 더했다. 앞의 세 축(혼잡도/만족도/VOE)과
성격이 다르다 — 앞의 셋은 **이미 벌어진 결과**이고, 편성 축은 **다음 주 식단을
짜기 전에 고칠 것**이다.

사실 수집은 순수 함수 `collect_planning_issues(overused, no_intake_menus,
clash_slot_count)`가 하고(§36.1 관례), LLM은 그걸 한 문장으로 다듬기만 한다.
LLM 요약이 없으면 사실을 그대로 보여준다 — 빈 카드보다 낫다
(`test_build_planning_point_falls_back_to_raw_facts`).

### 53.6 메뉴 하이라이트에 **양쪽 주 + 평가 건수**

담당자: "만족도 평가의 날짜를 모두 써줘야 함."

`prior_week`는 `menu_highlights.py`에 **지역변수로만 있고 필드에 없었다** —
계산은 이미 하고 있었으므로 필드 추가와 직렬화뿐이고 새 계산이 없다.

⚠️ 이 값은 **날짜가 아니라 그 메뉴가 나온 주의 월요일**이다(§28: 메뉴가 매주
나오지 않으므로 달력 주가 아니라 메뉴별 등장 주끼리 비교). 화면 문구를
"6/29 주"처럼 **주 단위임이 드러나게** 쓴다. 그냥 "6/29"로 쓰면 그날 평가된
것으로 오해한다.

**평가 건수를 양쪽 다 함께 띄운다.** 실제 데이터에서 "만족도 급상승 1위"가
직전 주 **평가 1건** 대비였고, "급하락 1위"는 최근 주가 **1건**이었다. 점수만
보면 큰 변화지만 표본 노이즈다. 어느 한쪽이 5건 미만이면
"평가 표본이 적어 변화폭이 과장됐을 수 있습니다"를 함께 띄운다
(`LOW_SAMPLE_WARN_COUNT`). 백엔드의 표본 보정(`low_sample_threshold`)과는
**별개의 화면 경고**다 — 보정을 거쳐도 한 자릿수 표본의 주간 비교는 흔들린다.

### 53.7 마이그레이션에서 손으로 뺀 것

`c8f387ed003d` 자동 생성 결과에서 **인덱스 DROP 구문을 전부 지웠다.**
§50에서 성능용으로 손으로 만든 복합 인덱스들(`b3f81c47d052`)은 모델에 선언이
없어서, autogenerate가 "모델에 없으니 지워라"로 판단한다. 그대로 두면 §50의
성능 개선이 통째로 되돌아간다.

**앞으로 이 레포에서 `alembic revision --autogenerate`를 돌릴 때마다 같은 일이
생긴다.** 생성된 파일의 `drop_index` 구문은 의도한 것인지 반드시 확인해야 한다.

---

## §54. 주간 식단표 일괄 적재 — 주차를 시트에서 읽는다 (2026-08)

식단표를 올릴 때마다 파일 하나당 명령을 한 번 치고 `--week-start`를 손으로
계산해 넣어야 했다. 8개월치 31개를 적재할 때 실제로 문제가 됐다.
`cli.py weekly-menu-batch <폴더>`로 통합한다.

### 54.1 `--week-start`가 애초에 필요 없었다

`parse_weekly_menu_grid` docstring에 *"원본 표에는 요일만 있고 절대 날짜가
없으므로(PRD 2.2), 호출부가 운영자에게 물어 전달한다"* 고 적혀 있었는데,
**같은 파일의 `find_header_row` 주석이 정반대를 적고 있었다** — 2026-07 실사용
확인 결과 헤더 셀은 `"7/6(월)"`처럼 날짜를 달고 있고, 날짜서식이면 xlwings가
`datetime`을 그대로 돌려준다. `_weekday_label`이 요일만 뽑고 **날짜를 버리고
있었을 뿐**이다.

두 서술이 어긋난 채로 남아 있었고 아무도 몰랐다. 낡은 쪽을 바로잡았다.

### 54.2 ⚠️ 연도를 "가장 가까운 해"로 고르면 안 된다

`"7/6(월)"`엔 연도가 없다. 근접도로 고르면 **소급 적재가 미래로 찍힌다**:

> 오늘이 2026-08-06일 때 `"12/22"`의 후보는 2025-12-22(227일 전)와
> 2026-12-22(138일 후)다. 가까운 건 **미래**다.

8개월치 소급은 연말을 반드시 넘으므로 이론적 걱정이 아니다.

**요일 라벨을 연도의 체크섬으로 쓴다.** 같은 월/일의 요일은 해마다 1~2일씩
밀리므로 후보 3년(작년/올해/내년) 안에서 요일이 겹치는 일이 없다 — 오프셋이
`0, s₁, s₁+s₂`이고 `1≤s≤2`라 최대 4로 7 미만이다. 즉 요일이 맞는 해는 **정확히
하나**다.

| 연도 | 7/6 | 12/22 |
|---|---|---|
| 2025 | 일 | **월** |
| 2026 | **월** | 화 |
| 2027 | 화 | 수 |

후보가 0개거나 2개 이상이면 **추측하지 않고 그 파일을 건너뛴다.** 2/29처럼 그
해에 없는 날짜는 후보에서 조용히 빠진다.

교차 검증도 건다: 6개 헤더 칸이 가리키는 월요일이 전부 같아야 한다. 한 칸만
다른 주를 가리키면(`7/13`도 월요일이라 그 칸만 보면 멀쩡하다) 실패시킨다.

### 54.3 ⚠️ 청크 분할이 방금 넣은 행을 지운다

`upload.py`는 500행씩 잘라 여러 번 POST하는데, 백엔드는 **요청마다** payload에
등장하는 `(plan_date, corner, meal_type)` 슬롯을 지우고 넣는다. 한 슬롯이 청크
경계에 걸치면 **두 번째 요청이 첫 번째 요청의 삽입분을 지운다.**

주 1개는 보통 500행 미만이라 지금은 안 터지지만, 조식·석식 파싱을 켜면 넘는다 —
그때 "부찬 몇 개가 조용히 사라지는" 형태로 나타난다. 그래서 `replace_existing`일
때는 슬롯 경계를 존중해 자른다(`_slot_aware_chunks`). 슬롯 하나가 500행을 넘으면
쪼개지 않고 단독 요청으로 보낸다 — 쪼개면 자기가 자기를 지운다.

회귀 방지를 위해 테스트가 **슬롯 인지 청킹을 끄면 실제로 깨지는지**까지
확인해 뒀다(끄면 `test_slot_is_never_split_across_requests` 등 2건 실패).

### 54.4 `--dry-run`을 먼저 권하는 이유

주를 잘못 읽으면 그 주 편성이 어긋나는 데서 끝나지 않는다 — 교체 방식이라
**멀쩡한 다른 주를 덮어쓴다.** 그래서 업로드 전에 항상 `파일 → 인식된 주 →
행 수` 표를 출력하고, `--dry-run`으로 그 표만 보고 끝낼 수 있게 했다.
이 표가 운영자의 마지막 확인 수단이라 한글 파일명이 섞여도 열이 맞도록
표시폭 기준으로 정렬한다(`_pad`).

같은 주를 가리키는 파일이 둘 이상이면 경고한다 — 교체 특성상 **나중 파일이 앞
파일을 덮기** 때문이다.

### 54.5 실패 격리

- 파일 하나가 이상해도 **전체를 중단하지 않는다.** ⚠️로 표시하고 다음 파일로
  간다. 31개 중 1개 때문에 30개를 못 올리면 도구를 안 쓰게 된다.
- 업로드는 **파일 단위**로 보낸다. 중간에 실패해도 어느 주가 안 올라갔는지
  바로 알 수 있고, 교체 방식이라 그 파일만 다시 올리면 된다.
- `~$`로 시작하는 엑셀 잠금 파일은 목록에서 뺀다 — 운영자가 식단표를 열어둔 채
  배치를 돌리는 건 흔한 일이고, 안 거르면 매번 깨진 파일로 실패한다.

### 54.6 Excel 인스턴스 재사용

`read_used_range`가 호출마다 `xw.App()`을 띄웠다 내려서 31개면 Excel이 31번 뜬다.
`excel_session()` 컨텍스트매니저로 하나를 재사용한다.

⚠️ App 수명을 늘린 만큼 정리를 놓치면 운영자 PC에 `EXCEL.EXE`가 남는다. 배치를
몇 번 돌리면 보이지 않는 프로세스가 쌓여 PC가 느려지고 그 파일들이 잠긴다.
`read_used_range(app=...)`는 **빌려 쓰고 닫지 않으며**, 수명은 준 쪽이 책임진다.
`app=None`이면 지금까지처럼 자기 인스턴스를 쓰므로 **기존 호출부는 안 바뀐다.**

### 54.7 검증의 한계

xlwings는 Windows 전용이라 **개발 환경에서는 실제 엑셀 파일로 검증할 수 없다.**
`read_used_range`/`excel_session`을 갈아끼워 나머지 전 구간(수집 → 인식 → 파싱 →
업로드 페이로드)을 테스트로 덮었지만, DRM 해제와 실제 시트 레이아웃은 운영자 PC
에서 `--dry-run`으로 확인해야 한다.

---

## §55. 재적재가 부찬을 중복 생성한 사고 (2026-08)

일괄 적재 직후 신고: **"주간식단표에 부찬이 두번씩 들어갔고 중복점검에서도 같은날
메뉴가 두번씩 카운트됨."** 조사해 보니 **서로 독립적인 결함 2개**였다. 하나는
쓰기 경로(진짜 중복 행이 생김), 하나는 읽기 경로(멀쩡한 데이터도 두 번 셈).

둘 다 §54의 배치 기능이 드러냈을 뿐 **그 이전부터 있던 버그**다. `replace_existing`
자체는 앞 라운드에 들어갔고, 그때는 아무도 재업로드를 안 해서 안 보였다.

### 55.1 MANUAL 제외가 오히려 중복을 만들었다

`api/ingest.py`가 슬롯을 교체할 때 `role_source != MANUAL` 행만 지웠다. 의도
("관리자가 화면에서 고친 값을 재업로드가 날리면 안 된다")는 옳다. **그런데 삽입
쪽은 payload를 통째로 다시 넣었다** — `WeeklyMenuPlan(...)` 생성자에 `role_source`가
없어 모델 기본값 `규칙기반`으로.

| 행 | 삭제 | 삽입 | 결과 |
|---|---|---|---|
| 평범한 부찬(RULE) | 지워짐 | 1개 | 1개 ✅ |
| 관리자가 고친 메뉴(MANUAL) | **안 지워짐** | 1개 | **2개** ❌ |

`set_menu_role`은 메인을 하나 지정할 때 **같은 슬롯의 다른 MAIN들을 SIDE로
내리면서 그것들도 MANUAL로 찍는다**(`weekly_menu_review.py:151-153`). 그래서
관리자가 메인 하나만 고쳐도 그 슬롯의 부찬 여러 개가 MANUAL이 되고, 재업로드하면
그게 전부 두 배가 됐다. 신고 문구와 정확히 일치한다.

(`set_health_garden_menus`도 MANUAL로 쓰지만 역할이 HEALTH_GARDEN이고 파서는 그
역할을 만들지 않아 중복되지 않았다 — 이 제외는 올바르게 작동 중이었다.)

**수정**: 살아남을 MANUAL 행의 `(슬롯, 메뉴)`를 먼저 모아두고, 삽입 루프에서 그
메뉴는 **건너뛴다.** 관리자 판단이 파서 결과를 이긴다. 건너뛴 수를
`skipped_manual`로 응답에 실어 CLI가 "N행은 화면에서 고친 값이 있어 그대로
뒀습니다"라고 알려준다 — 안 알려주면 "적재가 안 됐나?"로 읽힌다.

### 55.2 같은 모듈 안에서 집계 규칙이 반대였다

`menu_rotation.py`:

```python
count_in_window:      len({d for d in dates ...})   # 날짜 집합
find_overused_menus:  len(entries)                   # 행 개수
```

`count_in_window`의 docstring은 *"같은 날 여러 코너에 편성된 건 1회로 센다"*고
명시하는데, 같은 화면에 나가는 `find_overused_menus`는 행을 셌다. 같은 날 두
코너에 깔린 메뉴가 2회로, 55.1이 만든 중복 행은 또 2회로 잡혔다.

**수정**: `find_overused_menus`도 고유 날짜 기준으로. 같은 날 중복이 안 보이게
되는 건 아니다 — `classify_rotation`의 `SAME_DAY` 플래그가 그 축을 담당한다.

⚠️ `analysis.py`의 `dates_by_menu`는 **의도적으로** 중복 날짜를 남긴다(SAME_DAY
판정이 그걸 봐야 한다). 거긴 건드리면 안 된다.

### 55.3 replace_existing을 안 켜도 이제 안 쌓인다

예전 테스트가 *"dedup이 없으므로 그냥 다시 올리면 행이 쌓인다"*를 **의도된
성질로 고정**하고 있었다. 그 성질이 곧 이번 사고의 다른 얼굴이었다.

이제 삽입 전에 그 슬롯의 기존 행을 조회해 **이미 있는 `(슬롯, 메뉴, 역할)`은
건너뛴다.** `replace_existing`은 여전히 의미가 있다 — 그건 **식단표에서 빠진
메뉴를 지우는** 쪽이고, 이 경로는 **있는 걸 또 넣지 않는** 쪽이다.

payload 자체의 중복(한 셀에 같은 부찬이 두 번)도 같은 자리에서 제거한다.

### 55.4 유니크 인덱스 — 조용히 망가지지 않게

이번 건은 **에러 없이 데이터가 망가진 사고**다. 같은 슬롯에 같은 메뉴가 같은
역할로 두 번 있을 이유가 없으므로 제약을 걸었다:

```
uq_weekly_menu_plan_slot_menu_role (plan_date, corner_id, meal_type, menu_id, menu_role)
```

⚠️ **순서가 중요하다.** 제약을 먼저 걸면 정상 입력이 500으로 죽는다 — payload
중복 제거(55.3)가 반드시 먼저 들어가야 한다. 마이그레이션도 **기존 중복을 먼저
정리한 뒤** 인덱스를 만든다. 안 그러면 운영 DB에서 실패한다.
남기는 우선순위는 `관리자수동 > LLM추정 > 규칙기반`, 동률이면 가장 작은 id.

실제로 중복이 있던 로컬 DB에서 검증했다: 28행 → 20행, 인덱스 생성 성공,
§50의 성능 인덱스 11개 모두 생존.

### 55.5 이미 쌓인 중복 치우기

- **1차: 재실행.** 고친 백엔드로 같은 폴더를 `weekly-menu-batch` 다시 돌리면
  그 슬롯이 정리된다. 대부분 이걸로 끝난다.
- **2차: 정리 스크립트.** 원본 엑셀이 없는 과거 주는
  `python -m app.maintenance.dedupe_weekly_menu_plan` (dry-run 기본, `--apply`로만
  삭제). 마이그레이션과 같은 우선순위 규칙을 쓴다.

### 55.6 테스트가 실제로 잡는지 확인했다

두 결함 다 **"없으면 그냥 통과하는"** 종류라, 수정을 되돌려 테스트가 진짜
깨지는지 확인했다(§54.3에서 쓴 방법):

- `ingest.py`의 MANUAL 건너뛰기·payload dedupe를 되돌림 → 신규 5건 전부 실패
- `find_overused_menus`를 `len(entries)`로 되돌림 → 신규 4건 전부 실패

---

## §56. 실사용 피드백 6건 (2026-08)

### 56.1 메뉴명 매칭 — 표시명과 매칭 키를 분리한다

신고: "연어파피요트 취식현황에도 있고 주간식단표에 있는데 매칭이 안되고있음".

원인은 메뉴 join이 사실상 **정확 문자열 비교**라는 것이었다. 정규화가 "끝에 붙은
원산지 주석 떼기" 하나뿐이었고(`master_data.py`), `menu_master.menu_name`은
**바이트 단위 unique**라 아래가 전부 별개 행이 됐다:

| POS 표시명 | 식단표 셀 |
|---|---|
| `연어파피요트` | `연어 파피요트` (내부 공백) |
| `연어파피요트` | `연어파피요트（연어:노르웨이산）` (전각 괄호) |
| `연어파피요트` | `연어파피요트(연어:노르웨이자연산)` (7자 원산지 — 상한이 6자였다) |
| `(포장)연어파피요트` | `연어파피요트` (앞에 붙은 건 안 뗐다) |

매칭 진단은 `menu_id` 정수 집합 차집합이라, **눈에 똑같은 이름이 `plan_only`와
`log_only`에 동시에** 떴다.

**⚠️ 표시명을 정규화해 저장하지 않았다.** 그러면 담당자가 화면에서 엑셀 셀과
대조할 수 없고 감사 추적이 끊긴다. 대신 조회 전용 `menu_master.match_key`를 두고
`get_or_create_menu`가 그걸로 찾는다. `match_key`는 NFKC → 접두 주석 제거 →
원산지 주석 제거 → 공백 전부 제거 → 소문자화.

`unique`를 안 건 이유: 이미 갈라진 행들이 있어 제약을 걸면 마이그레이션이 운영
DB에서 실패한다. 병합은 `app/maintenance/merge_duplicate_menus.py`가 dry-run
확인을 거쳐 한다. **삭제가 아니라 참조 재지정(remap)이다** —
`purge_origin_annotation_menus`가 `meal_log.menu_id`를 NULL로 만들어 과거 취식
이력이 영영 끊긴 전례가 있다.

진단 화면에는 `likely_same_menu`를 추가했다. 정규화하면 같아지는 짝을 기계가
짚어준다 — 담당자가 두 목록을 눈으로 대조하던 일이다.

⚠️ 이걸로도 안 풀리는 경로가 남아 있다: `menu-plan/performance`가 **MAIN만**
세므로, 연어파피요트가 셀 둘째 줄에 있어 SIDE로 들어갔다면 여전히 `log_only`다.

### 56.2 과거 VoE가 항상 최신 주로 열리던 문제

원인이 둘이었다.

1. `App.tsx`의 `onOpenWeeklyVoe={() => setTab("weekly-voe")}` — **인자가 없다.**
   라우터도 URL도 없어 주차가 흐를 통로 자체가 없었다.
2. `WeeklyMenuVoeDetailPage`가 `useState(mondayOf(new Date()))`로 **현재 주에
   고정**(setter조차 없음). 탭 전환마다 재마운트돼 매번 오늘 기준으로 재계산됐다.

타일 숫자는 선택 주차를 따르는데 들어간 화면은 현재 주라 "숫자는 있는데 0건"이 됐다.
`App`에 `weeklyVoeMonday`를 두고 prop으로 넘긴다.

**함께 고친 것 — `mondayOf`의 시간대 버그.** 두 파일에 복제돼 있었고 둘 다
`getDay()`/`setDate()`(로컬)와 `toISOString()`(UTC)을 섞어 써서, KST 오전 9시
이전에는 **전날(=일요일)**이 나와 6일 창이 통째로 밀렸다. `src/lib/week.ts`로
합치고 전부 로컬 기준 포맷으로 바꿨다.

### 56.3 금주 예상 식수 코너별 — 백엔드 작업이 없었다

`simulation.py`가 이미 날짜마다 총계와 **코너 배열을 함께** 돌려주고 있었고
타입에도 있었다(`WeeklyForecastDay.corners`). 프론트가 총계만 뽑고 버리는 중이었다.
누적 막대로 다시 그리는 토글만 추가했다.

⚠️ **새 쿼리 파라미터로 만들면 안 된다.** 이 예측은 슬롯·코너·날짜마다 과거
180일을 다시 훑어 요청 하나가 수백~수천 SQL이라 "예측 계산하기" 버튼 뒤에 있다(§50).
토글은 순수 클라이언트 측이다 — Playwright로 **전환 시 추가 요청 0건**을 확인했다
(대조군으로 안 눌렀을 때와 비교; 처음엔 통합 추이 차트의 동명 "코너별" 버튼을
잘못 눌러 2건이 잡혔다).

### 56.4 `&`로 이어진 메인메뉴가 행 경계에서 잘리던 문제

같은 셀 안 줄바꿈(`함박스테이크\n&소스`)은 이미 처리됐지만, `&` 조각이 **그리드의
다음 행**으로 들어오면 `split_cell_into_items`가 셀 단위로만 이어붙여 `&소스`가
별도 부찬이 됐다.

emit 루프에서 항목을 모은 뒤 `_merge_ampersand_fragments`로 **`&`로 시작하는 항목을
직전 항목에 이어붙인다.** 셀 경계와 무관해진다. 첫 항목이 `&`로 시작하면(앞이
없으면) 지어내지 않고 그대로 둔다.

### 56.5 재료 주석 판정 확대 — 그리고 그 대가

`(햄-계육, 돈육:국내산)`이 부찬으로 들어왔다. `is_origin_annotation_text`가 괄호 안
**모든** 항목이 원산지여야 주석으로 봤는데, `햄-계육`은 끝 토큰이 `산`으로 안 끝나
원산지가 아니라서 괄호 전체가 메뉴가 됐다.

담당자 선택에 따라 **원산지가 없어도 재료 짝(`A-B`/`A:B`)만 있으면 주석**으로 본다.

⚠️ **정상 메뉴명을 지울 위험이 생겼다** — `(오징어볶음-매운맛)`도 같은 형태다.
완화 장치로 **첫 토큰이 조리법 어미**(볶음/구이/찜/탕/조림…)로 끝나면 메뉴명으로
보고 남긴다. 재료 주석의 첫 토큰은 `햄`·`돈육`·`계육`처럼 재료명이다.
**휴리스틱이라 실제 파일을 보며 계속 보강해야 한다.**

이 규칙은 백엔드 `menu_name.py`와 파서에 **복제**돼 있다 — 짝 테스트(`ORIGIN_CASES`)에
같은 케이스를 두어 한쪽만 고치면 깨지게 했다.

### 56.6 중복은 코너 안에서 — 건강가든만 예외

담당자 기준이 바뀌었다: "포기김치가 다른 코너에서 각각 나왔다고 중복이면 안 되고
건강가든하고만 중복 봐야함."

`find_overused_menus`가 코너를 **아예 안 봤다**. 이제 `(코너, 메뉴)` 단위로 세되,
건강가든 등장일은 **모든 코너에 합친다** — 건강가든은 누구나 가져가는 공용이라
어느 코너 부찬과 겹쳐도 중복이다.

```
코너 C에서 메뉴 M의 등장일 = {C에서 M이 나온 날} ∪ {건강가든으로 M이 나온 날}
```

⚠️ **`build_corner_menu_dates`는 같은 날짜 중복을 일부러 남긴다.** `classify_rotation`이
SAME_DAY를 리스트 안의 날짜 중복으로 판정하기 때문이다. 그래서 "한식 부찬 나물 +
같은 날 건강가든 나물"은 SAME_DAY로 잡히고, "한식 김치 + 분식 김치"는 각 코너에 한
번씩만 들어가 안 잡힌다 — 정확히 요청된 구분이다. 횟수를 셀 때만 `set()`으로 접는다.

회전 이력도 같은 집합을 쓴다. 같은 화면의 두 숫자가 다른 기준이면 안 된다(§55.2).

⚠️ 이 변경으로 예전 테스트 하나가 **정반대를 주장하게** 됐다 —
`test_rotation_flags_same_day_duplicate_across_corners`는 코너 간 같은 날 편성을
경고로 고정하고 있었다. 기준이 바뀐 것이므로 뒤집었다.

---

## §57. 병합 스크립트가 유니크 제약을 위반한 사고 (2026-08)

담당자가 `merge_duplicate_menus --apply`를 실행하자 IntegrityError로 죽었다:

```
key (plan_date, corner_id, meal_type, menu_id, menu_role) already exists
   → uq_weekly_menu_plan_slot_menu_role
```

### 57.1 병합이 필요한 데이터일수록 충돌이 난다

갈라진 메뉴 두 행을 합칠 때 `weekly_menu_plan.menu_id`를 대표 행으로 재지정하는데,
**같은 슬롯에 두 표기가 모두 편성돼 있으면** 재지정 결과가 기존 행과 완전히 같아져
§55.4에서 건 유니크 인덱스를 위반한다.

```
슬롯 (2026-07-06, 한식, 중식):
  행 A: menu_id=42 "연어파피요트"   role=메인
  행 B: menu_id=43 "연어 파피요트"  role=메인
  43 → 42 재지정하면 행 B가 행 A와 동일해진다
```

여기서 놓친 게 있다. **식단표에 두 표기가 같이 올라간 것이 애초에 갈라짐의
원인**이다. 즉 병합 대상이 되는 메뉴일수록 같은 슬롯에 공존할 확률이 높고,
"드문 예외"가 아니라 **기본 상황**이었다. 실사용에서 첫 실행에 바로 터졌다.

**수정**: 재지정 전에 대표 메뉴가 그 슬롯·역할에 이미 있는지 확인한다.
- 없으면 → 재지정 (편성 이력 보존)
- 있으면 → 진짜 중복이므로 대표 행에 **흡수**(삭제)

### 57.2 ⚠️ 흡수되는 행을 취식기록이 참조 중이다

`meal_log.menu_snapshot_id`는 `weekly_menu_plan.id`를 가리키는 FK다. 그냥 지우면
FK 위반으로 또 죽고, NULL로 밀면 **§56.1에서 내가 문제 삼은 "이력 끊김"을 그대로
반복**하는 것이다(`purge_origin_annotation_menus`가 그렇게 해서 과거 취식 이력이
영영 끊겼다).

삭제 전에 **살아남는 행으로 재지정**한다. 실데이터 검증에서 스냅샷 참조가
NULL이 아니라 생존 행을 가리키는 것까지 확인했다.

dry-run은 세 숫자를 나눠 보여준다 — `--apply` 전에 규모를 알아야 한다:

```
'연어파피요트'(id=42) ← '연어 파피요트'(id=43)
    식단표: 1행 옮김 / 1행은 같은 슬롯에 이미 있어 합침
    취식기록: 1행 옮김
    스냅샷 참조 재지정: 1행
```

### 57.3 데이터는 안 망가졌다

`merge_duplicate_menus`는 루프가 다 끝난 뒤 한 번만 `db.commit()` 한다. 예외는 그
전에 났고 `run()`의 `finally: db.close()`가 트랜잭션을 롤백한다 — **부분 반영 없음.**
실패해도 안전한 이 구조는 의도한 것이고, 대량 수정 스크립트에서 유지할 성질이다.

### 57.4 파생 컬럼을 손으로 채우면 언젠가 빠뜨린다

같은 조사에서 **아직 안 터진 같은 뿌리의 버그**를 찾았다.
`weekly_menu_review.set_health_garden_menus`가 `get_or_create_menu`를 안 쓰고 직접
`MenuMaster(menu_name=...)`를 만들어 **`match_key`가 NULL로 남았다.** 그러면 나중에
같은 이름이 식단표로 들어올 때 `get_or_create_menu`가 키로 찾다 못 찾고 같은
`menu_name`으로 INSERT → `menu_master_menu_name_key` 위반.

`match_key`를 §56.1에서 추가할 때 **채우는 곳을 하나만 고친 것**이 원인이다.

**구조적 수정**: `match_key`를 파생값으로 만들었다. `MenuMaster`에 SQLAlchemy
`before_insert`/`before_update` 이벤트를 걸어 `menu_name`에서 항상 계산한다.
이제 **어떤 코드 경로로 만들든** 키가 맞는다. 규칙을 "모든 작성자가 기억해야 하는
것"에서 "모델이 보장하는 것"으로 옮긴 셈이다.

건강가든 경로는 `get_or_create_menu`를 쓰도록 교체했다 — 이미 있는 함수를 안 쓰고
있던 것이라 코드가 줄었다. 부수 효과로 건강가든 메뉴도 food_vector 태깅을 받는데,
한 끼 구성 중복 판정이 그 값을 쓰므로 오히려 맞는 방향이다.

### 57.5 조회 경로도 하나만 고쳐져 있었다

`match_key`를 넣으면서 `get_or_create_menu`만 바꿔서, 아래 네 곳은 여전히 이름
정확 일치였다 — 담당자가 검색창에 `연어 파피요트`라고 띄어 쓰면 못 찾는다.

- `dashboard.py` 메뉴 이력 / 과거 VOE 코멘트
- `analysis.py` 신메뉴 지정 / 메뉴 단건 조회

`master_data.find_menu_by_name`으로 통일했다. 키로 찾고 **없으면 이름으로 폴백**한다
— 키가 아직 안 채워진 행이 남아 있을 때 조용히 "없음"이 되는 것보다 낫다.

### 57.6 FK를 손으로 열거하다 또 놓쳤다

같은 스크립트가 두 번째 신고로 다시 죽었다:

```
key menu_id is still referenced from table "menu_performance_stats"
```

`weekly_menu_plan`·`meal_log`만 챙기고 **`menu_performance_stats`를 빠뜨렸다.**
57.2에서 "참조를 옮긴 뒤에만 지운다"고 적어놓고도, 참조 목록을 머릿속에서 꺼내
쓴 탓에 세 번째를 놓쳤다. DB에 물어보면 3초면 나오는 것이었다.

`menu_performance_stats`는 성격이 다르다 — **파생 집계**다. 옮기면
`(period_start, period_end, menu_id)` 유니크에 걸리고(57.1과 같은 충돌), 설령
안 걸려도 두 행의 점수는 더할 수 있는 값이 아니라 원본에서 다시 계산해야 한다.
그래서 **대표 것까지 통째로 지우고 재계산에 맡긴다** — 병합으로 그 메뉴의 취식
집합 자체가 바뀌었으니 대표 행 통계도 어차피 낡았다.

**재발 방지**: 삭제 직전에 `information_schema`로 `menu_master.menu_id`를 참조하는
모든 (테이블, 컬럼)을 읽어 남은 참조가 있는지 검사한다. 있으면 raw IntegrityError
대신 **테이블 이름을 담은 메시지로 중단**한다:

```
'연어파피요트' 병합 중단 — 아직 참조가 남아 있습니다: {'새테이블.menu_id': 3}.
이 스크립트가 모르는 테이블이 생겼습니다. ...
```

교훈은 두 개다. **참조 목록처럼 스키마를 따라 늘어나는 것은 손으로 관리하지
않는다**(§57.4의 `match_key`와 같은 실수를 다른 형태로 반복했다). 그리고 잘못될
수 있는 지점에는 **원인을 말해 주는 실패**를 심어 둔다 — 이번에 두 번 다 스택만
보고 어느 테이블인지 찾아야 했다.

## §58. 원산지 주석이 문자열 끝이 아니면 안 떨어지던 버그 (2026-08)

신고 두 건:

```
명란크림파스타(명란:미국산)&베이컨포테이토피자 → 명란크림파스타&베이컨포테이토피자가 메인 메뉴여야 하는데 안 떨어짐
햄마늘종볶음(햄-계육, 돈육:국내산) → 햄마늘종볶음이 부찬이어야 하는데 안 떨어짐, 재료 중복 화면에 "햄마늘종볶음(햄-계육"처럼 잘려 나옴
```

### 58.1 원인 1 — 스트립이 문자열 끝에서만 동작했다

`strip_origin_annotation`(백엔드)과 `_strip_origin_annotation`(파서)이 쓰던
`_TRAILING_PAREN` 계열 정규식은 `\s*\(([^()]*)\)\s*$`로 **`$`(문자열 끝) 앵커**가
걸려 있었다. `"명란크림파스타(명란:미국산)&베이컨포테이토피자"`는 괄호 뒤에
`"&베이컨포테이토피자"`가 더 있어 괄호가 문자열 끝이 아니다 — 매치 자체가 안
되고 원문이 그대로 반환됐다.

**수정**: 끝에 고정된 패턴 + while 루프로 끝에서부터 벗겨내는 방식 대신,
`_PAREN_GROUP_PATTERN = re.compile(r"\s*\(([^()]*)\)")`(`$` 앵커 제거)로
**문자열 안의 모든 괄호 그룹**을 `re.sub`로 훑어 원산지/재료-짝으로 판정되는
것만 제거한다.

### 58.2 원인 2 — 두 판정 함수가 서로 다른 규칙을 썼다

§56.5에서 "원산지가 아닌 재료 짝만 있어도 주석으로 본다"는 규칙
(`is_ingredient_pair`)을 추가했는데, **`is_origin_annotation_text`(셀 전체가
주석인지 판정)에만 넣고 `strip_origin_annotation`(이름 뒤 주석을 떼는 함수)에는
안 넣었다.** `"햄-계육"`은 "산"으로 안 끝나 원산지로 안 잡힌다.
`is_origin_annotation_text`는 재료-짝 폴백이 있어 `"(햄-계육, 돈육:국내산)"`
같은 **단독** 셀은 통과시키지만, 이름 뒤에 붙은
`"햄마늘종볶음(햄-계육, 돈육:국내산)"`을 떼는 스트립 함수는 그 폴백이 없어
아예 못 뗐다.

**수정**: `_entries_are_removable(entries, *, allow_bare)` 공유 헬퍼(원산지
전부 OR 재료-짝 전부)를 뽑아 `is_origin_annotation_text`와
`strip_origin_annotation` 양쪽이 같은 판정을 쓰게 했다. "한쪽만 규칙을 넓히고
한쪽은 안 넓히는" 이번 사고 패턴이 구조적으로 막힌다.

양쪽 파일에 동일 적용 — `ingestion-tool/parsing/weekly_menu_parser.py`와
`backend/app/services/menu_name.py`는 코드 공유가 안 되는 복제 관계라(§51
이후 관례) 짝 테스트(`test_weekly_menu_parser.py` ↔ `test_menu_name.py`의
`ORIGIN_CASES`)로 어긋남을 잡는다.

⚠️ 조리법 어미로 끝나는 경우(`"(오징어볶음-매운맛)"`) 보호 장치는 그대로다 —
정상 메뉴명이 사라지는 회귀는 없다(기존 케이스 전부 재확인 완료).

### 58.3 이미 저장된 오염 데이터 — 새 정리 스크립트

`match_key`는 `strip_origin_annotation`을 호출해 계산되지만, 그건
`before_insert`/`before_update` 이벤트가 있을 때만 재계산된다(§57.4). 코드를
고쳐도 **이미 만들어진 `menu_master.menu_name`은 저절로 안 바뀐다.**

새로 만든 `app/maintenance/rename_menus_with_leftover_annotation.py`(dry-run
기본, `--apply`로 실행)가 `menu_name`에 아직 남은 주석을 정정된 값으로
UPDATE한다. UPDATE하면 `match_key`가 이벤트로 자동 재계산된다.

`menu_name`엔 unique 제약이 있어, 정정된 이름이 **이미 다른 행이 쓰고 있으면**
그대로 옮길 수 없다(예: "햄마늘종볶음"이 이미 따로 있는데 이 행도 "햄마늘종볶음"이
되려는 경우). 그런 행은 표시명은 그대로 두고 **`match_key`만** 손으로 정정된
값으로 맞춘다 — `merge_duplicate_menus.backfill_missing_match_keys`(§57)가 이미
쓰던 것과 같은 방식이다. 그러면 `merge_duplicate_menus.py`(§57에서 이미
검증된 슬롯 충돌·스냅샷 FK·성과 통계 처리)가 다음 실행에서 정확히 병합
대상으로 잡는다 — 이 스크립트는 자기 병합 로직을 새로 안 만든다.

운영 순서: `rename_menus_with_leftover_annotation` → `merge_duplicate_menus`
(둘 다 dry-run 먼저).

### 58.4 검증

두 신고 문자열을 그대로 재현해 고치기 전엔 실패, 고친 후엔 통과하는 것을
직접 확인했다(`ORIGIN_CASES`에 케이스 추가 — 파서·백엔드 양쪽에 동일 반영):

- `strip_origin_annotation("명란크림파스타(명란:미국산)&베이컨포테이토피자")
  == "명란크림파스타&베이컨포테이토피자"`
- `strip_origin_annotation("햄마늘종볶음(햄-계육, 돈육:국내산)") == "햄마늘종볶음"`
- 괄호 두 개짜리도 확인: `"A(원산지1)&B(원산지2)"` → `"A&B"`

수정을 되돌리면(`git stash`) 새 테스트 3건이 정확히 그 이유로 실패하고, 기존
케이스는 그대로 통과하는 것을 확인했다. 복원 후 백엔드 471개·ingestion-tool
170개 테스트 전부 통과.

`rename_menus_with_leftover_annotation`은 (1) 끝 주석/비-끝 주석/재료-짝
케이스 각각의 정정, (2) 주석 없는 이름은 그대로 두는지, (3) dry-run 무변경,
(4) 멱등성, (5) 이름 충돌 시 `match_key`만 정정하고 unique 위반 없이 넘어가는지,
(6) 정정 → `merge_duplicate_menus` 순서로 실행하면 실제로 병합까지 끝까지
이어지는지(end-to-end) — 8개 테스트로 확인했다.

## §59. "&"가 이름 끝에 남아도 이어붙이지 못하던 버그 (2026-08)

신고: `뽀모도로파스타&불고기피자`, `중국식게살볶음밥&자장소스` 같은 메뉴가
§56(4·5)에서 "&" 이어붙이기를 고쳤는데도 여전히 "&" 뒤가 부찬으로 분리됨.

### 원인

`split_cell_into_items`(셀 안 줄바꿈)와 `_merge_ampersand_fragments`(행 경계)
둘 다 "**다음** 조각이 `&`로 시작하는가"만 검사했다. 실제로는 엑셀 줄바꿈이
`&`의 반대쪽에서 끊기는 경우도 흔하다 — `"뽀모도로파스타&\n불고기피자"`처럼
`&`가 **이전** 조각의 끝에 남는 경우다. 이 경우 다음 조각(`"불고기피자"`)은
`&`로 시작하지 않으므로 이어붙이기 조건에 안 걸려 독립 부찬이 됐다.

### 수정

두 함수가 공유하는 `_continues_previous(prev, part)` 헬퍼를 추가해 "다음 조각이
`&`로 시작" **또는** "이전 조각이 `&`로 끝남" 둘 중 하나면 이어붙이게 했다.
`&`가 어느 쪽에 남든 엑셀 작성자 입장에선 같은 의도이므로 대칭으로 처리한다.

```python
def _continues_previous(prev: str, part: str) -> bool:
    return bool(prev) and (part.startswith("&") or prev.endswith("&"))
```

기존 케이스(`"함박스테이크", "&소스"` — 다음 조각이 `&`로 시작하는 경우, 앞에
붙일 게 없는 `"&소스"` 단독 케이스, 진짜 부찬을 안 먹는 케이스)는 회귀 없이
그대로 통과한다.

**이 버그는 파서(`ingestion-tool/parsing/weekly_menu_parser.py`)에만 있었다**
— "&" 이어붙이기는 셀/행을 몇 개의 `weekly_menu_plan` 행으로 나눌지 정하는
**파싱 시점** 로직이라 `backend/app/services/menu_name.py`(표시명 정규화)엔
대응하는 코드가 없다. §58과 달리 **정정 스크립트로 되돌릴 수 없다** — 이미
잘못 갈라져 저장된 메인/부찬 행 구조는 이름만 고쳐서 합칠 수 있는 문제가
아니라, 애초에 몇 개의 행으로 쪼갤지가 잘못됐기 때문이다. 영향받은 주차는
`POST /ingest/weekly-menu`에 `replace_existing=true`로 **재적재**해야 한다
(§118의 멱등 재적재 경로를 그대로 쓴다).

### 검증

두 신고 문자열을 그대로 재현해 고치기 전엔 실패(`test_ampersand_trailing_
previous_row_also_joins` 등 3건), 고친 후엔 통과하는 것을 확인했다(`git
stash`로 수정만 되돌려 재확인). 기존 "&" 관련 케이스 전부 회귀 없음.
ingestion-tool 전체 테스트 173개 통과.

## §60. "탕"이 이름 어디에 있어도 국물로 걸리던 버그 (2026-08)

신고: "탕수육이 탕이 들어간다고 해서 국물이 아니고, 중국식오이무침이 국이
들어간다고 국물로 오인함".

### 확인

`중국식오이무침`은 **현재 코드에서는 재현되지 않는다** — `soup_based` 키워드
(`국물`·`찌개`·`국밥`·`스프`·`우동`·`전골`·`샤브`)와 접미어 검사
(`국`/`탕`으로 끝나는지) 어느 것에도 안 걸린다(직접 실행해 확인: soup_based
0.2, `vegetable_ratio`가 "무침"에 걸려 매칭). §57.4의 "국" 오탐(외국산·중국산·
국내산이 걸리던 문제)은 이미 이전 라운드에서 접미어 조건으로 고쳐져 있었다.

`탕수육`은 **재현됐다** — `soup_based` 키워드 목록에 `"탕"`이 **바이트 그대로**
들어 있어 `"탕" in "탕수육"`이 참이 된다. "국"과 정확히 같은 버그 패턴인데
"탕"만 그때 같이 안 고쳐졌다.

### 원인과 수정

`_KEYWORD_RULES["soup_based"]`에서 `"탕"`을 제거하고, `_SOUP_SUFFIX`("국"
접미어 검사)를 `_SOUP_SUFFIXES = ("국", "탕")`로 넓혀 **"탕"도 이름 끝에 올
때만** 국물로 인정한다. `감자탕`·`설렁탕`·`삼계탕`·`곰탕`·`매운탕`처럼 실제
국물 메뉴는 전부 "탕"으로 끝나므로 회귀가 없고, `탕수육`(끝이 "육")·
`탕평채`(끝이 "채")는 더 이상 안 걸린다.

### 이미 저장된 데이터 — 새 정리 스크립트

이 버그도 §58·§57과 같은 구조다: 규칙은 `get_or_create_menu`가 신메뉴를 처음
만들 때만 불리므로, 코드를 고쳐도 **이미 규칙기반으로 태깅된 `food_vector`는
저절로 안 바뀐다.** `app/maintenance/retag_food_vector_with_rules.py`(신규,
dry-run 기본)가 `food_vector_source != MANUAL`인 모든 행에 대해
`tag_food_vector_from_name`을 다시 돌려, 값이 달라지면 갱신한다.

- **`MANUAL`인 행은 절대 안 건드린다** — food_vector 3단계 태깅의 공통 규칙.
- **LLM으로 채워졌던 행도 규칙이 새로 매칭되면 `RULE`로 승격**한다 — 신메뉴
  최초 태깅과 같은 우선순위(규칙 → LLM)를 기존 데이터에도 동일하게 적용하는
  것뿐이다.
- 규칙이 하나도 안 걸리는 행(`matched_any=False`)은 기존 값을 그대로 둔다 —
  LLM 추정치를 규칙 미스매치로 지우면 안 된다.

`중국식오이무침`이 실제 화면에서 여전히 국물로 보인다면, 그 메뉴의
`food_vector`가 **더 오래된(§57.4 이전) 버전의 "국" 규칙**으로 계산된 채
저장돼 있고 그 뒤로 재태깅된 적이 없다는 뜻이다 — 이 스크립트를 돌리면
`matched_any`가 이번엔 False가 되어(현재 규칙 어디에도 안 걸림) 값 자체를
바꾸진 않지만, 그 경우는 관리자가 화면에서 수동 조정(`PUT .../food-vector`)
하거나 `POST /api/analysis/menus/tag-with-llm`으로 LLM 보정을 새로 받아야
한다 — 규칙에 없는 조합이라 규칙 재적용만으로는 못 고친다.

### 검증

"탕수육"·"탕평채"를 직접 실행해 재현(수정 전 soup_based=0.85 확인) → 수정
후 낮아짐을 확인. "감자탕"·"설렁탕"·"삼계탕"·"곰탕"·"매운탕" 등 진짜 국물
메뉴는 회귀 없이 그대로 잡힘. 수정을 되돌리면(`git stash`) 새 테스트가 정확히
그 이유로 실패하고, 기존 국-관련 테스트는 그대로 통과하는 것을 확인했다.

`retag_food_vector_with_rules`는 (1) 옛 규칙으로 저장된 값의 갱신, (2)
`MANUAL` 행 보호, (3) 이미 최신 규칙과 일치하는 값은 안 건드림, (4) LLM
소스 행이 규칙 매칭 시 `RULE`로 승격, (5) dry-run 무변경, (6) 멱등성 — 6개
테스트로 확인했다. 백엔드 전체 479개 테스트 통과.

## §61. 자주 반복되는 부찬을 한눈에 보는 랭킹 뷰 (2026-08)

담당자 피드백: "부찬 중복 볼 때 보기가 너무 불편함. 정말 자주 나오고 돌려막기한
부찬을 보고싶어."

### 원인

"중복 점검" 화면(`DuplicationCheckSection`)은 한 주씩 넘기며 보는 구조였다.
그 주에 여러 번 편성된 메뉴는 화면 맨 아래 작은 배지 뭉치로 줄바꿈 나열만
됐다 — 정렬도 없고, 한 주 단위라 "지난 3개월 동안 이 부찬이 유독 자주
돌아갔다" 같은 그림 자체가 안 보였다.

### 수정

새 로직을 만들 필요는 없었다 — `app/services/menu_rotation.py`의
`find_overused_menus`가 이미 코너 안에서 고유 날짜 기준으로 세고 `-count`
정렬까지 하는 순수 함수였다(§128, §132). 문제는 기존
`/weekly-menu/rotation` 엔드포인트가 이걸 **화면이 요청한 한 주치**로만
호출하고 `threshold=3`(기본값)로 걸러 "이번 주 과다 편성"만 보여준다는
배선(wiring)에 있었다.

새 엔드포인트 `GET /analysis/weekly-menu/repeated-side-dishes`를 추가해
담당자가 직접 고른 임의 기간(길어도 됨) + 선택적 코너 필터로
`find_overused_menus(planned, threshold=0)`를 호출한다. `threshold=0`은
컷오프를 없애 등장 1회 이상인 모든 (코너, 메뉴)를 정렬된 채로 돌려준다 —
컷오프로 자르는 대신 순위(정렬)로 판단하게 한다. 응답은 메인을 빼고
부찬·건강가든만 남긴다(기존 화면이 이미 "부찬 · 건강가든"을 한 그룹으로
묶어온 경계와 동일).

`/weekly-menu/rotation`을 그대로 긴 기간에 재사용하지 않은 이유: 그쪽은 매
행마다 `classify_rotation` 회전 판정(`items`)까지 계산한다 — 이번 요청엔
집계만 필요해서, 그 연산을 안 하는 새 엔드포인트가 긴 기간에도 가볍다
(§117에서 "무거운 요청"을 문제 삼은 전례를 되풀이하지 않기 위해).

프론트(`DuplicationCheckSection`)는 기존 배지 블록을 독립된 기간 선택
(`<input type="date">` 시작/종료 — 다른 화면의 기존 패턴 재사용)과 코너
필터(`SegmentedControl` — `MenuComboSection`의 기존 패턴 재사용), 실제
정렬된 `Table`(순위/코너/메뉴/역할/횟수)로 교체했다. 이 서브섹션의 상태는
나머지 섹션이 쓰는 주간 네비게이션과 분리돼 있어 위쪽 회전 판정 표는 그대로
한 주씩 넘기고, 이 랭킹만 독립적으로 기간을 바꾼다. 기본 20개만 보여주고
더 있으면 "전체 N개 보기" 토글로 펼친다.

### 검증

API 레벨 테스트 5건: (1) 횟수 내림차순 정렬, (2) 메인은 결과에서 빠짐(임시로
역할 필터를 무력화해 실제로 테스트가 잡아내는 것까지 확인), (3) 코너 필터가
같은 이름이라도 코너별로 좁힘(§132 규칙), (4) 건강가든 항목 포함, (5) 같은
날 두 끼니에 겹쳐도 고유 날짜로만 셈. `find_overused_menus` 자체의 코너
스코프·정렬·건강가든 처리는 이미 `tests/test_menu_rotation.py`가 검증하고
있어 여기선 배선만 확인했다.

`npm run build` 타입체크 통과. `uvicorn`+`vite` 개발서버를 직접 띄우고
`/api/ingest/weekly-menu`로 6주치 샘플 데이터(포기김치 35회, 단무지 12회 등)를
넣은 뒤 Playwright로 실제 화면을 열어 확인: 랭킹 표가 횟수 내림차순으로
뜨는지, 코너 필터 클릭 시 그 코너(+건강가든)로만 좁혀지는지, 20개 초과 시
"전체 N개 보기"를 눌러 펼쳐지고 "접기"로 되돌아가는지 — 전부 스크린샷으로
확인. 백엔드 전체 484개 테스트 통과.

## §62. Toss 스타일 UI 리디자인 — 팔레트 · 폰트 · 컴포넌트 (2026-08)

담당자: "전반적인 UI도 toss 처럼 깔끔하고 전문적이게 바꿔줘 지금은 색상도 폰트도
난잡함."

### 조사 — "난잡함"의 실체는 색상이 아니라 폰트였다

색상은 이미 `frontend/src/index.css`의 `:root`/다크모드 블록 하나에 토큰
(`--ink`, `--surface`, `--accent`, `--critical` 등)으로 정리돼 있고, 컴포넌트는
전부 `var(--token)`으로만 참조한다(하드코딩 색은 앱 전체 4곳뿐, 전부 의도된
예외 — 히트맵 대비 계산 등, §40.5). 문제는 폰트였다:

1. 한글 웹폰트가 아예 없었다 — `system-ui, ..., "Malgun Gothic", sans-serif`
   (Windows 시스템 폰트 의존).
2. 작은 텍스트가 `text-xs`(12px)와 `text-[13px]`로 204곳에 걸쳐 규칙 없이
   섞여 있었다 — 같은 역할(표 셀·라벨·보조 텍스트)인데 크기가 들쭉날쭉.

### 수정 — 토큰 이름은 그대로, 값만 교체해 336곳 호출부를 안 건드림

**팔레트**: `index.css`의 `:root`/다크 블록 값을 Toss류 쿨 뉴트럴 그레이 +
선명한 블루로 교체(`--page: #f9f9f7`→`#F2F4F6`, `--accent: #2a78d6`→`#3182F6`
등). `--series-2`~`--series-8`, 차트 전용 값은 dataviz 스킬 기준으로 이미
접근성 검증돼 있어 그대로 뒀다 — 이번 불만과 무관.

**폰트**: Pretendard 가변 폰트(100~900 굵기 전부 커버, 파일 하나)를
self-host했다. 사내망 배포(PRD 9.4)라 외부 CDN(jsdelivr 등)은 프록시
정책상 막혀 있었고(`403`), `npm view pretendard dist.tarball`로 npm
레지스트리(허용 목록에 있음)를 통해 받아 `frontend/public/fonts/`에 넣었다
— `node_modules`를 통해 파일만 복사하고 `pretendard` npm 패키지 의존성 자체는
바로 제거해 런타임에 안 남게 했다.

**12px/13px 통일**: Tailwind v4의 CSS-first `@theme` 블록으로
`--text-xs: 0.8125rem`(13px)를 재정의했다. 이러면 기존 `text-xs`(76곳)가
전부 13px가 되어 더 많이 쓰인 `text-[13px]`(128곳)와 저절로 통일된다 — 204개
호출부를 하나도 안 건드리고 전역 수정. 리터럴 `text-[13px]`를 `text-xs`로
바꾸는 코드 정리는 급하지 않아 미룸(시각적으로 이미 같아짐).

**컴포넌트 재단장**(`frontend/src/components/ui.tsx`): props/API는 그대로
두고 클래스만 조정 — `Card`/`StatTile` `rounded-md`→`rounded-2xl` +
`shadow-sm`, `Button`/`ErrorState` `rounded-md`→`rounded-xl`,
`SegmentedControl`/`QuadrantBadge` 완전 라운드(`rounded-full`, Toss가 자주
쓰는 필 형태), `Table` 행 패딩 소폭 확대, `StatTile` 값 텍스트
`font-semibold`→`font-bold`. **"색은 점(dot)에만" 규칙(§39.12)은 그대로
유지** — 상태색은 여전히 값 텍스트가 아니라 점·왼쪽 보더에만 입힌다.

**스팟 체크**: `<Card>`를 안 쓰고 직접 마크업한 박스(`rounded-md border p-3`
패턴, `AnalysisPage.tsx` 9곳 + `HomePage.tsx` 1곳 — 중복 점검의 슬롯 클래시
카드 등)가 새 카드 스타일 옆에서 튀어 보여 `rounded-xl`로 맞췄다. 3400줄을
전수 스윕하지 않고, 스크린샷으로 실제로 안 맞아 보이는 곳만 점 수정했다.

### 검증

`npm run build` 타입체크 통과(props 불변이라 컴파일 에러 없음). `uvicorn`+
`vite` 개발 서버를 직접 띄우고 Playwright로 홈·메뉴 편성·운영(중복 점검
포함) 페이지를 라이트·다크 둘 다 스크린샷 확인 — Pretendard 폰트가 실제
`getComputedStyle`에 반영됐는지, 카드 라운드·그림자, 세그먼트 컨트롤 필
형태, 색-온-점 규칙이 살아있는지, 콘솔 에러 없는지 확인. 스팟 체크로 찾은
클래시 카드 수정 후 재스크린샷으로 통일 확인. 백엔드 484개 테스트는
이번 라운드가 CSS/클래스만 바꿔서 영향 없음 — 회귀 확인용으로 재실행해
전부 통과 확인.

## §63. 탭 제목 + 중복 점검 기간 선택·표 너비 개선 (2026-08)

담당자 피드백 3건:

1. 브라우저 탭 제목이 Vite 기본값 "frontend"로 남아 있었음.
2. "중복점검"의 회전 이력 표(재편성 과다/평소보다 이름 등)가 한 주씩
   넘기는 구조라 임의 기간으로 볼 수 없었음. "직전에 언제 나왔는지나 주기"도
   보고 싶다고 함.
3. "자주 반복되는 부찬 랭킹" 표(§61)의 코너 열이 좁아 코너명이 길면 글자가
   세로로 늘어짐.

### 1. 탭 제목

`frontend/index.html`의 `<title>` 텍스트만 "미래기술캠퍼스 Cafeteria"로 교체.

### 2. 회전 이력 표 — 백엔드 무변경, 프론트 배선만 교체

`GET /analysis/weekly-menu/rotation`은 이미 `period_start`/`period_end`를
임의로 받는다 — 화면(`DuplicationCheckSection`)이 `selectedMonday`로 매번
"한 주"만 넘겨서 호출하고 있었을 뿐이다. §61에서 "자주 반복되는 부찬
랭킹"에 적용한 것과 같은 패턴(독립된 `<input type="date">` 시작/종료)을
회전 이력 표에도 적용했다 — `rotationStart`/`rotationEnd`라는 별도 상태를
두고, 우측 "한 끼 구성 겹침" 축은 요청 범위 밖이라 그대로 주간 네비게이션을
유지했다(최소 범위).

"주기" 요청에 대응해 API가 이미 내려주던(§55.2~) `avg_interval_days`를
"평균 주기" 열로 새로 노출했다 — 예전엔 판정 색에만 간접 반영되고 화면에
숫자로 안 보였다. 넓은 기간을 고르면 행이 많아질 수 있어 §61과 같은
"상위 15개(그룹별) + 전체 보기" 안전판을 뒀다.

### 3. 표 가로 폭 — 공유 컴포넌트 + 레이아웃 두 가지로 고침

**공유 `Table`**(`components/ui.tsx`)에 `whitespace-nowrap`을 셀에 추가하고
`<table>`을 `overflow-x-auto`로 감쌌다 — 한 곳만 고쳐서 이 컴포넌트를 쓰는
모든 표(회전 이력, 랭킹, 레퍼토리, 스프레드랭킹 등)에 전부 적용되므로 같은
문제의 재발을 막는다. 셀 안에서 글자가 세로로 늘어지는 대신, 넘치면 표
컨테이너가 가로 스크롤을 받는다.

**"자주 반복되는 부찬 랭킹" 표 배치**: `lg:grid-cols-2`(좌: 회전+랭킹, 우:
클래시 체크) 구조의 **좌측 절반 폭**에 갇혀 5개 열(순위/코너/메뉴/역할/횟수)이
좁았다. 이 표를 grid 밖, **카드 전체 폭**을 쓰는 섹션으로 뺐다 — 회전
이력 표는 좌측 칼럼에 남고, 랭킹 표만 grid 아래 별도 블록이 됐다.

### 검증

`npm run build` 타입체크 통과. `uvicorn`+`vite` 개발 서버를 띄우고, 긴
코너명("미래기술캠퍼스 본관 지하1층 한식코너")과 10주치 편성 데이터를
`/ingest/weekly-menu`로 넣은 뒤 Playwright로 확인:
- 탭 제목이 "미래기술캠퍼스 Cafeteria"로 바뀌었는지
- 회전 이력 표 시작일을 11주 전으로 넓혔을 때 "재편성 과다"가 기간 전체
  (197건/239건)에서 잡히는지, "평균 주기" 열이 채워지는지("1일", "1.1일" 등),
  가로 스크롤로 "평균 주기"/"3개월" 열까지 보이는지
- 랭킹 표가 카드 전체 폭을 쓰고 긴 코너명이 줄바꿈 없이 한 줄로 나오는지
  (코너 필터 세그먼트에서도 확인)

백엔드 무변경이라 484개 테스트는 회귀 확인용으로만 재실행해 전부 통과 확인.

## §64. 강수-식수 상관관계 분석 — 과거 실측 기반, 중기예보 아님 (2026-08)

담당자 피드백: "비가 온다고 식수가 줄지 않고 오히려 외부에서 먹지 않아서
늘어날수도있음 이것도 과거 데이터를 토대로 보고싶은데 중기 날씨 api 받아서
할 수 없어?"

`app/api/simulation.py`의 `_WEATHER_MULTIPLIER[RAIN] = 0.90`은 "비가 오면
식수가 준다"는 **실측 근거 없는 v0 감**이고(§8에서 이미 "전부 v0 추정치"로
명시), 코드 주석에도 "날씨는 기상청 연동이 없어 사용자가 고른 값을 그대로
적용한다(2026-08 결정)"라고 남아 있다. 담당자의 가설은 이 v0 가정과 정반대다
— 감으로 정한 배수를 감으로 뒤집는 대신, 과거 실측 데이터로 먼저 검증하는
화면을 만들었다. **이번 라운드는 그 배수를 바꾸지 않는다** — 결과를 사람이
보고 나중에 별도로 판단한다.

담당자가 말한 "중기 날씨 api"는 미래 예보(4~10일 후)만 다루는 별도 API라
"과거 데이터를 토대로" 보고 싶다는 요청에는 맞지 않는다. 과거 실측 날씨가
필요해 기상청의 **ASOS 종관기상관측 일자료**(data.go.kr,
`AsosDalyInfoService/getWthrDataList`)를 썼다 — 관측소는 사업장 소재지
기준 수원(관측소 ID 119)을 기본값으로 뒀다.

### 데이터 원천 — 라이브 API + CSV 대체 경로

이 세션과 사내망 배포 서버 둘 다 data.go.kr(공인 인터넷)에 못 닿을 수 있어,
`InternalLLMClient.is_configured` 패턴을 그대로 따르는
`KmaWeatherClient`(`app/services/weather_client.py`)를 새로 만들었다 —
`KMA_WEATHER_BASE_URL`/`KMA_WEATHER_API_KEY`/`KMA_WEATHER_STATION_ID` 셋 다
없으면 API 호출 없이 조용히 빈 결과를 준다. `llm_client.py`와 반대로
`trust_env`를 강제로 끄지 않는다 — LLM 게이트웨이는 인트라넷 전용이라
사내 프록시를 우회해야 했지만, 이 API는 공인 인터넷 목적지라 오히려 그
프록시를 타야 도달할 수 있다.

라이브 연동이 안 되는 배포를 위해 `POST /ingest/weather-csv`(기존
`/ingest/*`와 같은 토큰 게이트)로 CSV 기반 수동 임포트 경로도 뒀다. 신규
`scripts/import_weather_csv.py`가 (1) 인터넷 되는 PC에서 CSV를 만들어
올리는 `csv` 서브커맨드, (2) 이 API와 DB 양쪽에 다 닿는 머신에서 전체
이력을 채우는 `backfill` 서브커맨드를 제공한다.

⚠️ 이 세션은 outbound가 제한돼 있어 data.go.kr 실제 응답을 라이브로
확인하지 못했다 — 필드명(`tm`/`sumRn`/`avgTa`)과 관측소 ID는 훈련 지식
기반 추정이다. 배포 전 실제 키로 한 번 대조 확인이 필요하다.

### 스키마 — `daily_weather`, 날짜 단독 키

날씨는 코너/구분/끼니와 무관한 날짜 단위 사실이라, `daily_corner_stats`처럼
코너별로 중복 저장하지 않고 `holiday_calendar`처럼 날짜 하나만 키로 잡는
별도 테이블(`app/models/stats.py::DailyWeather`)로 만들었다 — 코너 수십 개
행마다 같은 값을 복제하면 정정 시 N개 행을 다 고쳐야 하는 문제가 생긴다.
분석 엔드포인트는 SQL JOIN 없이 파이썬 dict 조회로 합친다(기간 내 행 수가
날짜 수 수준이라 카디널리티가 작음).

매일 새벽 배치(`scheduler.py::run_daily_batch`)에 `_fetch_weather_step`을
추가해 전날치를 자동 수집한다 — 기존 LLM 스텝과 같은 방어적 try/except로
감싸, 날씨 수집이 실패하거나 미설정이어도 나머지 배치(통계 집계 등)는
절대 막지 않는다.

### 분석 엔드포인트 — 분류를 섞지 않는다

`GET /analysis/weather-correlation`은 강수 여부 × 평일/주말+공휴일/
패밀리데이 조합별로 과거 실측 평균 식수를 반환한다. **분류를 섞은 전체
평균은 절대 계산하지 않는다** — 평일과 주말+공휴일은 기저 식수 자체가 크게
달라(주말은 원래 인원이 훨씬 적음), 섞으면 "비가 많이 온 달에 마침 주말이
적었다" 같은 우연으로 왜곡될 수 있다. 이게 이번 요청의 핵심 포인트다.
날씨 데이터가 없는 날짜는 `days_missing_weather`로 별도 집계해 화면에서
"N일은 날씨 데이터 없음"으로 밝힌다. 표본이 `weather_correlation_low_sample_days`
(기본 5일) 미만인 버킷은 `low_sample: true`로 표시해 화면에서 흐리게 뜬다.

### 프론트엔드 — "금주 예상 식수" 카드 바로 아래

`HomePage.tsx`의 "금주 예상 식수" 카드(날씨를 수동으로 고르는 v0 배수
드롭다운이 있는 그 카드) 바로 아래 `WeatherCorrelationSection`
(`AnalysisPage.tsx`에 정의, `CornerMetricComparisonSection`과 같은 방식으로
import)을 배치했다 — "위에서 고른 배수가 실측 근거 없는 가정치"라는 걸 바로
옆에서 확인할 수 있게 했다. 강수 유/무 그룹 막대 차트(ECharts) + 분류별 표
+ "상관관계이며 인과관계가 아닙니다" 고정 캐비아트 문구로 구성했다.

### 캐비아트 (반드시 유의)

1. 상관관계이지 인과관계 증명이 아니다.
2. 강수는 계절(장마철 vs 한겨울)과 얽혀 온도 등 다른 변수의 대리일 수 있다.
3. 표본 수가 적은 조합(예: 패밀리데이+비)은 통계적으로 신뢰하기 어렵다 —
   화면에 명시적으로 표시된다.
4. 이 결과가 `_WEATHER_MULTIPLIER`를 자동으로 바꾸지 않는다 — 사람이
   판단해 별도로 반영해야 한다.

### 검증

- 신규 `backend/tests/test_weather_client.py`(5개): `is_configured` 조합,
  정상 파싱(빈 `sumRn`=무강수 케이스 포함), 미설정 시 HTTP 호출 자체가
  안 나가는지, `trust_env`가 강제로 꺼지지 않았는지.
- `test_api_ingest_and_analysis.py`에 4개 추가: CSV 임포트 upsert(재업로드
  시 갱신), 토큰 게이트, 분류×강수 버킷 평균/N 계산, 날씨 데이터 0건일 때
  빈 버킷 반환.
- `pytest -q` 전체 493개 통과(회귀 없음).
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버에 기존 daily_corner_stats(14일, 평일/주말/
  패밀리데이 혼합)를 기준으로 강수·무강수·미설정 날짜를 섞은 `daily_weather`
  합성 데이터를 심고 Playwright로 확인 — 그룹 막대 차트, "N일은 날씨 데이터
  없음" 안내, 표본 부족(<5일) 행의 흐린 표시, 캐비아트 문구가 모두 정상
  렌더링됨을 확인.
- 실 API(data.go.kr) 호출은 이 세션 및 사내망 양쪽에서 라이브 검증이
  불가능했다 — 배포 전 사용자가 실제 키로 `scripts/import_weather_csv.py
  backfill`을 한 번 실행해 소량 대조 확인 필요.

## §65. "스냅스낵"/"스냅스넥" 코너 별칭 병합 (2026-08)

담당자 피드백: "스냅스낵과 스냅스넥은 같은 코너인데 따로 표기되고 있어 엑셀마다
적힌게 달라서 그러니 두개는 같은걸로 취급해줘"

Take Out R/M/L(§17 부근, `app/services/master_data.py`)과 같은 문제 — 엑셀
파일마다 같은 코너를 다르게 표기해서 `corner_master`에 별개 행으로 쌓이고
있었다. 같은 패턴으로 고쳤다:

- `master_data.py`에 `SNAP_SNACK_CORNER_NAME = "스냅스낵"` /
  `SNAP_SNACK_ALIASES = {"스냅스낵", "스냅스넥"}` 추가.
- `_normalize_corner_name`을 `TAKE_OUT_ALIASES`/`SNAP_SNACK_ALIASES` 두
  그룹을 하나의 `_CORNER_ALIAS_MAP` 조회로 처리하도록 일반화했다 — 별칭
  그룹이 늘어도 if/elif를 안 늘리고 매핑에 항목만 추가하면 된다.
- `get_or_create_corner`는 **앞으로 들어오는** 취식기록/식단표에만 적용된다.
  이미 별개 `corner_id`로 갈라져 적재된 과거 데이터를 위해
  `app/maintenance/merge_snap_snack_corners.py`(신규, `merge_take_out_corners.py`와
  동일 구조)를 만들었다 — `meal_log`/`weekly_menu_plan`을 대표 코너로
  재배정하고, 별칭 코너의 `daily_corner_stats`를 지운 뒤 별칭 행 자체를
  삭제한다. 여러 번 돌려도 안전하다(idempotent).

⚠️ 대표 이름("스냅스낵")을 별칭 집합에도 포함시켜서, Take Out과 달리
`get_or_create_corner(db, "스냅스낵")`이 새 행을 만들지 않고 이미 있는
"스냅스낵" 코너를 그대로 대표로 쓴다 — 재배정 대상은 "스냅스넥" 쪽만 된다
(Take Out은 "Take Out"이라는 대표 이름 자체가 원본 표기에 없어 항상 새 행이
생겼던 것과 차이).

### 적용 방법 (운영자)

배포 후 실제 DB에 이미 "스냅스낵"/"스냅스넥"이 별개 코너로 쌓여 있다면
1회 실행 필요:

```
cd backend && python -m app.maintenance.merge_snap_snack_corners
```

실행 후 안내 메시지대로 `daily_corner_stats` 재계산(분석 탭 "최근 180일
배치 집계 재계산" 버튼 또는 `POST /api/analysis/daily-stats/recompute`)이
필요하다.

### 검증

- `test_master_data.py`: 두 표기가 같은 `corner_id`로 합쳐지는지, 무관한
  코너명은 영향받지 않는지.
- `test_maintenance_merge_snap_snack_corners.py`(신규, `test_maintenance_merge_corners.py`와
  동일 구조): 이미 갈라진 과거 데이터를 흉내내 `meal_log` 재배정 검증,
  멱등성(두 번 실행해도 안전) 검증.
- `pytest -q` 전체 496개 통과.

## §66. 중복점검 화면 분리·색상 개선 + 스냅스낵 메뉴명 병합 버그 수정 (2026-08)

담당자 피드백 두 건.

### A. 중복점검이 너무 복잡함

`DuplicationCheckSection`(회전 이력+부찬 랭킹+한 끼 구성 겹침을 `lg:grid-cols-2`
로 한 카드에 몰아넣던 구조)을 두 개의 독립 카드로 쪼갰다:

- **`MenuRotationCheckSection`** — "메뉴 중복 점검"(회전 이력 표 + 자주
  반복되는 부찬 랭킹, 둘 다 "같은 메뉴가 반복 편성되는 문제"라 같이 둔다).
- **`MealClashCheckSection`** — "한 끼 구성 겹침 점검"(슬롯 내 재료·특성
  중복). 이전까지 카드 상단 공용 주간 네비게이션을 이 축만 실제로 썼으므로
  로컬 상태로 옮겼다.

**색 규칙 위반 수정**: 이 섹션만 경고/위험 상태를 텍스트 색(`var(--warning)`/
`var(--critical)`)으로 표시하고 있었다 — 이 앱의 다른 곳(`StatTile`,
`QuadrantBadge`, §39.12)은 전부 "색은 점(dot)에만 싣고 글자는 항상 ink"
규칙을 쓰는데 이 섹션만 안 따르고 있었다. 공용 `Badge` 컴포넌트
(`components/ui.tsx`, 점+ink 텍스트)를 새로 만들어 판정 flag, 최근 90일
초과 표시, 경고 N건 요약, 클래시 카드의 재료/특성 중복 항목 전부를 여기로
교체했다.

**"3개월" 열 명확화**: 실제로는 "최근 90일 편성 횟수(허용치: 메인 2회·부찬
6회)"인데 헤더가 "3개월"뿐이라 뜻이 안 드러났다 — 헤더를 "최근 90일"로
바꾸고, 4문장짜리 캡션을 핵심만 남긴 2문장으로 줄였다(글자 과다 지적 대응).

### B. 스냅스낵 코너 병합 후 메뉴명이 여전히 갈라짐

§65에서 코너명 "스냅스낵"/"스냅스넥"을 병합했지만, 원본 데이터의 메뉴명
자체가 `"진짬뽕라면(스냅스낵)"` / `"진짬뽕라면(스냅스넥)"`처럼 코너명을
괄호로 끝에 붙인 채 들어와 있어 `menu_master`에 별개 행으로 남아 있었다.
코너명 정규화(`master_data._normalize_corner_name`)와 메뉴명 정규화
(`menu_name.strip_origin_annotation`/`match_key`)는 완전히 분리된 경로라
지난 수정이 이 문제엔 영향을 못 줬다.

**설계**: 코너 별칭 상수(`TAKE_OUT_*`/`SNAP_SNACK_*`)를 의존성 없는 새 모듈
`app/services/corner_aliases.py`로 옮겼다 — `menu_name.py`는 "백엔드 안의
유일한 정규화 출처"라 코너 지식을 직접 가지면 안 되는데(순환 임포트 우려),
두 모듈이 같은 별칭 데이터를 공유해야 하기 때문이다. `master_data.py`는 이
모듈에서 다시 임포트해 같은 이름으로 재노출(re-export)하므로 기존
`analysis.py`/`taste_clustering.py`/두 merge 스크립트/테스트의 임포트 구문은
안 바뀐다.

`menu_name._entries_are_removable`에 조건 하나 추가 — 괄호 안 항목이
**정확히 하나**이고 그 항목이 `corner_aliases.ALL_CORNER_NAMES`(대표 이름 +
모든 별칭)와 **완전히 일치**하면 제거 대상으로 인정한다. 원산지 휴리스틱과
별개의 화이트리스트 판정이라 `"김치찌개(얼큰한맛)"` 같은 기존 케이스(실제로
다른 메뉴를 구분하는 임의 괄호 설명)에는 영향이 없다.

이 한 곳만 고치면 `match_key()`가 내부적으로 `strip_origin_annotation()`을
호출하므로 자동으로 효과가 퍼진다. **새 유지보수 스크립트를 안 만들어도
된다** — 기존 `app/maintenance/rename_menus_with_leftover_annotation.py`가
같은 `strip_origin_annotation()`을 직접 호출해 "정정 대상"을 찾으므로, 이미
있는 2단계 파이프라인(rename → merge)이 이 케이스까지 자동으로 잡는다.

같은 판정을 `ingestion-tool/parsing/weekly_menu_parser.py`에도 미러링했다
(두 패키지가 코드를 공유할 수 없어 복제하는 기존 관례 — 짝 테스트로
어긋남을 잡는다).

### 기존 데이터 정리 (운영자, 배포 후 1회)

배포 후에도 이미 갈라져 저장된 기존 `"진짬뽕라면(스냅스낵)"`류 행은 자동
병합되지 않는다(§65와 같은 이유). 이미 있는 2단계 스크립트를 순서대로
실행:

```
cd backend
python -m app.maintenance.rename_menus_with_leftover_annotation --apply
python -m app.maintenance.merge_duplicate_menus --apply
```

끝나면 메뉴 성과 재계산 필요 — `merge_duplicate_menus`가 실행 후 안내
메시지로 알려준다.

### 검증

- `pytest -q` 백엔드 전체 505개 통과(신규: `test_menu_name.py`에 코너 접미어
  케이스 4건 + match_key 병합 확인 1건, `test_master_data.py` 재노출 확인).
- `ingestion-tool` 전체 181개 통과(신규: `test_weekly_menu_parser.py`에 대응
  케이스 4건).
- `get_or_create_menu(db, "진짬뽕라면(스냅스낵)")`/`(스냅스넥)`이 같은
  `menu_id`(표시명 "진짬뽕라면")로 귀결되는지 직접 호출로 재확인.
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버로 Playwright 확인 — 두 섹션이 독립 카드로
  뜨는지, 판정/최근 90일/클래시 목록이 점(dot)+ink 텍스트 조합으로 바뀌어
  눈에 띄는지(실데이터로 재편성 과다 빨간 점, 클래시 카드 재료 중복 빨간
  점·특성 중복 주황 점 확인) 스크린샷으로 확인.

## §67. 메뉴 중복 점검 — 메뉴별로 묶어보기 (2026-08)

담당자 피드백: 스냅스낵 메뉴명 병합(§66)이 정상 작동하는지 함께 확인하는
과정에서, "회전 이력" 표가 (경고 종류 → 날짜) 순으로만 정렬돼 있어 같은
메뉴의 반복 편성 이력이 표 전체에 흩어져 있다는 걸 발견 — "운영 입장에서
알아보기 힘듦"이라는 지적. 예를 들어 "진짬뽕라면(스냅스낵)"이 3/13, 3/23,
4/14, 4/22에 편성됐으면 이 네 날짜가 각각 다른 위치에(경고 종류·날짜
순서로) 떨어져 있어, 이 메뉴 하나의 패턴을 보려면 표 전체를 뒤져 대조해야
했다.

### 원인

`GET /analysis/weekly-menu/rotation`(`analysis.py`)은 이미 올바르게
동작하고 있었다 — 각 행의 "직전 이후"는 그 행 **바로 이전** 편성일을
가리키도록 설계돼 있고(`menu_rotation.classify_rotation`의
`previous = before[-1]`), 실제로 확인해보니 4/22 행이 3/22가 아니라 4/14를
가리키는 것도 정상이었다(그 사이 4/14에도 편성이 있었다는 뜻). 문제는
표시 방식이었다 — `results.sort(key=lambda r: (flag_order, plan_date,
corner_name))`로 **경고 종류·날짜로만 정렬**하고 메뉴로는 전혀 묶지 않아서,
사람이 눈으로 "이 메뉴가 몇 번, 얼마나 자주 나왔는지"를 재구성해야 했다.

### 수정 — 프론트엔드에서 (코너, 메뉴) 단위로 그룹핑

백엔드 API는 필요한 데이터(코너·메뉴·판정·간격 전부)를 이미 다 내려주고
있어 **백엔드 변경 없이** 프론트에서만 해결했다. `AnalysisPage.tsx`에
`buildRotationGroups()` 추가 — `(corner_id, menu_id)` 키로 편성 이력을
묶고, 그룹 안에 경고가 하나라도 있으면 그룹 전체를 "문제 메뉴"로 표시한다.
"경고만 보기"는 이제 그룹 단위로 필터한다(문제 있는 메뉴만 카드로 보여줌).

각 메뉴 카드는: 메뉴명(+코너) · 총 편성 횟수 · 그룹 내 최고 심각도 판정
Badge를 헤더에 두고, 그 아래 개별 편성일·판정·직전 이후·평균 주기·최근
90일을 작은 표로 보여준다.

**추가로 발견한 문제**: 상시 부찬처럼 기간 내내 거의 매일 편성되는 메뉴는
그룹 하나의 이력이 수십 행(실측 60건)이 될 수 있어, 그룹으로 묶은 취지가
무색해질 뻔했다 — Playwright로 실데이터 검증 중 직접 발견. 그룹별로 최근
8건만 먼저 보여주고 "이전 N건 더 보기"로 펼치도록 캡을 뒀다(§61의
미리보기 안전판과 같은 패턴, 이번엔 그룹 개수가 아니라 그룹 안의 건수에
적용).

### 검증

- `npm run build` 타입체크 통과(백엔드 무변경).
- `uvicorn`+`vite` 개발 서버 + 실데이터(6~8월, 상시 부찬 포함 243건 편성)로
  Playwright 확인 — 메뉴별로 카드가 묶이는지, "60회 편성" 같은 대량
  이력이 있는 메뉴가 최근 8건만 보이고 "이전 52건 더 보기"로 펼쳐지는지,
  "문제 메뉴 N개" 요약이 그룹 기준으로 정확한지 확인.
- 백엔드 무변경이라 `pytest -q` 재실행은 생략(§66에서 이미 505개 통과
  확인한 상태 그대로).

## §68. `import_weather_csv.py backfill` — DB 접속 없이 CSV만 뽑을 때도 DB를 접속하던 버그 수정 (2026-08)

담당자가 백필 1단계(`backfill --out-csv ...`, DB 접속 불필요하게 설계된
경로)를 실행했는데 "5432 fatal error"(Postgres 인증 실패)가 났다는 신고.

**원인**: `scripts/import_weather_csv.py::cmd_backfill`이 `--write-db`
여부와 무관하게 함수 시작 시점에 무조건 `SessionLocal()`로 DB에 접속해
`daily_corner_stats`에서 백필 시작일을 추정하고 있었다 — `--out-csv`
전용으로 쓸 때도 이 DB 접속이 걸림돌이 됐다. 담당자의 `docker-compose.yml`은
`db` 서비스에 호스트 포트 매핑이 없어(사내망 컨테이너 간 통신만 전제),
서버에서 스크립트를 직접 돌리면 애초에 DB에 정상적으로 못 닿는 구성이었다
— CSV 전용 경로까지 DB를 요구한 게 설계 결함이었다.

**수정**: `--start-date`(및 `--end-date`) 옵션을 새로 추가해 시작일을
직접 지정할 수 있게 했다. `--start-date`가 있으면 DB를 아예 안 건드리고,
`--write-db`를 켰을 때만(그때는 어차피 DB에 upsert해야 하므로) 편의상
`daily_corner_stats`에서 자동 추정하는 기존 동작을 유지한다. 어느 쪽도
없이 `--out-csv`만 쓰면 명확한 안내 메시지와 함께 종료한다(자동 추정을
시도하지 않음).

사용법(DB 접속 전혀 없이 CSV만 뽑기):
```
python scripts/import_weather_csv.py backfill --start-date 2026-01-01 --out-csv weather_backfill.csv
python scripts/import_weather_csv.py csv --backend-url http://localhost:8000 --token $INGEST_API_TOKEN --file weather_backfill.csv
```

## §69. 기상청 API TLS 인증서 오류 대응 — `kma_weather_ca_bundle` (2026-08)

사내 방화벽을 연 뒤 기상청 API 백필 스크립트를 돌렸더니
`unable to get local issuer certificate` 에러가 났다는 신고. 사내 프록시가
아웃바운드 HTTPS를 TLS 인터셉션(자체 인증서로 재서명)하는 전형적인 증상이다
— curl/브라우저는 OS 신뢰 저장소를 봐서 문제없이 통과하는 경우가 많지만,
httpx는 기본으로 certifi가 번들한 인증서 목록만 신뢰하고 OS 신뢰 저장소나
`SSL_CERT_FILE` 환경변수를 자동으로 보지 않는다.

**수정**: `KmaWeatherClient`가 `settings.kma_weather_ca_bundle`(PEM 파일
경로)이 설정돼 있으면 그 경로를 `httpx.AsyncClient(verify=...)`로 넘겨
사내 루트 인증서를 추가로 신뢰하게 했다. 미설정 시 기본 동작(`verify=True`,
certifi 목록)은 그대로다. **`verify=False`로 검증 자체를 끄는 방식은
쓰지 않는다** — 안전하지 않고, 이 프로젝트의 다른 곳에서도 그런 패턴을
쓴 적이 없다.

- `config.py`에 `kma_weather_ca_bundle: str = ""` 추가.
- `.env.example`에 `KMA_WEATHER_CA_BUNDLE=` 추가.
- `docker-compose.yml`에 환경변수 전달 + (선택) 사내 인증서를 컨테이너에
  마운트하는 `volumes` 예시(기본은 `/dev/null` 매핑이라 안 쓰면 무해).

### 적용 방법 (운영자)

1. 사내 IT/보안팀에서 사내 프록시 루트 인증서(PEM)를 받는다.
2. Docker 없이 직접 실행하는 경우: `.env`에
   `KMA_WEATHER_CA_BUNDLE=/path/to/corp-ca.pem` 추가.
3. Docker Compose로 배포하는 경우: 인증서 파일을 서버에 두고,
   `docker-compose.yml`의 주석 처리된 `volumes` 줄을 해제 + `.env`에
   `KMA_WEATHER_CA_BUNDLE_HOST_PATH=/path/to/corp-ca.pem`과
   `KMA_WEATHER_CA_BUNDLE=/etc/ssl/certs/kma-weather-ca.pem`을 설정한다.

### 검증

- `test_weather_client.py`에 2개 추가: `kma_weather_ca_bundle` 미설정 시
  `verify=True`(기본 동작 유지), 설정 시 그 경로가 그대로 `verify`로
  전달되는지.
- `pytest -q` 전체 507개 통과.

## §70. 기상청 API 서비스키 이중 인코딩 방지 (2026-08)

담당자가 방화벽·인증서 문제를 다 해결한 뒤 "serviceKey가 이중 인코딩되는
것 같다"고 지적 — 공공데이터포털 API에서 매우 흔한 함정이다.

**원인**: 공공데이터포털은 같은 API에 "일반 인증키(Encoding)"와
"일반 인증키(Decoding)" 두 종류를 발급한다. Encoding 키는 이미 퍼센트
인코딩된 문자열(`%2F` 등 포함)인데, `KmaWeatherClient`가 이 값을 httpx의
`params=` 딕셔너리에 그대로 넣고 있었다 — httpx는 쿼리 파라미터 값을
자동으로 인코딩하므로, 이미 인코딩된 문자열을 넣으면 `%`가 `%25`로 다시
인코딩되는 이중 인코딩이 발생해 인증이 깨진다.

**수정**: 서비스키에 퍼센트 인코딩 패턴(`%[0-9A-Fa-f]{2}`)이 있으면
Encoding 키로 간주해 URL에 직접 붙여 다시 인코딩되지 않게 하고, 없으면
Decoding 키로 간주해 기존처럼 `params`에 넣어 httpx가 인코딩하게 둔다 —
사용자가 어느 키를 `.env`에 넣었는지 몰라도 두 경우 다 올바르게 동작한다.

### 검증

- `test_weather_client.py`에 2개 추가: 인코딩된 키(`%2F` 등 포함)를 넣으면
  URL에 그대로 붙어 `%25`로 깨지지 않는지, 인코딩 안 된 키는 기존처럼
  httpx가 정상적으로 인코딩하는지.

## §71. 메인메뉴 × 날씨유형(비/폭설/폭염/한파) 인기 랭킹 (2026-08)

날씨 데이터가 정상적으로 채워지기 시작한 뒤(§68~70), 담당자가
`GET /analysis/weather-correlation` 화면을 보고 추가 요청:

> "비오는건 부찬까진 신경 안 써도 되고 메인메뉴 기준으로. 예를 들면
> 비오면 김치찌개가 평소보다 많이 찾았다던지, 폭설이면 어떻고, 폭염이면
> 메밀소바 인기고 이런 식."

`weather_correlation`은 `daily_corner_stats`를 코너·메뉴 무관하게 전부
더한 **하루 총 식수** 하나만 보여준다 — 개별 메뉴가 날씨유형별로 어떻게
달랐는지는 안 보인다. 이번 기능은 그 아래 단계, **메인메뉴 하나하나가
비/폭설/폭염/한파의 날 평상시 대비 얼마나 달랐는지**를 보여주고, 주간
메인메뉴를 편성할 때 참고 자료로 쓰게 한다.

⚠️ 이번에도 원칙은 동일: **참고용 정보 제공까지만**이다. 이 결과가
`simulation.py`의 `_WEATHER_MULTIPLIER`(v0 감)나 주간 식단표 예측치
(`weekly_menu_prediction.py`)를 자동으로 바꾸지 않는다.

### 부찬은 왜 신경 안 써도 되는가

`meal_log.menu_id`는 이미 그 사람이 실제로 고른 **메인메뉴** 그 자체다 —
부찬은 1인당 개별 기록이 안 남는다(`menu_plan_performance`와 동일 전제,
§49 이후 계속 확인되는 사실). 그래서 `weekly_menu_plan.menu_role`을
조인해 "이게 메인인지" 따질 필요 없이, `meal_log`만으로 바로 메뉴별
집계가 된다.

### 날씨 데이터 확장 — 폭설/폭염/한파 분류에 필요한 필드

기존 `daily_weather`엔 `precip_mm`/`had_rain`/`avg_temp_c`만 있어 "비"는
이미 되지만, 폭설(적설량 필요)과 폭염/한파(일 최고/최저기온 필요 — 평균
기온으론 기상청 특보 기준과 안 맞음)는 못 만든다. ASOS 일자료 API
(`getWthrDataList`)는 같은 응답에 `dsnw`(일 신적설)/`maxTa`/`minTa`도
같이 내려주는 필드라 **API를 새로 붙이지 않고 파싱 필드만 추가**했다:

- `DailyWeatherRecord`/`DailyWeather`에 `snow_cm`/`max_temp_c`/`min_temp_c`
  추가(`weather_client.py`, `models/stats.py`, 마이그레이션
  `cc1556243b8c`).
- `/ingest/weather-csv`, `scripts/import_weather_csv.py`의 CSV 스키마에도
  같은 3개 컬럼 추가(없으면 하위호환으로 `None`).

⚠️ 이 세 필드도 기존 `precip_mm`/`avg_temp_c`와 같은 캐비아트가 적용된다
— 필드명이 훈련 지식 기반 추정이라 배포 전 실제 응답과 대조 확인 필요.

**기존 데이터 재백필 필요**: 이미 저장된 `daily_weather` 행은 이 세
필드가 `NULL`이라 폭설/폭염/한파 분류가 안 된다(비/평상시 구분만 가능).
배포 후 `scripts/import_weather_csv.py backfill --write-db`(또는 CSV
경로)를 한 번 더 돌려 기존 기간을 재백필해야 한다 — upsert 로직이라
같은 날짜를 다시 불러오면 기존 행이 새 필드까지 갱신된다.

### 날씨유형 분류 — `weather_event.py`

`WeatherEvent`: 평상시/비/폭설/폭염/한파, 상호 배타적. 순수 함수
`classify_weather_event(precip_mm, snow_cm, max_temp_c, min_temp_c, settings)`가
우선순위 **폭설 → 폭염 → 한파 → 비 → 평상시**로 하루를 분류한다(폭설은
저온 강수라 한파 조건과 겹칠 수 있어 더 구체적인 신호를 먼저 봄).
임계값은 `config.py`에 새로 추가한 `heavy_snow_threshold_cm`(5.0)/
`heatwave_temp_c`(33.0)/`coldwave_temp_c`(-12.0) — 기상청 특보 기준을
참고한 기본값이나, **실사용 전 담당자 확인 필요**(관측소 ID·ASOS
필드명과 같은 톤의 캐비아트).

### 메뉴×날씨유형 집계 — `analysis.py`

기존 `weather_correlation`은 건드리지 않는다(이미 검증된 카드, 회귀
리스크 최소화) — 별도 함수/엔드포인트로 신설:

- `_headcount_by_date_by_menu_bulk`: `meal_log`를 `(menu_id, 날짜)`로
  한 번의 group-by-count 쿼리로 묶어 메뉴별 일자별 식수를 만든다
  (`_corner_id_by_menu_from_meal_log`의 group-by-count 패턴 재사용,
  플레이스홀더 메뉴 제외).
- `_menu_weather_event_summary`: 메뉴 하나의 날짜별 식수를 날씨유형별로
  묶어 평상시 평균 대비 `diff_vs_normal`을 계산. 그 유형 자체가 표본
  부족이거나 비교 기준(평상시)이 표본 부족이면 `diff_vs_normal: null`
  + `low_sample: true`(표본 부족 기준은 기존 `weather_correlation_low_sample_days`
  재사용, 새 설정값 없음).
- `GET /analysis/menu-performance/weather-event-ranking?period_start=&period_end=&event=비|폭설|폭염|한파[&meal_type=]`:
  요청받은 유형 하나에 대해 전체 메뉴를 `|diff_vs_normal|` 내림차순으로
  랭킹(표본 부족 행은 숨기지 않고 뒤에 붙임 — 이 레포의 기존 관례). 4개
  유형을 한 응답에 다 넣지 않는 이유: 매번 전체 메뉴×4유형을 계산하면
  무거워서, 프론트가 탭을 눌러 유형을 바꿀 때만 그만큼 계산한다.

### 슬롯 상세 참고 — `predicted-impact` 확장

`/weekly-menu/{plan_id}/predicted-impact`(주간 식단표에서 "예측 보기"
누를 때만 호출되는 단건 엔드포인트) 응답에 `weather_reference` 필드
추가 — 그 슬롯 메인메뉴 하나의 날씨유형별(겪은 유형만) 평상시 대비
참고치. `compute_predicted_numbers`와 같은 이력 윈도우
(`_HISTORY_WINDOW_DAYS`, 그 슬롯 직전 180일)를 본다.

일괄 조회용 `/weekly-menu/predicted-impact-summary`(기간 전체 슬롯을
한 번에)엔 **넣지 않는다** — 슬롯 수만큼 쿼리가 늘어나는 걸 막기 위해
LLM 코멘트를 단건 전용으로 뺀 것과 같은 이유.

### 프론트

- `WeatherCorrelationSection`("비 오는 날 식수" 카드, 현황 탭)의 기존
  코너 합산 막대그래프 아래에 "메인메뉴 × 날씨유형 인기 랭킹" 블록
  추가 — 비/폭설/폭염/한파 탭 + 탭별 랭킹 표(메뉴명/그 유형 평균/평상시
  대비/표본). `Badge`(§66 dot+ink 컴포넌트)로 `|diff|`가 3명 이상이면
  강조(양수=초록/`good`, 음수=빨강/`critical`), 표본 부족은 회색/`muted`.
- `PredictedImpactPanel`(슬롯 상세)에 "과거 날씨 참고" 한 줄 추가 —
  그 메인메뉴가 겪은 유형별 평균·표본·평상시 대비를 나열, 표본 부족은
  흐리게.

### 검증

- `test_weather_event.py`(신규): `classify_weather_event` 경계값 8개
  케이스(폭설/폭염/한파/비/평상시, 우선순위 겹침, 결측 필드) 전부 통과.
- `test_api_ingest_and_analysis.py`에 6개 추가: 랭킹 엔드포인트가 비
  오는 날 유독 식수가 높은 메뉴를 상위에·올바른 부호로 올리는지, 표본
  부족 플래그, 잘못된 `event` 파라미터 400, `predicted-impact`의
  `weather_reference`가 이력 있을 때 채워지고 없을 때 빈 리스트로
  조용히 빠지는지. `pytest -q` 전체 522개 통과.
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버 기동 후 Playwright로 실제 브라우저에서
  확인: (1) "현황" 탭의 새 랭킹 표에서 비/맑음 각 5일씩(6명 vs 2명)
  시딩한 메뉴가 "비 6명 · 평상시 대비 +4명 · 표본 5일"로 정확히
  렌더링됨, (2) "메뉴 편성·운영" 탭의 슬롯 상세("예측 보기")에서 "과거
  날씨 참고: 비 6명(5일) +4 · 평상시 2명(5일)" 한 줄이 정확히 렌더링됨.
  콘솔 에러 없음.

### 검증 중 발견한 별개 이슈 (이번 라운드 범위 밖, 수정 안 함)

Playwright로 확인하던 중, **§71과 무관한 기존 버그**를 하나 발견했다 —
`/ingest/weekly-menu`로 이미 메인메뉴가 있는 슬롯(날짜·코너·끼니)에
`menu_role: "메인"`인 행을 또 넣으면, 기존 메인 행이 자동으로 부찬으로
강등되지 않는다(수동 변경 엔드포인트 `set_menu_role`만 그렇게 동작함).
그 결과 한 슬롯에 `menu_role=메인`인 행이 2개 이상 남을 수 있고, 그
슬롯의 "진짜 메인"이 무엇인지는 조회 기간에 따라 달라진다 — 예를 들어
그 날짜 하루만 조회하면 A가 메인으로 나오는데, 그 날짜를 포함하는 주
전체를 조회하면 B가 메인으로 나오는 식(`weekly_menu_review.py`의 슬롯
그루핑이 정렬 기준 없이 첫/마지막 매치를 쓰는 것으로 추정 — 근본 원인은
미확인). §71 기능(메뉴×날씨유형 집계, 슬롯 상세 참고)은 이 버그의
영향을 받지 않는다 — `weather-event-ranking`은 `meal_log.menu_id`만
쓰고, `predicted-impact`의 `weather_reference`는 `plan_id`로 행을 직접
조회해 그루핑 로직을 거치지 않기 때문이다. 다만 이 버그 자체는 실제
운영 데이터에서도 "정정된 식단표를 재업로드했는데 어떤 게 메인인지
화면마다 다르게 보인다"는 형태로 나타날 수 있어, 별도 라운드로 다뤄야
한다.
- `pytest -q` 전체 509개 통과.

## §72. 날씨유형 재백필 안내 + 메인메뉴 × 계절 인기 랭킹 (2026-08)

§71 배포 직후 담당자 피드백:

> "비 정보만 들어있음 폭설 폭염 한파 데이터도 추가해줘 계절로 묶은것도"

두 가지가 섞여 있었다.

### "비 정보만 들어있음" — 버그가 아니라 재백필 안내 부재

`classify_weather_event`(§71, `weather_event.py`)는 `snow_cm`/
`max_temp_c`/`min_temp_c`가 전부 `NULL`인 날은 그 세 분기가 전부
`is not None` 가드에 걸려 스킵되고 항상 "비" 또는 "평상시"로만 분류
된다. §71 배포 전에 이미 쌓여 있던 기존 `daily_weather` 행은 이
컬럼들이 구조적으로 `NULL`이므로 — **재백필
(`scripts/import_weather_csv.py backfill --write-db`) 전에는 폭설/
폭염/한파가 절대 나오지 않는다.** 이건 §71 문서에 이미 "기존 데이터
재백필 필요"로 적혀 있었지만, 화면이 이걸 스스로 알려주지 않고 그냥
"이 기간에 이 유형인 날이 없습니다"라고만 떠서, 마치 그 날씨가 애초에
없었던 것처럼 보여 혼동을 줬다.

고친 부분은 코드가 아니라 **화면이 원인을 구분해서 알려주는 것**뿐이다
— 재백필 자체는 여전히 운영자가 실행해야 한다.

`_weather_event_by_date`(`analysis.py`)가 기간 내 `DailyWeather` 행을
로드하는 김에, 그 기간에 `snow_cm`/`max_temp_c`/`min_temp_c`가 하나도
채워지지 않았는지를 같이 계산해 `extended_fields_missing: bool`로
반환한다(행 자체가 하나도 없으면 — 즉 그 기간에 날씨 데이터 자체가
없으면 — `False`다: "데이터가 없다"와 "재백필이 안 됐다"는 서로 다른
안내라 구분해야 한다). `GET /analysis/menu-performance/weather-event-
ranking` 응답에 이 필드가 추가됐다.

프론트(`WeatherCorrelationSection`)는 날씨유형 랭킹이 비어 있고
(`rows.length === 0`) `extended_fields_missing`이 참이고 선택된 탭이
"비"가 아닐 때만, 기존 "이 기간에 유형인 날이 없거나…" 문구 대신
"적설량·기온 데이터가 아직 없습니다. `scripts/import_weather_csv.py
backfill --write-db`로 날씨 데이터를 다시 백필해야 폭설/폭염/한파
분류가 가능합니다."로 안내한다. "비" 탭은 애초에 `precip_mm`만 있으면
분류되므로 이 안내와 무관하다.

### 계절별 메인메뉴 랭킹 — 신규 `backend/app/services/season.py`

`Season` enum(`SPRING="봄"`, `SUMMER="여름"`, `FALL="가을"`,
`WINTER="겨울"`) + 순수 함수 `classify_season(date) -> Season` — 기상학적
계절 관례(3~5월 봄, 6~8월 여름, 9~11월 가을, 12·1·2월 겨울)로 월만
보고 분류한다. 연도는 무관하다 — 여러 해의 같은 계절을 다 하나로
합쳐서 본다("여러 해의 여름을 합쳐 봄"). 날씨 임계값(폭염 33도 등)과
달리 계절 월 구간은 실측 캘리브레이션이 필요 없는 고정 관례라 새 config
값을 만들지 않았다.

`diff_vs_overall`이 §71의 `diff_vs_normal`과 기준이 다른 이유: 날씨유형은
"평상시"라는 자연스러운 기본 그룹이 있다(비 오는 날이 아닌 날이 다수) —
그래서 평상시 대비로 비교한다. 계절은 그런 기본 그룹이 없다 — 모든
날짜가 정확히 하나의 계절에 속한다. 대신 **그 메뉴의 전체 기간 평균
대비 그 계절 평균**을 쓴다 — `menu_throughput.py::
compute_menu_throughput_summary`가 이미 쓰는 "overall_avg 대비 하위
그룹 평균" 패턴을 그대로 재사용한 것이다.

신규 함수 `_menu_season_summary(headcount_by_date, low_sample_days)`가
전체 날짜 평균(`overall_avg`)을 먼저 구하고, `classify_season`으로
날짜를 계절별로 묶어 계절별 평균·표본수·`diff_vs_overall`(계절평균 -
전체평균)을 계산한다. 표본 부족 기준은 §71과 같은
`weather_correlation_low_sample_days`를 재사용한다. 데이터 로딩은
§71의 `_headcount_by_date_by_menu_bulk`를 그대로 재사용한다 — 계절은
날짜에서 바로 계산되므로 `daily_weather` 조회가 필요 없다.

신규 엔드포인트 `GET /analysis/menu-performance/season-ranking?
period_start=&period_end=&season=봄|여름|가을|겨울[&meal_type=]` —
§71의 `weather-event-ranking`과 같은 모양으로, 요청받은 계절 하나만
계산해 `|diff_vs_overall|` 내림차순으로 정렬하고 표본 부족 행은 뒤에
붙인다.

### 프론트

`client.ts`에 `Season` 타입, `MenuSeasonRow`/`MenuSeasonRankingResponse`
타입, `menuSeasonRanking(...)` 함수 추가. `WeatherCorrelationSection`의
"메인메뉴 × 날씨유형 인기 랭킹" 블록 아래에 같은 모양의 "메인메뉴 ×
계절 인기 랭킹" 블록을 추가했다 — 봄/여름/가을/겨울 탭, 표(메뉴명/그
계절 평균/전체 평균 대비/표본), `Badge`로 `|diff| >= 3`이면 강조(§71과
같은 기준). "냉면은 여름에, 팥죽은 겨울에" 같은 패턴을 보라는 안내
문구와 "여러 해의 같은 계절을 합쳐 봅니다"라는 캐비아트를 덧붙였다.

### 검증

- `test_season.py`(신규, 9개): `classify_season` 월 경계값(2/28, 3/1,
  5/31, 6/1, 8/31, 9/1, 11/30, 12/1) 전부 + 연도 무관 확인(2025년·2027년
  1월 둘 다 겨울).
- `test_api_ingest_and_analysis.py`에 6개 추가: `extended_fields_missing`이
  `snow_cm`/`max_temp_c`/`min_temp_c` 전부 `NULL`일 때 참, 하나라도
  채워지면 거짓임을 확인. 여름·가을 헤드카운트를 다르게 시딩한 메뉴가
  계절 랭킹 상위에 올바른 부호(`diff_vs_overall`)로 올라오는지, 표본
  부족 플래그, 잘못된 `season` 파라미터 400 확인. `pytest -q` 전체
  536개 통과.
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버 기동 후 Playwright로 실제 브라우저에서
  확인: (1) `daily_weather`에 `snow_cm`/`max_temp_c`/`min_temp_c`가
  전부 `NULL`인 행만 있는 기간에서 "폭설" 탭을 누르면 재백필 안내
  문구가 정확히 렌더링됨, (2) 여름 5일(6명) vs 가을 5일(2명)로 시딩한
  냉면이 "메인메뉴 × 계절 인기 랭킹"의 "여름" 탭에서 "여름 평균 6명 ·
  전체 평균 대비 +2명 · 표본 5일"로 1위에 정확히 렌더링됨. 콘솔 에러
  없음.

## §73. 기상청 API httpx 클라이언트 — 사내망 프록시 우회를 설정으로 (2026-08)

담당자가 `scripts/import_weather_csv.py backfill`을 사내망에서 돌리다가
에러를 만났고, 참고 자료가 `httpx.Client(proxies={"all://": None})`처럼
프록시를 완전히 꺼야 한다고 알려줬다 — **사내에서 안 되는 원인이
프록시**라는 뜻이다.

이건 `weather_client.py`의 기존 가정과 정반대다. §69에서 이미 사내
프록시 이슈(TLS 인터셉션)를 다뤘지만, 그때 결론은 "공인 인터넷
(data.go.kr) 목적지라 프록시를 **타야** 도달한다"였고, 그래서
`trust_env`를 기본값(`True`, 프록시 환경변수를 따름)으로 고정해뒀다.
이번에 확인된 건 정반대 사례 — 어떤 사내망에서는 프록시를 타는 것
자체가 실패 원인이다. 즉 "프록시가 필요한지 방해되는지"는 환경마다
다르다 — 코드에 하나로 못박을 수 없다.

**수정**: `httpx`의 옛 `proxies={"all://": None}` 문법(0.28에서 제거됨)을
그대로 쓰는 대신, 이미 코드베이스에 있는 같은 목적의 도구를 재사용했다
— `llm_client.py`가 사내 LLM 게이트웨이용으로 쓰는 `trust_env=False`
(프록시 등 환경변수 기반 설정을 전부 무시)다. 이걸 `kma_weather_ca_bundle`
처럼 신규 설정값 `kma_weather_trust_env`(기본값 `True`, §69 가정 유지)로
빼서, 프록시가 문제인 사내망에서는 `.env`에서 `KMA_WEATHER_TRUST_ENV=false`
로 뒤집을 수 있게 했다 — 코드 수정 없이 운영자가 전환 가능.

`weather_client.py`의 `httpx.AsyncClient(...)` 호출에
`trust_env=self._settings.kma_weather_trust_env`를 추가했을 뿐, 그 외
로직(CA 번들, 서비스키 이중 인코딩 방지 등 §69/§70)은 그대로다.

### 검증

- `test_weather_client.py`에 `test_fetch_daily_range_respects_kma_weather_trust_env_false`
  추가 — `kma_weather_trust_env=False`로 설정하면 `httpx.AsyncClient`에
  `trust_env=False`가 실제로 전달되는지 확인. 기존
  `test_fetch_daily_range_does_not_force_trust_env_false`(기본값 `True`일
  때 강제로 꺼지지 않는지)도 그대로 통과.
- `pytest -q` 전체 537개 통과.

## §75. "비 오는 날 식수" 카드 재설계 — 일별 타임라인 + 실측치 검증 + top5 랭킹 (2026-08)

배포된 화면을 보고 담당자가 네 가지를 지적했다:

1. "메인메뉴계절인기랭킹은 top5 상승/감소 보여주고 나머진 펼치기로 해줘"
2. "비가 실제로 왔는지도 봐야하니 같이 볼수잇게해줘"
3. "비오는 날 식수 그래프 주말+공휴일, 패밀리데이, 평일은 어떤 걸 보여주려는건지 모르겠어"
4. "비오는날 식수라고 하지말고 날씨에 따른 식수 변화나 현황이런 느낌으로 보고 싶음"

### 막대그래프 → 일별 타임라인 (3·4번)

기존 `GET /analysis/weather-correlation`은 "분류(평일/주말+공휴일/
패밀리데이) × 강수여부"로 쪼갠 **평균값 교차표**를 막대로 그렸다. 평일과
주말+공휴일은 기저 식수 자체가 원래 크게 다르다는 설계 의도(코드
주석에만 있고 화면엔 없었음)가 전혀 설명되지 않아 "이 막대가 뭘
비교하는 건지" 알 수 없었다.

교차표 자체를 없애고 **일별 원자료를 그대로 보여주는 타임라인**으로
바꿨다 — `GET /analysis/weather-headcount-timeline`이 날짜 하나하나를
가공 없이 반환하고(`stat_date`/`classification`/`headcount`/`precip_mm`),
평일/주말+공휴일/패밀리데이 구분은 막대 분리가 아니라 **체크박스
필터**로 옮겼다. "무엇과 무엇을 비교하는 그래프"가 아니라 "그날 실제
무슨 일이 있었는지"를 그대로 보여주는 그래프가 되어 설명이 거의
필요 없어졌다. 화면은 헤드카운트를 왼쪽 축 막대, 강수량(mm)을 오른쪽 축
선으로 겹쳐 그린다(`CornerMetricComparisonSection`의 듀얼축 구성 방식
재사용) — 이게 2번 요청("비가 실제로 왔는지도 같이") 답이기도 하다:
막대(식수)와 선(강수량)을 같은 그래프에서 바로 대조해 볼 수 있다.

카드 제목도 "비 오는 날 식수 — 과거 실측 상관관계"에서 "날씨에 따른
식수 변화 — 과거 실측 현황"으로 바꿔, 비뿐 아니라 날씨 전반을 다룬다는
프레이밍으로 맞췄다(4번).

`weather_correlation`은 `_weather_event_by_date`(§71)와 별개 함수였고
`HolidayService(db)`를 매번 새로 만들었는데, 이번에 세션 캐싱되는
`get_holiday_service(db)`로 통일했다(다른 곳들과의 기존 불일치 정리).

### 날씨유형 랭킹에 실측치 열 추가 (2번, §71 표 확장)

"메인메뉴 × 날씨유형 인기 랭킹"(§71) 표는 "이 메뉴가 폭설일 때 몇 명
먹었는지"는 보여줬지만 "그 폭설이 실제로 몇 cm였는지"는 안 보여줘서,
분류 결과를 실측치로 검증할 방법이 없었다.

`_weather_event_by_date`가 이제 `event_by_date` 옆에 `weather_by_date`
(이미 로드한 `DailyWeather` 행의 날짜별 맵)도 같이 반환한다 — 새 쿼리
없이 재사용. `_menu_weather_event_summary`가 이벤트별로 "그 메뉴가 그
유형을 겪은 날들"의 실측치 평균(`actual_avg`)을 계산한다 — 이벤트별로
뭘 봐야 하는지는 `_EVENT_ACTUAL_METRIC` 매핑(비→강수량mm, 폭설→적설cm,
폭염→최고기온℃, 한파→최저기온℃)으로 정한다. `menu_weather_event_ranking`
응답에 행별 `actual_avg`와 상단에 `actual_metric_label`(예: "평균
강수량(mm)")을 추가했다. 계절 랭킹(§72)은 날짜에서 결정론적으로 나오는
분류라 검증할 실측치 개념이 없어 그대로 뒀다.

### top5 상승/하락 + 펼치기 (1번, 날씨유형·계절 랭킹 공통)

두 랭킹 표 모두 이제 기본으로는 `|diff|` 기준 상위가 아니라 **top5
상승(diff 양수) + top5 하락(diff 음수)만** 보여주고, 나머지(표본 부족
포함)는 "전체 N개 보기" 버튼으로 펼친다 — `MenuRotationCheckSection`의
top-N + `showAll` 상태 + 버튼 idiom을 그대로 재사용한 신규 헬퍼
`topMoversAndFallers(rows, getDiff)`로 날씨유형·계절 랭킹 둘 다 같은
방식으로 처리해 일관성을 맞췄다. 탭을 바꾸면 펼침 상태도 초기화된다.

### 검증

- `test_api_ingest_and_analysis.py`: 기존 `weather_correlation` 테스트
  2개를 `weather-headcount-timeline` 테스트로 교체(일별 원자료가 맞게
  나오는지, 분류 누락일 제외, 날씨 없는 날은 `precip_mm=null`로 표시).
  `menu_weather_event_ranking` 관련 기존 테스트에 `actual_avg`/
  `actual_metric_label` 검증 추가(표본 부족이어도 `actual_avg`는 그대로
  계산됨을 포함). `pytest -q` 전체 537개 통과.
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버 기동 후 Playwright로 실제 브라우저에서
  확인: (1) 타임라인 차트가 헤드카운트 막대 + 강수량 선 듀얼축으로
  렌더링됨, 체크박스로 분류를 켜고 끄면 x축 날짜 집합이 바뀜, (2) "비"
  탭에서 "실측 평균" 열 헤더가 "평균 강수량(mm)"으로, 값이 실제 시딩한
  강수량과 일치하게 렌더링됨, (3) 날씨유형 랭킹은 기본 접힌 상태(표본
  부족으로 top5 상승만 있던 케이스), 계절 랭킹은 "전체 23개 보기" 클릭
  시 전체가 펼쳐지고 "접기" 버튼으로 바뀜을 확인. 콘솔 에러 없음.

## §76. 날씨유형 랭킹 중식 고정 + 미캠회관(전골) 코너 제외 (2026-08)

§75로 배포된 "메인메뉴 × 날씨유형 인기 랭킹"을 보고 담당자가 두 가지를
요청했다: "중식 기준으로 봐줘"(조/중/석식을 합쳐 집계하던 것), "미캠회관
코너도 제외해줘". AskUserQuestion으로 확인한 결과, 미캠회관(전골) 제외는
날씨유형·계절 랭킹 둘 다에 적용하고(타임라인 차트의 전체 식수는 코너
단위가 아니라 대상 밖), 중식 고정은 조/중/석식 선택 버튼을 새로 만들지
않고 쿼리 자체를 중식으로 고정하는 쪽으로 정했다(계절 랭킹은 이번 요청
대상이 아니라 그대로 전체 식사시간 합산 유지).

**미캠회관(전골) 제외**: `menu_weather_event_ranking`(§71)과
`menu_season_ranking`(§72)은 이미 같은 헬퍼
`_headcount_by_date_by_menu_bulk`를 공유해 메뉴별 일자별 식수를 만든다.
이 헬퍼 한 곳에 코너 제외를 추가하면 두 랭킹에 자동으로 같이 적용된다 —
랭킹 엔드포인트 코드는 그대로 두고, 이미 있던 `excluded_menu_ids`
(`PLACEHOLDER_MENU_NAMES`) 필터와 같은 스타일로 `MealLog.corner_id`
기준 `excluded_corner_ids` 필터를 하나 더 추가했다. 상수
`MICAM_HALL_CORNER_NAME = "미캠회관(전골)"`은 `TAKE_OUT_CORNER_NAME`과
같은 자리(`corner_aliases.py` → `master_data.py` 재노출 → `analysis.py`
import)에 뒀다. 프론트의 `SHARE_EXCLUDED_CORNER_NAMES`(점유율 차트 전용
제외 목록)는 별개로 그대로 둔다 — 우연히 같은 코너를 가리키지만 하나는
프론트 차트용, 하나는 백엔드 집계용이라 억지로 공유 모듈을 만들 필요는
없다. 슬롯 상세("예측 보기")의 `_menu_weather_reference`가 쓰는 단건
버전 `_headcount_by_date_for_menu`는 이번 요청(랭킹 표 두 개) 범위
밖이라 손대지 않았다.

**중식 고정**: 백엔드는 이미 `meal_type` 쿼리 파라미터를 지원하고
있었으므로(§71), 프론트 `WeatherCorrelationSection`의 `menuRankingQuery`
호출에 `meal_type: "중식"`을 고정으로 추가했다. §75에서 "이게 뭘 보여주는
건지 모르겠다" 피드백을 받은 전례가 있어, 소제목에도 "(중식 기준)"을
명시해 범위를 화면에서 바로 알 수 있게 했다.

### 검증

- `test_api_ingest_and_analysis.py`: 신규 테스트 2개 —
  `test_menu_weather_event_ranking_excludes_micam_hall_corner`(미캠회관
  메뉴가 날씨유형 랭킹에서 빠지고 다른 코너 메뉴는 남는지),
  `test_menu_season_ranking_excludes_micam_hall_corner`(같은 걸 계절
  랭킹에서). `pytest -q` 전체 539개 통과.
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버로 Playwright 확인: 소제목이 "메인메뉴 ×
  날씨유형 인기 랭킹 (중식 기준)"으로 뜨고, 실제 네트워크 요청에
  `meal_type=중식`이 포함됨을 확인. 콘솔 에러 없음.

## §77. 날씨 카드 이동 + 하이라이트 LLM 프롬프트 개선 + 주간 식단표 규칙 검증 (2026-08)

담당자 요청 세 가지: (1) "날씨에 따른 식수변화는 메뉴편성운영 탭 내의
시뮬레이션으로 따로 빼는 게 좋을 듯", (2) "메뉴 하이라이트에서 LLM이
만족도 하락 원인을 잘 특정 못 한다 — 프롬프트를 고쳐서 퀄리티를 올릴
수 없냐", (3, 대화 중 추가) 주간 식단표가 4개 기준(해장/면류/매운빨간
국물/최근 저조 식수 재편성)을 지키는지 자동으로 경고해 달라는 새 기능.

### A. 날씨 카드 이동

`WeatherCorrelationSection`(§75에서 타임라인으로 재설계한 카드)이
"현황" 탭(`HomePage.tsx`)에 있었는데, 2026-08 개편 때 "시뮬레이션" 탭
자체가 이미 삭제됐고(§47.2) 그 시절 유일한 기능("사내 행사" 토글)은
"금주 예상 식수" 카드로 흡수됐던 상태라 "메뉴 편성·운영" 탭엔 시뮬레이션
관련 섹션이 전혀 없었다. `HomePage.tsx`에서 import·렌더를 제거하고
`MenuPlanningPage`(`AnalysisPage.tsx`) 맨 끝으로 옮겼다 — 카드 자체
제목이 이미 있어 별도 "시뮬레이션" 래퍼 헤더는 만들지 않았다(이 탭의
다른 섹션들도 헤더 없이 Card만 나열하는 방식이라 일관성 유지).

### B. 하이라이트 LLM 프롬프트 — 실제 코멘트 + 부찬 조합 배선

`llm_analysis.py`의 `_build_menu_trend_prompt`는 이미 `prior_sides`/
`recent_sides`(부찬 조합)와 `competing_menus`(같은 날 다른 코너 인기
메뉴) 필드를 프롬프트에 넣을 준비가 돼 있었는데, 유일한 호출부
`refresh_llm_analyses`가 이 필드들을 **한 번도 채운 적이 없었다** —
실제로 LLM에 넘어가던 사실은 메뉴명·직전/최근 주 점수 2개·날짜 2개·월
2개뿐이었다. "왜 바뀌었는지"를 판단하기엔 원래 너무 얇은 사실 집합이라,
LLM의 "특정하기 어렵다" 답변은 오히려 정직한 반응이었던 셈이다.

새 헬퍼 두 개를 추가해 `facts`를 실제로 채웠다:
- `_recent_comments_for_menu(db, menu_id, week_monday, limit=3)` —
  `dashboard.py`의 `GET /menu-comments/{menu_name}`과 같은 쿼리 패턴
  (menu_id + `comment IS NOT NULL`)을 그 주(월~일) 범위로 좁혀 재사용.
  직전/최근 주 각각 호출해 `prior_comments`/`recent_comments`를 채운다
  — 점수만으로는 안 보이는 "왜"의 가장 직접적인 근거.
- `_side_dishes_for_menu_week(db, menu_id, week_monday)` — 그 메뉴가
  MAIN으로 나온 슬롯(plan_date, corner_id, meal_type)을 찾아 같은
  슬롯의 SIDE 메뉴명을 모은다 — 이미 프롬프트가 기대하던 `prior_sides`/
  `recent_sides`를 이제 실제로 채운다.

`_build_menu_trend_prompt`에 코멘트 라인과 "직원 코멘트가 있다면 우선
근거로 삼으세요" 안내를 추가했다. 거짓을 지어내지 말라는 기존
가드레일은 그대로 뒀다 — 코멘트가 진짜 없는 메뉴는 여전히 "특정하기
어렵다"가 정직한 답일 수 있다. `competing_menus`는 구현 비용 대비
효용이 낮고 위 둘과 정보가 겹쳐 이번 라운드에서는 배선하지 않았다(필드
자체는 남겨둠). 캐시(`LlmAnalysisCache`)는 스키마 변경이 없어 새벽
배치가 돌면 최신 `created_at`으로 자연 교체된다.

### C. 주간 식단표 규칙 검증 (신규 기능)

담당자가 준 4개 기준(주중 기준):
① 해장 메뉴 최소 1개, ② 면류(라면 포함) 4개 초과 편성 금지, ③ 매운
(빨간국물) 메뉴 4개 초과 편성 금지, ④ 최근 식수 200식 이하 메뉴는
재편성 금지(스냅스낵/그린미트/미캠회관(전골) 코너는 예외).

`backend/app/services/menu_plan_rules.py`(신규, `weather_event.py`/
`season.py`와 같은 순수함수 스타일)가 ①~③을 판정한다. "면류"·"해장"은
food_vector 차원에 없어 새 키워드 목록(`_NOODLE_KEYWORDS`/
`_HANGOVER_KEYWORDS`)을 만들었고, "매운(빨간국물)"은 새 목록을 또
만들지 않고 `food_vector_tagging.py`에서 새로 뽑아낸 공개 헬퍼
`menu_matches_dimension(menu_name, dimension)`으로 spicy ∩ soup_based
판정을 재사용했다(기존 `tag_food_vector_from_name`도 이 헬퍼를 쓰도록
리팩터— 로직 중복 제거). ①~③은 물리적으로 "그 주에 뭐가 나갔는지"를
보는 것이라 메인/부찬/건강가든 역할 무관하게 전부 스캔한다(§132의
"건강가든은 코너 무관" 원칙과 동일).

④는 `analysis.py`의 새 헬퍼 `_recent_avg_headcount_by_menu`가 처리 —
MAIN 역할만(부찬은 취식 기록이 없어 식수를 알 수 없다), 예외 코너가
아닌 메뉴에 대해 이 레포의 관례인 `_HISTORY_WINDOW_DAYS=180` 창으로
"그 메뉴가 실제로 나간 날짜별 식수 평균"을 계산해 200 이하면 위반으로
담는다. 이력이 아예 없는 메뉴(진짜 신메뉴)는 판단 근거가 없으니 조용히
건너뛴다. 예외 코너 3개(스냅스낵/그린미트/미캠회관(전골))는
`corner_aliases.py`의 새 상수 `LOW_HEADCOUNT_EXEMPT_CORNER_NAMES`로
한 곳에 묶었다 — §76에서 미캠회관 제외를 다룰 때와 같은 성격의 요청이
또 나와, 이참에 정리했다.

신규 엔드포인트 `GET /analysis/weekly-menu/plan-rule-check`는
`weekly-menu/combination-check`와 똑같이 `period_start`/`period_end`를
받는다 — 프론트 `WeeklyMenuReviewTab`이 이미 같은 파라미터로 그 주
슬롯을 조회하므로, 화면에 보이는 주와 규칙검증 결과가 항상 일치한다.
응답은 규칙별 `{ok, count, limit, matches}`(해장/면류/매운빨간국물)와
`{ok, violations: [...]}`(저조 식수 재편성)이다.

화면은 `WeeklyMenuReviewTab`의 날짜 네비게이터 바로 아래에 "주간 편성
규칙 검증" 패널을 추가 — 4개 규칙을 `Badge tone="good"/"critical"`
한 줄씩(기존 `ROTATION_FLAG_TONE` 관례 재사용) 보여주고, 위반이 있으면
해당 메뉴 목록을 캡션으로 펼친다. 이번 라운드는 키워드 기반 자동 판정
만 넣고 `MenuMaster`에 수동 오버라이드 컬럼은 추가하지 않았다 — "경고"
기능이지 완벽한 분류 체계가 필요한 건 아니라서, 오분류가 나오면 키워드
목록만 조정하면 된다(필요해지면 다음 라운드에서 `new_menu_override`와
같은 패턴으로 추가).

### 검증

- `backend/tests/test_menu_plan_rules.py`(신규): 키워드 판정 3종 +
  `check_*_rule` 경계값(정확히 4개=통과, 5개=위반, 해장 0개=위반) 9개
  유닛 테스트.
- `test_api_ingest_and_analysis.py`: 신규 엔드포인트 3개 테스트 — 면류
  초과+해장 없음 위반, 준수하는 주, 저조 식수 재편성이 일반 코너는
  걸리고 미캠회관(전골)은 빠지는지.
- `test_llm_analysis.py`: 신규 코멘트/부찬 fact-수집 헬퍼 2개 + 프롬프트
  반영 여부 5개 테스트.
- `pytest -q` 전체 556개 통과(539 + 신규 17개).
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버로 Playwright 확인: 현황 탭엔 날씨 카드가
  없고 메뉴 편성·운영 탭 맨 아래에 있음, 주간 식단표 관리 화면 상단에
  규칙검증 패널이 4개 배지와 함께 뜸. 콘솔 에러 없음.

## §78. 규칙검증 요일별(주중)로 재설계 + 격자 하이라이트 연동 + LLM 캐시 수동 재계산 (2026-08)

§77에서 배포한 "주간 편성 규칙 검증" 패널을 보고 담당자가 지적했다:
"각각 주간식단표에서 표기할 때 요일별로 봐야해 하루 기준임 (주중만
보면되고) 하루에 면류 4개 초과 금지 이런 식이야" — 해장/면류/매운(빨간
국물) 세 규칙 모두 §77에선 **한 주 전체 합산**으로 판정했는데(예: "이번
주에 라면 5번 나왔다"), 실제로는 **그날 하루** 기준이어야 했다("그날
면류가 4개를 넘게 편성됐는지"). 토/일은 대상에서 뺀다. 추가로 "클릭하면
어떤 요일의 코너의 메뉴인지 하이라이트 되기"도 요청했다.

### 요일별(주중만) 재설계

`menu_plan_rules.py`의 `MenuPlanSlotItem`에 `corner_id`를 추가하고(격자
셀 키 join용), 기존 "기간 전체 1건" 결과 대신 요일별 리스트를 도입했다
— `check_hangover_rule`/`check_noodle_rule`/`check_spicy_red_broth_rule`
셋이 공유하는 내부 헬퍼 `_check_daily`가 슬롯을 `plan_date.weekday() < 5`
로 걸러 날짜별로 묶고, 그 날짜 하루의 매치 개수만으로 판정한다. "해장
최소 1개"도 하루 기준으로 재해석했다 — 슬롯이 아예 없는 날(식단표 미등록)
은 결과에서 빠진다(데이터 누락과 "편성했는데 기준 미달"은 다른 문제).
매치도 문자열 라벨 대신 `MenuPlanRuleMatch`(menu_name/corner_id/
corner_name/plan_date) 구조체로 바꿔 프론트가 그대로 격자 셀 키를 만들 수
있게 했다. `analysis.py`의 `weekly_menu_plan_rule_check`는 `corner_id`도
같이 select하고, 응답의 `hangover`/`noodle`/`spicy_red_broth`가 날짜별
결과 배열이 되도록 직렬화를 바꿨다(`low_headcount_reuse`는 요일 개념이
아니라 메뉴 단위라 그대로 둠).

### 격자 하이라이트 연동

`WeeklyMenuReviewTab`엔 이미 셀 클릭→하이라이트 메커니즘
(`selectSlot`/`selectedSlotKey`, 셀 키 `${plan_date}_${corner_id}`)이
있었다 — 규칙검증 패널의 위반 매치를 클릭 가능한 칩으로 바꿔
`onClick={() => selectSlot(`${m.plan_date}_${m.corner_id}`)}`만 걸면
새 state 없이 그대로 재사용된다. 패널은 규칙마다 "월~금" 5칸 배지(그날
결과가 없으면 "-")를 보여주고, 위반인 날의 매치들을 그 아래 칩으로
나열한다.

### LLM 캐시 수동 재계산

같이 확인한 "현황에서 메뉴하이라이트llm에 분석이 아무것도 없어"는
버그가 아니었다 — `refresh_llm_analyses`가 새벽 2시 스케줄러
(`scheduler.py::run_daily_batch`)에서만 돌고 앱 시작 시점엔 안 돌기
때문에, 스케줄러가 계속 떠 있지 않은 로컬/개발 환경은 캐시가 계속
비어 있는 게 정상이다(`_trend_cause`가 캐시 없으면 `{}`를 줘서 화면이
그 줄을 조용히 안 그림). 다만 `daily-stats/recompute`·
`menu-performance/recompute`처럼 수동으로 당장 채울 수 있는 엔드포인트가
이 기능만 없다는 게 실제 공백이었다 — `POST /analysis/llm-analyses/recompute`
를 추가해 `refresh_llm_analyses`를 수동 트리거할 수 있게 했다
(`extract_ingredients_with_llm`/`tag_menus_with_llm`과 같은 `async def`
+ 인증 없음 패턴).

### 검증

- `test_menu_plan_rules.py`: 요일별 시맨틱으로 전면 재작성 — 같은 날
  5개(위반) vs 5일에 걸쳐 하루 1개씩(매일 통과) 구분, 주중만(토/일 슬롯
  제외), match에 corner_id/plan_date가 정확히 담기는지 확인.
- `test_api_ingest_and_analysis.py`: 배열 응답에 맞게 기존 테스트 갱신 +
  같은 5개를 하루에 몰아넣기/5일에 나눠 넣기 대조 테스트, 토요일 제외
  테스트, 신규 `POST /llm-analyses/recompute` 엔드투엔드 테스트(LLM
  미설정 상태에서 호출 → 폴백 요약이 캐시에 저장되고
  `GET /dashboard/menu-highlights` 응답에 `cause`가 채워짐을 확인).
- `pytest -q` 전체 560개 통과(556 + 신규 4개).
- `npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버로 Playwright 확인: 월요일에 면류 5개를
  몰아넣은 주를 실제로 시딩해 규칙검증 패널이 "면류 (하루 최대 4개) ●
  월 5개 ● 화 0개..."로 뜨고 월요일이 critical 배지로 표시됨, 매치 칩
  "냉면(한식2, 08-10)"을 클릭하니 격자표에서 그 셀이 실제로 하이라이트
  됨(기존 선택 스타일 그대로), `POST /llm-analyses/recompute` 호출이
  `menu_trend` 카운트를 반환함을 확인. 콘솔 에러 없음.

---

## §79. 흰화면 진단(코드 결함 아님) + 해장 키워드 확장 + 중복점검 2화면 재구성 + 날씨를 "시뮬레이션"으로 분리 (2026-08)

§78 배포 직후 담당자가 "메뉴편성 탭 누르면 흰화면되면서 내용이 안나옴"을
신고했고, 이어서 세 가지를 더 요청했다: 해장 메뉴 키워드가 부대찌개·
짬뽕밥 같은 흔한 해장 음식을 못 잡는다, "메뉴 중복점검 보기가 힘듦
재구성", "날씨에 따른 식수 변화 시뮬레이션으로 따로 빼줘".

### 흰화면 조사 — 코드 결함 아님, 낡은 프론트 번들로 추정

postgres·uvicorn·vite dev 셋 다 이 세션에서 직접 새로 띄우고, 실제 개발
DB(`weekly_menu_plan` 251건, 2026-06-01~08-11)로 Playwright로 "메뉴
편성·운영" 탭을 그대로 재현했다 — 규칙검증 패널·격자표·날씨 카드까지
페이지 끝까지 스크롤해도 콘솔 에러 0건이었다. `npx tsc -b`·
`npx vite build`도 클린, `/analysis/weekly-menu/plan-rule-check`를 실제
이번 주 데이터로 직접 호출해도 200 정상 응답이었다. §77~§78의
`ruleCheckQuery.data && (...)` 가드, 배열 필드 전부 non-null 보장 등
이미 방어적으로 짜여 있어 render 중 throw할 지점을 찾지 못했다 — **§77~
§78 코드 자체에는 흰화면을 일으킬 결함이 없다**. 가장 유력한 설명은
담당자 브라우저에 §77~§78의 큰 구조 변경 이전 번들이 남아 있다가 Vite
HMR이 못 따라가 깨진 경우다(같은 대화의 "왜 업데이트가 안되지" 혼선과
같은 계열) — 하드 리프레시나 `npm run dev` 재시작으로 해결될 가능성이
높다.

다만 조사 중 이 앱 전체에 **React 에러 바운더리가 하나도 없다**는 걸
확인했다(`grep ErrorBoundary` 전체 0건) — 렌더 중 예외가 나면 항상
트리 전체가 언마운트돼 화면이 통째로 하얗게 빈다. 이번 건의 근본 원인은
아니지만 재발 방지용 안전망으로 `frontend/src/components/ErrorBoundary.tsx`
(class 컴포넌트, `getDerivedStateFromError`/`componentDidCatch`)를 만들어
`main.tsx`에서 `QueryClientProvider` 바깥을 감쌌다 — fallback UI는 기존
`ErrorState` 톤(테두리+`var(--critical)`)에 에러 메시지와 새로고침
버튼을 더했다. 컴포넌트 하나에 임시로 `throw`를 넣어 fallback이 실제로
뜨는지 확인 후 되돌렸다(회귀 코드에는 남기지 않음).

### 해장 키워드 확장

`menu_plan_rules.py`의 `_HANGOVER_KEYWORDS`는 "해장"이 이름에 직접 들어간
메뉴만 잡았다 — 부대찌개·짬뽕(밥)처럼 통상 해장 음식으로 꼽히지만
이름에 "해장"이 없는 메뉴는 전부 놓쳤다. 같은 성격의 잘 알려진 해장
음식(순대국/순댓국, 감자탕, 육개장, 뼈다귀, 청국장, 동태찌개, 매운탕)도
같이 추가했다. "짬뽕"이 해장 키워드에도 들어가면서 면류 판정(규칙②)과
겹치는 메뉴가 생기지만, 두 규칙은 완전히 독립적으로 판정되므로 문제
없다(한 메뉴가 여러 규칙에 동시에 걸리는 건 원래부터 있던 설계 전제).

### 중복점검 화면 2개 재구성

담당자에게 확인한 결과("둘 다") 두 화면 다 손봤다:

- **`MenuRotationCheckSection`**("메뉴 중복 점검")은 회전/재편성 경고와
  "자주 반복되는 부찬 랭킹"이라는 서로 다른 두 기능이 각자 독립된 기간·
  코너 필터를 가진 채 한 카드에 쌓여 있었다 — §66에서 한 번 분리했던
  "너무 복잡함" 문제가 한 레벨 아래서 재발한 것. "자주 반복되는 부찬
  랭킹" 블록을 통째로 `RepeatedSideDishRankingSection`이라는 새 카드로
  뺐다(§66과 같은 절개선 — 관심사가 다르고 필터가 독립적이면 카드를
  나눈다). `MenuRotationCheckSection`은 이제 회전/재편성 경고 표 하나에
  집중된 카드가 됐다.
- **`MealClashCheckSection`**("한 끼 구성 겹침 점검")은 한 주의 겹침
  슬롯을 그룹·접기 없이 전부 카드로 나열만 했다(재료 중복·특성 중복
  배지가 한 줄에 섞여 나옴). 상단에 요약 배지("이번 주 재료 중복 N건,
  특성 중복 M건")를 추가하고, `clashSlots`를 `plan_date`로 묶어 요일별
  소제목 아래 그날 슬롯 카드들을 모았다. `MenuRotationCheckSection`의
  `ROTATION_PREVIEW_COUNT`/`showAll` idiom을 그대로 따라 기본 상위
  `CLASH_DAY_PREVIEW_COUNT`(3)일만 보여주고 "전체 N일 보기"로 펼친다.
  재료 중복(critical)과 특성 중복(warning) 배지도 두 하위 목록으로
  나눠 섞이지 않게 했다.

`MenuPlanningPage`의 렌더 순서는 `MenuRotationCheckSection` →
`RepeatedSideDishRankingSection` → `MealClashCheckSection`.

### 날씨 카드를 "시뮬레이션"으로 시각적 분리

`MenuPlanningPage`에서 `<WeatherCorrelationSection />`을 `<h2>시뮬레이션
</h2>` 라벨과 구분선으로 감쌌다 — 이 탭의 다른 카드들은 헤더 없이 쭉
나열되는데, 날씨 카드만 참고용 시뮬레이션이라는 다른 층위에 있다는 걸
표시하려는 의도다. §47.2에서 이미 삭제된 옛 "시뮬레이션" 최상위 탭을
되살리는 게 아니라(그 탭의 유일한 고유 기능은 이미 "금주 예상 식수"
카드로 흡수됨, §77에서 확인) 새 하위 탭 없이 라벨 섹션만 추가했다 —
`WeatherCorrelationSection` 자체는 손대지 않았다.

### 검증

- `test_menu_plan_rules.py`: 부대찌개·짬뽕밥·순댓국·감자탕·육개장이
  `is_hangover_dish`로 잡히는지 확인하는 테스트 추가.
- `test_api_ingest_and_analysis.py`: 노듈 초과 테스트의 시딩 메뉴 중
  "짬뽕"이 새 해장 키워드와 겹쳐 그 테스트의 hangover 어서션이 깨져서
  "쫄면"으로 교체(면류 판정 자체는 동일하게 유지).
- `pytest -q` 전체 561개 통과(560 + 신규 1개).
- `npx tsc -b`·`npm run build` 타입체크 통과.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인: 메뉴
  편성·운영 탭이 콘솔 에러 없이 끝까지 렌더됨, "메뉴 중복 점검"·"자주
  반복되는 부찬 랭킹"·"한 끼 구성 겹침 점검"이 별도 카드 3개로 뜸,
  실제 겹침이 있는 주(2026-08-03~09)에서 요약 배지+요일별 그룹 렌더링
  확인, 날씨 카드 위에 "시뮬레이션" 라벨이 뜸, 에러 바운더리는 임시
  `throw` 주입으로 fallback UI가 실제로 뜨는 것까지 확인 후 원복.

## §80. Home 예측 카드 재설계 + 코너별 분석 단순화 + 부찬 상세/만족도 + 편성분석 축 교체 + VOE AI 브리핑 (2026-08)

담당자가 Home/분석 두 구분으로 8개 항목을 한 번에 피드백했다. 큰 줄기는
두 가지 — (1) 홈의 "예측" 계열 카드가 오차 리스크가 있어 보이니 실측
기반으로 바꾸거나 설명을 보강해달라는 것, (2) 분석 탭 여러 화면이
"이해하기 어렵다"는 것. AskUserQuestion으로 네 갈래를 확정했다: 예상
식수 카드는 예측 로직을 걷어내고 최근 실측 평균으로 완전히 교체(점유율/
대기시간 예측 엔진은 그대로 유지), 코너-메뉴 그래프는 요일별 추이 대신
이번 주 전체 랭킹 가로막대로, 편성분석 X축은 "편성 횟수" 대신 "1회
편성당 식수"로(만족도는 Y축 유지), VOE AI 브리핑은 Home의 기존 좁은
요약과 별개로 만족도·VoE 탭에 전체 브리핑 카드를 신설.

### A. "금주 예상 식수" 카드 — 실측 평균 기반 코너-메뉴 랭킹 가로막대

`HomePage.tsx`에서 날씨/메뉴배수 예측 기반의 `forecastOption`/
`forecastByCornerOption`/`forecastView` 토글을 전부 걷어냈다(점유율·
대기시간 뷰가 쓰는 `forecastMealType`/`forecastRequested`는 유지 — 이번
요청은 식수 숫자 자체의 오차 리스크에 한정). 대신 `analysis.py`에
`GET /weekly-menu/planned-headcount-ranking` 신규 엔드포인트를 추가해,
`weekly_menu_plan_rule_check`가 이미 쓰던 `_recent_avg_headcount_by_menu`/
`_HISTORY_WINDOW_DAYS`(180일) 패턴을 그대로 재사용한다 — 이번 주 편성된
MAIN 슬롯마다 과거 180일 실측 평균 식수를 붙여 내림차순 정렬하고,
이력 없는 신메뉴(`None`)는 맨 뒤로 보낸다. 프론트는 게이팅 버튼 없이
바로 조회해 코너-메뉴별 가로막대로 보여준다(`yAxis` category+inverse,
`xAxis` value) — 냉면·국물류처럼 날씨 영향이 큰 메뉴도 메뉴 단위로
개별 확인 가능해졌다. 카드 설명 문구를 "날씨·메뉴배수 예측이 아니라
최근 실측 평균입니다"로 명시했다.

### B. "예상 피크 식수" — 설명 캡션 + 메뉴명 추가

계산 로직(`simulation.py`의 `_forecast_corners`/`compute_peak_share_ratio`)
자체는 손대지 않고 UI 설명만 보강했다. 오늘 날짜로 스코프한
`cornerMainMenuByDate` 쿼리를 새로 호출해 최고 혼잡 예상 코너의 오늘
메인메뉴를 `StatTile`의 `sub` 텍스트에 이어 붙이고, 카드 하단에 공식을
평문으로 설명하는 캡션("요일별 최근 8회 평균 식수 × 계획 메뉴 인기도
배수 × 최근 60일 피크타임 점유율로 추정합니다")을 추가했다.

### C. "식수 추이" 차트 — 선 → 누적 막대 + N일 평균

`headcountTrendOption.series`를 `type:"line"`에서 `type:"bar"` +
`stack:"total"`로 바꿨다(코너별 추이가 이미 쓰던 `stack:"corner"` 패턴과
동일). 새 로컬 state `trendAvgWindow: 7|14|30`(기본 7)을 추가하고,
일별 추이일 때만 `SegmentedControl`로 7/14/30일 선택이 가능하게 했다 —
`SegmentedControl<T extends string>`이 문자열만 받으므로
`value={String(trendAvgWindow)}` / `onChange={(v) => setTrendAvgWindow(Number(v) as 7|14|30)}`
로 변환한다. 새 백엔드 호출 없이 이미 가져온 `trendRows`를 프론트에서
합산해 "최근 N일 평균: {값}명"을 표시한다.

### D. `CornerMetricComparisonSection` — 기본 단일 지표로 단순화

코너마다 지표 2개(듀얼축) 선을 항상 같이 그려 최대 16개 선이 뜨던 걸,
`showSecondMetric`(기본 `false`) state로 감쌌다. 기본값에서는 오른쪽
축 선택기를 숨기고 `yAxis`/`series` 모두 왼쪽 지표 하나만 구성해
코너당 선 1개(최대 8개)로 단순화한다. "두 번째 지표 비교" 체크박스로
기존 듀얼축 동작을 그대로 켤 수 있다.

### E. `RepeatedSideDishRankingSection` — 클릭 상세 + 만족도 정렬

`menu_combination.py`에 `build_side_combos_for_main_menu`(부찬→메인
방향)를 뒤집은 `find_main_menu_pairings_for_side_dish`를 추가했다 —
부찬이 SIDE 슬롯이면 같은 코너의 MAIN만, HEALTH_GARDEN 슬롯이면 §132의
"건강가든은 코너 무관" 관례대로 같은 (날짜, 끼니)의 모든 코너 MAIN을
찾는다. 매칭된 각 슬롯의 그날 실제 만족도(`MealLog.taste_score` 평균)를
붙여 `SideDishPairing` 리스트로 반환하고, `summarize_side_dish_pairings`
가 `{avg_main_satisfaction, pairing_count}`로 요약한다.
`weekly_menu_repeated_side_dishes` 응답 각 항목에 `avg_main_satisfaction`을
추가하고, 신규 엔드포인트 `GET /weekly-menu/side-dish-detail`(메뉴명·
코너명으로 조회)을 만들었다. 프론트는 기존 `Table` 대신 `SortableHeader`
를 쓴 raw `<table>`로 바꿔 "횟수"/"연결 메인 만족도" 컬럼 정렬을 넣고,
부찬 이름을 클릭 가능한 버튼으로 바꿔 클릭 시 날짜·코너·메인메뉴(+만족도)
상세 목록을 펼친다.

### F. `MenuPlanPerformanceSection` — X축을 "1회 편성당 식수"로 교체

X축만 바꾸고 판정 로직은 그대로 두면 "화면은 식수 축인데 감편/증편
라벨은 편성 횟수 기준"이라는 불일치가 생긴다 — `menu_plan_analytics.py`의
`classify_planning_action`이 실제로 `plan_count >= median_plan_count`를
판정 기준으로 쓰고 있었기 때문이다. 그래서 축 교체의 필연적 귀결로
판정 기준 자체를 `headcount_per_plan`/`median_headcount_per_plan`으로
같이 바꿨다(`high_demand = headcount_per_plan >= median_headcount_per_plan`).
`NO_INTAKE` 판정은 그대로 동작한다 — 취식이 없으면 `headcount_per_plan`도
0이 되므로. `analysis.py`의 `menu_plan_performance`는
`median_headcount_per_plan`을 계산해 분류기에 넘기고 응답 필드명도
`median_plan_count`→`median_headcount_per_plan`으로 바꿨다. 프론트
산점도는 `value` 순서를 `[headcount_per_plan, avg_satisfaction, plan_count]`
로 바꾸되 `symbolSize`(버블 크기)는 여전히 `plan_count` 기준으로 남겨
"편성 횟수는 축에서 뺐지만 정보 자체는 버블 크기로 유지"했다. 사분면
라벨을 "감편 검토(식수 많은데 반응 낮음)"/"증편 후보(식수 적은데 반응
좋음)"로, X축 라벨을 "1회 편성당 식수 →"로 갱신했다.

### G. `VoeAnalysisTab` — "이달의 VOE AI 브리핑" 카드

Home의 "개선 필요 포인트" 카드에 이미 있는 VOE 요약(카테고리 1개,
코멘트 10개 한정)과 별개로, 만족도·VoE 탭에 이번 달 전체 주관식
코멘트를 다중 테마로 요약하는 새 카드를 만들었다. `cluster_monthly_voe`
가 이미 계산해둔 `MonthlyVoeCluster`(테마 라벨·키워드·대표 코멘트·건수)
를 그대로 재사용하고 재임베딩/재군집은 하지 않는다 — `llm_analysis.py`에
`_collect_voe_briefing_facts`(그 달 클러스터를 건수 내림차순으로 모음),
`_build_voe_briefing_prompt`(3~4문장 한국어 브리핑 요청, 네이버 리뷰
AI 브리핑처럼), `_fallback_voe_briefing`(LLM 미설정/실패 시 클러스터를
"라벨(건수): 대표 코멘트" 불릿으로 나열), `summarize_voe_briefing`을
기존 `summarize_menu_trend`와 같은 하우스 패턴으로 추가했다. 캐시는
`KIND_VOE_BRIEFING` kind로 기존 `get_cached`/`save_analysis`를 그대로 쓴다.

`dashboard.py`에 `GET /voe-briefing`(캐시 조회 + 그 달 `MonthlyVoeCluster`
존재 여부를 `has_clusters`로 같이 반환)과 `POST /voe-briefing/recompute`
(요약 후 캐시 저장)를 `voe-clusters` 엔드포인트들 옆에 추가했다.
프론트 카드는 카테고리 카드와 클러스터 카드 사이에 배치하고,
`recomputeVoeClusters`와 동일한 `useQuery`+`useMutation` 패턴을 쓴다.
클러스터링이 아직 안 돈 달(`has_clusters === false`)이면 브리핑 텍스트
유무와 무관하게 "먼저 아래 '월간 VOE 클러스터링'을 계산하세요" 안내만
보여준다 — 클러스터가 없는 상태에서 재계산을 누르면 폴백 문구("이번 달
주관식 의견이 없습니다")가 캐시에 저장되는데, 이걸 안내 문구와 나란히
보여주면 "클러스터링을 먼저 하라면서 왜 결과가 있지"처럼 모순돼 보여서
`has_clusters`가 true일 때만 브리핑 본문을 렌더링하도록 조건을 좁혔다.

### 검증

- `test_llm_analysis.py`: `_collect_voe_briefing_facts`(건수 내림차순
  정렬, 클러스터 없을 때 빈 리스트)·`_build_voe_briefing_prompt`·
  `_fallback_voe_briefing`(클러스터 있을 때/없을 때)·
  `summarize_voe_briefing`(LLM 미설정 폴백, 클러스터 없으면 LLM 설정
  여부와 무관하게 폴백)·`KIND_VOE_BRIEFING` 캐시 라운드트립 테스트 추가.
- `test_api_ingest_and_analysis.py`: `GET /voe-briefing`이 클러스터링
  전엔 `has_clusters=false`+`briefing=null`을 주는지, `POST
  /voe-briefing/recompute`가 기존 `MonthlyVoeCluster`를 재임베딩 없이
  재사용해 요약을 캐시에 저장하는지(`side-dish-detail`/
  `repeated-side-dishes`/`plan-performance`의 `median_headcount_per_plan`
  테스트도 이 라운드에서 §80-E/F와 함께 추가) 확인.
- `pytest -q` 전체 575개 통과.
- `npx tsc -b`·`npm run build` 타입체크·빌드 통과.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) 홈 "금주 예상 식수"가 실측 평균 코너-메뉴 가로막대로
  뜨고 예측 관련 문구가 사라짐, (2) 최고 혼잡 예상 코너 카드에 설명
  캡션이 뜸(메뉴명은 그날 편성 데이터가 있을 때만 표시되는 데이터
  의존 동작을 확인), (3) 식수 추이가 누적 막대로 바뀌고 "최근 7일
  평균: 70명" + 7/14/30일 선택기가 뜸, (4) 코너별 분석이 기본 단일
  지표(지표 1개 선택 + "두 번째 지표 비교" 체크박스 미체크)로 뜸,
  (5) 부찬 랭킹 표에서 "연결 메인 만족도" 열이 보이고 항목 클릭 시
  날짜·코너·메인메뉴 상세가 펼쳐짐, (6) 편성 분석 X축이 "1회 편성당
  식수 →"로, 사분면 라벨이 "식수 많은데/적은데"로 바뀜, (7) 만족도·
  VoE 탭에서 클러스터링 계산 전엔 "먼저 아래... 계산하세요" 안내만,
  클러스터링 후 재계산하면 실제 브리핑 텍스트(LLM 미설정 폴백
  포함)와 계산 시각이 뜸.

## §81. 시뮬레이션 탭 분리 + 날씨 상관관계 분석 + 홈 통계 정합 + 식수추이 기본값 + 규칙 하이라이트 + 중복점검 재설계 + NO_INTAKE 접기 (2026-08)

§80 배포 후 담당자가 6개 항목을 다시 피드백했다 — §79~§80에서 이미
손댄 화면인데 의도가 제대로 전달 안 됐거나 마저 안 바뀐 부분(날씨
위치, 홈 통계, NO_INTAKE), 기본값/필터 조정(식수추이, 규칙
하이라이트), 화면 하나를 아예 재설계해달라는 요청(메뉴 중복점검)이
섞여 있었다. AskUserQuestion으로 세 가지를 확정했다: 온도/강수량
상관관계 분석은 설명만 하지 말고 이번 라운드에 실제로 구현할 것,
메뉴 중복점검의 "편성 기준(일)"은 최소 재편성 간격이라 그보다 짧게
재편성된 경우를 위반으로 보여줄 것, Top5/기준 목록은 메인 메뉴만
다룰 것(부찬·건강가든은 이번 재설계 대상 밖).

### 날씨 관련 기능을 "시뮬레이션" 탭으로 분리 + 기온/강수량-식수 상관관계 분석

`WeatherCorrelationSection`은 §79까지 `MenuPlanningPage`(메뉴 편성·운영
탭) 안에 "시뮬레이션" 라벨 `<h2>`로만 시각적으로 구분돼 있었다 — 담당자는
진짜 별도 탭을 원했다. `App.tsx`의 `Tab` 유니온·`TABS` 배열에
`"simulation"`/"시뮬레이션"을 추가하고, `AnalysisPage.tsx`에 새
`export function SimulationPage()`(`<WeatherCorrelationSection />` 하나만
렌더)를 만들어 `MenuPlanningPage`에서 그 섹션을 뗐다. 2026-08 개편 때
"시뮬레이션" 탭을 없애고 유일한 고유 기능(사내 행사 토글)을 "금주 예상
식수" 카드로 흡수했던 결정을 날씨 콘텐츠에 한해서만 되돌리는 것 — 다른
흡수된 기능까지 복원하는 건 아니다.

같이 담당자가 궁금해한 "기온/강수량이 높은 날 식수가 늘어나는 메뉴"는
기존 이벤트형 랭킹(비/폭설/폭염/한파, §71/§72 — 임계값을 넘는 날만
범주화해 평상시와 비교)과 다른 축이라 새로 만들었다. 순수 함수 모듈
`weather_correlation.py`에 `pearson_correlation(xs, ys) -> float | None`
(외부 통계 라이브러리 없이 평균/분산으로 직접 계산, 표본 2개 미만이거나
분산 0이면 None)을 추가하고, `analysis.py`에
`GET /menu-performance/weather-correlation-ranking` 신규 엔드포인트를
추가했다 — 기존 `_headcount_by_date_by_menu_bulk`(플레이스홀더 메뉴·
미캠회관 제외가 이미 내장됨, §71/§76)를 그대로 재사용해 menu_id 기준으로
집계하고(날씨유형 랭킹과 동일하게 코너 구분 없음), 그 메뉴가 나온 날짜와
`DailyWeather`의 `max_temp_c`/`precip_mm`을 페어링해 상관계수를 낸다.
표본이 `min_days`(기본값은 기존 `weather_correlation_low_sample_days`
설정 재사용) 미만인 메뉴는 응답에서 제외한다. 프론트는
`WeatherCorrelationSection`에 날씨유형·계절 랭킹과 같은 구조의 새
하위 블록을 추가해 기온/강수량 탭 버튼 + 상관계수 랭킹 표(기존
`topMoversAndFallers()` 헬퍼를 `correlation` 필드 기준으로 재사용)를
보여주고, "상관관계일 뿐 인과관계가 아니다"는 기존 디스클레이머 톤을
유지했다.

### 홈 통계 정합

§80에서 "금주 예상 식수" 카드(코너-메뉴 랭킹 가로막대)는 실측 평균
기반으로 새로 만들었지만, 그 위 스탯타일 중 "오늘 예상 총 식수"는
옛 혼잡도 예측 파이프라인(`congestionForecast`, 오늘 날짜·중식 한정)을
그대로 쓰고 있었다 — §80의 "예측 대신 실측" 취지와 안 맞았다. 라벨을
"금주 예상 식수"로 바꾸고 값도 `plannedHeadcountBars`(§80에서 만든,
null 제외된 코너-메뉴 랭킹 행)의 `recent_avg_headcount` 합계로
교체했다. "최고 혼잡 예상 코너" 타일은 라벨을 "최고 혼잡 예상
코너/메뉴"로 바꾸고, §80에서 `sub`에 곁다리로 붙였던 메뉴명을 `value`로
옮겨 코너·메뉴를 동급으로 표기했다(`sub`는 피크 식수 숫자만 남김).
"최고 혼잡 예상 코너/메뉴" 타일은 여전히 예측이 맞는 용도(어디가
붐빌지 미리 보기)라 `congestionForecast` 쿼리 자체는 유지했다.

### 식수 추이 기본값 — 주간·코너별 + 7개 코너 기본 체크

`HomePage.tsx`의 "식수 추이" 차트 기본값을 `trendGranularity: "daily"→
"weekly"`, `trendGroupBy: "total"→"corner"`로 바꿨다. 코너 필터
(`trendCornerIds`)는 담당자가 부른 7개 코너 이름(고슬고슬비빈, 모던키친,
싱푸차이나, 한식사계, 동방식객, 도담찌개, 스냅스낵)을 기본으로 켠 상태로
시작해야 하는데, 코너 목록은 하드코딩된 마스터 리스트가 없고
`cornerListQuery`(DB 기반)로만 얻을 수 있어 그 쿼리가 로드된 뒤 이름
매칭으로 1회만 초기화하는 `useEffect` + `useRef` 플래그를 추가했다(이후
사용자가 수동으로 코너를 켰다 껐다 해도 이 초기화가 다시 개입하지
않음). 개발 DB에는 이 7개 이름 중 실제로 존재하는 코너가 없어(운영 DB
전용 이름으로 추정) 필터가 빈 채로 남는 것까지 Playwright로 확인했다 —
이름이 매칭 안 되면 조용히 전체 코너로 폴백하는 게 의도된 동작이다.

### 규칙 라벨 클릭 → 해당 주 전체 매치 하이라이트

`WeeklyMenuReviewTab`의 "주간 편성 규칙 검증" 패널은 §78에서 개별 위반
메뉴 칩을 클릭하면 격자표 셀 하나를 하이라이트하는 기능이 있었다
(`selectedSlotKey: string | null`, 단일 선택). 담당자는 "각 규칙을
클릭하면" 이라고 했으므로, 규칙 라벨(예: "면류 (하루 최대 4개)") 자체를
클릭하면 그 규칙의 이번 주 위반 매치 전체가 동시에 하이라이트되길
원했다 — 단일 선택으로는 표현할 수 없어 `selectedSlotKeys: Set<string>`
으로 바꿨다. `selectSlot(key)`는 그대로 단일-키 토글로 동작하고(기존
칩/셀 클릭 UX 유지), 새 `selectRuleMatches(matches)`가 규칙의
`violatingMatches`를 키 집합으로 변환해 세팅한다(같은 집합이 이미
선택돼 있으면 토글 오프). 격자 셀의 `isSelected`는
`selectedSlotKeys.has(key)`로, 슬롯 상세/편집 패널은
`selectedSlotKeys.size === 1`일 때만 렌더하고 2개 이상 선택되면
"N개 슬롯이 격자에서 강조 표시되어 있습니다" 안내만 보여준다.

### 메뉴 중복점검 재설계 — Top5 최단 재편성(메인) + 사용자 기준 미달 목록

`MenuRotationCheckSection`은 경고 있는 모든 (코너, 메뉴) 그룹을
역할별(메인 / 부찬·건강가든)로 나눠 preview-cap과 함께 보여주는
방식이었다 — "너무 모든 내용이 다 뜬다"는 재신고를 받았다. 백엔드
`GET /weekly-menu/rotation`의 `items`는 이미 슬롯 단위로
`gap_days`(직전 대비 며칠 후)·`avg_interval_days`(평균 주기)를 갖고
있어 "가장 이르게 재편성된 순" 정렬에 새 집계가 필요 없었다 — 다만
만족도·식수가 없어 새로 조인했다: `_avg_satisfaction_by_menu`(신규,
`_recent_avg_headcount_by_menu`와 같은 조회 창을 쓰는 짝 헬퍼,
`TASTE_SCORE_POINTS` 평균)와 기존 `_recent_avg_headcount_by_menu`를
호출해 각 `items` 행에 `avg_satisfaction`/`recent_avg_headcount`를
채웠다.

프론트는 역할 필터를 메인으로 고정(담당자 확인: "메인만" — 통합도
분리도 아니고 부찬·건강가든은 아예 대상 밖)하고, 재편성 이력이 있는
(FIRST_TIME이 아닌) 행만 대상으로 (1) `gap_days` 오름차순 Top5를
"가장 이르게 재편성된 메뉴 Top5"로 기본 표시, (2) "편성 기준(일)" 숫자
입력이 채워지면 `gap_days < threshold`인 전체 행을 별도 목록으로
추가 표시(기존 `ROTATION_PREVIEW_COUNT`+"전체 보기" idiom 재사용)한다.
각 행은 메뉴(코너)·만족도·식수·평균 주기·직전 대비를 보여주고,
"편성이력 보기" 토글로 같은 (코너, 메뉴)의 전체 편성일 이력을
드릴다운으로 펼친다(새 API 없이 이미 받은 `items`를 클라이언트에서
필터링). 기존 `warningsOnly` 토글, 부찬·건강가든 블록,
`over_frequency`/최근 90일 블록은 이번 재설계 범위 밖이라 제거했다
(필요해지면 나중에 별도 요청으로 복원).

### 편성빈도×성과 — NO_INTAKE 리스트 접기

`MenuPlanPerformanceSection`의 "편성됐지만 취식 기록이 0인 메뉴" 칩
목록은 이 파일에서 유일하게 미리보기 상한이 없었다 — 다른 섹션이 이미
쓰는 "기본 N개 + 전체 보기" 패턴(`MenuRotationCheckSection` 등)을
그대로 가져와 `NO_INTAKE_PREVIEW_COUNT=12` + `showAllNoIntake` 토글을
추가했다.

### 검증

- `test_weather_correlation.py`(신규): `pearson_correlation` 유닛
  테스트 — 완전 양의/음의 상관, 분산 0(None), 표본 2개 미만(None),
  길이 불일치(None).
- `test_api_ingest_and_analysis.py`: `weather-correlation-ranking`
  엔드포인트 — 기온이 오를수록 식수가 느는 메뉴를 시딩해 상관계수
  1.0으로 나오는지, `min_days` 미만 표본 메뉴가 응답에서 빠지는지.
  `weekly_menu_rotation`에 `avg_satisfaction`/`recent_avg_headcount`가
  채워지는지(취식 기록 없으면 0이 아니라 null인지 포함) 확인.
- `pytest -q` 전체 585개 통과.
- `npx tsc -b`·`npm run build` 타입체크·빌드 통과.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) nav에 "시뮬레이션" 탭이 새로 뜨고 날씨 카드+상관관계
  랭킹이 그 안에서만 보이며 메뉴 편성·운영 탭에는 더 이상 안 보임,
  (2) 홈 "금주 예상 식수"/"최고 혼잡 예상 코너/메뉴" 타일이 새 라벨과
  값으로 뜸, (3) 식수 추이 요청이 `granularity=weekly&group_by=corner`
  로 나가는지 네트워크 요청으로 확인(7개 코너는 이 개발 DB에 없어
  필터 없이 전체 코너로 폴백 — 의도된 동작), (4) "면류" 규칙 라벨
  클릭 시 위반 매치 5개 전체가 격자에서 동시에 하이라이트되고 안내
  문구가 뜸, (5) 메뉴 중복점검이 Top5로 재구성됐고 "편성 기준(일)"에
  값을 넣으면 기준 미달 목록이 추가로 뜨며 "편성이력 보기"로
  드릴다운되는지, (6) 편성빈도×성과의 NO_INTAKE 목록이 렌더되는지
  (이 개발 DB는 8개뿐이라 12개 임계값 아래라 토글 버튼은 안 뜸 — 정상).

## §82. 기능 축소 — 메뉴 편성·운영 탭 8개 섹션 → 4개로 간결화 (2026-08)

81라운드 동안 계속 "추가"만 해온 결과 "메뉴 편성·운영" 탭이
`WeeklyMenuReviewTab`·`MenuRotationCheckSection`(메뉴 중복 점검)·
`RepeatedSideDishRankingSection`(부찬 반복 랭킹)·`MealClashCheckSection`
(한 끼 구성 겹침 점검)·`MenuPlanPerformanceSection`(편성 빈도×성과)·
`MenuComboSection`(부찬 조합 만족도)·`MenuRepertoireSection`(레퍼토리
집중도)·`MenuPairAnalysisSection`(코너 동반 선택쌍) 8개 섹션이 한 페이지에
계속 쌓인 상태였다. 담당자가 "전체적으로 기능을 축소하고 간결하게
정리"하고 싶다고 요청했고, AskUserQuestion으로 확인한 결과:

- **목적**: 화면이 너무 복잡해 실사용자(식당 운영담당자)가 헷갈림 —
  실제 쓰는 핵심 기능만 남긴다.
- **범위**: 메뉴 편성·운영 탭 우선(8개 섹션으로 가장 많고, 서로 겹치는
  기능이 있다는 문제의식).
- **방식**: 코드까지 완전 삭제(단순 UI 숨김이 아님) — git 이력에서
  나중에 복원 가능하니 코드량 자체를 줄인다.

8개 섹션을 세 그룹으로 나눠 확인했다:
- **"중복" 계열 3개**(메뉴 중복 점검=재편성 간격, 부찬 반복 랭킹=반복
  횟수, 한 끼 구성 겹침 점검=같은 끼니 내 재료/특성 겹침) — 서로 다른
  각도지만 개념이 겹쳐 보인다는 지적. **1개 카드로 통합**(삭제 아님 —
  기능 자체는 다 남기되 카드 수만 줄인다).
- **"탐색적 분석" 계열 3개**(부찬 조합별 만족도, 레퍼토리 집중도, 코너
  동반 선택쌍) — 일상 운영 판단보다 탐색적 분석 도구에 가깝다는 지적.
  부찬 조합별 만족도는 남기고, **레퍼토리 집중도·코너 동반 선택쌍은
  완전 삭제**.
- **핵심 2개**(주간 식단표 관리+규칙검증, 편성 빈도×성과) — 실제
  식단표를 관리하고 실행 가능한 추천을 주는 화면이라 **그대로 유지**.

결과: `MenuPlanningPage`가 8개 섹션 → **4개**(주간 식단표 관리, 메뉴
중복 점검(통합), 편성 빈도×성과, 부찬 조합별 만족도)로 줄었다.

### 완전 삭제 — 레퍼토리 집중도 + 코너 동반 선택쌍

사전 조사(Explore)로 삭제 대상의 의존 관계를 정확히 확인했다 — 프론트
다른 화면에서 재사용되는 함수·타입은 없었다. 백엔드는 엔드포인트
3개(`GET /menu-plan/repertoire`, `GET /corners/{corner_id}/core-layer-menu-pairs`,
`GET /menu-pairs/top`)를 지우면서, 그 엔드포인트들만 쓰던 서비스
함수만 같이 지웠다: `compute_repertoire`(`menu_plan_analytics.py`),
`build_menu_controlled_meal_log_rows`/`classify_menu_controlled_corner_preference`
(`corner_core_layer.py`), `is_obvious_pair`/`compute_top_menu_pairs`
(`menu_affinity.py`). 반면 같은 파일의 `build_employee_corner_counts`/
`classify_corner_core_layer`(코너 코어층 요약 엔드포인트가 계속 씀),
`build_employee_menu_sets`(메뉴 동반선택 엔드포인트가 계속 씀),
`_corner_id_by_menu_from_meal_log`(`dashboard.py`/`simulation.py`도
직접 import)는 **다른 곳에서 재사용 중이라 절대 지우지 않았다** — "삭제
대상 엔드포인트에서만 쓰였는지"를 exhaustive grep으로 하나하나 확인한
뒤에야 지웠다.

프론트에서는 `MenuRepertoireSection`·`MenuPairAnalysisSection` 함수
전체와 그 전용 헬퍼(`buildMenuPairGraphOption`, 모듈 상수
`ALL_MENUS_TAB`, `type PairSortKey`)를 삭제하고, `MenuPlanningPage`가
`MenuPairAnalysisSection`에게 `corners` prop을 주기 위해서만 갖고 있던
`cornersQuery` 선언도 같이 지웠다(단 `api.cornerList()` 자체는
`HomePage.tsx`/`MenuComboSection`/`RepeatedSideDishRankingSection`이
각자 독립적으로 호출하므로 함수는 유지). `client.ts`에서도 대응하는
타입·함수(`menuPlanRepertoire`, `cornerCoreLayerMenuPairs`,
`topMenuPairs`, `RepertoireResponse`/`RepertoireRow`,
`MenuPairRow`/`CornerCoreLayerMenuPairsResponse`)를 지웠다.

테스트는 삭제된 엔드포인트를 직접 때리는 API 테스트 10개와 삭제된
서비스 함수의 유닛 테스트 17개(레퍼토리 6개, `menu_affinity` 8개,
`corner_core_layer`의 `menu_controlled_preference` 3개)를 지우고,
`test_demoted_features_keep_working_apis`(예전 "UI만 숨기고 API는
유지" 라운드의 계약 테스트)는 전체 삭제가 아니라 이번에 지운 두
엔드포인트에 대한 assert 두 줄만 제거해 살아있는 다른 demoted
엔드포인트 검증은 그대로 남겼다.

### 통합 — "메뉴 중복 점검" 하나로(재편성/부찬반복/한끼겹침)

세 컴포넌트는 서로 상태를 공유하지 않고(날짜 범위도 각자 관리 —
`MealClashCheckSection`은 주 단위 이전/다음 네비게이터라 나머지 둘의
자유 시작·종료일 선택기와 구조가 달라 하나의 날짜 컨트롤로 억지로
통합하지 않았다) API 호출도 독립적이라, **로직은 그대로 두고 카드
껍데기만 하나로 합쳤다** — 백엔드·`client.ts` 변경 없음.

새 컴포넌트 `MenuDuplicationCheckSection`이 `activeTab` state
(`"rotation" | "repeated" | "clash"`)와 `SegmentedControl`로 세 패널
중 하나만 렌더한다. 기존 `MenuRotationCheckSection`/
`RepeatedSideDishRankingSection`/`MealClashCheckSection` 세 함수는
이름을 `RotationCheckPanel`/`RepeatedSideDishPanel`/`MealClashPanel`로
바꾸고 최상위 `<Card title="...">...</Card>` 래퍼만 벗겨내 안쪽
`useState`/`useQuery`/JSX는 그대로 이식했다(§81에서 재설계한 Top5+
편성기준, 정렬+클릭 상세, 요일별 그룹 로직은 완전히 그대로 유지). 탭을
바꾸면 안 보이는 패널은 언마운트되고(다시 돌아오면 재요청) —
`WeatherCorrelationSection`의 날씨유형/계절 탭 전환이 이미 같은 패턴이라
일관된 관례. 부수 효과로 페이지 로드 시 동시에 나가던 API 요청이
3개에서 1개(기본 탭)로 줄었다.

### `MenuPlanningPage` 최종 구성

```tsx
export function MenuPlanningPage() {
  return (
    <div className="space-y-6">
      <WeeklyMenuReviewTab />
      <MenuDuplicationCheckSection />
      <MenuPlanPerformanceSection />
      <MenuComboSection />
    </div>
  );
}
```

## 검증

- `pytest -q` 전체 회귀 — 558개 통과(585개에서 27개 삭제: API 10개 +
  레퍼토리 6개 + menu_affinity 8개 + corner_core_layer 3개; 재편성/
  부찬반복/한끼겹침 테스트는 그대로 유지).
- `npx tsc -b`·`npm run build` — 삭제 후 안 쓰는 import·타입이 안 남아
  있는지, 통합 컴포넌트가 타입 에러 없이 컴파일되는지 확인. 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) "메뉴 편성·운영" 탭에 "레퍼토리"·"동반 선택 쌍" 텍스트가
  더 이상 안 보이고 "메뉴 중복 점검"·"편성 빈도"·"부찬 조합" 4개 섹션만
  남았는지, (2) "메뉴 중복 점검" 카드 안에서 재편성 점검/부찬 반복
  랭킹/한 끼 겹침 세 탭을 각각 눌렀을 때 §81 재설계 내용(Top5+편성기준,
  정렬+클릭 상세, 요일별 그룹+주 네비게이터)이 그대로 동작하는지, (3)
  삭제된 세 엔드포인트(`/menu-plan/repertoire`, `/menu-pairs/top`,
  `/corners/{id}/core-layer-menu-pairs`)를 직접 호출하면 404가, 살아있는
  `/corners/core-layer-summary`는 200이 나오는지 — 전부 확인됨.

## §83. 코너 필터 기본값 / 홈 스탯타일 2개 교체 / 메뉴 중복점검 30일 기본값 / 날씨 시뮬레이션 정리 (2026-08)

§82 배포 후 담당자가 작은 피드백 4건을 한 번에 요청했다 — 서로 다른
화면(HomePage.tsx 2건, AnalysisPage.tsx 2건)을 건드리지만 각각
독립적이라 한 라운드로 묶어 처리했다. AskUserQuestion으로 애매한 부분
3곳을 확정했다: "최고 혼잡 예상 코너/메뉴" 타일 대체안은 "실측 기준
최고 식수 코너/메뉴"(§80/§81의 예측→실측 전환 기조와 같은 방향, 이미
로드된 데이터 재사용), 날씨 시뮬레이션 강수량 타임라인은 §82와 같은
방식으로 프론트+백엔드 완전 삭제, 메뉴 중복점검 30일 기본값은 재편성
점검+부찬 반복 랭킹 두 탭 모두 적용.

담당자가 요청한 "날씨별로 취식 많았던 메뉴"는 조사 결과 이미
`WeatherCorrelationSection`에 "메인메뉴 × 날씨유형 인기 랭킹"
블록(§71/§76)으로 존재했다 — 신규 기능은 필요 없었고, 강수량 타임라인
차트만 지우면 됐다.

### 1. 식수 추이 코너 필터 기본값에서 스냅스낵 제외

`HomePage.tsx`의 `DEFAULT_TREND_CORNER_NAMES`(§81에서 지정한 7개 코너)
에서 "스냅스낵" 한 줄만 삭제 — 6개 코너만 기본 체크된다. 1회성 초기화
`useEffect`와 체크박스 UI는 배열 길이에 무관하게 동작해 손대지 않았다.

### 2. 홈 스탯타일 2개 교체

**"금주 예상 식수" → "최근 7일 식수"**: 선택한 주(`selectedMonday`)
스코프의 실측 평균 합계(`plannedHeadcountRanking` 기반) 대신, 어느
주를 보고 있든 안 바뀌는 "오늘 기준 트레일링 7일 실측 식수 합계"
스냅샷으로 바꿨다. 새 쿼리 `recentHeadcountQuery`가 `api.weeklySummary`
를 분류/끼니 필터 없이 `isoDaysAgo(6)`~`isoDaysAgo(0)` 범위로 호출한다
(둘 다 optional 파라미터라 생략하면 백엔드가 전체 합산). 이 타일의
유일한 소비자였던 `weeklyPlannedHeadcountTotal` 파생값은 삭제했지만,
`plannedHeadcountRanking`과 그 파생값들(`plannedHeadcountBars` 등)은
아래 타일과 기존 "코너-메뉴별 예상 식수 랭킹" 가로막대가 계속 쓰므로
그대로 유지했다.

**"최고 혼잡 예상 코너/메뉴" → "최고 식수 코너/메뉴"**: 요일별 평균×
메뉴배수×피크점유율 예측(`congestionForecast`) 대신, 바로 아래 랭킹
막대그래프와 같은 실측 데이터를 재사용한다 — 백엔드가 이미
`recent_avg_headcount` 내림차순으로 정렬해 주므로
`plannedHeadcountBars[0]`이 곧 최고 식수 행이다. 새 API 호출 없이
기존 데이터만 재사용해 구현했다. `congestionForecast`/
`topCongestedCorner`/`todayMainMenu`/`topCongestedCornerMenuName`과 옛
"예상 피크 식수 = ..." 공식 설명 각주는 이 타일에서만 쓰였다는 걸
`HomePage.tsx` 안에서 grep으로 확인 후 삭제했다.

**주의**: `api.congestionForecast`가 부르는 백엔드
`GET /simulation/congestion-forecast`는 Agent 채팅 그라운딩
(`chat_grounding.py`)이 `from app.api.simulation import congestion_forecast`
로 직접 import해서 쓴다 — 이번 변경은 `HomePage.tsx` 안의 이 타일
전용 사용부만 지우는 것으로 한정했고, `client.ts`의 함수·타입과 백엔드
엔드포인트는 그대로 뒀다.

### 3. 메뉴 중복 점검 기본 기간 — 180일 → 30일

`AnalysisPage.tsx`의 공유 상수 `PERIOD_START`/`PERIOD_END`(180일, 파일
전역 수십 곳이 참조)는 그대로 두고, 새 상수
`DUPLICATION_CHECK_PERIOD_START`/`_END`(`isoDaysAgo(30)`/`isoDaysAgo(0)`)
를 추가해 `RotationCheckPanel`(재편성 점검)과
`RepeatedSideDishPanel`(부찬 반복 랭킹)의 초기 `useState`만 이 상수로
바꿨다. `MealClashPanel`(한 끼 겹침, 이미 월요일 기준 주 단위
네비게이터)은 이번 요청 대상이 아니라 그대로 뒀다.

### 4. 날씨 시뮬레이션 — 강수량 타임라인 완전 삭제

`WeatherCorrelationSection`은 하나의 `<Card>`가 타임라인 차트 블록과
날씨유형/계절/상관관계 랭킹 블록 3개를 형제 요소로 감싸고 있었다 —
Card 래퍼는 유지하고 타임라인 관련 조각만 지웠다: `timelineQuery`
(`api.weatherHeadcountTimeline`), `visibleClassifications`/
`CLASSIFICATION_OPTIONS`/`toggleClassification`(타임라인 전용 분류
체크박스 필터), `timelineOption` ECharts 옵션, 로딩/에러/빈상태/차트
렌더 JSX. `periodStart`/`periodEnd` state와 그 날짜 입력은 날씨유형/
계절/상관관계 랭킹 세 블록이 공유하므로 그대로 남겼다. 카드
제목("날씨에 따른 식수 변화 — 과거 실측 현황" → "날씨·계절별 메뉴
식수 랭킹")과 인트로 문구도 남은 3개 랭킹 블록에 맞게 재작성했다.

백엔드는 `GET /analysis/weather-headcount-timeline`
(`weather_headcount_timeline`) 엔드포인트를 지웠다 — `_load_corner_stats`
/`get_holiday_service`는 다른 두 엔드포인트도 쓰는 공유 헬퍼라 그대로
뒀고, 이 엔드포인트 전용 헬퍼는 원래 없어(공유 헬퍼+인라인 로직만으로
구성) 함수 하나만 지우면 끝났다. 테스트도
`test_weather_headcount_timeline_returns_daily_rows`/
`test_weather_headcount_timeline_returns_empty_days_without_meal_log`
2개만 지우고, 같은 파일의 다른 날씨 테스트가 쓰는 `_seed_menu_rain_vs_normal`
헬퍼는 그대로 뒀다. `client.ts`의 `weatherHeadcountTimeline` 함수와
`WeatherHeadcountTimelineDay`/`WeatherHeadcountTimelineResponse` 타입도
지웠다.

## 검증

- `pytest -q` — 556개 통과(§82의 558개에서 타임라인 테스트 2개 삭제).
- `npx tsc -b`·`npm run build` — 클린(미사용 import 없음).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건, 기존 `StatTile` 컴포넌트의 `borderColor`/`borderLeftColor`
  shorthand 충돌 경고 1건은 `tone` prop을 쓰는 모든 타일에 이미 있던
  기존 이슈로 이번 변경과 무관함을 확인): (1) 홈 "최근 7일 식수"가
  주 네비게이터(이전 주 버튼)를 눌러도 값이 그대로인지, "최고 식수
  코너/메뉴"는 주가 바뀌면 랭킹 막대그래프 1위와 함께 바뀌는지, 옛
  "예상 피크 식수 =" 각주가 사라졌는지, (2) 메뉴 중복 점검의 "재편성
  점검"·"부찬 반복 랭킹" 두 탭 모두 날짜 입력이 2026-07-14~2026-08-13
  (오늘 기준 정확히 30일)로 뜨고, "한 끼 겹침" 탭은 그대로 주 단위
  네비게이터인지, (3) 시뮬레이션 탭에 강수량 차트(canvas 0개)·분류
  체크박스가 없고 날짜 입력은 남아있으며 날씨유형/계절/상관관계 랭킹
  3개 블록이 정상 동작하는지, (4) `DEFAULT_TREND_CORNER_NAMES`에서
  스냅스낵이 빠졌는지는 소스 grep으로 확인(이 개발 DB의 실제 코너
  명칭이 §81 하드코딩 목록과 애초에 하나도 안 겹쳐 화면상 체크 상태로
  직접 확인은 안 됐지만, 코드 변경 자체는 검증됨).
- 문서화 후 커밋·푸시.

# §84. 시뮬레이션 탭: 날씨 시나리오 예측 섹션 + 랭킹 연동 (2026-08)

## Context

담당자가 "날씨 시뮬레이션 탭 개편 스펙" 문서를 전달했다 — 기상청 API
연동을 전제로 탭 전체를 재설계하는 상세 스펙(오늘/내일 날씨 요약 카드,
날씨 시나리오 선택기, 예상 식수 카드, 기존 랭킹 UI 정리, 코너별 날씨
민감도 5개 블록)이었다. 조사 결과 스펙의 핵심 전제 두 가지가 이
코드베이스 상태와 어긋나 있었다:

- **강수량 타임라인 삭제(스펙 1번)는 직전 §83 라운드에서 이미 완료**돼
  있었다 — 프론트 컴포넌트·백엔드 엔드포인트·테스트 전부 지워진 상태를
  재확인만 했다(재작업 없음, grep으로 잔여 참조 0건 재확인).
- **오늘/내일 날씨 요약 카드(스펙 2-1)는 기상청 단기예보(실시간 예보)
  API를 전제**로 하는데, 이 프로젝트에 연동된 건 기상청 ASOS **과거
  관측 일자료**뿐이다(§64에서 "중기 날씨 api는 미래 예보라 과거 데이터
  요청과 안 맞는다"며 의도적으로 미도입 결정한 이력 있음) — 이번
  라운드에 새로 만들어야 하는 일이었다.
- 반대로 **시나리오 선택기 + 예상 식수 예측(스펙 2-2/2-3)이 필요로 하는
  백엔드 예측 엔진은 이미 만들어져 있었지만 프론트 어디서도 호출되지
  않는 고아 코드**였다 — `simulation.py`의 `Weather` enum(맑음/비/폭염/
  한파 4종)·`_WEATHER_MULTIPLIER`와 `POST /simulation/what-if` 엔드포인트.

AskUserQuestion으로 방향을 확정했다: (1) 실시간 날씨 요약 카드(2-1)는
이번 라운드에서 **완전히 제외**(담당자가 "참고용으로 어제 날씨라도
보여주자"는 절충안 대신 완전 제외를 선택), (2) 시나리오 선택기+예측
카드(2-2/2-3)는 기존 `what-if` 엔진을 재사용하되 스펙이 요구하는 6종
(맑음/흐림/비/눈/폭염/한파)을 맞추기 위해 흐림·눈 배수를 새로 추가,
(3) "코너별 날씨 민감도"(2-5)는 이번 스코프에서 제외. 스펙 2-4(기존
랭킹 UI 정리 — Top5~10 제한, 시나리오와 동기화, 화살표+숫자 표기)는
그대로 진행했다.

## 설계

### 1. 백엔드 — 날씨 배수 4종 → 6종 확장

`backend/app/api/simulation.py`의 `Weather` enum에 `CLOUDY = "흐림"`/
`SNOW = "눈"`을 추가하고, `_WEATHER_MULTIPLIER`에 `CLOUDY: 0.97`
(맑음과 비의 중간 — 아직 비가 안 와 이동은 자유롭지만 나들이·외부식당
유인이 살짝 줄어든다는 가정)·`SNOW: 0.85`(비의 0.90보다 낮게 — 적설로
통근이 비보다 더 지연되고 재택/단축근무가 걸리는 경우도 있어 감소폭이
크다고 봤다)를 추가했다. 둘 다 기존 배수와 같은 톤으로 "방향성만 맞춘
v0 값, 실측 근거 없음" 주석을 남겼다.

`what_if`/`weekly_congestion_forecast` 둘 다 `_WEATHER_MULTIPLIER[...]`
제네릭 딕셔너리 조회만 하고 카테고리별 분기가 없어, enum+dict 확장만으로
두 엔드포인트가 자동으로 6종을 다 받는다 — 라우트 로직 변경은 없었다.
`WeatherEvent`(`weather_event.py`, 과거 실측 랭킹·분류 전용, "비/폭설/
폭염/한파")는 `Weather`와 이름이 비슷한 완전히 별개 enum이라 건드리지
않았다 — 매핑은 프론트 동기화 로직에서만 처리(아래 3번).

### 2. 프론트 — 신규 시나리오 예측 섹션

`AnalysisPage.tsx`에 `WeatherScenarioForecastSection` 컴포넌트를 신설해
`WeatherCorrelationSection` 바로 위에 뒀다. 날씨 6종/끼니 3종
`SegmentedControl`(이 파일에서 `SegmentedControl`을 처음 쓰는 자리 —
기존 랭킹 블록 3곳은 손수 만든 pill 버튼을 각각 중복 구현해왔음, 4번째
중복을 만들지 않았다)과 날짜 입력으로 `POST /simulation/what-if`를
호출한다. 예상 총 식수는 `Σ predicted_headcount`, "평시 대비" 비교는
`(Σpredicted - Σbaseline) / Σbaseline`로 계산해 `StatTile`에 화살표
(↑/↓/→)와 함께 표시한다. **"전주 대비"라고 쓰지 않았다** —
`baseline_headcount`는 "최근 8회 같은 분류·끼니 평균"이지 지난주 그
자체가 아니기 때문. "코너별 예측 보기" 토글(기본 접힘)을 펼치면
`HomePage.tsx`의 `plannedHeadcountOption`과 동일한 구조(내림차순 정렬
가로막대, `label.formatter="{c}명"`)의 코너별 예측 차트가 뜬다.

### 3. 프론트 — 시나리오 → 랭킹 탭 단방향 연동

`WeatherCorrelationSection`에 옵셔널 prop `syncedEvent?: WeatherEvent`를
추가해, 값이 있으면 `useEffect`로 그 이벤트 탭을 선택하도록 했다(무프롭
호출 시 기존 자기완결적 동작은 그대로 — 이 컴포넌트는 전체 프론트에서
`SimulationPage` 한 곳에서만 호출돼 안전하다는 걸 grep으로 확인).
`SimulationPage`가 `selectedWeather` 상태를 쥐고
```ts
const WEATHER_TO_EVENT: Partial<Record<Weather, WeatherEvent>> = {
  비: "비", 폭염: "폭염", 한파: "한파", 눈: "폭설",
};
```
로 매핑해 두 섹션을 연결한다. "눈→폭설"만 이름이 다르고, "맑음"/"흐림"은
대응하는 `WeatherEvent` 랭킹 카테고리가 없어 `Partial`이 자연히
`undefined`를 넘겨 랭킹 탭이 그대로 유지된다(Playwright로 확인 — 흐림
선택 시 직전에 선택된 랭킹 탭이 안 바뀜).

### 4. 프론트 — 기존 랭킹 3블록의 증감 표기를 화살표+숫자로

날씨유형 랭킹(`diff_vs_normal`)·계절 랭킹(`diff_vs_overall`)·상관관계
랭킹(`correlation`) 세 곳의 `<Badge>` 라벨 앞에 `↑`/`↓`/`→` 접두사를
붙였다 — 기존 `Badge`/`tone`(색 dot) 체계는 그대로 유지, 화살표+숫자를
주 신호로 추가한 것뿐이다. `topMoversAndFallers`(§75에서 추가, top5
상승/top5 하락=최대 10행 콜랩스)는 이미 스펙의 "Top5~10 제한"을
만족하고 있어 변경하지 않았다.

## 스펙 대비 이번에 하지 않은 것

- **오늘/내일 날씨 요약 카드(스펙 2-1)**: 실시간 단기예보 API 연동이
  필요해 이번 라운드에서 제외(담당자 확인). 필요해지면 별도 라운드로.
- **코너별 날씨 민감도(스펙 2-5)**: 이번 스코프에서 제외(담당자 확인).

## 검증

- `pytest -q` — 558개 통과(§83의 556개 + 흐림/눈 배수 신규 테스트 2개).
  새 테스트는 `test_what_if_uses_quadrant_multiplier_for_planned_menu_with_performance_data`
  와 같은 시딩 패턴으로 `weather=흐림`/`weather=눈` 각각 호출해
  `predicted_headcount == round(baseline * 0.97, 1)`/`* 0.85`를 검증한다.
- `npx tsc -b`·`npm run build` — 클린.
- `weatherHeadcountTimeline`/`weather-headcount-timeline` 잔여 참조
  0건 재확인(문서 언급 제외, §83 삭제가 이번 변경으로 되살아나지
  않았음).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) 시나리오 선택기(날씨 6종+끼니+날짜)와 "예상 총 식수"
  카드가 "평시 대비"로 표기됨("전주 대비" 없음) 확인, (2) "코너별
  예측 보기" 토글이 기본 접힘이고 펼치면 내림차순 막대그래프가 뜸
  확인(그린미트 23.2명 1위 등), (3) 시나리오를 폭염/눈으로 바꾸면
  아래 랭킹 탭이 각각 폭염/폭설로 따라가고, 흐림으로 바꾸면 직전
  선택(폭설)이 그대로 유지됨을 스크린샷으로 확인, (4) 날씨유형·계절·
  상관관계 3개 랭킹 표에 화살표(↑/↓/→)가 라벨 앞에 붙어 보임 확인.
- 문서화 후 커밋·푸시.

# §85. 홈 화면 정리(설명 요약·중복 차트 삭제) + 코너별 분석 표 중심 재구성 (2026-08)

## Context

담당자가 4가지를 요청했다: (1) 전체 페이지에서 긴 설명 문단을 사용자
시점으로 요약, (2) "주간 식수 추이" 차트 삭제(바로 아래 "식수 추이 —
기간 단위 · 끼니 · 코너 · 회사구분" 통합 차트가 같은 정보를 이미
보여줌), (3) "금주 예상 식수 · 점유율 · 대기시간" 카드 삭제, (4) 코너별
분석 — 지표 비교에서 그래프는 지우고 표만 남기며 "그린미트" 컬럼 삭제 +
컬럼별 정렬 추가.

조사(Explore 에이전트 3개 병렬 + 직접 코드 확인)로 두 가지 중요한
교차 참조를 찾아 잘못된 삭제를 피했다:

- `plannedHeadcountRanking` 쿼리는 삭제 대상 카드 안에 있었지만, 그
  파생값 `topPlannedHeadcountRow`는 스탯타일 그리드의 "최고 식수
  코너/메뉴" 타일(§83)이 그대로 쓰고 있었다 — 쿼리와
  `plannedHeadcountBars`/`topPlannedHeadcountRow`는 남기고, 카드 안의
  예상 식수 랭킹 가로막대(JSX)와 그 전용 ECharts 옵션만 지웠다.
- `api.weeklyMenuPredictedImpactSummary`(점유율/대기시간 엔드포인트)는
  삭제 대상 카드 말고 `AnalysisPage.tsx`의 주간 식단표 관리 탭
  ("전체 예측 비교" 히트맵)에서도 쓰고 있었다 — HomePage 쪽 호출과
  `forecastRequested` 상태만 지우고, `client.ts` 함수·타입과 백엔드
  엔드포인트는 그대로 뒀다.

반대로 `GET /analysis/corners/trend`(`cornerAnalysisTrend`)는 코너별
분석 컴포넌트 안에서만 쓰이는 게 grep으로 확인돼(프론트 전체에서 이
컴포넌트 말고 다른 호출부 없음, 백엔드도 이 라우트 하나뿐) 그래프를
지우면서 프론트 함수·타입·백엔드 엔드포인트·테스트까지 §82와 같은
원칙으로 완전 삭제했다.

## 설계

### 1. 전체 페이지 설명 텍스트 요약

긴 설명 문단은 전부 `HomePage.tsx`와 `AnalysisPage.tsx` 두 파일에만
있었다(나머지 페이지 파일은 짧은 상태 메시지뿐, Explore로 확인).
원칙: (a) 지금 뭘 보고 있는지/뭘 하면 되는지 한 마디, (b) 숫자를
잘못 읽지 않게 막는 핵심 경고(표본 부족, 상관관계≠인과관계, "예측이
아니라 실측")만 남기고, 왜 이렇게 설계했는지 이력·배치 스케줄 주기
같은 내부 구현 설명·변경 이력은 뺐다. 두 파일 합쳐 약 25곳의 설명
문단을 1문장(또는 짧은 절 하나 추가) 수준으로 줄였다 — 코너별 분석·
메뉴별 분석·음식벡터 관리·부찬 조합·주간 식단표 관리·VOE 4개 카드·
메뉴 중복 점검 3개 탭·편성 빈도×성과·날씨 시나리오 예측·날씨/계절/
상관관계 랭킹 3개·Admin 화면 2곳 등. 스타일(`text-[13px]`/`text-xs` +
`var(--ink-muted)`)은 그대로 두고 텍스트 내용만 줄였다.

### 2. "주간 식수 추이" 카드 삭제 (HomePage.tsx)

`Card title="주간 식수 추이"` 블록과 그 전용 파생값
(`chartWeeklyData`/`classificationByDate`/`weekdayAxisLabel`/
`pointColorForClassification`/`chartOption`, 색상 상수들,
`axisTooltipFormatter`/`formatTooltipNumber`)을 지웠다. `showSaturday`
상태와 그 유일한 UI 트리거인 "토요일 포함 보기" 버튼도 같이 지웠다 —
이 토글의 유일한 소비자가 `chartWeeklyData`뿐이었다(누적 식수
스탯타일은 `weekly.data`를 직접 써 영향 없음). `weekly` 쿼리 자체와
`recomputeDailyStats` mutation은 "선택한 주의 누적 식수" 스탯타일이
계속 쓰므로 남겼다. 이 카드 안에 있던 "선택한 주 식수 0 → 재계산"
복구 UX는 4개 스탯타일 그리드 바로 위 작은 조건부 배너로 옮겼다(축약된
문구 "이 기간 식수가 0으로 나옵니다 — 배치 집계가 안 됐을 수
있어요." + 기존 재계산 버튼 그대로 재사용).

### 3. "금주 예상 식수 · 점유율 · 대기시간" 카드 삭제 (HomePage.tsx)

카드 전체(예상 식수 랭킹 가로막대 + 점유율·대기시간 게이트+표)를
지웠다. 같이 지운 전용 코드: `plannedHeadcountOption`,
`plannedHeadcountNewMenuCount`, `forecastRequested` 상태,
`predictedImpact` 쿼리, `WAIT_MINUTES_PLAUSIBLE_MAX`. 남긴 것:
`plannedHeadcountRanking` 쿼리와 `plannedHeadcountBars`/
`topPlannedHeadcountRow`("최고 식수 코너/메뉴" 스탯타일이 씀),
`api.weeklyMenuPredictedImpactSummary`/`PredictedNumbersRow`/백엔드
엔드포인트(주간 식단표 관리 탭이 독립적으로 씀).

### 4. 코너별 분석 — 지표 비교: 표 중심 재구성 (AnalysisPage.tsx `CornerMetricComparisonSection`)

지표 선택형 통합 그래프(듀얼축, 좌/우 지표 선택기, "두 번째 지표
비교" 체크박스, 주간/월간/주차별 추이) 전체와 그 전용 상태·쿼리·파생값
(`leftMetric`/`rightMetric`/`showSecondMetric`/`trendGranularity`/
`weekOfMonthPeriod`/`trendQuery`/`womQuery`/`womMainMenuQuery`/
`cornerMetricOption` 등)을 지웠다. 모듈 상수 `CornerMetricKey`/
`CORNER_METRIC_OPTIONS`/`CORNER_METRIC_LABELS`/`CORNER_METRIC_AXIS`와
`monthRange`/`weekOfMonthLabel` 헬퍼도 이 컴포넌트에서만 쓰여 같이
지웠다(`formatTooltipNumber`/`axisTooltipFormatter`는 파일의 다른
차트가 계속 써서 남김).

표에서 "그린미트"(`is_diet_corner`를 "예"/"-"로 보여주던 컬럼, 실제
코너명 "그린미트"와 헷갈리기 쉬운 이름이었음) 컬럼을 삭제하고, 남은
4개 컬럼(코너/누적 식수/평균 만족도/피크타임 분당 서브) 모두 클릭
정렬 가능하게 만들었다 — 이 파일에 이미 있던 `SortableHeader`
컴포넌트(`MenuQuadrantTab`/`RepeatedSideDishPanel`이 쓰던 "같은 키
다시 클릭하면 방향 반전, 다른 키 클릭하면 desc로 리셋" 패턴)를
재사용해 `Table` 제네릭 컴포넌트 호출을 손수 만든 `<table>`로
교체했다. "표로 보기"/"표 숨기기" 토글은 그대로 뒀다.

`GET /analysis/corners/trend`(`corner_analysis_trend`)가 완전히
고아가 돼(grep으로 프론트·백엔드 각 1곳뿐임을 확인) `client.ts`의
`cornerAnalysisTrend` 함수·`CornerTrendRow` 타입, 백엔드 엔드포인트,
테스트 2개(`test_corner_analysis_trend_groups_by_period_and_corner`/
`test_corner_analysis_trend_filters_by_meal_types`)를 완전 삭제했다.
`_period_bucket` 헬퍼는 다른 엔드포인트도 써서 남겼다.

## 검증

- `pytest -q` — 556개 통과(§84의 558개에서 고아 테스트 2개 삭제).
- `npx tsc -b`·`npm run build` — 클린.
- `cornerAnalysisTrend`/`corners/trend`/`showSaturday`/
  `forecastRequested`/`predictedImpact`/`plannedHeadcountOption`
  잔여 참조 0건 재확인(문서 언급 제외).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) 홈에 "주간 식수 추이"·"금주 예상 식수 · 점유율 ·
  대기시간" 카드가 없고 "토요일 포함 보기" 버튼도 없음, 스탯타일
  4개(선택한 주의 누적 식수/최근 7일 식수/최고 식수 코너·메뉴/금주
  메뉴 과거 VOE) 정상 표시, 통합 "식수 추이" 차트와 축약된 문구
  정상, 식수 0일 때 재계산 배너가 스탯타일 위에 뜨고 버튼 동작함을
  확인, (2) "메뉴 편성·운영" 탭의 주간 식단표 관리 "전체 예측 비교"
  히트맵이 여전히 정상 동작(점유율/대기시간 백엔드 보존 검증), (3)
  코너별 분석 — 지표 비교에서 그래프 없이 "코너별 분석 — 지표 비교
  (식수 / 만족도 / 피크타임 서브속도)" 카드만 뜨고, 표에 "그린미트"
  컬럼이 없으며(코너명 "그린미트"는 행 데이터로는 정상 표시), 컬럼
  헤더 클릭 시 오름/내림차순 정렬과 화살표(▲/▼) 표시가 정상 동작함을
  스크린샷으로 확인.
- 문서화 후 커밋·푸시.

# §86. VOE 클러스터링 버그 수정 + 규칙 하이라이트 확장 + 코너별 분석 주간평균 + 메뉴 하이라이트 키워드 태그 + 편성빈도 재설계 (2026-08)

## Context

담당자가 5가지를 요청했다: (1) 월간 VOE 클러스터링이 "502 client error
404 not found"를 낸다는 버그 신고, (2) 메뉴편성·운영 탭의 주간 편성
규칙 검증에서 각 규칙을 클릭하면 주간 식단표에 해당 슬롯이 음영
처리되게, (3) 현황(HomePage)의 "코너별 분석 — 지표 비교" 표를
기본적으로 숨기지 말고 처음부터 보이게, "누적 식수" 대신 "주간 평균
식수"(평일 기준 — 주말에 운영 안 하는 코너가 있어서), (4) "메뉴
하이라이트"의 LLM 원인 설명에서 키워드를 태그처럼 뽑아 보여주기,
(5) "편성 빈도 × 성과"가 만족도·VoE 탭의 "메뉴별 분석"과 겹쳐 보이니
편성 주기 자체가 짧은 메뉴 / 나올 때가 됐는데 안 나온 메뉴 위주로
바꿔달라.

## 1. VOE 클러스터링 502/404 버그 — 임베딩 API → LLM 채팅 그룹핑

`backend/app/services/voe_clustering.py`의 `cluster_monthly_voe`가
사내 LLM 게이트웨이의 `POST {base_url}/embeddings`를 호출했는데,
게이트웨이가 그 경로에 404를 돌려주고 `dashboard.py`의
`recompute_voe_clusters`가 그 예외를 502로 감싸 보여준 것이 원인이었다
(`llm_client.py` 자체 주석에도 "임베딩 경로는 아직 실제로 확인된 적
없음"이라고 남아 있었다 — `/chat/completions`만 실사용에서 검증됨).
정확한 임베딩 경로를 확인하려 했으나 담당자도 지금 알 수 없다고 해서,
**임베딩 API 자체를 아예 안 쓰는 방향으로 전환**했다 — 이미 검증된
`chat_complete()` 하나로 LLM이 코멘트를 직접 그룹핑하게 한다(K-means
임베딩 클러스터링 → LLM 직접 그룹핑 요청).

`cluster_monthly_voe`는 이제 그 달 코멘트를 최대 `max_comments=150`개
샘플링해 번호를 매기고, `_build_cluster_prompt`로 "라벨/키워드/
대표코멘트/번호(콤마 분리)" 델리미터 텍스트 형식을 요청하는 프롬프트를
만들어 `chat_complete()`를 한 번 호출한다. `_parse_cluster_response`가
응답을 빈 줄 기준 블록으로 나눠 각 블록을 파싱하고, 번호 목록에서
범위(1~len(sample))를 벗어나거나 숫자가 아닌 토큰은 버린다. 유효한
번호가 하나도 없는 블록은 건너뛰고, 클러스터가 하나도 안 파싱되면
`ValueError`를 던진다(기존 502 감싸기 계약은 그대로 유지 — 실패 원인이
임베딩에서 채팅으로 바뀔 뿐).

`llm_client.py`의 `embed()`/`_mock_embedding()`은 지우지 않았다 —
범용 클라이언트 API로 남겨둔다(이번 문제의 원인은 메서드가 아니라 그
메서드를 부르던 유일한 호출부였다). 대신 `_mock_chat_stream`에 분기를
하나 추가했다 — 프롬프트에 "번호:"와 "대표코멘트:"가 둘 다 있으면(=
클러스터링 프롬프트 형식이면) `_mock_cluster_reply`로 항목 전체를
클러스터 하나로 묶어 파싱 가능한 모의 응답을 만든다. 이게 없으면
사내 LLM 미설정 환경(로컬/이 리포의 테스트 DB)에서 클러스터링이 항상
"파싱 실패"로 죽어, 예전(임베딩+KMeans는 모의 임베딩으로도 항상
성공)보다 오히려 배선 검증이 어려워지는 역행이었다.

## 2. 규칙 하이라이트 — "저조 식수 재편성" 규칙까지 확장

해장/면류/매운(빨간국물) 3개 규칙은 §78에서 이미 클릭 하이라이트가
완전히 구현·검증돼 있었다 — 버그가 아니었다. 4번째 규칙인 "최근 저조
식수(200식 이하) 재편성"만 위반 항목(`LowHeadcountViolation`)이
메뉴 단위로 집계돼 `plan_date`/`corner_id`가 없어 그리드 키를 못
만들었다.

`backend/app/api/analysis.py`의 `weekly_menu_plan_rule_check`에서
`low_headcount_violations` 생성 루프를 확장했다 — 위반으로 판정된
각 (menu_id, menu_name, corner_name)에 대해 이미 가져온 `plan_rows`를
다시 훑어, 같은 menu_id·corner_name·`MenuRole.MAIN`인 행들을
`matches: [{plan_date, corner_id, corner_name, menu_name}]`로 붙인다
(새 쿼리 없음, `_daily_rule_payload`의 `matches`와 같은 shape).

프론트(`AnalysisPage.tsx`, `WeeklyMenuReviewTab`)에서 "최근 저조
식수(200식 이하) 재편성" 라벨 자체를 클릭 가능한 버튼으로 바꿔
`selectRuleMatches(모든 위반의 matches 합침)`을 호출하게 했다(§81에서
만든 토글 메커니즘 그대로 재사용). 위반 목록도 각 매치마다 개별
클릭 버튼(`selectSlot`)으로 바꿔, 개별 슬롯 하나만 골라 하이라이트할
수도 있게 했다.

## 3. 코너별 분석 — 표 항상 표시 + "주간 평균 식수"(평일×5)

**백엔드** — `corner_analysis`의 코너별 결과 dict에 `"day_count":
len({s.stat_date for s in stats})`을 한 줄 추가했다(이미 그 루프
안에서 `stats`를 순회 중이라 새 쿼리 불필요).

**프론트** — `CornerMetricComparisonSection`(`AnalysisPage.tsx`):
`classification` state 기본값을 `"전체"` → `"평일"`로 바꾸고(다른
분류도 SegmentedControl로 계속 볼 수 있음), `showCornerTable` 상태와
"표로 보기"/"표 숨기기" 토글 버튼을 지워 표를 조건 없이 항상
렌더한다. "누적 식수" 컬럼을 "주간 평균 식수"로 바꿨다 — `weeklyAvg =
day_count > 0 ? round(headcount_total / day_count * 5) : null`("이
코너가 평일 페이스를 유지한다면 한 주에 낼 식수" 추정치). 정렬 키의
"headcount" 분기도 이 값 기준으로 바꿨다.

## 4. 메뉴 하이라이트 — LLM 키워드 태그

`backend/app/models/stats.py`의 `LlmAnalysisCache`에 `keywords:
ARRAY(String(64))`(nullable) 컬럼을 추가했다(`MonthlyVoeCluster.keywords`와
동일 패턴, planning_notice는 채우지 않음) — Alembic 마이그레이션
`9a3f7c1e2b6d`.

`llm_analysis.py`의 `_build_menu_trend_prompt`에 "설명 뒤 마지막 줄에
핵심 원인 관련 키워드 2~4개를 '키워드: 키워드1, 키워드2' 형식으로
덧붙이세요(원인을 특정하기 어려우면 생략)"를 추가했다. 새 함수
`_parse_menu_trend_response(response) -> (요약, 키워드)`가 "키워드:"로
시작하는 줄만 분리해 콤마로 쪼개고, 나머지 줄을 요약 본문으로
합친다(`voe_clustering._parse_cluster_response`와 같은 델리미터 텍스트
파싱 스타일). `summarize_menu_trend`의 반환 타입을 `str` →
`tuple[str, list[str]]`로 바꾸고, `_fallback_menu_trend_summary`(미설정
폴백)는 키워드 없이 `[]`를 반환한다. 유일한 호출부인
`refresh_llm_analyses`에서 `summary, keywords = await
summarize_menu_trend(...)`로 받아 `save_analysis(..., keywords=keywords)`로
저장한다. `save_analysis`에 `keywords: list[str] | None = None` 선택
인자를 추가했다(기존 두 호출부 — planning_notice/voe_briefing —는
영향 없음).

`dashboard.py`의 `_trend_cause`가 `cause_keywords: cached.keywords or
[]`도 같이 반환하도록 확장했다. `client.ts`의 `MenuTrendEntry`에
`cause_keywords?: string[]` 추가, `HomePage.tsx`의 `MenuTrendList`가
원인 설명 문단 아래에 작은 pill 스타일 span(`rounded-full border`,
`var(--surface-2)` 배경)으로 키워드를 나열한다. 로컬(LLM 미설정)
환경은 폴백이 항상 빈 키워드를 주므로, 개발 DB에 키워드가 채워진 캐시
행을 수동 삽입해 칩 렌더링 자체를 Playwright로 시각 확인했다.

## 5. 편성 빈도 × 성과 — 편성 주기 짧은 메뉴 + 나올 때 됐는데 안 나온 메뉴

기존 산점도(1회 편성당 식수 × 만족도, 감편/증편/주력/현행 4분류)는
만족도·VoE 탭의 "메뉴별 분석" 4분면(취식 데이터 기준 만족도×수요)과
개념이 겹쳐 보인다는 지적이었다. 완전히 지우고 두 리스트로 교체했다.

**주의**: 이 둘은 `RotationCheckPanel`("재편성 점검" 탭)의 인스턴스
단위 `gap_days`(이번 재편성이 얼마나 일렀나)와는 다른, **메뉴 단위**
질문이다. 특히 "나올 때가 됐는데 안 나온 메뉴"는 `weekly_menu_rotation`의
기존 `items` 루프(조회 기간 안에서 실제로 재편성된 행만 순회)로는
구조적으로 잡을 수 없다 — 그 기간에 아예 재편성이 안 된 메뉴가
대상이라서다.

`backend/app/services/menu_rotation.py`에 순수 함수 2개를 추가했다:

- `rank_by_shortest_cycle(dates_by_corner_menu, *, min_occurrences=2)` —
  `(코너, 메뉴) -> 날짜 목록` 딕셔너리를 받아, 이력이 `min_occurrences`회
  미만인 메뉴(평균 주기 계산 불가)는 빼고 `average_interval_days`
  오름차순으로 `ShortCycleMenu(corner_name, menu_name,
  avg_interval_days, occurrence_count, last_date)` 리스트를 낸다.
- `find_overdue_menus(dates_by_corner_menu, as_of, *, min_occurrences=2,
  ratio=LONG_ABSENT_RATIO)` — 마지막 등장 이후 경과일이 평균 주기 ×
  ratio(기존 `LONG_ABSENT_RATIO=2.0` 재사용)를 넘는 메뉴를
  `OverdueMenu(corner_name, menu_name, avg_interval_days, last_date,
  days_since_last)`로, "얼마나 오래됐는지"(경과일/평균주기) 내림차순
  정렬해 낸다.

`weekly_menu_rotation` 엔드포인트에서 이미 가져온 `all_planned`을
`menu_role == "메인"`으로 필터링해 `main_planned`을 만들고,
`build_corner_menu_dates(main_planned)`로 MAIN 전용
`dates_by_corner_menu_main`을 별도로 빌드한다(부찬·건강가든까지 섞인
기존 `dates_by_corner_menu`와는 별개 — 이 화면은 원래도 MAIN
전용이었다). 응답에 `shortest_cycle_menus`(상위 10개)와
`overdue_menus`를 새 필드로 추가했다(기존 `items`/`overused`는
그대로 — `RotationCheckPanel`이 계속 씀).

프론트 `MenuPlanPerformanceSection`을 `api.menuPlanPerformance` →
`api.weeklyMenuRotation`으로 교체했다. 산점도 ECharts 옵션, 사분면
markArea/markLine, "편성 조정 후보"/"취식 기록 없음" 표는 전부 지우고,
"편성 주기가 짧은 메뉴"와 "나올 때가 됐는데 안 나온 메뉴"(기본
`OVERDUE_PREVIEW_COUNT=12`개 + "전체 보기") 두 개의 단순 표로
교체했다.

**풀스택 고아 정리**: `api.menuPlanPerformance`/`PlanPerformanceRow`/
`PlanPerformanceResponse`/`PlanningAction`(client.ts),
`GET /analysis/menu-plan/performance` 엔드포인트,
`backend/app/services/menu_plan_analytics.py` 전체 파일(`classify_planning_action`/
`median_or_zero`/`DEFAULT_MIN_EVALUATIONS` — grep으로 이 엔드포인트
말고 다른 호출부가 없음을 확인), `tests/test_menu_plan_analytics.py`,
`test_api_ingest_and_analysis.py`의 관련 테스트 5개를 전부 삭제했다.

이 엔드포인트를 지우면서 걸린 교차 참조 하나: `dashboard.py`의
`_collect_planning_facts`(홈 화면 "개선 필요 포인트"의 편성 축)가
`menu_plan_performance`를 호출해 "편성됐지만 취식 기록 0인 메뉴"
목록을 얻고 있었다. 새 헬퍼 `_no_intake_main_menus(db, period_start,
period_end)`를 `dashboard.py`에 추가해 MAIN 역할 편성 메뉴 중 그
기간 취식 기록이 하나도 없는 메뉴를 직접 계산하도록 바꿨다(같은
결과를 얻는 더 가벼운 전용 쿼리 — `menu_plan_performance`가 계산하던
편성횟수/만족도/4분류/매칭진단은 이 축엔 필요 없었다).

## 손대지 않은 것 (교차 확인)

- `RotationCheckPanel`("재편성 점검" 탭)과 그 `items`/`overused` —
  그대로 유지, 새 두 리스트는 별개 필드로만 얹었다.
- 만족도·VoE 탭의 `MenuQuadrantTab`(4분면, 취식 데이터 기준
  만족도×수요) — 변경 없음.
- `llm_client.py`의 `embed()`/`_mock_embedding()`/`chat_stream`/
  `chat_complete` — 그대로 둠, VOE 클러스터링만 이 메서드 호출을 끊음.
- 해장/면류/매운(빨간국물) 3개 규칙의 기존 하이라이트 로직
  (`selectRuleMatches`/그리드 키) — 이미 동작해 재사용만 함.
- `_apply_classification_filter`/`DayClassification`/휴일 서비스 —
  새 분류 개념 추가 없이 재사용만.
- `menu_name.py`의 `pair_likely_same_menu` — `menu_plan_performance`
  삭제로 그 안의 유일한 호출부는 없어졌지만, 자체 유닛 테스트가 있는
  범용 문자열 매칭 유틸리티라 지우지 않음(`embed()`와 같은 성격).

## 테스트

- `backend/tests/test_voe_clustering.py` — chat 기반으로 재작성.
  `_parse_cluster_response`의 범위 밖/숫자 아닌 번호 무시, 빈 그룹
  스킵, 응답 파싱 실패 시 `ValueError`, 502 계약(이제 `chat_complete`
  실패를 모킹)까지 8개 테스트.
- `backend/tests/test_llm_analysis.py` — `summarize_menu_trend`가
  튜플을 반환하도록 갱신, 키워드 줄 파싱/키워드 없는 응답 테스트 추가.
- `backend/tests/test_menu_rotation.py` — `rank_by_shortest_cycle`/
  `find_overdue_menus` 유닛 테스트 6개(단일 이력 제외, 평균 주기·
  최근 편성일 정확성, 오름차순/최다 경과 순 정렬).
- `backend/tests/test_api_ingest_and_analysis.py` — 저조 식수 위반의
  `matches` 필드, `corners` 응답의 `day_count`, `weekly-menu/rotation`
  응답의 `shortest_cycle_menus`/`overdue_menus` 검증 추가, 삭제된
  `menu-plan/performance` 관련 테스트 5개 제거.
- `pytest -q` — 557개 통과.
- `npx tsc -b`·`npm run build` — 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB(`weekly_menu_plan`
  251건, 2026-06-01~08-11) + PostgreSQL(로컬)로 검증(콘솔 에러
  0건): (1) VOE 클러스터링 "이번 달 재계산"이 모의 응답 모드에서도
  502 없이 200으로 성공(`clusters_created: 1`), (2) 저조 식수 재편성
  규칙 라벨 클릭 시 3개 슬롯이 격자에서 동시 하이라이트되고 안내
  문구("3개 슬롯이...")가 뜸(스크린샷 확인), (3) 코너별 분석 표가
  토글 없이 바로 뜨고 기본 분류가 "평일"이며 "주간 평균 식수" 컬럼
  숫자가 그럴듯함(한식 174명/5일×5=174명), (4) 메뉴 하이라이트에
  키워드가 있는 캐시 행을 DB에 수동 삽입해 pill 스타일 태그(`양념`,
  `짠맛`)가 정상 렌더됨을 확인, (5) "편성 빈도 × 성과 — 편성 주기
  점검" 카드에 산점도 대신 "편성 주기가 짧은 메뉴"/"나올 때가 됐는데
  안 나온 메뉴" 두 표가 뜨고, 삭제된 `GET /menu-plan/performance`
  직접 호출 시 404 확인.
- Alembic 마이그레이션(`9a3f7c1e2b6d`)을 로컬 개발 DB에 적용
  확인(`llm_analysis_cache.keywords` 컬럼 생성).

## 검증

- `pytest -q` 전체 회귀(557개 통과).
- `npm run build` 타입체크.
- 위 Playwright 확인.
- 문서화 후 커밋·푸시.

# §88. 주관식 VOE 탭 월별 다중 조회 (기본 최근 3개월) (2026-08)

## Context

담당자 요청: "주관식 VOE 관련 기능을 전부 월별로 볼 수 있게 해주고
기본은 최근 3개월로 보여줘." 조사 결과 대상은
`frontend/src/pages/AnalysisPage.tsx`의 `VoeAnalysisTab`(만족도·VoE
탭의 "주관식 VOE" 영역) 하나였다 — 카드 4개(조회 컨트롤, 월간 VOE
분류, 이달의 VOE AI 브리핑, 월간 VOE 클러스터링)가 전부 단일
`period`(YYYY-MM) state 하나를 공유하며 한 번에 딱 1개월치만
보여줬다(`<input type="month">` 하나로 달을 바꿔가며 순차 조회). 유일한
예외는 클러스터링 카드 맨 아래 "월별 VOE 코멘트 수 추이" 스파크라인
차트뿐인데, 이마저 `VOE_TREND_MONTHS = 6`으로 하드코딩된 참고용
그래프였다.

백엔드 세 GET 엔드포인트(`voe-by-category`/`voe-clusters`/
`voe-briefing`)는 전부 `period: dt.date` 단일값만 받고 여러 달을 한
번에 주는 기능이 없었다. 다만 정확히 같은 패턴으로 여러 달을 병렬
조회하는 선례가 이미 이 파일 안에 있었다 — 클러스터링 카드의 6개월
추이 차트가 `Promise.all(trendMonths.map(m =>
api.voeByCategory(...)))`로 이미 하던 방식이다. 세 엔드포인트 모두
가벼운 조회(그 달 코멘트 스캔 1건 또는 캐시 조회 1건)이고 이미
6개월치 병렬 조회가 실사용 중이었으므로, **백엔드 변경 없이 이 프론트
패턴을 세 카드 전체로 확장**했다 — 새 range 쿼리 파라미터를 만드는
것보다 훨씬 작은 변경이다.

AskUserQuestion으로 두 가지를 확정했다: (1) 개월 수는 사용자가 직접
조절 가능(1/3/6/12개월, 기본 3개월) — 이 파일에 이미 있는
`usePlanPeriod`/`PLAN_PERIOD_OPTIONS`(편성 빈도 섹션의 30일/60일/90일/
6개월 `SegmentedControl`) 패턴 재사용. (2) 재계산 버튼은 달마다 개별
배치 — "전체 재계산" 한 번에 몰아 돌리면 개월 수가 많을 때(6/12개월)
LLM 호출이 순서대로 밀려 오래 걸리므로, 특정 한 달만 다시 계산하고
싶을 때 그 달만 누르게 한다.

## 설계

`VoeAnalysisTab`(`AnalysisPage.tsx`) 하나만 재작성했다. 백엔드·
`client.ts`·다른 컴포넌트는 변경 없음 — 기존 단일월 API 함수
(`api.voeByCategory`/`api.voeClusters`/`api.voeBriefing`/
`api.recomputeVoeByCategory`/`api.recomputeVoeClusters`/
`api.recomputeVoeBriefing`, 전부 `(period: string) => ...`)를 그대로
달 개수만큼 반복 호출한다.

**State**: 단일 `period` → `anchorMonth`(기준월=최신 달, 여전히
`<input type="month">`) + `monthCount`(`"1"|"3"|"6"|"12"`, 기본
`"3"`, 새 `SegmentedControl`)로 분리. 파생값 `months =
Array.from({length: Number(monthCount)}, (_, i) =>
monthsBefore(anchorMonth, i))`(기존 `monthsBefore` 헬퍼 재사용) —
최신 달이 맨 앞, 과거로 갈수록 뒤.

**쿼리**: 기존 3개 단일월 쿼리 + 6개월 트렌드 전용 쿼리
(`monthlyVolumeQuery`, 삭제)를 3개 다중월 쿼리로 교체 —
`voeCategoryMulti`/`voeClustersMulti`/`voeBriefingMulti`, 각각
`queryFn`이 `Promise.all(months.map(m => api.xxx(`${m}-01`)))`로
병렬 호출 후 `{month, data}[]`를 반환한다(`queryKey`는
`months.join(",")`).

**재계산 뮤테이션**: `mutationFn: (month: string) =>
api.recomputeXxx(`${month}-01`)`로 파라미터화. 버튼은
`onClick={() => mutate(month)}`, 로딩 상태는 `isPending &&
variables === month`로 판정해 같은 카드 안 다른 달 버튼과 안
섞이게 했다(react-query 뮤테이션이 마지막 호출 인자를 `.variables`로
노출하는 것을 활용).

**카드별 렌더**: "VOE 분류"/"VOE AI 브리핑"/"VOE 클러스터링"(제목에서
"월간"/"이달의" 접두어 제거 — 이제 여러 달을 보여주므로) 세 카드
모두 `voeXxxMulti.data`를 `.map()`으로 돌며 달마다 소제목
(`formatMonthLabel(month)`, 새 헬퍼, "2026년 8월" 형식) + 그 달
전용 재계산 버튼 + 기존 렌더 로직을 그대로 반복한다. "이달의 VOE
최다 코너/메뉴" 계산 로직은 컴포넌트 본문 인라인이던 것을 순수 헬퍼
`computeTopVoeEntries(categories)`로 추출해 달마다 호출한다.
카테고리 드릴다운 state `selectedVoeCategory`는 `string | null` →
`{month, category} | null`로 바꿔 서로 다른 달 블록의 선택이 안
섞이게 했다.

**트렌드 차트**: 새 쿼리를 만들지 않고 이미
`voeCategoryMulti.data`에 달마다 들어있는 `total_comments`를
그대로 재사용한다(`[...voeCategoryMulti.data].reverse()`로
과거→최신 순으로 뒤집어 X축이 시간순이 되게). 캡션도 "최근
{VOE_TREND_MONTHS}개월" → "선택한 {months.length}개월"로 바꾸고
`VOE_TREND_MONTHS` 상수는 삭제.

## 손대지 않은 것 (교차 확인)

- 백엔드 `voe-by-category`/`voe-clusters`/`voe-briefing`(GET·POST
  재계산 전부) — 시그니처·로직 변경 없음.
- `improvement_points` 엔드포인트의 VOE 축(현재 달 vs 직전 달 고정
  비교) — "개선 필요 포인트" 카드는 이번 "주관식 VOE" 화면과 다른
  화면이라 범위 밖.
- `menu-comments`/`WeeklyMenuVoeDetailPage.tsx`("금주 메뉴 VOE
  상세") — 메뉴별 "최근 N건" 조회이지 달력월 단위 조회가 아니라 이번
  요청과 무관.

## 검증

- 백엔드 변경이 없어 `pytest` 재실행 불필요.
- `npx tsc -b`·`npm run build` — 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) 만족도·VoE 탭 진입 시 기본으로 최근 3개월(2026년
  8/7/6월) 블록이 세 카드 모두에 뜨고, 네트워크 요청이 정확히
  9건(카드 3개 × 3개월) 발생함을 확인, (2) "표시 기간"을 6개월로
  바꾸면 요청이 18건(3×6)으로 늘고 월 소제목이 카드마다 6개씩(총
  18개) 뜸을 확인, (3) 서로 다른 두 달에서 카테고리를 각각 클릭해도
  드릴다운이 안 섞임을 확인, (4) 특정 한 달 "재계산" 클릭이 다른
  달 버튼에 영향 없이 정상 동작, (5) 클러스터링 카드 하단 추이
  차트가 선택한 개월 수만큼(3개월/6개월) 점을 찍고 시간순(과거→
  최신)으로 표시되며 실제 코멘트 수(2026-06:1건, 2026-07:35건,
  2026-08:0건)와 일치함을 확인.

## 검증 요약

- `npm run build` 타입체크.
- 위 Playwright 확인.
- 문서화 후 커밋·푸시.

# §89. 주간 편성 규칙 검증 — 번호 붙은 태그 칩으로 재디자인 (2026-08)

## Context

담당자 신고: "주간식단표 관리에서 주간편성규칙 4개 모두 클릭하면
하이라이트 되게 해줘 지금은 각규칙이 잘 안 드러나는데 규칙1) 이런식으로
태그로 네모낳게 만들고... 지금 최근저조식수만 파란색 밑줄되어잇는데
촌스러움." 조사 결과 4개 규칙(해장/면류/매운(빨간국물)/최근 저조 식수
재편성) 모두 이미 `selectRuleMatches`로 격자 하이라이트가 정상 동작하고
있었다(§78/§81) — 순수 스타일 문제였다. 라벨 버튼이 전부
`underline decoration-dotted` + `color: var(--accent)`(위반 있을 때만)로만
렌더돼, 위반이 없는 주는 그냥 검은 텍스트로 보여 "클릭 가능한 버튼"이라는
게 전혀 안 드러났다.

## 변경

`frontend/src/pages/AnalysisPage.tsx`의 `WeeklyMenuReviewTab`만 수정
(로직·백엔드 변경 없음):

- `isRuleSelected(matches)` — 현재 격자에 하이라이트 중인 슬롯 집합과
  이 규칙의 매치 집합이 완전히 같은지 판정(active 테두리용).
- `renderRuleChip(ruleNumber, label, matches)` — "규칙N) 라벨" 형태의
  사각 태그 버튼. 위반유무는 앞의 점(dot) 색(빨강/초록)으로만 표시하고
  글자는 `var(--ink)`/`var(--ink-muted)` 유지(§39.12 "색은 점에만"
  관례). 선택(active) 상태는 `var(--accent)` 테두리 +
  `var(--surface-2)` 배경(기존 필터 칩 패턴, `AnalysisPage.tsx:3427`
  재사용). 해장/면류/매운(빨간국물) 3개는 `renderDailyRuleRow`가
  이 칩으로 라벨을 교체(규칙번호 인자 추가), 최근 저조 식수는
  4번으로 직접 호출.
- 담당자가 추가로 지적한(작업 중 재검토 요청) 개별 위반 매치 목록의
  파란 밑줄 링크도 같은 이유로 촌스러워 보여, `renderMatchChip(m,
  label, key)`로 함께 교체 — `HomePage.tsx`의 정적 키워드 태그(§86,
  `rounded-full border`)와 같은 모양의 작은 알약 칩, 클릭 시
  `selectSlot` 그대로 호출, 선택된 슬롯만 accent 테두리.
- `selectRuleMatches`/`selectSlot`/`selectedSlotKeys`/격자 하이라이트
  로직은 전혀 안 건드림.

### 추가 수정 — "규칙4만 하이라이트됨" 버그

칩 스타일 재디자인 직후 담당자가 "다른 규칙들도 클릭하면 해당하는
메뉴가 하이라이트 되어야 하는데 규칙4만 그게 적용됨"이라고 재신고했다.
실측 데이터로 원인을 확인했다 — `menu_plan_rules.py`의
`_check_daily`는 `matches`를 "predicate(그 규칙의 조건)를 만족하는
슬롯들"로 채운다. 면류/매운(빨간국물)처럼 **"너무 많음"이 위반**인
규칙은 위반 시 matches가 자연히 그 초과분(실제 면류/매운 메뉴들)으로
채워져 문제없이 하이라이트된다. 하지만 해장(규칙1)은 **"하루에 1개도
없음"이 위반**이라, 위반인 날은 정의상 matches가 항상 빈 배열이다 —
가리킬 "해장 메뉴"가 애초에 없기 때문이다. 실데이터로 확인해 보니
해장 위반은 거의 매주 4~5일씩 발생하는데(요일 배지는 빨갛게 뜸)
`renderRuleChip`의 `hasViolations`가 `matches.length > 0`으로 판정돼
칩은 항상 초록/비활성으로 보이고 클릭도 안 먹었다 — 규칙4(위반 =
저조 식수 메뉴가 실제로 존재)만 우연히 이 문제가 없어 "규칙4만
된다"고 보인 것.

수정: `renderDailyRuleRow`에 `highlightFullDayOnViolation` 옵션을
추가해, 해장 규칙만 위반일 때 그 predicate-matches(항상 빈 배열)
대신 **그날 편성된 모든 코너 슬롯**(이미 컴포넌트가 갖고 있는
`slots`에서 `plan_date`로 필터)을 하이라이트 대상으로 쓴다 — "이
슬롯이 위반이다"가 아니라 "이 날 전체를 보라, 해장 메뉴가 하나도
없다"는 의미로. 위반 매치 칩 목록(개별 메뉴명 나열)은 여전히 실제
predicate-matches만 쓰므로(해장은 항상 빈 배열 → 빈 목록, 정상)
misleading하게 "이게 위반 메뉴다"라고 나열되지 않는다 — 칩 클릭
하이라이트 대상과 아래 표시 목록을 분리했다. 백엔드/API 변경 없음,
프론트 `AnalysisPage.tsx`만 수정.

## 검증

- 백엔드 변경 없어 pytest 불필요.
- `npx tsc -b` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): 4개 규칙 모두 "규칙N)" 사각 태그로 렌더, 위반 있는 주는
  빨간 점, 없는 주는 초록 점 — 위반 0건이어도 박스 형태 유지. 개별
  위반 매치 목록도 더 이상 파란 밑줄 링크가 아니라 작은 테두리 칩으로
  렌더됨을 확인.
- 실측 데이터로 규칙별 위반 발생 빈도를 조회해(2026-06~08 여러 주
  스캔) 해장 규칙이 사실상 매주 위반된다는 것과 그때 matches가
  항상 비어있다는 것을 확인 → 원인 확정.
- `highlightFullDayOnViolation` 적용 후 실제 위반 주(2026-08-03주,
  해장 5일 위반)로 이동해 규칙1 칩이 빨간 점+활성 상태로 바뀌고,
  클릭 시 "12개 슬롯이 격자에서 강조 표시되어 있습니다" 안내와 함께
  그 주 월~금의 실제 편성 슬롯 12개(빈 셀 "-" 제외)가 격자에서
  정확히 하이라이트됨을 스크린샷으로 확인, 재클릭 시 해제도 확인.
  회귀 확인으로 같은 세션에서 규칙2(면류)·규칙4(저조 식수)도 여전히
  정상 동작함을 재확인(각각 5개/3개 슬롯 하이라이트).
- 문서화 후 커밋·푸시.

# §90. 메뉴별 분석 4분면 기본 기준값 고정 + VOE AI 브리핑 카드 순서 (2026-08)

## Context

담당자 요청 두 가지: (1) "만족도·VoE"의 "메뉴별 분석" 4분면 그래프가
지금은 그 기간 데이터의 중앙값을 기준값으로 자동 계산해 보여주는데,
데이터가 바뀔 때마다 기준선이 흔들려 매번 다르게 보인다 — 고정된
사업 기준값(1회 제공당 평균 식수 200식 / 만족도 3.5점)을 기본값으로
써달라는 것. (2) "VOE AI 브리핑" 카드가 지금은 "VOE 분류" 카드
아래(세 번째)에 있는데, 담당자가 가장 먼저 확인하는 정보라 맨 위로
올려달라는 것.

## 변경

**메뉴별 분석 4분면(`MenuQuadrantTab`, `AnalysisPage.tsx`)**: 기존
`autoDemandThreshold`/`autoScoreThreshold`(그 기간 `metrics`의
`median()`)를 지우고, 모듈 상수 `DEFAULT_DEMAND_THRESHOLD = 200`/
`DEFAULT_SCORE_THRESHOLD = 3.5`로 교체했다. 슬라이더의
`demandThresholdOverride`/`scoreThresholdOverride`(사용자가 직접
조절한 값, "초기화"로 되돌림) 메커니즘은 그대로 — "초기화"를 누르면
이제 중앙값이 아니라 이 고정값으로 돌아간다. 슬라이더 상한
(`maxDemand`)에 `DEFAULT_DEMAND_THRESHOLD`를 포함시켜, 실제 데이터의
최대 수요가 200명 미만이어도 슬라이더 트랙이 기본값을 못 담는 일이
없게 했다. 카드 안내 문구도 "중앙값" 언급을 지우고 "기본 3.5점"/
"기본 200명"으로 명시했다. `median()` 헬퍼 함수 자체는 다른 곳
(피크타임 대기시간 계산)이 계속 쓰므로 그대로 둔다.

**VOE AI 브리핑 카드 순서(`VoeAnalysisTab`)**: "주관식 VOE"(기준월·
표시 기간 컨트롤 카드) 바로 다음, "VOE 분류"/"VOE 클러스터링"보다
앞으로 옮겼다 — 최종 순서: 주관식 VOE(컨트롤) → **VOE AI 브리핑** →
VOE 분류 → VOE 클러스터링. 카드 내부 로직(쿼리·재계산 뮤테이션·JSX)은
전혀 안 건드리고 JSX 블록 위치만 옮겼다.

## 검증

- `npx tsc -b` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): 메뉴별 분석 슬라이더가 기본으로 "200.0명"/"3.50점"을
  보여주는지, 안내 문구가 "기본 3.5점"/"기본 200명"으로 바뀌었는지,
  "만족도·VoE" 탭에서 카드 순서가 주관식 VOE → VOE AI 브리핑 → VOE
  분류 → VOE 클러스터링인지 스크린샷으로 확인.
- 문서화 후 커밋·푸시.

## 추가 수정 — 메뉴별 분석 4분면을 중식 전용으로 고정 (같은 날)

담당자가 이어서 "메뉴별 분석 사분면은 중식만 보여줘"라고 요청했다.
`MenuQuadrantTab`은 원래 전체/조식/중식/석식 4개 탭(`mealTypeFilter`
state)을 지원했다 — "전체"는 사전에 배치로 계산해 캐시해 둔
`MenuPerformanceStats`(`api.menuPerformance`, "재계산" 버튼으로
`api.recomputeMenuPerformance` 수동 트리거)를 읽고, 조식/중식/석식은
그 자리에서 계산하는 `api.menuPerformanceByMealType`을 썼다.

이번 요청으로 `mealTypeFilter` state와 그 `SegmentedControl`, "전체"
전용 "재계산" 버튼을 전부 지우고, `query`가 항상
`api.menuPerformanceByMealType({ ..., meal_type: "중식" })`만 호출하도록
고정했다. 카드 안내 문구 맨 앞에 "중식 기준."을 추가해 §76(날씨유형
랭킹 중식 고정)과 같은 톤으로 범위를 명시했다.

**남겨둔 것**: `api.menuPerformance`/`api.recomputeMenuPerformance`
(client.ts)와 백엔드 `GET /analysis/menu-performance`/
`POST /analysis/menu-performance/recompute` 엔드포인트는 지우지
않았다 — 이 화면에서만 안 쓰이게 됐을 뿐(grep으로 프론트 전체에서
다른 호출부가 없음을 확인했지만), 그 기반 캐시 테이블
(`MenuPerformanceStats`)과 이를 채우는 `aggregate_menu_performance`
함수 자체는 `scheduler.py`의 새벽 배치가 계속 쓰고
`weekly_menu_prediction.py`/`simulation.py`/`dashboard.py`도 그
테이블을 읽는다 — 엔드포인트 삭제는 이번 요청 범위 밖의 더 큰
변경이라 다음 정리 라운드로 남겨둔다.

### 검증

- `npx tsc -b` 클린.
- Playwright: 카드 안내 문구가 "중식 기준."으로 시작하는지, 전체/
  조식/석식 선택 버튼이 더 이상 안 보이는지, 네트워크 탭에서
  `menu-performance/by-meal-type?...&meal_type=%EC%A4%91%EC%8B%9D`
  요청 1건만 나가는지 확인(콘솔 에러 0건).
- 문서화 후 커밋·푸시.

# §91. 코너별 조식/중식/석식 식수 현황 표(홈) + 코너 등장 순서 전역 고정 (2026-08)

## Context

담당자가 실제 운영 리포트 스크린샷(코너별 조식/중식/석식 식수 현황 —
Take In 7개 코너를 도담찌개/고슬고슬비빈/싱푸차이나/모던키친/동방식객/
한식사계/스냅스낵 순으로 나열, 이어서 Take Out/소계/합계, 끼니별로
메뉴·수량·식수율 3열씩)을 보여주며 두 가지를 요청했다: "스크린샷 형태로
현황에 나타나게 해주고 모든 기능내 코너 등장 순번을 저 순서대로 해줘."
`AskUserQuestion`으로 두 가지를 확정했다 — (1) 고정 순서를 "코너
목록/필터/차트 색상" 같은 순수 나열 자리뿐 아니라 식수순 등 다른 기준으로
정렬하던 곳까지 **모든 곳 공통 기준**으로 적용, (2) 스크린샷에 없는
코너(그린미트·미캠회관(전골)·테스트코너 등)는 맨 뒤에 기존 순서(corner_id
오름차순)대로.

조사 결과 코너 순서를 매기는 자리가 백엔드 7곳 + `simulation.py` 2곳 +
프론트 3곳, 총 11곳이 서로 다른 독립 구현(일부는 알파벳순, 일부는
corner_id순, 일부는 아예 무순서)이었다. "모든 곳 공통 기준"을 문자
그대로 적용하면 이미 다른 기준(식수 desc, core_employee_count desc 등)
으로 랭킹하는 화면들의 목적이 훼손된다 — 그래서 원칙을 이렇게 나눴다:
**순수 나열(코너 목록/필터/차트 색상 배정) 자리는 새 고정 순서를 1차
정렬 키로**, **이미 다른 지표로 랭킹하는 자리는 그 지표를 1차로 유지하고
새 고정 순서를 동점 처리(tiebreak)로만** 추가한다 — 랭킹 화면 자체의
의미는 안 바꾸면서 "같은 순위끼리는 항상 같은 순서로 보인다"는 일관성만
더한다.

스크린샷의 7개 코너 이름은 이 세션 샌드박스 DB에 전혀 없다(샌드박스는
한식/그린미트/일품/분식/양식/… 같은 자리표시용 이름을 쓴다) — 실제
운영 코너 이름 그대로 구현하고, 순서 정확성은 시드 데이터를 넣은
pytest(`test_corner_aliases.py`)로 검증했다. Playwright는 이 샌드박스로
표의 **구조·계산식·Take Out 격리**만 실제 데이터로 확인했다(정확한
"도담찌개가 맨 앞" 시각적 확인은 이름이 일치하는 코너가 없어 불가능).

## 설계

### 1. 코너 고정 순서 — `corner_aliases.py`에 단일 소스 추가

새 DB 컬럼/마이그레이션 없이 순수 파이썬 상수로 뒀다(코너 집합이 자주
안 바뀌어 마이그레이션+시드 비용이 안 맞음):

```python
# backend/app/services/corner_aliases.py
CORNER_DISPLAY_ORDER: tuple[str, ...] = (
    "도담찌개", "고슬고슬비빈", "싱푸차이나", "모던키친",
    "동방식객", "한식사계", SNAP_SNACK_CORNER_NAME, TAKE_OUT_CORNER_NAME,
)

def corner_display_sort_key(corner_id: int, corner_name: str) -> tuple[int, int]:
    """목록에 있으면 그 순번, 없으면 목록 길이(=항상 뒤) — 목록 밖 코너끼리는
    corner_id 오름차순으로 2차 정렬. 이미 다른 기준(식수 desc 등)으로 랭킹하는
    화면은 그 기준을 1차로 유지하고 이 키는 tiebreak로만 쓴다."""
    try:
        rank = CORNER_DISPLAY_ORDER.index(corner_name)
    except ValueError:
        rank = len(CORNER_DISPLAY_ORDER)
    return (rank, corner_id)
```

### 2. 11개 호출부에 적용

**백엔드 `analysis.py`** — 7곳:
- `corner_analysis`(`/corners`): 식수 desc 유지, `corner_display_sort_key`를
  3차(그린미트류 배치 다음) tiebreak로 추가.
- `corner_list`(`/corners/list`): corner_id 정렬 → `corner_display_sort_key`
  정렬로 완전 교체(1차 키) — 이 목록이 프론트 코너 필터/차트 색상 배정의
  사실상 유일한 출처라, 여기만 바꾸면 그 화면들도 새 순서를 물려받는다.
- `corner_main_menu_by_date`(`/corners/main-menu-by-date`): 원래 정렬이
  아예 없었음 — `(plan_date, corner_display_sort_key)`로 추가.
- `corner_core_layer_summary`: `core_employee_count` desc 유지,
  `corner_display_sort_key`를 tiebreak로 추가.
- `headcount_trend`(`group_by="corner"`): 기존 정렬이 `series_key`
  (문자열 corner_id)의 사전식 비교라 "10" < "2"인 잠재 버그가 있었음 —
  `corner_display_sort_key`로 교체하며 같이 고쳤다.
- `weekly_menu_combination_check`/`weekly_menu_rotation`: 각각 클래시
  개수/플래그 순서 유지, `corner_name` 알파벳 tiebreak를
  `corner_display_sort_key` tiebreak로 교체.

**백엔드 `simulation.py`** — 2곳(`what_if`, `_forecast_corners`): 둘 다
`db.query(CornerMaster).all()`(무순서)를 `corner_display_sort_key`로
정렬해 반환 — 코너별 예측 막대그래프의 응답 배열 순서가 그대로 UI
나열 순서로 쓰이는 화면이라 정렬 자체가 필요했다.

**프론트 `AnalysisPage.tsx`** — 3곳: `CornerMetricComparisonSection`의
"코너" 컬럼 정렬(알파벳 → `corner_list` 응답 위치를 랭크로 쓰는
`cornerRank` Map), `WeeklyMenuReviewTab`의 격자 행 순서와 차트 색상
배정(`cornerColor`)도 같은 `cornerRank` 기반으로 통일.

**의도적으로 안 건드림**: `weekly_menu_prediction.py`의 코너 순회는
`dict[corner_id, float]` 룩업 테이블을 만들 뿐 화면에 순서 그대로
노출되지 않아 영향이 없다. `WeatherScenarioForecastSection`의 코너별
예측 막대는 `predicted_headcount`(연속값) desc라 동점이 사실상 안
나서 tiebreak 추가 비용(별도 `corner-list` fetch)이 안 맞다고 판단해
생략했다.

### 3. 신규 — `GET /analysis/corners/meal-type-headcount`

`backend/app/api/analysis.py`, `corner_list` 바로 다음에 추가. 스크린샷
표를 그대로 재현하는 단일 날짜(`target_date`) 스냅샷:

```python
@router.get("/corners/meal-type-headcount")
def corner_meal_type_headcount(target_date: dt.date, db: Session = Depends(get_db)):
```

- **데이터 소스**: `daily_corner_stats`(나이트 배치)가 아니라 `meal_log`를
  그때그때 GROUP BY — `headcount_trend`와 같은 이유(배치를 기다리지
  않고 "오늘" 스냅샷도 봐야 함, §22/§45의 배치 미갱신 교훈 재적용).
- **메뉴 열**: `WeeklyMenuPlan.menu_role == MAIN`을 그 날짜·코너·끼니로
  조인해 채운다(없으면 `null`).
- **식수율**: `compute_share_of_traffic`(기존 순수함수, 그대로 재사용) —
  분모는 그 끼니의 **전체 합계(Take Out 포함)**. 스크린샷 수치로 역산
  검증됨(도담찌개 조식 78/2094=3.7%, Take Out 1963/2094=93.7% 일치).
- **응답 구조**: `take_in`(Take Out 제외, `corner_display_sort_key` 순),
  `take_out`(단일 행, 분리), `subtotal`(Take In만 합산),
  `total`(Take Out까지 포함 — 항상 식수율 100%).
- Take Out 코너 판별은 기존 `TAKE_OUT_CORNER_NAME` 상수 재사용(별칭
  병합은 이미 ingest 단계에서 끝나 있음, `corner_aliases.py`).

**`client.ts`**: `CornerMealTypeHeadcountRow`/`MealTypeHeadcountCell`/
`MealTypeHeadcountBucket`/`CornerMealTypeHeadcountResponse` 타입과
`api.cornerMealTypeHeadcount({ target_date })` 함수 추가.

**`HomePage.tsx`**: 새 컴포넌트 없이 `HomePage` 본문에 직접
`Card title="코너별 조식/중식/석식 식수 현황"`로 추가(식수 추이 카드
다음, 코너별 지표 비교 카드 앞). 이 파일에 그루핑된 2행 `<thead>`
전례가 없어(`Table` 컴포넌트는 flat 컬럼만 지원) 손수 만든 `<table>`로
구현 — 1행은 `colSpan=3`으로 조식/중식/석식 그룹, 2행은 메뉴/수량/
식수율. Take In 행들 → Take Out 행(배경 강조) → 소계 → 합계 순.
날짜 입력(`<input type="date">`, `max`를 오늘로 제한)으로 스냅샷 날짜를
고른다 — 페이지 상단의 "선택한 주" 네비게이터와는 완전히 독립된
state(`mealTypeHeadcountDate`)다(우연히 같은 `type="date"` 셀렉터라
Playwright 스크립트가 처음에 서로 다른 입력을 헷갈렸을 만큼 시각적으로
비슷하니, 컴포넌트를 더 추가할 땐 `aria-label`/구조로 구분할 것).

## 손대지 않은 것 (교차 확인)

- `weekly_menu_prediction.py`의 코너 순회(딕셔너리 룩업 전용) — 순서
  무관, 미적용.
- `WeatherScenarioForecastSection`의 코너별 예측 막대 — 연속값 desc라
  tiebreak 비용 대비 효과가 낮아 미적용.
- 그 외 8개(백/프론트 각각) 적용 지점의 기존 1차 정렬 기준(식수 desc,
  core_employee_count desc, 클래시 개수 desc 등) — 전부 그대로 유지,
  이번 변경은 tiebreak만 추가.

## 테스트

- `backend/tests/test_corner_aliases.py`(신규): `corner_display_sort_key`
  유닛 테스트 — 목록 안 코너 순번, 목록 밖 코너는 뒤로, 목록 밖끼리는
  corner_id 순, 혼합 집합 end-to-end 정렬.
- `backend/tests/test_api_ingest_and_analysis.py`:
  `test_corner_meal_type_headcount_matches_report_layout` — 한식/도담찌개/
  Take Out 3개 코너에 중식 식수를 시딩해 식수율(분모=끼니 합계, Take Out
  포함) 계산, Take In/Out 분리, 소계(Take In만)/합계(Take Out 포함) 차이,
  고정 순서(도담찌개가 한식보다 먼저) 전부 검증.
- `pytest -q` 전체 회귀 — 562개 전부 통과(기존 557 + 신규 5).
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔 에러
  0건): 새 표가 그루핑된 헤더(조식/중식/석식 → 메뉴/수량/식수율)로
  렌더되는지, 날짜를 바꾸면(2026-08-01) 실제 데이터(한식 제육볶음
  20명·50%, 그린미트 9명·22.5%, 일품 11명·27.5%, 소계=합계=40명·100%,
  이 샌드박스엔 그날 Take Out 기록이 없어 0으로 표시)가 정확히 반영
  되는지 확인 — 표 구조·계산식·Take Out 격리(있었다면 소계에서
  제외됐을 것)는 실증됐고, "도담찌개가 맨 앞" 순서 자체는 이 샌드박스에
  이름이 일치하는 코너가 없어 위 pytest로 대체 검증했다.

## 검증

- `pytest -q` 전체 회귀(562개 통과).
- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인.
- 문서화(§91) 후 커밋·푸시.

# §92. 홈 상단 스탯타일 4개 교체 — 금일 식수/맛평가 + 금주 VOE + 편성 규칙 이상 여부 (2026-08)

## Context

담당자 요청(원문): "현황 4개 카드에 금일식수(일주일간일평균식수) 금일맛평가점수
(일주일간 일평균점수) 금주 메뉴과거 VoE 금주 메뉴 편성 규칙 이상 여부 이거로
바꿔줘." 기존 4개 스탯타일(선택한 주의 누적 식수 / 최근 7일 식수 / 최고 식수
코너·메뉴 / 금주 메뉴 과거 VOE) 중 "금주 메뉴 과거 VOE"만 그대로 남기고
나머지 셋을 교체한다.

"금일 식수"/"금일 맛평가 점수"는 **오늘** 값이 필요한데, 기존
`daily_corner_stats`(나이트 배치)는 어제까지만 채워져 있어(§22/§45/§91에서
반복 확인된 문제) 그대로 쓰면 항상 0/공백으로 보인다 — `headcount_trend`가
이미 같은 이유로 meal_log를 그때그때 집계하는 방식을 쓰고 있어, 이번에도
같은 패턴을 새 전용 엔드포인트에 적용한다.

"최고 식수 코너/메뉴" 타일이 빠지면서, 그 타일 전용이었던
`weekly_menu_planned_headcount_ranking`(§80에서 추가, 이번 주 편성된
MAIN 슬롯을 실측 평균 식수로 랭킹) 엔드포인트가 프론트 전체에서 완전히
고아가 됐다(grep으로 다른 소비처 없음 확인) — §82/§85 원칙대로 백엔드
엔드포인트·`client.ts` 타입/함수·프론트 쿼리까지 전부 같이 삭제했다.

"금주 메뉴 편성 규칙 이상 여부"는 새 계산을 만들지 않고, "메뉴 편성·운영"
탭의 규칙검증 패널이 이미 쓰는 `GET /analysis/weekly-menu/plan-rule-check`
(§77~§78에서 만든 해장/면류/매운맛 요일별 판정 + 저조 식수 재편성 판정)를
선택한 주로 그대로 호출해, 위반 건수만 합산해서 요약한다.

## 설계

### 1. 백엔드 — `GET /analysis/home-daily-summary` 신규

`backend/app/api/analysis.py`, `headcount_trend` 바로 다음에 추가:

```python
@router.get("/home-daily-summary")
def home_daily_summary(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """홈 "금일 식수"/"금일 맛평가 점수" 스탯타일 전용 — headcount_trend와
    같은 이유로 daily_corner_stats(나이트 배치) 대신 meal_log를 그때그때
    집계한다."""
```

기간 내 `meal_log`를 `func.date(eaten_at)`로 그루핑해 날짜별 headcount(행
개수)와 `avg_taste_score`(`TASTE_SCORE_POINTS` 환산 평균, 평가 없는 날은
`None`)를 계산하고, 요청한 기간의 모든 날짜(데이터 없는 날 포함, headcount=0/
avg_taste_score=None)를 순서대로 반환한다.

### 2. 백엔드 — 고아가 된 엔드포인트 삭제

`weekly_menu_planned_headcount_ranking`(`GET
/weekly-menu/planned-headcount-ranking`) 함수 전체를 삭제. 이 엔드포인트가
쓰던 `_recent_avg_headcount_by_menu`/`_HISTORY_WINDOW_DAYS`는 다른 3곳
(`weekly_menu_plan_rule_check`의 `low_headcount_reuse`, `menu_plan_performance`
등)에서 계속 쓰여 그대로 둔다 — 엔드포인트 함수만 고아였다.

### 3. `client.ts`

`HomeDailySummaryDay`(`date`/`headcount`/`avg_taste_score`) 타입 +
`api.homeDailySummary({period_start, period_end})` 추가. `PlannedHeadcountRankingRow`/
`WeeklyMenuPlannedHeadcountRankingResponse` 타입과 `weeklyMenuPlannedHeadcountRanking`
함수는 삭제(고아).

### 4. `HomePage.tsx`

- `plannedHeadcountRanking` 쿼리와 그 파생값(`plannedHeadcountRows`/
  `plannedHeadcountBars`/`topPlannedHeadcountRow`) 전부 삭제 — "최고 식수
  코너/메뉴" 타일이 유일한 소비자였다.
- `recentHeadcountQuery`(배치 기반 `api.weeklySummary`)를
  `homeDailySummaryQuery`(`api.homeDailySummary`, 트레일링 7일 = 오늘 포함
  최근 7일)로 교체. 오늘 값은 `homeDailySummaryDays.find(d => d.date ===
  isoDaysAgo(0))`로 뽑고, 일평균은 7일 평균(headcount)과 평가가 있었던
  날만의 평균(avg_taste_score)을 따로 낸다 — 평가 자체가 없는 날까지
  0으로 넣으면 점수가 왜곡된다.
- `weeklyRuleCheckQuery`(`api.weeklyMenuPlanRuleCheck({period_start:
  selectedMonday, period_end: saturdayOfSelected})`) 신규 — 이미 "메뉴
  편성·운영" 탭이 쓰는 것과 동일한 엔드포인트를 홈에서도 같은 주로
  호출한다. 위반 건수(`ruleViolationCount`) = 해장/면류/매운맛 3개
  배열의 `ok===false`인 날 개수 합 + `low_headcount_reuse.violations`
  길이.
- 스탯타일 4개 최종 구성: **금일 식수**(값=오늘 headcount, sub=최근 7일
  일평균) → **금일 맛평가 점수**(값=오늘 avg_taste_score, sub=최근 7일
  일평균 점수, 평가 없으면 "-"/"최근 7일 평가 없음") → **금주 메뉴 과거
  VOE**(기존 그대로, 클릭 시 `onOpenWeeklyVoe`) → **금주 메뉴 편성 규칙
  이상 여부**(위반 0건이면 "이상 없음"+`tone="good"`, 있으면 "이상 N건"+
  `tone="critical"`).
- `weekly` 쿼리와 `totalHeadcount`는 삭제하지 않았다 — "이 기간 식수가
  0으로 나옵니다" 배치 재계산 배너(§85)가 여전히 그 값을 쓴다.

## 손대지 않은 것 (교차 확인)

- `weekly`/`totalHeadcount`/`recomputeDailyStats` — 배치 재계산 배너가
  계속 씀.
- `weeklyVoeHistory`/`onOpenWeeklyVoe` — "금주 메뉴 과거 VOE" 타일 로직
  자체는 무변경.
- `_recent_avg_headcount_by_menu`/`_HISTORY_WINDOW_DAYS` — 다른 3개
  호출부가 계속 씀, 삭제 안 함.
- `GET /analysis/weekly-menu/plan-rule-check`와 그 백엔드 로직
  (`menu_plan_rules.py`) — 로직 변경 없음, 홈에서 같은 엔드포인트를
  한 번 더 호출할 뿐.

## 테스트

- `backend/tests/test_api_ingest_and_analysis.py::test_home_daily_summary_computes_live_headcount_and_avg_taste_score`
  (신규) — 이틀치 취식 로그(맛남/보통/개선 혼합)를 시딩해 날짜별
  headcount·평균 점수가 정확한지, 데이터 없는 날은 `headcount=0`/
  `avg_taste_score=None`인지 확인.
- `pytest -q` 전체 회귀 — 563개 통과(기존 562 + 신규 1). 삭제한
  `weekly_menu_planned_headcount_ranking`을 직접 때리는 기존 테스트는
  없어 회귀 감소 없음.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): 홈 상단 4개 타일이 "금일 식수"/"금일 맛평가 점수"/"금주
  메뉴 과거 VOE"/"금주 메뉴 편성 규칙 이상 여부" 순으로 뜨는지,
  "금일 맛평가 점수" sub에 최근 7일 일평균이 보이는지, "금주 메뉴 편성
  규칙 이상 여부" 타일의 건수가 `GET /weekly-menu/plan-rule-check`
  응답(해장 0 + 면류 1 + 매운맛 0 + 저조식수 3 = 4건)과 정확히 일치하고
  `tone="critical"`(빨간 좌측 테두리)로 뜨는지 확인.

## 검증

- `pytest -q` 전체 회귀(563개 통과).
- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인.
- 문서화(§92) 후 커밋·푸시.

# §93. 총식수 꺾은선 필터 무관화 + 코너별 분석 지표 비교 재정리(주 선택 + 일평균) (2026-08)

## Context

담당자 요청 두 가지: (1) "총식수 꺾은선 그래프는 토글이 안 켜져있어도 전체
식수기반으로 보여줘" — §91에서 추가한 홈 "식수 추이" 차트의 "총식수" 꺾은선이
지금은 코너 필터/회사구분/끼니 체크박스(토글)로 걸러진 `trendRows`를 그대로
합산해서 그리고 있어, 코너 필터가 기본값(§81의 7개 프리셋)만 켜진 상태에서는
실제 전체 식수보다 적게 나온다. (2) "코너별 분석 지표보고에서 전체/평일/
주말공휴일/패밀리데이 식수를 다시 정리해줘, 어떤 주간의 평균 식수인지 사용자가
정할 수 있게 해줘" — `CornerMetricComparisonSection`의 "주간 평균 식수" 컬럼이
§86에서 "평일 하루 평균 × 5"로 만든 추정 공식인데, 이 ×5는 평일 분류에만
말이 되는 계산이라 주말+공휴일/패밀리데이/전체를 고르면 숫자가 왜곡된다.
게다가 조회 기간이 고정 180일(`PERIOD_START`~`PERIOD_END`)이라 "어떤 주"의
평균인지 사용자가 고를 수 없었다.

## 설계

### 1. 홈 "총식수" 꺾은선 — 무필터 전용 쿼리로 분리

`frontend/src/pages/HomePage.tsx`: 기존에는 `totalHeadcountByPeriod`를
필터가 걸린 `trendRows`에서 그대로 합산했다. 이제 `headcountTrend`(필터
있음, 막대용)와 별개로 `totalHeadcountTrend`(무필터, 꺾은선 전용) 쿼리를
새로 추가한다:

```ts
const totalHeadcountTrend = useQuery({
  queryKey: ["headcount-trend-total", trendPeriodStart, trendPeriodEnd, trendGranularity],
  queryFn: () =>
    api.headcountTrend({
      period_start: trendPeriodStart,
      period_end: trendPeriodEnd,
      granularity: trendGranularity,
      group_by: "total",
    }),
});
```

`meal_types`/`corner_ids`/`divisions`/`classification` 전부 안 넘긴다 —
백엔드 `headcount_trend`는 이 파라미터들이 없으면 전체를 합산해서 준다
(기존 로직 그대로, 새 백엔드 변경 없음). `totalHeadcountByPeriod` map을
이 쿼리 결과로 채우고, "총식수" 꺾은선과 "최근 N일 평균" 뱃지 둘 다 이
값을 쓴다 — 코너 필터를 껐다 켜도, 끼니 체크박스를 조절해도 더 이상
흔들리지 않는다.

**부수 확인**: 백엔드 `GET /analysis/headcount-trend`는 이미 이 파라미터들을
전부 optional로 받고 있어(§91 이전부터) 코드 변경이 필요 없었다 — 프론트
쿼리 호출부만 하나 늘었다.

### 2. `CornerMetricComparisonSection` — 주 선택 + 일평균으로 재정리

`frontend/src/pages/AnalysisPage.tsx`: 조회 기간을 고정 180일에서 사용자가
고르는 한 주(월~토, 이 앱의 "일요일 미운영" 관례)로 바꾼다:

```ts
const [weekMonday, setWeekMonday] = useState(() => weeklyMondayOf(new Date()));
const weekSaturday = weeklyAddDays(weekMonday, 5);
```

`◀ 이전 주` / `<input type="date">` / `다음 주 ▶` 네비게이터를
`HomePage.tsx`의 기존 주 선택 패턴과 동일하게 추가하고, `api.cornerAnalysis`
호출의 `period_start`/`period_end`를 이 값으로 바꾼다. "누적 식수 ×5"
공식(§86)을 지우고, 순수 일평균으로 교체한다:

```ts
const avgHeadcount = (row: CornerAnalysisRow) =>
  row.day_count > 0 ? Math.round(row.headcount_total / row.day_count) : null;
```

`day_count`는 이미 선택한 주·분류(전체/평일/주말+공휴일/패밀리데이)로
필터된 뒤의 실제 배치일수이므로, 분류가 뭐든 "그 분류에 해당하는 날짜의
하루 평균 식수"로 일관되게 해석된다(평일 분류만 정확하고 나머지는 틀리던
문제 해소). 컬럼 라벨을 "주간 평균 식수" → "일평균 식수"로 바꾸고, 캡션에
현재 조회 중인 주 범위와 "선택한 분류에 해당하는 날짜의 일평균"이라는
설명을 추가했다.

### 3. 부수 수정 — `StatTile`의 `borderLeftColor`/`borderColor` 콘솔 경고 제거

Playwright 검증 중 "금주 메뉴 편성 규칙 이상 여부" 타일(§92, tone이 로딩
중 `undefined`였다가 나중에 `"critical"`/`"good"`으로 바뀜)에서 React가
"don't mix shorthand and non-shorthand properties" 콘솔 경고를 내는 걸
발견했다 — `ui.tsx`의 `StatTile`이 `borderLeftColor`/`borderLeftWidth`를
`tone` 유무에 따라 스프레드로 껐다 켰다 해서, 렌더마다 그 스타일 키
자체가 있다가 없다가 했기 때문(shorthand `borderColor`와 longhand
`borderLeftColor`를 같이 쓰면서 후자가 렌더마다 사라짐/생김을 반복하면
React가 경고한다). `borderLeftColor: toneColor ?? "var(--border)"`,
`borderLeftWidth: toneColor ? 3 : 1`로 항상 같은 키를 넣도록 고쳐
해결했다 — 이 컴포넌트를 쓰는 다른 모든 화면(타일 전반)에 공통 적용되는
수정이라 부수적으로 콘솔이 깨끗해졌다.

## 손대지 않은 것 (교차 확인)

- `GET /analysis/headcount-trend` 백엔드 로직 — 무변경, 프론트가 파라미터
  없이 한 번 더 부르는 것뿐.
- `GET /analysis/corners`(`corner_analysis`) 백엔드 로직 — 무변경, 프론트가
  기간 파라미터만 다르게 넘긴다.
- `HomePage.tsx`의 "선택한 주"(`selectedMonday`) 네비게이터 — 독립 상태,
  `CornerMetricComparisonSection`의 `weekMonday`와 서로 안 얽힌다.
- 코너 필터/회사구분/끼니 체크박스와 그 토글 로직 자체 — 막대(분해) 쪽엔
  그대로 적용, 총식수 꺾은선만 분리했다.

## 테스트

- 백엔드 변경 없음 — `pytest -q` 재실행 불필요(회귀 확인 차원에서
  563개 재실행, 전부 통과).
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔 에러
  0건): (1) 홈 "식수 추이" 네트워크 탭에 `group_by=total`이면서
  `corner_ids`/`meal_types`/`divisions` 파라미터가 전혀 없는 요청이 별도로
  나가는지 확인(막대용 필터 요청과 분리됐는지), (2) `CornerMetricComparisonSection`
  에서 "이전 주"/"다음 주"/날짜 입력을 조작하면 `GET /analysis/corners`
  요청의 `period_start`/`period_end`가 정확히 그 주(월~토)로 바뀌는지,
  분류 탭을 바꾸면 `classification` 파라미터가 정확히 바뀌는지, (3) 실제
  데이터가 있는 주(2026-07-27)로 이동하면 "일평균 식수" 컬럼이
  `headcount_total / day_count`(반올림) 그대로인지 API 응답과 대조 확인
  (한식 194/6일 → 32, 이전 ×5 공식이면 162로 나왔을 자리), (4) StatTile
  콘솔 경고가 더 이상 안 뜨는지.

## 검증

- `pytest -q` 전체 회귀(563개 통과, 백엔드 변경 없음).
- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인.
- 문서화(§93) 후 커밋·푸시.

# §94. 코너별 분석 "전체 < 평일" 문의 — 계산 오류 아님, 안내 문구 추가 (2026-08)

## Context

담당자 신고: "코너별분석에서 지표 비교 할 때 전체 식수가 평일보다 낮음
오류 발샌." §93 직후 "일평균 식수" 컬럼을 실제 데이터로 대조 확인했다 —
2026-07-27주(월~토) 한식 코너: 평일 174명/5일=34.8→**35**, 전체
194명/6일=32.33→**32**. 코드를 다시 읽어 확인한 결과 **계산 버그가
아니다** — `corner_analysis`(`analysis.py`)의 "전체"는 `classification`
필터를 아예 안 걸어(184-194행 `_apply_classification_filter`) 그 주에
있는 **모든** `daily_corner_stats` 행(월~토 6일, 토요일 포함)을 그대로
평균 내고, "평일"은 `is_holiday=False`인 5일만 골라 평균 낸다. 이 주
토요일 한식 코너 식수는 194-174=20명으로 평일 평균(34.8)보다 훨씬 적어,
그 낮은 하루가 "전체" 평균에 섞여 들어가면서 평일 평균보다 낮아진 것 —
가중평균에 값이 작은 항목이 섞이면 전체 평균이 내려가는 건 산수적으로
당연한 결과다. 이 앱은 카페테리아가 월~토 6일 운영하지만(§72 이후 여러
곳에서 확인된 관례), **분류 체계 자체는 토요일을 "주말"로 취급**한다
(`is_weekend`가 ISO 요일 6/7을 휴일로 봄, `holidays.py`) — 운영일과
분류 체계가 다르다는 게 원래부터 있던 설계이고, 이번 §93에서 "전체" 컬럼을
평일에만 맞던 ×5 공식에서 순수 일평균으로 바꾸면서 이 차이가 숫자로
분명하게 드러난 것뿐이다.

## 조치 — 코드 수정 없음, 화면에 안내 문구만 추가

계산 자체를 바꿀 이유가 없다("전체"가 평일보다 낮게 나오는 게 실제
사실을 정확히 반영한 것) — 대신 이 결과가 왜 나오는지 화면에서 바로
알 수 있게 안내 문구를 추가했다.

`frontend/src/pages/AnalysisPage.tsx`의 `CornerMetricComparisonSection`,
기존 캡션("{weekMonday} ~ {weekSaturday} 중 선택한 분류에 해당하는
날짜의 일평균입니다") 아래에 `classification === "전체"`일 때만 보이는
문구를 추가한다:

```tsx
{classification === "전체" && (
  <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
    토요일·공휴일처럼 식수가 적은 날도 함께 평균에 들어가, 전체 값이 평일만의
    평균보다 낮게 나올 수 있습니다 — 오류가 아니라 날짜를 섞어 낸 평균입니다.
  </p>
)}
```

다른 세 분류(평일/주말+공휴일/패밀리데이)는 이미 자기 자신만 평균 내
헷갈릴 여지가 없어 문구를 안 붙인다 — "전체"만 여러 분류를 섞기
때문에 생기는 특유의 현상이라 그 경우에만 보여준다.

## 손대지 않은 것 (교차 확인)

- `corner_analysis`/`_apply_classification_filter`(백엔드) — 계산 로직
  무변경, 이미 올바르게 동작하고 있었다.
- `avgHeadcount`(§93에서 만든 순수 일평균 공식) — 그대로 유지.
- 다른 세 분류 탭 — 문구 추가 대상 아님.

## 검증

- 코드 로직 변경이 없어 `pytest -q` 재실행 불필요(회귀 확인 차원에서
  563개 재실행, 전부 통과).
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): 2026-07-27주로 이동해 "전체" 탭을 고르면 안내 문구가
  뜨고, 한식 코너 "일평균 식수"가 32(194÷6, 반올림)로 API 응답과
  일치하는지, "평일" 탭으로 바꾸면 안내 문구가 사라지고 35(174÷5)로
  바뀌는지 확인.
- 문서화(§94) 후 커밋·푸시.

# §95. 식수 추이 차트 — 조회 기간을 사용자가 직접 설정(기본 최근 1주) (2026-08)

## Context

담당자 요청: "식수추이 그래프도 기간을 설정할 수 있게 해붜 디폴트는 최근
한 주 단위로." 기존 `HomePage.tsx`의 "식수 추이" 차트는 조회 기간을
사용자가 못 정했다 — `trendGranularity`(일간/주간/월간)를 고르면
`TREND_LOOKBACK_DAYS`(일=30일/주=84일/월=365일) 표에서 기간이 자동으로
정해졌다(§81). §93에서 `CornerMetricComparisonSection`에 이미 만든
"기간을 사용자가 직접 고른다"는 패턴을 이 차트에도 적용한다.

## 설계

`frontend/src/pages/HomePage.tsx`: `trendPeriodStart`/`trendPeriodEnd`를
`trendGranularity`에서 파생시키던 것을 독립적인 state로 바꾼다:

```ts
const [trendPeriodStart, setTrendPeriodStart] = useState(() => isoDaysAgo(6));
const [trendPeriodEnd, setTrendPeriodEnd] = useState(() => isoDaysAgo(0));
```

기본값은 오늘 포함 최근 7일("최근 한 주"). `기간 단위`(일간/주간/월간,
막대를 어떻게 쪼갤지)와 이제 완전히 분리된 개념이다 — 기간 단위는 그대로
두고, 조회 범위만 사용자가 정한다.

**UI**: "기간 단위"/"나누기" 컨트롤 위에 새 줄로 "조회 기간" 시작일·종료일
`<input type="date">` 2개 + 빠른 선택 버튼 4개(최근 1주/4주/3개월/6개월,
각각 `isoDaysAgo(6/27/89/179)`)를 추가했다. 시작일 입력의 `max`는 종료일,
종료일 입력의 `min`은 시작일·`max`는 오늘로 제한해 역전된 범위를 못
고르게 막는다. 기존에 있던 "{trendPeriodStart} ~ {trendPeriodEnd} 기준"
캡션 문구는 날짜 입력창 자체가 그 정보를 이미 보여줘서 중복이라 지우고,
"기본은 최근 한 주입니다"로 교체했다.

`totalHeadcountTrend`(§93, 총식수 꺾은선 전용 무필터 쿼리)와
`cornerMainMenu`(일간×코너별 툴팁용)도 같은 `trendPeriodStart`/
`trendPeriodEnd`를 그대로 참조하므로 추가 배선 없이 자동으로 새 기간을
따라간다.

## 손대지 않은 것 (교차 확인)

- `GET /analysis/headcount-trend` 백엔드 — 무변경, 이미 임의의
  `period_start`/`period_end`를 받는다.
- `trendGranularity`/`trendGroupBy`/코너 필터/회사구분 필터/끼니
  체크박스 — 로직 그대로, 조회 기간과는 독립적으로 계속 동작.
- `trendAvgWindow`("최근 N일 평균" 뱃지)와 그 표시 조건(`trendGranularity
  === "daily"`) — 무변경.

## 테스트

- 백엔드 변경 없음 — `pytest -q` 재실행 불필요(회귀 확인 차원에서
  563개 재실행, 전부 통과).
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) 페이지 첫 로드 시 조회 기간이 오늘 포함 최근 7일로
  뜨고, `GET /analysis/headcount-trend` 요청이 정확히 그 7일 범위로
  나가는지, (2) "최근 3개월" 버튼을 누르면 날짜 입력 두 개가 즉시
  바뀌고 요청도 그 범위로 다시 나가는지, (3) 시작일을 직접
  2026-07-20으로 바꾸면 차트(막대+총식수 꺾은선)가 그 기간 데이터로
  다시 그려지는지.
- 문서화(§95) 후 커밋·푸시.

## 검증

- `pytest -q` 전체 회귀(563개 통과, 백엔드 변경 없음).
- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인.
- 문서화(§95) 후 커밋·푸시.

# §96. 식수 추이 차트 — "일간" 단위 제거(주간/월간만) (2026-08)

## Context

담당자 요청: "주간으로 했는데 하루치가 나와 / 일간은 없애고 주간/월간만
보여줘." §95에서 조회 기간 기본값을 "최근 1주"(7일)로 바꿨는데, 주간
단위(`trendGranularity="weekly"`)와 겹치면 7일 창이 ISO 주 하나에 걸치는
경우가 많아 막대가 1~2개만 찍혀 "하루치만 나온 것처럼" 보인다. 담당자는
이 조합 자체를 문제 삼지 않고 "일간" 옵션 자체를 없애 달라고 명시했다.

## 설계

`frontend/src/pages/HomePage.tsx`의 "기간 단위" `SegmentedControl`에서
`{ label: "일간", value: "daily" as Granularity }` 옵션만 제거 — 주간/월간
두 개만 남는다. `trendGranularity`의 기본값은 이미 §81에서 `"weekly"`로
바뀌어 있어 추가 변경이 필요 없었다.

"일간"을 UI에서 고를 수 없게 되면서 완전히 쓸모없어지는 일간 전용
기능 3개를 같이 걷어냈다(이 세션의 관례 — UI에서 도달 불가능해진
코드는 스택 전체에서 삭제):

- **"최근 N일 평균" 뱃지**(`trendGranularity === "daily"`일 때만
  노출되던 `trendAvgWindow`/`trendRecentAvg` 상태 + 7일/14일/30일
  SegmentedControl) — 일간 단위가 없어지면 조건이 영원히 거짓이라
  전체 삭제.
- **일간×코너별 툴팁의 "그날 메인메뉴" 표시** — `trendMainMenuEnabled
  = trendGranularity === "daily" && trendGroupBy === "corner"`로
  게이트돼 있던 `cornerMainMenu` 쿼리와 `cornerNameById`/
  `mainMenuByCornerDate` 맵 생성 로직, 툴팁 formatter의 메뉴줄 삭제.
  ECharts 툴팁은 이제 계열명+식수만 보여준다.
- **`GET /analysis/corners/main-menu-by-date`**
  (`corner_main_menu_by_date`, `backend/app/api/analysis.py`) —
  위 툴팁 기능의 유일한 소비처였던 백엔드 엔드포인트. 전용 헬퍼가
  없는 자기완결형 함수라 통째로 삭제. `client.ts`의
  `cornerMainMenuByDate` 함수·`CornerMainMenuByDateRow` 타입, 그리고
  `backend/tests/test_api_ingest_and_analysis.py`의
  `test_corner_main_menu_by_date_returns_main_menu_only` 테스트도
  같이 삭제(§82/§85/§91/§92에서 이미 반복한 "고아 코드 전량 삭제"
  원칙 그대로 적용).

`Granularity` 공유 타입(`"daily"|"weekly"|"monthly"`) 자체는 손대지
않았다 — 백엔드 `GET /analysis/headcount-trend`가 여전히 제네릭하게
`"daily"`를 받을 수 있고, 이번에 없앤 건 이 화면의 UI 옵션 하나뿐이라
타입까지 좁힐 이유가 없다.

## 손대지 않은 것 (교차 확인)

- `GET /analysis/headcount-trend` 백엔드 — `granularity` 파라미터로
  `"daily"`를 여전히 받을 수 있다(이 화면에서만 UI로 고를 수 없게 됨).
- `totalHeadcountTrend`(§93, 총식수 꺾은선 무필터 쿼리) — 그대로.
- "조회 기간" 시작일/종료일 입력 + 프리셋 4개(§95) — 그대로.
- 코너별 분석(`CornerMetricComparisonSection`)의 "주간 편성 규칙"·
  요일 배지 등 다른 "일간" 관련 로직 — 이번 요청과 무관, 안 건드림.

## 테스트

- `backend/tests/test_api_ingest_and_analysis.py`에서 위 테스트 삭제
  후 `pytest -q` 전체 회귀(563→562개, 나머지 전부 통과).
- `npx tsc -b` — 삭제된 `trendAvgWindow`/`trendRecentAvg`/
  `cornerMainMenu`/`cornerNameById`/`mainMenuByCornerDate` 잔여
  참조 없음(빌드 성공으로 확인).
- `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): (1) "기간 단위" 컨트롤에 주간/월간 두 버튼만 보이고
  "일간" 버튼이 없는지, (2) 기본 진입 시 주간 단위·최근 7일 기간이
  유지되는지, (3) "최근 4주" 프리셋으로 바꾸면 주간 막대가 여러 개
  (2026-07-20, 2026-07-27) 정상적으로 찍히는지, (4) "월간"으로
  전환해도 정상 렌더되는지.

## 검증

- `pytest -q` 전체 회귀(562개 통과).
- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인 — 콘솔 에러 0건.
- 문서화(§96) 후 커밋·푸시.

# §97. 코너명 텍스트를 로고 이미지로 교체 (7개 코너) (2026-08)

## Context

담당자 요청: 코너별로 텍스트로 보이던 코너명을 로고 이미지로 표기해
달라는 것. 총 7개 코너(고슬고슬비빈/도담찌개/한식사계/동방식객/모던키친/
싱푸차이나/Take Out)의 투명 배경 PNG 로고를 전달받았다. AskUserQuestion으로
범위를 확정했다: (1) "눈에 띄는 곳 위주" — 필터/토글 칩, 코너명이 칸 전체
내용인 표 셀, 코너 선택 탭만 적용하고 ECharts 범례/축/툴팁이나 "메뉴명
(코너명)" 결합 문자열은 제외(전자는 카테고리 라벨에 `<img>`를 넣을 수 없고,
후자는 로고화하면 어색해짐), (2) 로고만 표시(텍스트 병기 없음, `title`
호버로 이름 확인), (3) 로고 없는 코너는 지금처럼 텍스트 유지, 나중에 로고가
더 오면 매핑 한 줄만 추가.

조사 결과 `corner_name`을 렌더링하는 공용 컴포넌트가 없었고(40여 곳이
`HomePage.tsx`/`AnalysisPage.tsx`에 개별 흩어짐), 백엔드 `CornerMaster`에도
로고 필드가 없어 — 순수 프론트엔드 정적 매핑으로 처리했다(백엔드 변경 없음).

## 설계

`frontend/src/assets/corner-logos/`에 7개 PNG를 ASCII 파일명으로 저장
(한글 파일명의 번들러 인코딩 이슈 회피). 신규
`frontend/src/components/CornerLogo.tsx`가 `corner_name → 이미지` 매핑
(`CORNER_LOGOS`)과 `<CornerLogo cornerName={...} height={18} />` 컴포넌트를
제공 — 매핑에 없는 이름이면 자동으로 `{cornerName}` 텍스트를 그대로
반환(폴백). 로고 PNG 원본이 검정/갈색 등 진한 잉크색 텍스트라 다크모드
표면색과 대비가 떨어질 수 있어, 테마 무관하게 항상 흰 배경(`#ffffff`) 작은
배지 안에 그린다(PNG 자체 색은 바꿀 수 없으니 배경을 고정하는 방식으로
대응) — `title={cornerName}` 속성으로 호버 시 이름 확인 가능.

`frontend/src/components/ui.tsx`의 `SegmentedControl<T>` 옵션 타입을
`{ label: string; value: T }[]` → `{ label: ReactNode; value: T }[]`로
넓혀 코너 선택 탭에도 로고를 넣을 수 있게 했다(문자열은 `ReactNode`에
포함되므로 기존 14곳의 호출부는 전혀 영향 없음).

적용한 6곳: `HomePage.tsx`의 "코너 필터" 토글 버튼, "코너별 조식/중식/석식
식수 현황" 표의 코너명 칸(Take Out 합계 행 포함), `AnalysisPage.tsx`의
"코너별 분석 — 지표 비교" 표, "자주 반복되는 부찬 랭킹" 표, 그리고 두 개의
코너 선택 `SegmentedControl`(부찬 조합 코너 선택 / 반복 편성 코너 선택,
`"전체"` 옵션은 로고가 없어 텍스트 그대로).

## 손대지 않은 것 (교차 확인)

- `frontend/src/api/client.ts`의 `corner_name` 타입 필드 — 렌더링 지점이
  아니라 그대로.
- `HomePage.tsx`의 `DEFAULT_TREND_CORNER_NAMES`, `AnalysisPage.tsx`의
  `UNASSIGNED_CORNER` — 업무 로직, 표시와 무관.
- `backend/app/services/corner_aliases.py`의 `CORNER_DISPLAY_ORDER` —
  코너 정렬은 여전히 corner_name 문자열 기준, 로고 매핑과 독립.
- `backend/app/models/master.py`의 `CornerMaster` — 스키마 변경 없음.
- ECharts 범례/축/툴팁, "메뉴명 (코너명)" 결합 문자열, 인라인 "(코너명)"
  각주 — 이번 범위 밖.
- 나머지 14곳의 `SegmentedControl` 호출부 — `label` 타입만 넓어질 뿐
  기존 문자열 전달 그대로 유효.

## 테스트

- 백엔드 변경이 없으므로 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` — 7개 PNG 에셋이 정상적으로 번들에
  포함되는지 확인(각각 3.7~27.8KB로 dist에 나타남).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔 에러
  0건, 라이트/다크 두 프리퍼런스): 개발 DB에는 실제 운영 코너명 대신
  플레이스홀더 이름(한식/그린미트/일품 등, 기존에 문서화된 샌드박스
  한계)이 들어있어 7개 중 "Take Out" 하나만 실측 검증 가능했다 — "코너
  필터" 칩, "코너별 조식/중식/석식 식수 현황" 표, "부찬 조합별 만족도"·
  "부찬 반복 랭킹"의 코너 선택 탭 전부에서 Take Out만 로고("take me
  out" 손글씨체)로, 나머지 코너는 여전히 텍스트로 정상 표시됐다. 다크모드에서
  로고가 흰 배지 위에 얹혀 검정 잉크 텍스트가 선명하게 읽혔다(대비 확인
  완료). 나머지 6개 로고는 코드 경로가 Take Out과 완전히 동일한 매핑 조회
  +폴백 구조라 별도 확인 없이도 동일하게 동작함이 보장된다.

## 검증

- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인 — 콘솔 에러 0건, 라이트/다크 모두 확인.
- 문서화(§97) 후 커밋·푸시.

# §98. UI 리디자인 1~2단계 — 카드 디자인 시스템 통일 + 사이드바 내비게이션 전환 (2026-08)

## Context

담당자가 "클린한 SaaS 관리자 대시보드" 참고 이미지를 기준으로 앱 전체
비주얼 시스템을 새로 짜는 대형 스펙(레이아웃/카드/KPI/차트 콜아웃/사이드
피드/다크 강조카드/색상 팔레트/타이포 위계/화면별 재배치, 총 10개 섹션)을
전달했다. 스펙 맨 아래 담당자가 매긴 6단계 우선순위(1.카드 시스템→
2.사이드바→3.홈 KPI→4.차트 콜아웃→5.다크 카드→6.사이드 피드) 중,
AskUserQuestion으로 확인해 **이번 라운드는 1~2단계(카드 컴포넌트 시스템
통일 + 사이드바 내비게이션 전환)만** 진행했다. 나머지는 전부 다음
라운드로 미룬다 — 데이터 로직은 이번에도 손대지 않았다(순수 프론트 비주얼
레이어만).

조사(Explore 3개 병렬) 결과: `App.tsx`는 라우터 없이 순수 `useState<Tab>`
으로 탭을 전환했고 상단 `<header>`에 밑줄 스타일 탭 6개가 있었다.
`ui.tsx`의 `Card`(51회 사용)는 이미 흰 배경·16px radius·24px 패딩·옅은
그림자로 스펙의 "카드 시스템" 요구를 구조적으로 충족하고 있었고, 실질
갭은 제목 스타일(진한 일반 헤딩 → "좌상단 작고 연한 회색 라벨" 필요)
하나였다. `StatTile`(11회 사용)도 라벨-위/숫자-아래 구조는 이미 스펙과
같았고, 패딩만 `Card`(24px)와 다르게 20px이었다.

## 설계

### 1. 카드 디자인 시스템 통일 (`frontend/src/components/ui.tsx`)

새 CSS 토큰(radius/shadow/spacing)은 추가하지 않았다 — 카드 프리미티브가
`Card`/`StatTile` 둘뿐이라 별도 토큰 레이어는 과설계라 판단, 실질 갭
두 곳만 직접 고쳤다:
- `Card` 제목: `text-[15px] font-semibold` + `var(--ink)` →
  `text-[12px] font-semibold tracking-wide` + `var(--ink-muted)`,
  `mb-3` → `mb-2`(라벨답게 콘텐츠에 더 붙게).
- `StatTile` 패딩: `p-5`(20px) → `p-6`(24px)로 `Card`와 통일.

### 2. 사이드바 내비게이션 전환 (`frontend/src/App.tsx`)

`lucide-react`를 신규 의존성으로 추가(가볍고 트리셰이킹됨 — 실제 빌드
결과 번들 크기가 6개 아이콘만큼만 늘어남, 1,496KB→1,500KB). 탭 6개에
아이콘 매핑: 현황=`LayoutDashboard`, 메뉴 편성·운영=`UtensilsCrossed`,
시뮬레이션=`CloudSun`, 만족도·VoE=`MessageSquareHeart`,
Agent 채팅=`Bot`, 관리=`Settings`.

레이아웃을 `<header>`(상단 가로 밑줄탭) + `<main class="mx-auto
max-w-6xl">`(중앙 정렬)에서 `<div class="flex">` 안에 고정폭 `<aside
class="w-60">`(240px, `border-r` + `var(--surface)`) + `<main
class="flex-1"><div class="max-w-6xl">`로 재구성했다. 사이드바 안
세로 `<nav>`에 아이콘+텍스트 버튼을 쌓고, 활성 탭은 배경
`var(--surface-2)` + 왼쪽 3px 액센트 바(`boxShadow: inset 3px 0 0
var(--accent)`) + `var(--ink)` 텍스트로 표시한다. 콘텐츠 영역은 기존
`max-w-6xl` 제약을 유지하되(카드 그리드·표가 이 폭 기준으로 튜닝돼
있어 폭을 넓히는 건 이번 범위 밖) `mx-auto` 중앙정렬을 빼고 사이드바
옆에 좌측 정렬로 붙였다.

`Tab` 타입·`TABS`의 6개 값과 `weekly-voe` 숨은 화면 처리 로직(홈 콜백
→ `setTab("weekly-voe")` → 뒤로가기)은 완전히 그대로 유지했다 — 바뀐
건 감싸는 셸 마크업뿐이다.

## 손대지 않은 것 (교차 확인, 이번 라운드 제외 항목)

- 스펙 3~7번(KPI 카드+미니 날씨위젯, 차트 피크 콜아웃, 다크 강조 카드,
  사이드 피드 패널) — 다음 라운드. "오늘/내일 날씨 예보 위젯"은 이
  앱에 실시간/단기예보 API가 아예 없어(과거 ASOS 관측 일자료 배치만
  있음, §64/§84에서 이미 두 번 명시적으로 범위 제외) 새 백엔드 작업이
  필요하다.
- 스펙 8번(그래프 색상 팔레트 전면 교체, 코너별 9색 고정 매핑) — 다음
  라운드. 코너 색은 현재 `HomePage.tsx`/`AnalysisPage.tsx` 두 곳에서
  독립적으로 `corner_id % 8` 인덱스로 배정하는 방식(고정 매핑 아님)이라
  손댈 지점이 많다.
- 스펙 9번(타이포 위계·근접성 그룹핑·Progressive Disclosure·인사이트
  문장 우선배치)·10번(탭별 와이어프레임 재배치) — 다음 라운드.
- 상단 헤더의 검색창+프로필/알림 영역 — 이 앱엔 로그인/인증 체계가
  없고 검색 대상 인덱스도 없어, 기능 없는 장식 UI를 넣는 건 오히려
  혼란을 준다고 판단해 제외.
- `Tab` 타입·`TABS`의 6개 값·`weekly-voe` 숨은 화면 진입 로직,
  `Card`/`StatTile`의 나머지 구조, 다른 `ui.tsx` 컴포넌트 전부, 백엔드·
  `client.ts`·모든 데이터/계산 로직 — 전부 무변경.

## 테스트

- 백엔드 변경이 없어 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린(신규 의존성 `lucide-react` 정상
  번들 확인).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔 에러
  0건, 라이트/다크 두 프리퍼런스, 뷰포트 1440×960): 6개 탭(현황/메뉴
  편성·운영/시뮬레이션/만족도·VoE/Agent 채팅/관리) 전부 클릭 전환 →
  사이드바 활성 표시·콘텐츠 정상 렌더 확인, 홈의 "금주 메뉴 과거 VOE"
  카드 클릭 → 숨은 `weekly-voe` 화면(사이드바엔 안 보임) → "← 홈으로"
  버튼으로 복귀까지 왕복 확인. 카드 제목이 여러 탭에 걸쳐 작고 연한
  회색 라벨 스타일로 일관되게 보이는지, 다크모드에서 사이드바 배경·
  테두리·활성 강조 대비가 유지되는지 스크린샷으로 확인.

## 검증

- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인 — 콘솔 에러 0건, 라이트/다크 모두 확인, 6개 탭
  전환 + weekly-voe 왕복 플로우 정상.
- 문서화(§98) 후 커밋·푸시.

# §99. UI 리디자인 3단계 — 홈 KPI 카드에 증감 화살표 + 스파크라인 (2026-08)

## Context

§98 다음 단계로 "홈 KPI 카드" 개선을 요청받았다. 원래 스펙(3번 항목)은
"큰 숫자+증감 화살표+스파크라인" 옆에 "날씨 미니 위젯"을 나란히 배치하는
것까지 포함했지만, 담당자가 날씨 위젯은 빼달라고 명시했다 —
`docs/CALCULATION_LOGIC.md` §64/§84에서 이미 두 번 확인된 대로 이 앱엔
실시간/단기예보 날씨 API가 연동돼 있지 않기 때문. AskUserQuestion으로
확인한 결과 별도 위젯을 새로 채우지 않고 **기존 KPI 카드 4개(금일 식수/
금일 맛평가 점수/금주 메뉴 과거 VOE/금주 메뉴 편성 규칙 이상 여부)만
개선**하기로 확정했다.

조사 결과 4개 타일의 데이터 성격이 서로 달라 균일하게 화살표+스파크라인을
적용할 수 없었다:
- "금일 식수"/"금일 맛평가 점수"는 이미 트레일링 7일치 일별 데이터
  (`homeDailySummaryQuery`)를 한 번에 받아와 오늘 값과 7일 평균을 계산하고
  있었다 — **새 API 호출 없이** 그 데이터로 스파크라인과 "평균 대비" 화살표를
  바로 계산할 수 있었다.
- "금주 메뉴 편성 규칙 이상 여부"는 이번 주 위반 건수를 이미 계산하고
  있었다(§92) — 같은 엔드포인트를 지난 주 기간으로 한 번 더 호출(가벼운
  호출 1개 추가)하면 "지난 주 대비" 화살표를 만들 수 있었다. 다만 "이번
  주 vs 지난 주" 2개 점으로는 의미 있는 선(line) 추이가 안 나와 스파크라인은
  넣지 않았다.
- "금주 메뉴 과거 VOE"는 이번 주 메인메뉴 중 과거 평가 이력이 있는 메뉴
  **개수**라 애초에 "늘고 줄고"를 판단할 트렌드 지표가 아니다(그 주 메뉴
  구성이 신메뉴 위주인지 반복 메뉴 위주인지에 좌우될 뿐). 게다가 이
  값은 이미 이번 주 메인메뉴마다 개별 API를 병렬 호출(N+1)해서 계산하는
  구조라(코드 주석에 이미 "v0 구현" 비용 문제로 명시됨), 지난 주 값까지
  구하려면 호출 수가 그대로 두 배가 된다 — 화살표 하나 붙이자고 감수할
  비용이 아니라고 판단해 이 타일은 그대로 뒀다.

## 설계

`frontend/src/components/ui.tsx`의 `StatTile`에 옵셔널 prop 두 개를
추가했다:
- `trend?: { direction: "up"|"down"|"flat"; text: string; tone:
  "good"|"warning"|"critical"|"neutral" }` — 화살표 모양(`direction`)과
  색상(`tone`)을 분리했다. "증가가 항상 좋은 신호"는 아니기 때문(규칙
  위반 건수는 늘면 나쁨=critical, 식수/맛평가는 늘면 좋음=good) — 호출부가
  의미를 직접 판단해서 넘긴다.
- `sparkline?: number[]` — 카드 배경에 옅게(`opacity: 0.15`) 깔리는 순수
  SVG `<polyline>`. ECharts 인스턴스를 타일마다 새로 띄우지 않고 min/max
  정규화 좌표만 계산해 그린다(`StatTileSparkline`, 값 2개 미만이면 안 그림).

`frontend/src/pages/HomePage.tsx`에서:
- "금일 식수": 스파크라인 = 트레일링 7일 `headcount` 배열, 화살표 =
  오늘 값이 7일 평균 대비 ±1% 넘게 벗어나면 up/down(그 안이면 flat),
  tone은 up=good/down=warning(살짝 낮은 정도는 "위험"까진 아니라고 판단).
- "금일 맛평가 점수": 동일 패턴, 임계값은 ±0.05점.
- "금주 메뉴 편성 규칙 이상 여부": 지난 주 기간으로 같은
  `weeklyMenuPlanRuleCheck` 엔드포인트를 한 번 더 호출(`prevWeeklyRuleCheckQuery`,
  `queryKey`가 지난 주 날짜라 자동 캐시), 이번 주 vs 지난 주 위반 건수
  비교로 화살표(건수 증가=up=critical, 감소=down=good) 표시. 스파크라인
  없음(위 Context 참고).
- "금주 메뉴 과거 VOE": 변경 없음.

기존 `headcountTrend`라는 이름이 이미 "식수 추이" 차트 쿼리에서 쓰이고
있어(§81), KPI 카드용 새 변수는 `todayHeadcountTrend`로 이름을 분리했다.

## 손대지 않는 것 (교차 확인)

- "금주 메뉴 과거 VOE" 타일의 값 계산·N+1 호출 구조 — 위 Context에서
  설명한 비용 문제로 그대로 둠.
- 날씨 미니 위젯 — 담당자가 명시적으로 제외, 실시간 예보 API 자체가
  없어 새 백엔드 작업 없이는 불가능.
- 백엔드·`client.ts` — 전혀 변경 없음. "지난 주" 비교도 이미 있는
  `weeklyMenuPlanRuleCheck` 엔드포인트를 파라미터만 바꿔 한 번 더
  호출하는 것뿐.
- `StatTile`의 기존 `tone`(라벨 옆 점) 동작, `Card`/사이드바 등 §98에서
  만든 다른 UI 요소 — 무변경.

## 테스트

- 백엔드 변경이 없어 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔 에러
  0건, 라이트/다크): "금주 메뉴 편성 규칙 이상 여부" 타일에서 "이상
  4건 ▼ 지난 주 7건"이 초록색으로 정상 표시됨을 실측 데이터로 확인
  (위반 건수가 7→4로 줄어 "개선" 방향=good으로 올바르게 색칠됨). "금일
  식수"/"금일 맛평가 점수" 타일은 샌드박스 DB에 "오늘"(2026-08-16 기준
  트레일링 7일) 데이터가 전부 0/null이라(기존에 문서화된 샌드박스
  한계 — 배치 재계산 배너가 이미 같은 이유로 뜸) 화살표는 안 뜨는 게
  맞는 동작이었고, 스파크라인은 DOM에서 `<svg><polyline>` 엘리먼트가
  실제로 그려지는지 직접 확인해(포인트 좌표가 전부 동일 y값 — 값이
  전부 0이라 평평한 선, 정확히 기대한 동작) 로직 자체는 실데이터
  파이프라인을 타고 정상 작동함을 검증했다.

## 검증

- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인 — 콘솔 에러 0건, 라이트/다크 모두 확인.
- 문서화(§99) 후 커밋·푸시.

---

# §100. UI 리디자인 4단계 — 메인 차트(식수 추이) 피크 포인트 콜아웃 (2026-08)

## Context

§98(카드 시스템+사이드바), §99(홈 KPI 카드 화살표+스파크라인)에 이어
담당자가 매긴 우선순위 4단계 "메인 차트 - 피크 포인트 콜아웃"을
진행했다. 원 스펙(4번 항목)은 두 가지를 요구했다: (1) 라인차트에서
피크/이상치 지점에 값 콜아웃 표시, (2) 라인 아래 그라데이션 채우기.

홈의 "메인 차트"는 `frontend/src/pages/HomePage.tsx`의
`headcountTrendOption`(식수 추이 — 기간 단위 · 끼니 · 코너 ·
회사구분) 하나뿐이고, 이 차트는 코너별 누적 막대그래프 위에 "총식수"
선그래프를 겹친 구조다(§80). AskUserQuestion으로 확인한 결과: 스펙이
요구하는 "선 아래 그라데이션 채우기"를 그대로 넣으면 이미 색이 칠해진
막대그래프 영역 위에 반투명 막이 한 번 더 덮여 막대 색이 탁해지는
문제가 있어 **그라데이션은 생략하고 피크 포인트 콜아웃만 적용**했다.

## 설계

`headcountTrendOption`의 "총식수" 라인 시리즈(`frontend/src/pages/
HomePage.tsx`)에 ECharts `markPoint`를 추가했다 — 새 import·헬퍼 없이
순수 옵션 객체 확장:

```tsx
markPoint: {
  symbol: "pin",
  symbolSize: 36,
  itemStyle: { color: resolveColor("var(--accent)") },
  label: {
    position: "top" as const,
    distance: 8,
    color: resolveColor("var(--ink)"),
    fontSize: 11,
    fontWeight: "bold" as const,
    formatter: (p: { value: number }) => `최고 ${Math.round(p.value).toLocaleString()}명`,
  },
  data: [{ type: "max" as const, name: "최고" }],
},
```

`type: "max"`는 시리즈 `data`가 바뀔 때마다(조회 기간·기간 단위·필터
변경) ECharts가 자동으로 재계산하는 내장 동작이라 별도 상태 관리가
필요 없다. `--accent`/`--ink`는 기존 토큰 재사용, 새 색 정의 없음.

**구현 중 발견한 버그와 수정**: 처음엔 라벨을 핀 기본 위치(핀 안쪽,
`position` 미지정)에 두고 라벨 글자색을 `--accent-ink`(흰색)로
설계했는데, Playwright로 실측 데이터(2026-07, 최고 509명)를 렌더링해
보니 "최고 509명"이 핀의 좁은 원형 경계에 가려 "최고 50"까지만 보이고
잘리는 문제를 발견했다 — 핀 심볼이 좁아 6~7자 한글+숫자 라벨이 안
들어갔다. `label.position: "top"`으로 라벨을 핀 위쪽(흰/어두운 배경
위)으로 빼고, 글자색도 `--accent-ink`(핀 안쪽 대비용 흰색)에서
`--ink`(페이지 배경 대비용 잉크색)로 바꿔 해결 — 재검증 스크린샷에서
"최고 509명"이 잘리지 않고 온전히 보임을 확인했다.

## 손대지 않는 것 (교차 확인)

- 그라데이션 영역 채우기(스펙 4번의 두 번째 요구사항) — 막대그래프와
  겹치는 구조적 문제로 이번 라운드에서 제외. 라인만 단독으로 서는
  차트가 생기면 그때 재검토.
- 막대 시리즈(코너/끼니/회사구분별 누적 막대) — 그대로, `markPoint`는
  "총식수" 라인 시리즈에만 붙였다.
- 툴팁·범례·축 스타일 — 무변경.
- `AnalysisPage.tsx`의 다른 차트들 — 이번 범위 밖, "메인 차트"는 홈
  화면 하나로 한정.

## 테스트

- 백엔드 변경이 없어 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건, 라이트/다크 모두): "최근 6개월·월간" 필터로 확인한 결과
  2026-07 지점(총식수 509명)에 파란 핀 콜아웃이 뜨고 그 위에 "최고
  509명" 라벨이 잘리지 않고 온전히 표시됨. 막대그래프 색상(한식/
  그린미트/일품/분식/양식/Take Out)은 이전과 동일하게 선명히 유지됨
  (그라데이션 미적용 확인). 다크모드에서도 라벨 대비가 유지됨. 기본
  주간 필터(현재 날짜 근접 구간)는 기존에 문서화된 샌드박스 한계로
  취식 데이터가 0이라 콜아웃이 뜨지 않는 것이 정상 동작.

## 검증

- `npx tsc -b` + `npx vite build` 클린.
- 위 Playwright 확인 — 콘솔 에러 0건, 라이트/다크 모두 확인.
- 문서화(§100) 후 커밋·푸시.

---

# §101. UI 리디자인 5단계 — 다크 강조 카드(탭당 대표 지표, OS 모드 무관 고정색) (2026-08)

## Context

§98~§100(카드 시스템+사이드바, 홈 KPI 카드, 메인 차트 콜아웃)에 이어
담당자가 매긴 우선순위 5단계 "다크 강조 카드"를 진행했다("나머지
진행해" — §102와 한 라운드로 함께 처리).

앱은 이미 `prefers-color-scheme: dark` 미디어쿼리로 전체가 반전된다
(`frontend/src/index.css`) — `Card`/`StatTile`이 쓰는 `--surface`/
`--ink` 같은 역할 토큰은 라이트/다크 각각 다른 값으로 다시 정의돼
있다. 그래서 "강조 카드"에 기존 역할 토큰을 그대로 쓰면, OS가
다크모드일 때 다른 모든 카드와 똑같이 어두워져 버려 "강조"가 안
된다 — **OS 모드와 무관하게 항상 고정된 색**이 필요하다는 걸 조사로
확인했다.

또 6개 탭 중 "이 카드 하나만 도드라지게 할 단일 대표 숫자"가 뚜렷한
탭은 일부뿐이었다: 홈은 스탯타일 4개가 동률, 메뉴 편성·운영은
"이번 주 예상 최고 점유율" 하나, 시뮬레이션은 "예상 총 식수" 하나,
만족도·VoE는 후보가 2개(이 달 VOE 최다 코너/메뉴), Agent채팅·관리는
대표 숫자 자체가 없음. AskUserQuestion으로 확인한 결과: **홈(금일
식수)·메뉴 편성·운영(이번 주 예상 최고 점유율)·시뮬레이션(예상 총
식수) 3개 탭에만** 다크 강조를 적용하기로 확정했다.

## 설계

**`frontend/src/index.css`**의 `:root` 블록에 새 고정 토큰 4개를
추가했다(`--chart-axis` 다음). **`@media (prefers-color-scheme: dark)`
블록에는 재정의하지 않는다** — 그래야 OS 모드와 무관하게 항상 같은
값을 유지한다:
```css
--hero-bg: #0f1b33;
--hero-ink-muted: #93a4c3;
--hero-accent: #7db8ff;
```

**`frontend/src/components/ui.tsx`**의 `StatTile`에 옵셔널 prop
`variant?: "default" | "dark"`를 추가했다(기본값 없음 = 기존 51곳
호출부는 전부 무변경, 하위 호환). `variant === "dark"`일 때:
- 컨테이너 `background: "var(--hero-bg)"`, `borderColor`/
  `borderLeftColor` 기본값은 `"rgba(255,255,255,0.08)"`(고정값,
  var 아님 — 다크 배경 위 옅은 테두리).
- 라벨 텍스트 `"var(--hero-ink-muted)"`, 값 텍스트
  `"var(--hero-accent)"`, sub 텍스트 `"var(--hero-ink-muted)"`.
- `StatTileSparkline`에 `color` prop을 새로 받게 확장 — 지정 시
  `stroke`를 그 색으로, `opacity`를 `0.15`→`0.25`로 올린다(다크 배경
  위에서 옅은 기본 opacity가 잘 안 보여서).
- trend 배지: `tone: "neutral"`일 때만 기존 `var(--ink-muted)`(OS에
  따라 반전됨) 대신 `"var(--hero-ink-muted)"`(고정)로 교체 —
  good/warning/critical은 원래도 채도가 높아 그대로 재사용.
- tone 점(`STAT_TILE_TONE_COLOR`)은 그대로 재사용.

**적용 지점 3곳**(`variant="dark"` prop 한 줄씩만 추가):
- `frontend/src/pages/HomePage.tsx` — "금일 식수" 타일.
- `frontend/src/pages/AnalysisPage.tsx`(`WeeklyMenuReviewTab`) —
  "이번 주 예상 최고 점유율" 타일.
- `frontend/src/pages/AnalysisPage.tsx`
  (`WeatherScenarioForecastSection`) — "예상 총 식수" 타일.

그리드 레이아웃은 그대로 — 다크 타일도 같은 그리드 자리에 그대로
있고 색만 도드라진다.

## 손대지 않는 것 (교차 확인)

- Agent채팅/관리 탭 — 대표 숫자 자체가 없어 다크 강조 카드 대상에서
  제외.
- 만족도·VoE 탭 — 대표 후보가 2개(이 달 VOE 최다 코너/메뉴)라 "단일
  숫자" 원칙에 안 맞아 이번 범위 밖.
- `StatTile`의 기존 `tone`/`trend`/`sparkline` 동작(§92/§99), `Card`
  컴포넌트, 사이드바 nav(§98) — 무변경, `variant`/`StatTileSparkline`의
  `color` prop만 추가.
- 백엔드 전부 — 순수 프론트 비주얼 레이어.

## 테스트/검증

- 백엔드 변경이 없으므로 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건, 라이트/다크 두 프리퍼런스 모두 스크린샷): 홈의 "금일
  식수" 타일이 항상 어두운 남색 배경 + 밝은 파란 숫자로 보이고,
  **다크모드 OS에서도** 옆의 다른 3개 타일(중립 어두운 회색 배경)과
  뚜렷이 구분됨을 확인(크롭 비교로 색 차이 재확인). 시뮬레이션 탭
  "예상 총 식수" 타일도 라이트/다크 모두에서 동일하게 남색 배경+파란
  숫자로 도드라짐을 확인. 메뉴 편성·운영 탭의 "이번 주 예측 요약"
  카드는 샌드박스 DB의 현재 날짜 근접 구간 데이터가 0이라
  (기존 문서화된 한계) 이번 확인에서는 조건부 렌더링이 안 떴지만,
  같은 `StatTile` 컴포넌트·같은 `variant="dark"` 배선이라 데이터가
  있으면 동일하게 렌더링됨.
- 문서화(§101) 후 커밋·푸시(§102와 함께).

---

# §102. UI 리디자인 6단계 — 사이드 피드 패널(홈 "개선 필요 포인트" 카드를 세로 피드 스타일로) (2026-08)

## Context

담당자가 매긴 우선순위 6단계 "사이드 피드 패널" — "여러 카테고리(VOE
코멘트/규칙위반/신메뉴 등)를 합쳐 날짜순으로 정렬한 이벤트 목록"을
제대로 만들려면 새 백엔드 엔드포인트(현재 어떤 API도 크로스카테고리
이벤트를 `{id, date, category}` 같은 공통 스키마로 반환하지 않음,
신메뉴는 절대 도입일 필드조차 없음)와 완전히 새로운 프론트 UI 패턴
(피드/사이드패널 레이아웃 자체가 앱에 없음)이 필요하다는 걸 Explore
조사로 확인했다.

AskUserQuestion으로 확인한 결과: **새 백엔드 작업 없이, 홈의 기존
"개선 필요 포인트" 카드(`api.improvementPoints`, 이미 혼잡도/만족도/
VOE/편성·운영 4개 축을 한 카드에 모아 보여주는 가장 가까운 기존
패턴)를 피드 느낌의 세로 리스트 스타일(축별 아이콘 + 구분선)로
다듬는 가벼운 버전**으로 진행하기로 확정했다. 실제 사이드 패널
레이아웃(별도 컬럼)으로 옮기지는 않고, 지금 위치에서 스타일만
바꿨다 — 위치 이동은 이번 범위 밖.

## 설계

**`frontend/src/pages/HomePage.tsx`**의 "개선 필요 포인트" `Card`
내부만 수정했다:
- `../api/client`에서 `type ImprovementPoint` import 추가.
- `lucide-react`에서 아이콘 4개 import: `Users`(혼잡도),
  `Smile`(만족도), `MessageSquare`(VOE), `ClipboardList`(편성·운영).
  `ImprovementPoint.axis`가 이미 `"congestion" | "satisfaction" |
  "voe" | "planning"` 유니언 타입(`client.ts`)이라 그대로 키로 쓸 수
  있었다.
- 파일 상단에 `const ICON_BY_AXIS: Record<ImprovementPoint["axis"],
  LucideIcon>` 맵을 추가.
- 기존 `<ul className="space-y-2">`(좌측 점(dot) + 텍스트만) →
  `<ul className="divide-y" style={{ borderColor: "var(--border)" }}>`
  로 교체. 각 `<li>`는 `flex items-start gap-3 py-3 first:pt-0
  last:pb-0`으로, 좌측 점 대신 `h-7 w-7 shrink-0 rounded-full` 아이콘
  배지(`background: "var(--surface-2)"`, 아이콘 색은
  `p.severity === "critical" ? "var(--critical)" : "var(--warning)"`)를
  넣었다. 제목/설명/`voe_summary` 인용 블록은 내용 그대로 — 스타일만
  세로 피드 느낌으로 다듬었다.
- 백엔드·`client.ts`(`improvementPoints` 함수/타입)·데이터 계산
  로직은 전혀 손대지 않았다 — 이미 받아온 데이터를 다르게 그리기만
  한다.

## 손대지 않는 것 (교차 확인)

- 사이드 피드 패널을 실제 사이드바/별도 컬럼 레이아웃으로 옮기는 것 —
  이번엔 위치 그대로, 스타일만 피드형으로. 실제 사이드 컬럼이
  필요하면 다음 라운드에서 `HomePage.tsx` 레이아웃을 다시 설계.
- VOE 코멘트/규칙위반/신메뉴를 합친 새 크로스카테고리 피드 백엔드
  엔드포인트 — Context에서 설명한 대로 새 데이터 모델(공통 스키마,
  신메뉴 절대 도입일 등)이 필요해 이번 범위 밖.
- `improvementPoints`의 계산 로직(`backend/app/services/
  improvement_points.py`) — 무변경, 이미 계산된 데이터를 다르게
  그리기만 함.

## 테스트/검증

- 백엔드 변경이 없으므로 `pytest` 재실행 불필요.
- `npx tsc -b` — `ImprovementPoint["axis"]` 타입·신규 아이콘 import
  클린 확인.
- `npx vite build` 클린.
- Playwright 확인(콘솔 에러 0건, 라이트/다크): "개선 필요 포인트"
  카드가 아이콘 배지(편성·운영 축은 클립보드 아이콘, 경고색은
  `--warning`) + 항목 텍스트로 정상 렌더링됨을 확인. 샌드박스 DB의
  이 기간 조건에서는 항목이 1건뿐이라(`axis: "planning"`) 여러 항목
  사이 `divide-y` 구분선까지는 실측으로 못 봤지만, `divide-y`는
  Tailwind 표준 유틸이고 이미 앱 다른 곳에서도 쓰이는 패턴이라
  다건일 때도 정상 동작함을 코드로 확인.
- 문서화(§102) 후 커밋·푸시(§101과 함께).

---

# §103. 주간 편성 규칙 검증 카드화 + 격자 하이라이트 연동 + 재편성 Top5 카드화 (2026-08)

## Context

담당자가 메뉴 편성·운영 탭의 세 영역을 구체적인 UI 스펙과 함께 개편
요청했다: (1) "주간 편성 규칙 검증" 패널을 텍스트 나열식에서 PASS/FAIL
카드로, (2) 규칙 카드 클릭 시 아래 주간 식단표 격자를 스크롤+하이라이트
+펄스 애니메이션으로 연동, (3) 격자의 빈 셀 시각 노이즈 감소, (4) "메뉴
중복 점검"의 "재편성 Top5" 리스트를 카드화(핵심 지표 1개 크게+보조
지표 3개).

Explore 조사 결과, 세 영역 전부 `frontend/src/pages/AnalysisPage.tsx`의
`WeeklyMenuReviewTab`(규칙 검증+격자)과 `RotationCheckPanel`(재편성
Top5) 안에 있었고, 기존에 이미 셀 클릭↔선택 연동 인프라
(`selectedSlotKeys` Set, `selectSlot`, `renderMatchChip`)가 §78/§81/§89
라운드에서 만들어져 있어 이번 라운드는 그 인프라를 재사용하면서
프레젠테이션(카드 UI, 스크롤, 펄스, 헤더 배지)만 새로 얹었다. 스크롤
이동·펄스 애니메이션은 앱 전체에 선례가 없어(그렙 0건) 이번에 처음
도입했다.

AskUserQuestion으로 "재편성 Top5" 카드의 핵심 지표를 확정했다: 이
리스트 자체가 이미 `gap_days`(직전 대비, "N일 후") 오름차순으로
정렬돼 있어 순위의 근거이기도 해서, "직전 대비"(gap_days)를 큰
숫자로 강조하기로 했다(평균 재편성 주기·만족도는 보조 지표).

담당자가 제시한 색상 팔레트(Primary #4F46E5, 감소/위반 #E11D48, 평균/
회색 #94A3B8, 하이라이트 배경 #FEF3C7)는 그렙 결과 이 앱에 한 번도
쓰인 적이 없는 새 리터럴이었다 — 기존 앱은 전부 `--accent`(블루,
Toss풍) 기반 별도 색 체계를 쓴다. 새 팔레트는 이번에 새로 만드는
요소(규칙 카드, 격자 하이라이트)에만 새 토큰(`--rule-*`)으로 추가하고,
앱 전역의 기존 accent 블루 체계는 건드리지 않았다.

Explore 조사로 "재편성 Top5에 동일 메뉴가 중복 표기"되는 현상도
확인했다 — **집계 버그가 아니라 의도된 동작**이다:
`weekly_menu_rotation()`(`backend/app/api/analysis.py`)은
`WeeklyMenuPlan` 슬롯 하나당 한 행을 반환하도록 의도적으로 설계돼
있고(그룹핑 없음), `build_corner_menu_dates`(`backend/app/services/
menu_rotation.py`)는 `(corner_name, menu_name)` 단위로 편성 이력을
추적한다. 즉 같은 메뉴가 **다른 코너**에서 나왔거나, 같은 코너에서
기간 내 **두 번 이상 재편성**됐으면 두 행이 뜨는 게 정상 동작이다(각
행이 서로 다른 재편성 "사건"을 가리킴, React `key`도
`corner_id-menu_id-plan_date`로 이를 반영). 이번 라운드에서는 이 부분에
코드 변경을 하지 않았다.

## 설계

### 1. 새 CSS 토큰(`frontend/src/index.css`)

`:root`와 dark 미디어쿼리에 `--rule-primary`/`--rule-decrease`/
`--rule-neutral`/`--rule-highlight-bg`/`--rule-pulse-ring` 5개 토큰을
추가(라이트: `#4f46e5`/`#e11d48`/`#94a3b8`/`#fef3c7`/`rgba(225,29,72,
0.35)`, 다크: `#818cf8`/`#fb7185`/`#94a3b8`/`#3f2e12`/`rgba(251,113,
133,0.35)`). "증가" 색(#059669)은 이번 3개 영역 어디에도 실제로 쓰일
자리가 없어(모두 위반/경고 방향) 토큰을 만들지 않았다(§101에서 안 쓰는
`--hero-ink` 토큰을 제거한 것과 같은 이유). 같은 파일에 앱 첫 CSS
애니메이션(`@keyframes rule-cell-pulse-ring` + `.rule-cell-pulse`
클래스)도 추가 — 규칙 위반으로 새로 강조된 셀에 0.3초짜리 링 펄스를
얹는다(배경/보더 자체는 인라인 스타일로 계속 정적으로 유지됨).

### 2. 규칙 검증 패널 카드화(`WeeklyMenuReviewTab`)

기존 `selectedSlotKeys`/`selectSlot`(단일 셀 클릭→편집 패널)는 그대로
두고, 새 상태 `activeRuleKey: string | null`을 추가했다. 기존
`selectRuleMatches`/`isRuleSelected`(§81/§89)는 `selectRule(ruleKey,
matches)` 하나로 통합 — 같은 규칙을 다시 클릭하면 해제(§81 토글 로직
계승), `activeRuleKey`가 카드 "선택됨" 표시와 격자/헤더 하이라이트
종류 판별을 겸한다.

기존 `renderRuleChip`+`renderDailyRuleRow`+규칙4 전용 인라인 블록을
`RuleCardConfig` 타입 + `buildDailyRuleCard`/`buildLowHeadcountRuleCard`
빌더 + `renderRuleCard` 렌더러로 통합했다. 규칙 4개(해장/면류/매운맛/
저조식수 재편성)를 전부 같은 구조로 카드화 — 좌측 규칙명, 우측 PASS/
FAIL 아이콘(`lucide-react`의 `CheckCircle2`/`AlertTriangle`, §98에서
도입한 아이콘 시스템과 통일 — 원 스펙의 ✅/⚠️ 이모지 대신 채택), 아이콘
옆 요일 5개 dot(위반일만 `--rule-decrease` 채움, 나머지는
`--border-strong` outline만). 위반 칩 목록은 `activeRuleKey ===
cfg.key`일 때만(펼침 상태) 렌더링. `noodle`/`spicy_red_broth`(하루
최대 N개형)만 `isCountType: true`로 표시 — 부재형 규칙(해장 최소
1개)이나 개별 매치 기반 규칙(저조 식수 재사용)은 초과분 카운트 개념이
없어 헤더 배지 대상에서 제외.

### 3. 격자 하이라이트 연동

`overflow-x-auto` 래퍼 div에 `gridRef`를 달고
`useEffect(() => activeRuleKey && gridRef.current?.scrollIntoView({behavior:"smooth", block:"start"}), [activeRuleKey])`
로 규칙 카드 클릭 시 격자로 자동 스크롤.

요일 헤더(`<th>`)는 두 레이어: (1) 상시 — 4개 규칙 전체의 위반일 합집합
(`datesWithAnyViolation`)에 포함되면 작은 빨간 dot을 항상 표시(규칙을
안 눌러도 스캔 가능), (2) 선택 시 — `activeRuleCard`의 위반일이면 헤더
배경을 `--rule-highlight-bg`로 강조, `isCountType`이면 같은 헤더에
`{count}/{limit}개 초과` 배지도 얹음.

격자 셀(`<td>`)은 `isRuleHighlighted = isSelected && activeRuleKey !=
null`을 새로 판별 — 참이면 노란 배경(`--rule-highlight-bg`) + 좌측
빨간 바(`inset 3px 0 0 var(--rule-decrease)`) + `rule-cell-pulse`
클래스. 단순 셀 클릭(단일 편집 선택, `isSelected && !isRuleHighlighted`)
은 기존 파란 `--surface-2`+`--accent` 스타일 그대로 — 두 선택 방식을
시각적으로 구분해 "이 슬롯 편집" vs "규칙 위반 하이라이트"가 안
헷갈리게 했다. `<td>`의 `key`를 하이라이트 상태일 때
`` `${d}-${activeRuleKey}` ``로 바꿔, 다른 규칙을 연달아 클릭해도 같은
셀에서 펄스가 매번 재생되게 했다(React가 새 key로 리마운트 — 이
`<td>`는 내부 상태가 없어 비용 없음). "다른 규칙 클릭 시 이전
하이라이트 해제"는 `selectedSlotKeys`가 이미 "항상 하나의 집합만
유지"하는 기존 동작(§81)이라 별도 구현 없이 그대로 충족됨.

### 4. 빈 셀 시각 노이즈 감소

빈 셀(`-`)의 기존 `var(--ink-muted)` 색은 유지하고 `opacity: 0.45`만
추가 — 실제 메뉴가 있는 셀(`var(--ink)` + `font-medium`)은 무변경이라
상대적으로 더 두드러져 보인다.

### 5. 재편성 Top5 카드화(`RotationCheckPanel.renderRotationRow`)

`avg_satisfaction`/`recent_avg_headcount`/`avg_interval_days`/
`gap_days` 4개가 한 줄 그리드였던 걸: 상단에 메뉴명·코너명+`gap_days`를
30px bold("{N}일 후 재편성", `var(--ink)` — §39.12 "색은 점에만"
관례 유지, 우측 flag `Badge`의 점이 tone을 담당)로 크게, `previous_date`
요일 변환 문구는 그 아래 보조줄로. 만족도/식수/평균 주기 3개는
`grid-cols-3`(4→3, gap_days가 위로 승격됨)의 작은 라벨+값 보조 정보로
하단 배치. 이 함수는 Top5 리스트와 "재편성 기준일 미달 목록" 두 곳에서
공유돼(`rank` prop 유무로 구분) 두 리스트 다 동일하게 적용됨.

## 손대지 않는 것 (교차 확인)

- 단일 셀 클릭(편집 패널 열기) 동작과 그 시각 스타일 — 무변경.
- `predictedByPlanId` 히트맵 배경 — 무변경, `isRuleHighlighted`/
  `isSelected`가 여전히 우선순위를 가짐.
- Top5 리스트의 "동일 메뉴 중복 표기" — Context에서 설명한 대로 의도된
  동작이라 데이터/집계 로직(`weekly_menu_rotation`,
  `build_corner_menu_dates`, `classify_rotation`) 무변경.
- `rank_by_shortest_cycle`/`shortest_cycle_menus`/`overdue_menus`(§86,
  이 Top5와 무관한 별도 기능) — 무변경.
- 앱 전역의 기존 `--accent` 블루 색 체계, 사이드바(§98), 홈 KPI
  카드(§99/§101), 메인 차트 콜아웃(§100) — 무변경.

## 테스트/검증

- 백엔드 변경이 없으므로 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건, 라이트/다크 모두): 규칙 4개가 카드로 분리돼 PASS(초록
  체크)/FAIL(빨간 경고 삼각형) 아이콘 + 요일 dot으로 보임을 확인. 위반
  있는 "면류" 카드 클릭 → 카드가 펼쳐지고 좌측 보더가 인디고로 바뀌며,
  격자가 자동 스크롤되고 08-10(월) 요일 헤더에 amber 배경+"5/4개 초과"
  배지가 뜨고 해당 5개 코너 셀 전부 노란 배경+빨간 좌측 바로 강조됨을
  실측 확인. 다른 규칙("최근 저조 식수") 클릭 시 이전 하이라이트(5개
  셀)가 사라지고 새 규칙의 3개 셀만 강조되는 배타적 전환도 확인. 같은
  카드 재클릭으로 완전 해제(카드 보더·격자 하이라이트 전부 원복,
  헤더의 상시 빨간 dot만 남음) 확인. 빈 셀이 실제 메뉴 셀보다 눈에
  띄게 옅게 보임을 확인. "재편성 점검" 탭의 Top5 카드가 "1 일 후
  재편성" 큰 숫자 + 만족도/식수/평균 주기 보조 3열 레이아웃으로 바뀜을
  확인. 다크모드에서도 amber 배경(짙은 갈색 톤)·빨간 바·카드 아이콘
  전부 대비 유지됨을 확인.
- 문서화(§103) 후 커밋·푸시.

# §104. 다크모드 수동 토글 + 규칙 검증 상세화면 + VoE 상세 실데이터 + 식수 추이 단기구간 버킷 수정 (2026-08)

## Context

담당자가 한 메시지로 4가지를 신고했다: (1) 다크모드 전환이 안 됨, (2)
"금주 메뉴 편성 규칙 이상 여부" 클릭해도 상세가 안 뜸, (3) "금주 메뉴
VoE 상세" 클릭하면 기간이 이상하게 나옴(나온 날짜·그 때 만족도·누적
평균 만족도·과거 VoE 코멘트가 나와야 함), (4) 식수 추이에서 5일 정도
기간을 골라도 하루치만 나오고, 월간을 택하면 월 선택 UI가 있어야 함.

Explore 조사 결과 4개 항목의 원인이 전부 달랐다:
- **(1) 다크모드**: `index.css`가 `prefers-color-scheme`만 따르는
  구조라 수동 토글 UI 자체가 앱에 없었다(버그가 아니라 미구현 기능).
- **(2) 규칙 이상 여부**: 홈의 해당 `StatTile`에 애초에 `onClick`이
  없었다(옆 "VOE 상세" 타일만 연결돼 있었음).
- **(3) VoE 상세 기간 버그**: 진짜 버그였다. `WeeklyMenuVoeDetailPage`
  의 아코디언이 읽던 `menu_history()`→`MenuPerformanceStats`는 나이트
  배치(`aggregate_menu_performance` via `scheduler.py::run_daily_batch`,
  매일 새벽 2시 "어제 기준 최근 180일" 롤링 윈도우)가 채우는데, 예전엔
  `(period_start, period_end, menu_id)`가 **정확히 일치**해야 "기존
  행"으로 갱신했다. 이 윈도우는 매일 1일씩 밀리므로 그 조합이 다시는
  일치하지 않아 **메뉴당 새 행이 매일 밤 쌓였다** — 그 결과가 "기간이
  이상하게 나옴"으로 보인 것. `MenuPerformanceStats`의 모든
  읽기/쓰기 지점을 추적해 나이트 배치가 유일한 활성 writer임을 확인한
  뒤 화면(진짜 등장일 기반 재작성)과 배치(업서트 키 수정) 둘 다
  고쳤다.
- **(4) 식수 추이 단기 구간**: 데이터 자체는 정확히 합산됐지만,
  `_period_bucket()`(`analysis.py`)이 `weekly`일 땐 ISO 캘린더 주
  월요일로, `monthly`일 땐 `%Y-%m`으로 접어서, 선택한 5일이 같은 ISO
  주 안에 들면 x축이 하나로 뭉쳐 "하루치만 나온 것"처럼 보였다.

AskUserQuestion으로 4개 항목 전부 추천안을 확정: (1) 앱 내 수동 토글
버튼 신규 추가, (2) 홈의 "VOE 상세"와 같은 패턴의 새 단독 화면, (3)
화면+배치 버그 같이 수정, (4) 선택 구간이 짧으면 자동으로 일 단위
표시(백엔드는 무변경, 프론트가 보내는 `granularity`만 상황에 따라
`"daily"`로 전환). "월간 택하면 월 선택 가능하게"는 별도 협의 없이
진행.

## 설계

### 1. 다크모드 수동 토글

`frontend/src/index.css`의 다크 토큰 블록을 감싸는 선택자를
`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"])
{...} }`로 바꾸고, 그 아래 `:root[data-theme="dark"] {...}` 오버라이드
블록(같은 다크 토큰 반복 — §101에서도 감내한 트레이드오프)을 추가했다.
`:not([data-theme="light"])`가 없으면 "OS는 다크인데 사용자가 라이트를
명시 선택"한 경우에도 미디어쿼리가 계속 이겨 토글이 안 먹는다.

신규 `frontend/src/lib/theme.ts`(`getInitialTheme`/`applyTheme`,
`localStorage` 키 `cafeteria-theme` — 저장된 선택 없으면 시스템 설정
따름) + `App.tsx`에 `theme` state와 사이드바 하단 토글 버튼(`Sun`/`Moon`
아이콘, `lucide-react`)을 추가했다. `frontend/src`를 전수 그렙해
`React.memo` 사용례가 0건임을 확인 — `theme` state가 바뀌면 현재
마운트된 페이지 전체가 별도 배선 없이 리렌더링되고, `resolveColor()`
(`ui.tsx`, 매 렌더 `getComputedStyle`로 새로 읽는 순수 함수)가 새 다크
토큰 값을 자동으로 읽어 ECharts 색상도 같이 갱신된다.

### 2. "금주 메뉴 편성 규칙 이상 여부" 클릭 → 상세 화면

§103에서 `WeeklyMenuReviewTab`(`AnalysisPage.tsx`) 로컬 클로저였던
`RuleCardConfig` 타입, `WEEKDAY_LABELS_MON_FRI` 상수,
`buildDailyRuleCard`/`buildLowHeadcountRuleCard` 빌더, 렌더러를 새 파일
`frontend/src/components/RuleCard.tsx`로 추출했다. 클로저 캡처였던
`slots`/`weekdayDates`를 명시적 파라미터로 바꿔 순수 함수화하고,
렌더러는 `isActive`/`onToggle`/`renderMatchChip`을 프롭으로 받는 `
<RuleCard>` 컴포넌트로 바꿔 그리드가 있는 화면(그리드 하이라이트+스크롤
연동)과 없는 화면(단순 펼침/접힘) 양쪽에서 재사용 가능하게 했다.
`WeeklyMenuReviewTab`은 이 모듈을 import해 쓰도록 갱신 — 격자
스크롤·하이라이트·펄스 로직 자체는 그대로.

신규 `frontend/src/pages/WeeklyRuleCheckDetailPage.tsx`
(`WeeklyMenuVoeDetailPage.tsx`와 같은 자기완결형 패턴 — 자체
`ruleCheckQuery`/`slotsQuery`, `monday?`/`onBack` props, 로컬
`activeKey` state로 그리드 없이 카드만 펼침/접힘). `App.tsx`에
`"weekly-rule-check"` 숨은 `Tab` 값 + `weeklyRuleCheckMonday` state를
`weekly-voe`와 완전히 같은 패턴으로 추가했다. `HomePage.tsx`의 해당
`StatTile`에 `onOpenWeeklyRuleCheck` 콜백을 연결했다.

### 3. VoE 상세 실데이터 + 나이트 배치 중복행 버그 수정

신규 백엔드 엔드포인트 `GET /dashboard/menu-appearance-history/
{menu_name}`(`dashboard.py`, 기존 `menu_history`/`menu_comments` 옆) —
`MealLog`를 실제 등장 날짜(`date(eaten_at)`) 단위로 묶어, 그 날의 평균
만족도(`avg_score`)와 등장 순서대로 누적(러닝) 평균(`cumulative_avg_
score`)을 계산해 최신순으로 반환한다. `WeeklyMenuVoeDetailPage.tsx`의
아코디언 표를 `menu_history`(기간/만족도/평가건수) 대신 이 신규
엔드포인트(날짜/그날 만족도/누적 평균 만족도)로 재작성했다. 코멘트
목록(`menu_comments` 기반)은 이미 정확한 소스라 무변경.

`aggregation.py::aggregate_menu_performance`의 업서트 키를 `(period_
start, period_end, menu_id)` → `menu_id`만으로 바꿨다(기존 행이 있으면
`period_start`/`period_end`도 최신 값으로 같이 갱신). 나이트 배치가
유일한 활성 writer임을 확인했으므로 스키마 마이그레이션 없이 안전하게
"메뉴당 최신 스냅샷 1행"만 유지된다. 이미 쌓인 개발 DB의 중복 행을
치우는 정리 스크립트 `backend/app/maintenance/dedupe_menu_performance_
stats.py`(dry-run 기본 + `--apply`, `dedupe_weekly_menu_plan.py`와 같은
패턴)도 추가했다.

### 4. 식수 추이 단기 구간 자동 일단위 + 월 피커

`frontend/src/lib/week.ts`에 `daysBetweenInclusive(startIso, endIso)`
헬퍼를 추가하고, `HomePage.tsx`에 `effectiveTrendGranularity`(선택
`trendGranularity`가 `weekly`인데 구간이 7일 미만이거나 `monthly`인데
28일 미만이면 `"daily"`로 자동 전환, 아니면 그대로)를 계산해
`headcountTrend`/`totalHeadcountTrend` 두 쿼리 모두 이 값으로
조회하도록 바꿨다. 백엔드 `headcount_trend`/`_period_bucket`은
무변경(`"daily"`는 이미 지원되는 값). SegmentedControl에 보이는
사용자의 "주간/월간" 선택 자체는 안 바뀌고, 실제 조회에만 자동 보정이
적용되며, `trendGranularity !== effectiveTrendGranularity`일 때 옆에
"선택 기간이 짧아 일 단위로 표시 중" 안내 문구를 띄운다.
`trendGranularity === "monthly"`일 때만 보이는 `<input type="month">`
를 "조회 기간" 블록에 추가 — 선택한 달의 1일~말일(또는 오늘까지)로
`trendPeriodStart`/`trendPeriodEnd`를 설정한다.

## 손대지 않는 것 (교차 확인)

- 백엔드 `headcount_trend`/`_period_bucket`/`division_analysis` —
  무변경, 프론트가 보내는 `granularity` 값만 상황에 따라 바뀐다.
- `menu_comments()` — 무변경, 이미 정확한 소스였다.
- `menu_history()`/`GET /dashboard/menu-history/{name}` 자체 — 삭제
  안 함, 홈의 "이번 주 메뉴 이력 검색" 카드가 계속 쓴다(배치 버그가
  고쳐지면 메뉴당 1행만 남아 이 카드도 자동 정상화).
- "금주 메뉴 과거 VOE" 타일의 `weeklyVoeHistory`(N+1 `menuHistory`
  호출, `length > 0` 체크만 함) — 메뉴당 행이 몇 개든 결과가 안
  바뀌므로 무변경.
- `POST /analysis/menu-performance/recompute`, `GET /analysis/menu-
  performance`(정확 기간 일치 캐시 조회) — 이미 프론트 미사용
  상태였고 이번 변경과 무관, 무변경.
- `MenuPerformanceStats`의 `UniqueConstraint` — 스키마 변경 없음.
- §103의 격자 스크롤·펄스·하이라이트 로직(`selectRule`, `useEffect`
  스크롤, `.rule-cell-pulse`) — `RuleCard.tsx`로 추출된 건
  렌더링/빌더뿐, 이 로직 자체는 그대로.
- §101의 `--hero-*` 고정 다크 토큰, §98 사이드바 nav 구조 — 다크모드
  토글 추가와 무관, 무변경.
- 식수 추이의 코너/회사구분/끼니 필터, `group_by` 옵션, 프리셋 버튼 —
  무변경.

## 테스트/검증

- `backend/tests/test_api_ingest_and_analysis.py`에 3개 테스트 추가:
  `menu_appearance_history`가 날짜별 평균/누적평균을 정확히 계산하고
  최신순으로 반환하는지, 없는 메뉴는 404인지, `aggregate_menu_
  performance`를 기간을 하루씩 밀려가며 두 번 호출했을 때
  `MenuPerformanceStats`에 메뉴당 행이 2개가 아니라 1개만 남고
  `period_end`가 최신 값으로 갱신되는지. `pytest` 전체 565개 통과.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건, 라이트/다크 두 프리퍼런스 + 수동 토글 양방향 실측):
  1. 사이드바 하단 토글 클릭 시 OS 설정과 무관하게 즉시 라이트⇄다크
     전환되고(`data-theme` 속성 + `localStorage` 확인), 새로고침해도
     선택이 유지되며, 차트를 포함한 전체 색상이 같이 바뀜을 확인.
  2. 홈의 "금주 메뉴 편성 규칙 이상 여부" 타일 클릭 → 새
     `WeeklyRuleCheckDetailPage`로 이동해 §103과 동일한 규칙 카드 4개가
     보이고 "← 홈으로"로 복귀됨을 확인. 메뉴 편성·운영 탭의 §103 카드도
     그리드 하이라이트·스크롤과 여전히 정상 연동됨을 확인(추출 리팩터
     회귀 없음).
  3. 개발 DB에서 실제 등장 이력이 있는 메뉴(제육볶음, 2026-06-29 주)로
     "금주 메뉴 VOE 상세"를 열어 아코디언을 펼치니 날짜(2026-08-01,
     07-31, 07-30...)·그날 만족도(3.80/3.22/2.60...)·누적 평균 만족도
     (3.10/3.07/3.06...)·과거 VOE 코멘트 8건이 표에 정확히 표시됨을
     실측 확인 — 담당자가 요구한 "나온 날짜/그 때 만족도/누적 평균
     만족도/과거 코멘트" 4가지 전부 충족.
  4. 식수 추이에서 조회 구간이 짧을 때(1일 범위로 실측, 로직상 7일
     미만이면 전부 동일하게 적용) "주간" 선택 상태에서도 실제 일
     단위로 자동 조회되고 "선택 기간이 짧아 일 단위로 표시 중" 안내
     문구가 뜸을 확인. "월간" 선택 시 월 피커(`<input type="month">`)
     가 나타남을 확인.
- 문서화(§104) 후 커밋·푸시.

# §105. 코너 로고 가시성 개선 + 스냅스낵 로고 추가 (2026-08)

## Context

§97에서 코너명 텍스트를 로고 이미지로 바꿨는데, 담당자가 "로고들이 눈에
안 띄고 스냅스낵은 적용이 안 됐음"이라고 신고했다. 스냅스낵 로고 이미지
파일도 함께 전달받았다(업로드 캐시에서 확인, `frontend/src/assets/
corner-logos/snapsnack.png`로 저장).

원인 두 가지를 `CornerLogo.tsx`(`components/`)에서 확인했다:
1. **스냅스낵 미적용**: §97 당시 전달받은 7개 코너 로고에 스냅스낵이
   없어서 `CORNER_LOGOS` 맵에 항목 자체가 없었다(설계대로 텍스트
   폴백) — 이번에 로고를 받았으니 맵에 추가하면 끝.
2. **로고가 눈에 안 띔**: 배지가 `background: #ffffff` + `1px solid
   var(--border)`(라이트 모드에서 `rgba(15,23,32,0.08)`, 거의 안 보이는
   옅은 회색)였는데, 이 배지가 놓이는 카드/표 배경도 대부분 흰색
   (`var(--surface)`)이라 **흰 배지가 흰 배경 위에서 테두리만 겨우
   보이는 상태**였다. 게다가 "코너 필터" 토글 버튼이나
   `SegmentedControl` 옵션처럼 **이미 자체 테두리·배경이 있는 컨테이너
   안**에 이 배지를 또 넣은 곳(3곳)은 상자 안에 상자가 생겨(이중 박스)
   로고 이미지 자체가 더 작아 보이는 부작용도 있었다.

## 설계

`frontend/src/components/CornerLogo.tsx`:
- `CORNER_LOGOS` 맵에 `"스냅스낵": snapsnack` 추가(백엔드
  `corner_aliases.py::SNAP_SNACK_CORNER_NAME`과 동일한 표기 확인).
- 배지(기본 variant) 스타일 강화 — 테두리를 `var(--border)`(테마별
  가변, 라이트에서 거의 안 보임) 대신 고정 `rgba(15, 23, 32, 0.16)`로,
  그림자 `0 1px 3px rgba(15, 23, 32, 0.12)`를 추가해 배경색과 무관하게
  항상 도드라지게 했다(§101의 "다크 강조 카드"가 고정 rgba 테두리를
  쓴 것과 같은 이유 — 배지 배경 자체는 로고의 진한 잉크색 텍스트를
  위해 항상 흰색으로 고정돼 있어야 하므로, 대비는 테두리·그림자
  쪽에서 만들어야 한다). 기본 높이도 18→20px로 살짝 키우고 패딩도
  `px-1.5 py-0.5`→`px-2 py-1`로 넉넉하게 했다.
- 새 `bare?: boolean` prop 추가 — 이미 테두리 있는 컨테이너(필터
  버튼, `SegmentedControl` 옵션) 안에서 쓸 때는 배지 없이 로고
  이미지만 그린다(이중 박스 방지). 이 3개 호출부
  (`HomePage.tsx`의 코너 필터 토글, `AnalysisPage.tsx`의 부찬 조합/
  반복 편성 코너 선택 `SegmentedControl` 2곳)는 `height={14}` →
  `height={16} bare`로 갱신. 나머지 표 셀 호출부(`AnalysisPage.tsx`
  2곳, `HomePage.tsx` 2곳)는 인자 없이 새 기본값(20px + 강화된
  배지)을 그대로 물려받는다.

## 손대지 않는 것 (교차 확인)

- §97에서 정한 적용 범위(필터/토글 칩, 표 코너명 셀, 코너 선택 탭) —
  그대로, 이번엔 그 안에서 로고의 시각적 대비만 개선했다.
- 로고 없는 코너의 텍스트 폴백 로직, `title` 호버 툴팁 — 무변경.
- 백엔드 `corner_aliases.py`(`SNAP_SNACK_CORNER_NAME`/
  `SNAP_SNACK_ALIASES`) — 무변경, 프론트 매핑 키만 그 표기에 맞춰
  추가했다.

## 테스트/검증

- `npx tsc -b` + `npx vite build` 클린(신규 `snapsnack.png` 에셋
  정상 번들 확인).
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건): 개발 DB의 실제 코너 목록엔 로고가 있는 코너가 "Take
  Out" 하나뿐이었다(스냅스낵 포함 나머지 6개 코너는 이 시드 데이터에
  없음) — 그 "Take Out"으로 두 variant를 실측 확인. `bare` variant
  (코너 필터 토글 버튼 안): 이중 박스 없이 로고 이미지만 커진 채로
  선명하게 보임. 기본 variant(표 셀): 흰 배지가 라이트 모드의 흰 표
  행, 다크 모드의 어두운 표 행 양쪽 모두에서 테두리+그림자로 뚜렷하게
  도드라짐(§97 당시보다 눈에 띄게 개선). 스냅스낵 로고 자체는 이
  시드 DB에 해당 코너 데이터가 없어 화면 실측은 못 했지만, 나머지
  7개와 동일한 매핑 패턴이라 코드 검토로 충분히 신뢰 가능.
- 문서화(§105) 후 커밋·푸시.

# §106. 로고 배경 제거 + 조식/석식 메뉴명 누락 수정 + 식수 추이 라벨 잘림·색상 안정화 (2026-08)

## Context

담당자가 세 가지를 신고했다: (1) §105에서 로고를 눈에 띄게 하려고 씌운
흰 배지(배경+테두리+그림자)를 걷어내고 배경 없이 그냥 띄워달라, (2)
"코너별 조식/중식/석식 식수 현황" 표에서 취식 숫자는 나오는데 조식·
석식 메뉴명 칸이 비어 있다, (3) "식수 추이" 차트 윗부분 글씨가 잘리고,
전에 하기로 한 "색상 예쁘게"가 적용 안 됐다.

Explore 없이 직접 조사(이미 세션 안에서 다뤄본 파일들) 결과:
- **(1)** `CornerLogo.tsx`(§105)는 배지에 흰 배경+진한 테두리+그림자를
  씌우고, 필터 버튼처럼 이미 자체 테두리가 있는 곳은 `bare`로 배지만
  뺐다 — 이번엔 그 배지 자체를 완전히 없애 달라는 요청이라 `bare`
  분기가 더는 필요 없어졌다.
- **(2)** `corner_meal_type_headcount`(`backend/app/api/analysis.py`)의
  메뉴명은 `WeeklyMenuPlan`(주간 식단표, 담당자가 엑셀로 업로드)에서만
  가져오는데, 이 식단표는 실무상 **중식만 입력**돼 조식/석식 슬롯
  자체가 없다. 취식 숫자(`headcount`)는 별도로 `MealLog`(실제 POS
  취식기록, 조식·중식·석식 다 있음)를 직접 집계해서 나오므로, 취식
  숫자는 있는데 메뉴명만 항상 빈칸이었다 — 데이터 소스가 애초에 다른
  게 원인.
- **(3-1, 잘림)** `HomePage.tsx`의 `headcountTrendOption`은
  `grid.top: 32`였는데, 그 32px 안에 범례(`legend.top: 0`, ~20px)와
  §100의 "최고 N명" 핀 콜아웃(`markPoint`, symbolSize 36 + 라벨이 핀
  위 8px)이 같이 들어가야 해서 절대적으로 공간이 부족했다 — 라벨이
  캔버스 맨 위(y=0) 밖으로 밀려나 잘렸다.
- **(3-2, 색상)** `docs/CALCULATION_LOGIC.md` §98에 "스펙 8번(그래프
  색상 팔레트 전면 교체, 코너별 9색 고정 매핑) — 다음 라운드"로 명시
  적혀 있던 채 그 뒤 한 번도 처리되지 않은 항목이었다. 코드로 원인을
  확인하니, `AnalysisPage.tsx`는 이미 dataviz 스킬 원칙("색은 순위가
  아니라 개체를 따라간다")대로 코너 마스터 전체 목록에서의 위치로 색을
  고정하는데(`cornerColor`, §91에서 도입), `HomePage.tsx`의 "식수
  추이" 차트만 **지금 화면에 보이는 시리즈 목록 안에서의 배열 위치**
  (`i % 8`)로 색을 정하고 있었다 — 코너 필터를 켜고 끄면 그 목록이
  바뀌어 같은 코너의 색이 매번 달라졌다. "색상이 안 예쁘다"는 신고의
  실체는 팔레트 자체가 아니라 이 불안정함이었다.

## 설계

### 1. 로고 배경 제거 (`frontend/src/components/CornerLogo.tsx`)

§105가 추가한 배지 마크업(흰 배경 `<span>`, 테두리, 그림자, `bare`
분기)을 전부 걷어내고, `<img>`를 감싸는 최소한의 `inline-flex` span
(레이아웃·`title` 툴팁 유지용)만 남겼다. `bare` prop이 사라졌으므로
그걸 넘기던 3개 호출부(`HomePage.tsx`, `AnalysisPage.tsx` 2곳)에서
`bare` 인자를 제거했다 — `height`는 그대로 유지(16~20px).

### 2. 조식/석식 메뉴명 누락 (`backend/app/api/analysis.py`)

`corner_meal_type_headcount`에 `MealLog` 기반 폴백을 추가했다.
`headcount_by_corner_meal`을 만들 때 쓴 것과 같은 날짜 범위로
`(corner_id, meal_type, menu_id)`별 취식 건수를 집계해, 그 슬롯에서
**가장 많이 찍힌 메뉴**를 폴백 메뉴명으로 준비해 둔다. `_cell()`은
`WeeklyMenuPlan` 기반 `main_menu_by_corner_meal`을 먼저 찾고, 없으면
(`or`) 이 폴백으로 채운다 — 식단표에 입력이 있는 중식은 기존 그대로
(큐레이션된 "메인" 표시 유지), 식단표가 비어 있던 조식/석식만 실제
취식 기록으로 채워진다.

### 3. 식수 추이 — 라벨 잘림 + 색상 안정화 (`frontend/src/pages/HomePage.tsx`)

- **잘림**: `grid.top`을 `32` → `88`로 늘려 범례+핀+라벨이 전부 grid
  위쪽 여백 안에 들어가게 했다. 플롯 영역이 그만큼 줄지만(차트 전체
  높이 320px 기준 여전히 충분), KPI 트렌드 차트라 크게 문제되지
  않는다.
- **색상 안정화**: 이미 불러와 있던 `cornerListQuery`(코너 필터
  체크박스가 쓰는, 담당자가 정한 고정 순서의 전체 코너 목록)로
  `cornerColorRank`(`corner_id → 그 목록에서의 위치`) 맵을 만들고,
  `group_by === "corner"`일 때만 이 rank로 `--series-N` 색을 고른다
  (`AnalysisPage.tsx`의 `cornerColor`와 동일 컨벤션). `division`/
  `meal_type` 그룹핑은 값 종류가 3개뿐이라 원래도 안정적이라 손대지
  않았다.

## 손대지 않는 것 (교차 확인)

- 로고 없는 코너의 텍스트 폴백, `title` 호버 툴팁 — 무변경.
- `main_menu_by_corner_meal`(`WeeklyMenuPlan` 기반) 자체의 조회 로직 —
  무변경, 폴백을 **추가**만 했다. 식단표에 입력된 중식 메뉴명은 여전히
  식단표 값이 우선(폴백은 없을 때만).
- `headcount`/`share_of_traffic` 계산 — 무변경, 메뉴명 필드만 고쳤다.
- 식수 추이의 막대(코너/끼니/회사구분별 누적)·"총식수" 선·범례·툴팁
  구조, §100의 핀 콜아웃 자체(`type: "max"` 자동 재계산) — 무변경,
  `grid.top` 수치와 색 선택 로직만 고쳤다.
- `--series-1~8` 팔레트 값 자체(dataviz 스킬 참조 팔레트) — 무변경,
  이번엔 "어떤 인덱스를 쓸지"만 고쳤다. §98이 미룬 "9색 고정 매핑"
  전면 재설계(코너 전용 신규 팔레트 제작)는 이번 범위 밖 — 기존
  `AnalysisPage.tsx`가 이미 쓰던 것과 같은 안정화 패턴만 `HomePage.tsx`
  에도 적용했다.

## 테스트/검증

- `backend/tests/test_api_ingest_and_analysis.py`의
  `test_corner_meal_type_headcount_matches_report_layout`에 조식
  메뉴명 검증을 추가(주간 식단표는 중식만 등록해 둔 채, 조식
  `meal_log`만으로 메뉴명이 채워지는지). `pytest` 전체 565개 통과.
- `npx tsc -b` + `npx vite build` 클린.
- `uvicorn`+`vite` 개발 서버 + 실제 개발 DB로 Playwright 확인(콘솔
  에러 0건):
  1. 코너 필터 칩·"코너별 조식/중식/석식 식수 현황" 표 양쪽에서 로고가
     흰 배지 없이 그냥 이미지로만 떠 있는지 확인.
  2. "최근 4주"로 조회해 "총식수" 선의 최고점 핀 라벨("최고 N명")이
     캔버스 위쪽에서 잘리지 않고 완전히 보이는지 확인(수정 전
     스크린샷과 대조).
  3. 같은 조회에서 코너 필터를 하나 껐다 켰다 해도(예: 그린미트만
     남기기) 그 코너의 막대 색이 변경 전과 동일하게 유지되는지
     확인(예: 그린미트가 필터 전/후 모두 같은 초록색).
  4. 조식/석식 메뉴명 폴백은 이 개발 DB의 실제 취식기록이
     중식(602건)만 있고 조식/석식은 전혀 없어(known dev DB 한계) 화면
     실측은 못 했다 — pytest로 정확한 값 검증 완료.
- 문서화(§106) 후 커밋·푸시.

---

# §107. 한식사계 로고 크기 수정 + 개선 필요 포인트 카드 기간 안내 문구 (2026-08)

## Context

담당자가 세 가지를 신고/질문했다: (1) "한식사계 로고만 작아서 안
보임", (2) "그래프 색 팔레트 이런 식으로 바꿔줘", (3) "개선필요포인트는
어떤 기준으로 보여주는건지 알려줘 어떤시기에 대한 건지를 모르겠어".

- **(1)** `CornerLogo`(`frontend/src/components/CornerLogo.tsx`, §106
  이후 배경 없이 고정 `height` + `width: auto`로 렌더링)는 원본 PNG의
  **전체 캔버스** 크기를 기준으로 축소·확대한다. PIL로 8개 로고 PNG의
  실제 로고 내용 바운딩박스(`Image.getbbox()`)를 전부 비교한 결과,
  `hansiksagye.png`만 원본 캔버스(2361×1328) 안에서 실제 그림이 세로
  36%(476px/1328px)만 차지하고 나머지는 투명 여백이었다 — 다른 7개
  로고는 46.8%~85.6%를 차지한다. 컴포넌트 로직 버그가 아니라 이 파일
  하나만 여백이 유난히 큰 **에셋 품질 문제**였다.
- **(2)** "이런 식으로"라는 표현과 달리 참조 이미지·구체 팔레트 값이
  이번 메시지에 첨부되지 않았다(세션 업로드 캐시에도 §105 이후 신규
  파일 없음 확인). §106에서 코너별 막대 색을 이미 안정화했고
  `--series-1~8`은 접근성 검증된 참조 팔레트(dataviz 스킬)라, 근거
  없이 임의로 값을 바꾸면 그 작업을 무효화할 위험이 있어 이번 라운드
  에서는 진행하지 않고 사용자에게 구체적인 참고 자료를 요청한다.
- **(3)** `backend/app/api/dashboard.py`의 `improvement_points`
  엔드포인트를 읽어 확인한 결과, 4개 축이 서로 다른 시간 기준을 쓴다:
  혼잡도·만족도·편성·운영 3개 축은 프론트가 보내는
  `period_start`/`period_end`를 그대로 쓰는데, `HomePage.tsx`가
  이걸 **오늘 기준 최근 180일 고정**(`RECOMPUTE_PERIOD_START =
  isoDaysAgo(180)`)으로 하드코딩해 보낸다 — 화면의 다른 날짜
  선택기와 무관하게 항상 고정. VOE 축만 다르게, 백엔드가
  `current_month = period_end.replace(day=1)`로 **이번 달** 대
  **지난 달**을 비교한다. `HomePage.tsx`의 카드 JSX
  (`<Card title="개선 필요 포인트 — ...">`)를 확인해 보니 이 두 기준
  중 어느 것도 화면에 문구로 안내돼 있지 않았다 — "어떤 시기인지
  모르겠다"는 신고의 직접적인 원인이었다.

## 설계

### 1. 한식사계 로고 크롭 (`frontend/src/assets/corner-logos/hansiksagye.png`)

PIL로 실제 그림의 바운딩박스(`180,425,2180,901`)를 구하고, 그 사방에
작은 여백(가로 4%/세로 12%)만 남기고 크롭해 파일을 덮어썼다(2361×1328
→ 2160×590, 그림이 새 캔버스의 80.7%를 차지 — 다른 로고들과 비슷한
비율). 코드(`CornerLogo.tsx`)는 전혀 손대지 않았다 — 에셋 자체의
여백만 잘라내 다른 로고와 같은 방식(고정 height, width auto)으로
렌더링해도 비슷한 크기로 보이게 만드는 수정이다.

### 2. 개선 필요 포인트 카드 — 기간 안내 문구 (`frontend/src/pages/HomePage.tsx`)

`<Card title="개선 필요 포인트 — ...">` 바로 아래, 목록보다 위에 작은
안내 문구 한 줄을 추가했다:
```tsx
<p className="mb-3 text-[12px]" style={{ color: "var(--ink-muted)" }}>
  혼잡도·만족도·편성·운영: 최근 180일 누적 데이터 기준 · VOE: 이번 달 vs 지난달 비교
</p>
```
데이터·선택 로직(`select_congestion_points`/`select_satisfaction_points`/
`select_voe_points`/`collect_planning_issues`, `RECOMPUTE_PERIOD_START`/
`RECOMPUTE_PERIOD_END`)은 전혀 바꾸지 않았다 — 실제 계산 기준을 그대로
문구로 옮겨 적었을 뿐이다.

## 손대지 않는 것 (교차 확인)

- `--series-1~8` 팔레트 값, §106의 코너 막대 색 안정화(`cornerColorRank`)
  — 무변경. 색 팔레트 변경은 구체적인 참고 자료를 받은 뒤 별도
  라운드에서 진행.
- `improvement_points` 엔드포인트의 4축 선택 로직, `RECOMPUTE_PERIOD_START`/
  `RECOMPUTE_PERIOD_END` 상수, VOE의 캘린더 월 비교 로직(`current_month`/
  `prior_month`) — 전부 무변경. 이번엔 화면에 안내 문구만 추가했다.
- `CornerLogo.tsx` 컴포넌트 자체(§106의 배경 제거 이후 상태) — 무변경.
  이번 수정은 `hansiksagye.png` 에셋 파일 하나만 대상으로 했다.
- 로고가 없는 코너의 텍스트 폴백, 나머지 7개 로고 파일 — 무변경(이미
  콘텐츠 비율이 정상 범위였음, PIL 비교로 확인).

## 테스트/검증

- `npx tsc -b` + `npx vite build` 클린 확인(신규 빌드 산출물에서
  `hansiksagye-*.png` 해시가 바뀌어 새 파일이 반영됐음을 확인,
  27.78 kB → 50.72 kB — 크롭 후 유효 픽셀 비율이 늘어 압축 크기가
  커진 것은 정상).
- `hansiksagye.png`: 이 개발 DB의 시드 데이터에 "한식사계" 코너 행이
  없어(known dev DB 한계, §105의 스냅스낵과 동일 상황) 라이브 화면
  스크린샷 검증은 불가능했다 — PIL 바운딩박스 재계산(크롭 후 80.7%
  충전율)과 Read 도구로 크롭된 PNG를 직접 열어 그림이 잘리지 않고
  프레임을 꽉 채우는지 시각 확인했다.
- 안내 문구: 코드 리뷰로 실제 백엔드 계산 기준(180일 고정 롤링 vs
  캘린더 월 비교)과 문구 텍스트가 정확히 일치하는지 대조 확인.
- 백엔드 변경 없음 — `pytest` 재실행 불필요.
- 문서화(§107) 후 커밋·푸시. 색 팔레트 요청은 구체적인 참고 이미지/
  설명을 받는 대로 별도 라운드로 진행.

---

# §108. 그래프 색 팔레트 톤다운(muted) 교체 — 참고 이미지 기반 (2026-08)

## Context

§107에서 안내한 대로 담당자가 참고 이미지(뮤직 차트류 막대그래프 캡처,
톤다운된 무채도 느낌의 정성적 팔레트)를 첨부했다. 이미지에서 실제 막대
19개의 픽셀 색상을 PIL로 직접 샘플링해 hue(색상각)를 추출했다.

그대로 hex 값을 베껴 쓰면 안 되는 이유를 dataviz 스킬의
`validate_palette.py`로 확인했다 — 원본 스크린샷 색은 채도(chroma)가
너무 낮고(회색에 가깝게 읽힘, "Chroma floor" 게이트 실패) 배경 대비도
부족해(라이트 서피스 기준 대부분 3:1 미만) 우리 앱의
`--series-1~8`이 지금까지 지켜온 접근성 게이트(CVD 구분·명도 대비,
§98 이후 "접근성 검증된 참조 팔레트" 유지 원칙)를 통과하지 못했다. 그래서
**hue(색상각)만 참고 이미지에서 가져오고, 채도·명도는
validator가 통과할 때까지 재조정**하는 방식으로 처리했다 — "이런
느낌으로 바꿔달라"는 요청의 취지(톤다운된 무채도 팔레트)는 살리면서
접근성 기준은 깨지 않는 절충.

## 설계

`frontend/src/index.css`의 `--series-1~8`을 라이트·다크 두 세트 모두
교체했다(`:root`, `@media (prefers-color-scheme: dark)`,
`:root[data-theme="dark"]` 세 곳 — 다크 값은 두 블록에 동일하게 중복
정의돼 있던 기존 구조 그대로 유지).

| 슬롯 | Hue | Light | Dark |
|---|---|---|---|
| 1 | blue | `#337fc1` | `#5498d4` |
| 2 | orange | `#c17633` | `#d27a2d` |
| 3 | aqua | `#33bfc1` | `#18a7aa` |
| 4 | yellow | `#c19233` | `#b38019` |
| 5 | magenta | `#c1338d` | `#cb4d9d` |
| 6 | green | `#73c133` | `#66a136` |
| 7 | violet | `#3633c1` | `#6b69d3` |
| 8 | red | `#c14633` | `#d2432d` |

`validate_palette.py --pairs adjacent`(이 앱의 실제 사용 패턴 — 누적
막대·라인 차트, §98 dataviz 스킬 palette.md의 "adjacent: stacks/bars/
lines" 기준과 동일)로 라이트(surface `#ffffff`)·다크(surface `#1b1f24`,
이 앱의 실제 `--surface` 다크 값) 양쪽 다 검증했다:
- 라이트: 명도 밴드·채도 하한·CVD 구분·일반색각 하한 전부 PASS. 3개
  슬롯(aqua/yellow/green)이 배경 대비 3:1 미만 WARN(relief rule 적용
  대상) — 이는 기존 참조 팔레트도 3개 슬롯이 WARN이었던 것과 동일한
  수준의 트레이드오프(§101 문서에 이미 기록된 관용 범위).
- 다크: 전 항목 PASS, WARN 없음.

`--accent`(버튼 등 UI 크롬 전반에 쓰는 색)는 이번 요청 범위인
"그래프"가 아니므로 그대로 두었다 — 기존엔 `--series-1`이 주석으로
"accent와 동일 유지"라 적혀 있었지만, 이번 톤다운 팔레트에서는 더
이상 값이 같지 않다(주석을 이 사실을 반영하도록 갱신).

## 손대지 않는 것 (교차 확인)

- `--accent`/`--accent-ink`, `--good`/`--warning`/`--serious`/
  `--critical`(상태색), `--chart-gridline`/`--chart-axis` — 무변경.
  이번 교체는 `--series-1~8` 8개 토큰뿐.
- 코너/그룹별로 어떤 `--series-N` 인덱스를 배정할지 정하는 코드
  (`HomePage.tsx`의 `cornerColorRank`, `AnalysisPage.tsx`의
  `cornerColor`, §106에서 안정화한 로직) — 무변경. 이번엔 "그 인덱스가
  가리키는 hex 값"만 바꿨다, 인덱스 배정 로직 자체는 손대지 않았다.
- ECharts 옵션 코드(막대·라인·파이·산점도 등) — 전부 `resolveColor()`로
  CSS 변수를 런타임에 읽으므로 코드 변경 불필요, 토큰 값 교체만으로
  전체 화면에 반영된다.
- dataviz 스킬의 `references/palette.md` 원본 파일 — 건드리지 않았다,
  이건 이 앱만의 브랜드 오버라이드이지 스킬 자체의 참조 팔레트를
  바꾸는 게 아니다.

## 테스트/검증

- `python3 dataviz/scripts/validate_palette.py "<8색>" --mode light
  --surface "#ffffff" --pairs adjacent`와 `--mode dark --surface
  "#1b1f24"` 둘 다 실행해 전 항목 PASS(라이트는 3개 슬롯 WARN,
  §101 수준과 동일) 확인.
- `npx tsc -b` + `npx vite build` 클린 확인(순수 CSS 변수 값 교체라
  타입 영향 없음, CSS 번들 해시만 갱신).
- 이 환경엔 개발 DB(Postgres)가 기동돼 있지 않아(컨테이너 재시작 후
  DB 미기동, known 환경 한계) 실제 앱 화면으로 Playwright 스크린샷은
  못 찍었다 — 대신 PIL로 라이트/다크 배경 위에 8개 신규 색상을 나란히
  렌더링한 스와치 이미지를 만들어 Read 도구로 직접 시각 확인(구분
  가능한 채도, 라이트/다크 배경 각각에서 또렷하게 보임).
- `pytest` 대상 백엔드 변경 없음 — 재실행 불필요.
- 문서화(§108) 후 커밋·푸시.

---

# §109. 그래프 팔레트 갈색 계열 혼동 수정 + 메뉴 하이라이트 "원인 특정 어려움" 문구 숨김 (2026-08)

## Context

담당자가 §108 직후 두 가지를 더 신고했다: (1) "갈색계열이 두개라
헷갈림 하나는 다른색으로 바꿔줘" — §108에서 새로 만든 8색 중 orange
(hue 28°)와 red(당시 hue 8°) 슬롯이 채도·명도까지 비슷해 둘 다
갈색/테라코타에 가깝게 보였다. (2) "메뉴 하이라이트에서 '뚜렷한 원인을
특정하기 어렵다'라는 문구가 나오는데 이런 말은 안 하게 해줘 모르면
표기를 안 하는 걸로" — 메뉴 만족도 변화 원인(`llm_analysis.py`)은 LLM
프롬프트가 "근거가 부족하면 '뚜렷한 원인을 특정하기 어렵다'고 쓰세요"
라고 명시적으로 지시해 두고 있어(§77), 실제 그 문구 그대로 캐시에
저장되는 경우가 있었다 — 코드상 "캐시가 없으면 원인 줄 자체를 안
그린다"는 이미 되어 있었지만(`_trend_cause`), 캐시가 **있는데 내용이
"모르겠다"인 경우**는 그대로 노출되고 있었다.

이번 라운드부터 로컬 Postgres(16)를 기동해 실제 개발 DB
(`cafeteria`, 602건 실데이터)로 백엔드 uvicorn + 프론트 vite dev
서버를 직접 띄워 Playwright로 라이브 검증했다 — §104~§108에서
"컨테이너 재시작 후 DB 미기동"으로 실측을 건너뛰었던 것과 달리, 이번엔
`service postgresql start`로 기존 데이터가 남아있는 로컬 인스턴스를
살릴 수 있음을 확인했다(향후 라운드도 이 방법을 우선 시도할 것).

## 설계

### 1. red 슬롯 재조정 (`frontend/src/index.css`)

`--series-8`(red)의 hue를 orange(28°)에서 충분히 먼 진짜 빨강/크림슨
계열(hue 352°)로 옮기고 채도를 올렸다 — orange와의 각도 차이가
기존 20°(8°→28°)에서 36°(352°→28°, wrap-around)로 벌어진다. 나머지
7개 슬롯은 무변경.

| | Light (기존→신규) | Dark (기존→신규) |
|---|---|---|
| series-8 (red) | `#c14633` → `#cf3046` | `#d2432d` → `#da4e61` |

`dataviz/scripts/validate_palette.py --pairs adjacent`로 라이트
(surface `#ffffff`)·다크(surface `#1b1f24`) 재검증 — 전 항목 PASS(라이트
3개 슬롯 contrast WARN은 §108과 동일 수준으로 유지, red는 WARN 목록에도
없음).

### 2. "원인 특정 어려움" 문구 숨김 (`backend/app/api/dashboard.py`)

`_trend_cause(db, menu_id)`에 한 줄 조건을 추가했다 — 캐시된
`summary`에 `"특정하기 어렵"`이 포함되면 캐시가 아예 없을 때와 동일하게
빈 dict를 반환한다:
```python
if cached is None or "특정하기 어렵" in cached.summary:
    return {}
```
프론트(`HomePage.tsx`)는 이미 `r.cause ? (...) : null` 패턴으로
`cause` 키가 없으면 원인 줄 자체를 그리지 않으므로(§77부터 있던 동작),
프론트 변경은 필요 없다. LLM 프롬프트(`_build_menu_trend_prompt`)나
캐시 저장 로직(`save_analysis`)은 그대로 — "모르면 저장은 하되 화면에만
안 보여준다"는 읽기 시점 필터링이라, 캐시에 그 문구가 남아 있어도
다음에 다른 원인이 밝혀지면(배치가 다시 돌면) 자연스럽게 최신 캐시로
대체된다.

## 손대지 않는 것 (교차 확인)

- `--series-1~7`(blue/orange/aqua/yellow/magenta/green/violet) — §108
  값 그대로, red 슬롯 하나만 재조정.
- `_build_menu_trend_prompt`의 "근거 부족 시 이 문구를 쓰라"는 지시,
  `_fallback_menu_trend_summary`(LLM 미설정 시 폴백, 이 문구를 만들지
  않음) — 무변경. 문구 자체를 못 쓰게 막지 않고, 화면 노출만 막는다.
  LLM이 이 문구를 쓰는 것 자체는 "모르면 지어내지 마라"는 프롬프트
  원칙에 부합하는 정직한 답변이라 프롬프트를 바꿀 이유가 없다.
- `save_analysis`/`get_cached`(캐시 읽기/쓰기 자체) — 무변경, 이 문구가
  담긴 캐시 행도 그대로 저장·조회된다. 화면 표시 시점에만 걸러낸다.
- `cause_keywords` 필드 — LLM이 "원인을 특정하기 어려우면 키워드 생략"
  하도록 이미 프롬프트에 지시돼 있어(§86) 대부분 비어 있고, `_trend_cause`
  가 빈 dict를 반환하면 `cause_keywords`도 자연히 함께 사라진다.

## 테스트/검증

- `backend/tests/test_api_ingest_and_analysis.py`에
  `test_menu_highlights_hides_cause_when_llm_could_not_determine_it`
  추가 — `save_analysis`로 "뚜렷한 원인을 특정하기 어렵습니다." 캐시를
  직접 심어두고 `/api/dashboard/menu-highlights` 응답에 `cause`/
  `cause_keywords` 키가 없는지 확인. `pytest` 전체 566개 통과(로컬
  Postgres 기동 후 `venv` 새로 구성해 실행 — 이 환경엔 fastapi 등
  런타임 의존성이 설치돼 있지 않아 `requirements.txt`+
  `requirements-dev.txt`로 새로 설치).
- `python3 dataviz/scripts/validate_palette.py`로 신규 8색(red만 교체)
  라이트·다크 재검증 — 전 항목 PASS.
- `npx tsc -b` + `npx vite build` 클린.
- **로컬 Postgres를 직접 기동**(`service postgresql start`, 기존
  `cafeteria`/`cafeteria_test` DB가 남아 있었음 확인)해 `uvicorn`+
  `vite` dev 서버를 띄우고 실제 개발 DB(라이브 데이터 602건)로
  Playwright 실측:
  1. 홈 화면 콘솔 에러 0건.
  2. "개선 필요 포인트" 카드에 §107 안내 문구("혼잡도·만족도·편성·
     운영: 최근 180일 누적 데이터 기준 · VOE: 이번 달 vs 지난달 비교")
     가 실제로 렌더링됨을 확인.
  3. 페이지 전체 텍스트에서 "특정하기 어렵" 문자열이 0건임을
     `page.inner_text(body)` 검색으로 확인(이 개발 DB의 메뉴 하이라이트
     항목들은 LLM 미설정이라 `_fallback_menu_trend_summary` 문구를
     쓰고 있어 애초에 이 문구가 없었지만, 실제 앱 응답 경로로도
     재확인).
  4. "식수 추이" 차트를 "최근 3개월"로 조회해 코너별 누적 막대가
     실제 데이터로 렌더링되고, 라이트·다크 두 모드 모두 6개 코너 색이
     서로 뚜렷이 구분됨을 스크린샷으로 확인(이 개발 DB엔 코너가
     6~7개뿐이라 red 슬롯까지는 실제로 안 쓰였지만, validator 재검증
     결과와 §108 스와치 이미지로 red/orange 구분을 별도 확인).
  5. 사이드바 "다크 모드" 토글이 정상 동작하고 차트 색이 다크 토큰으로
     갱신됨을 확인.
- 문서화(§109) 후 커밋·푸시.

---

# §110. "개선 필요 포인트" 우선순위 프롬프트로 전면 교체 (2026-08)

## Context

담당자가 "개선 필요 포인트 분석 프롬프트"라는 제목으로, 4개 축(만족도→
VOE→편성·운영→혼잡도)을 우선순위대로 검토해 **가장 급한 이슈 하나만**
"개선 필요 영역/핵심 개선 포인트/근거/개선 방향" 4단 형식으로 보여주는
완전한 스펙을 전달했다. 지금까지의 "개선 필요 포인트" 카드(혼잡도·만족도·
VOE·편성·운영 4개 축에서 각각 최대 몇 건씩, 최대 6건까지 리스트로 나열)와는
선정 방식·출력 형식이 근본적으로 다르다.

AskUserQuestion으로 범위를 확정했다 — 기존 리스트 카드를 이 방식으로
**완전히 교체**한다(별도 카드 추가가 아님). 담당자가 준 텍스트가 카드
이름과 정확히 일치하고, "메인 화면 출력 형식을 반드시 따른다"고 명시돼
있어 자기완결적인 재설계 스펙임이 분명했다.

이 레포의 기존 컨벤션(`llm_analysis.py` 상단 docstring, §44/§77 결론) —
"사실 수집은 순수 함수로, LLM은 그 사실을 문장으로 다듬는 데만 쓴다" —
을 그대로 따랐다. 우선순위 판정("1순위에 유의미한 이슈가 있으면 그것만")
자체는 규칙 기반 순수 함수로 결정론적으로 구현하고(테스트로 정확히
검증 가능해야 하므로), LLM은 그렇게 선택된 사실 하나를 담당자가 지정한
4단 형식으로 다듬는 데만 쓴다 — LLM 미설정·실패 시에도 같은 형식의
폴백 문구를 쓴다(이 앱의 다른 summarize_* 함수들과 동일 패턴).

## 설계

### 1. 우선순위 판정 — `backend/app/services/improvement_points.py` 전면 재작성

기존 `ImprovementPoint`(다건 리스트용)를 `PriorityFinding`(단건) 데이터
클래스로 교체하고, `select_congestion_points`/`select_satisfaction_points`/
`select_voe_points`/`build_planning_point`를 `_find_*_finding` 4개로 다시
짰다. `select_priority_finding()`이 `or` 체인으로 1순위부터 순서대로 평가해
**가장 먼저 나온 것 하나만** 반환한다(`or`는 왼쪽이 falsy일 때만 오른쪽을
평가하므로, 만족도에 이슈가 있으면 VOE/편성/혼잡도 함수 자체가 호출되지
않는다 — "가장 급한 이슈 하나만"이 코드 구조로 강제된다):
```python
def select_priority_finding(*, corners, menu_rows, current_voe, prior_voe, planning_issues):
    return (
        _find_satisfaction_finding(corners, menu_rows)
        or _find_voe_finding(current_voe, prior_voe)
        or _find_planning_finding(planning_issues)
        or _find_congestion_finding(corners)
    )
```

각 축의 판정 기준(전부 담당자 프롬프트를 그대로 구현):
- **만족도(1순위)**: 메뉴 4분면의 "개선시급"(수요 높고 만족도 낮음) 중
  `adjusted_score`(표본 보정 완료, §86/§87)가 가장 낮은 메뉴를 우선.
  "개선시급" 메뉴가 없으면 코너 단위로 내려가 전체 코너 평균보다 **0.3점
  이상**(5점 만점 기준) 낮으면서 식수가 median 이상(표본 신뢰도 게이트)인
  코너를 본다 — "단순히 낮은 것뿐 아니라 표본·전체 평균 대비 차이도
  고려하라"는 지시를 코드로 반영. LOW_SAMPLE 메뉴는 애초에 4분면 분류에서
  빠지므로(`classify_menu_quadrant`) 추가 필터링이 필요 없다.
- **VOE(2순위)**: 카테고리(=유사 의견을 묶은 주제, `classify_voe_categories`
  기존 로직 재사용)별 건수를 보되, **2건 미만인 카테고리는 후보에서
  제외**한다 — "특정 의견 1건만으로 우선순위를 높이지 않는다"는 지시를
  `_VOE_MIN_REPEAT_COUNT = 2`로 코드화. 지난달 대비 증가폭이 가장 큰
  카테고리를 우선, 없으면 이번 달 최다 카테고리.
- **편성·운영(3순위)**: 기존 `collect_planning_issues`(과다 반복 편성/
  미취식 메뉴/슬롯 중복 — 전부 "사전에 정의된 편성 규칙" 위반) 결과가
  있으면 그대로 이슈 하나로.
- **혼잡도(4순위)**: 기존 로직 그대로 — 식수가 median 이상인 코너 중
  피크타임 분당 서브(처리량)가 median보다 낮은 코너.

### 2. 문구 다듬기 — 담당자 지정 4단 형식

`_build_priority_prompt(finding)`이 선택된 이슈의 사실(영역/대상/근거/
개선방향 힌트)을 LLM에 넘기며 정확히 "핵심 개선 포인트: .../근거: .../
개선 방향: ..." 형식으로 답하도록 지시한다(사실에 없는 내용 금지, 과장·
단정 표현 금지 — 프롬프트 원문 그대로). `_parse_priority_response`가
그 3줄을 파싱해 `{area, point, evidence, direction}` dict로 만든다.
LLM 미설정·호출 실패 시 `_fallback_priority_result`가 같은 4개 필드를
결정론적으로 채운다(`point`는 "{대상} 개선이 필요합니다.", `evidence`/
`direction`은 판정 단계에서 이미 만들어 둔 문장 그대로) — §44 결론대로
LLM 실패가 카드를 죽이지 않는다.

`select_priority_finding()`이 `None`(4개 축 전부 유의미한 이슈 없음)을
반환하면 "데이터만으로 명확히 판단하기 어려우면 억지로 문제를 만들지
말고 '특이사항 없음'"이라는 지시를 그대로 따라 `{"status": "no_issue"}`를
반환한다.

### 3. 엔드포인트 — `backend/app/api/dashboard.py::improvement_points`

기존엔 최대 6개 포인트를 배열로 반환했지만, 이제 단일 객체를 반환한다:
```json
{"status": "no_issue"}
```
또는
```json
{"status": "issue", "axis": "satisfaction", "area": "만족도",
 "point": "그린미트 코너 개선이 필요합니다.",
 "evidence": "평균 만족도 3.16점 — 전체 코너 평균(4.00점)보다 낮습니다(누적 식수 125명).",
 "direction": "이 코너의 메뉴 구성이나 조리 품질을 점검해보세요."}
```
축이 VOE면 기존처럼 `voe_summary`(해당 카테고리 원문 코멘트 요약)를
덧붙인다 — 이 부분은 무변경.

**오케스트레이션 정리**: 예전엔 편성·운영 축의 문구를 새벽 배치
(`refresh_llm_analyses`)가 미리 계산해 `KIND_PLANNING_NOTICE` 캐시에
넣어 두고 화면이 읽기만 했다. 이제는 우선순위 판정 직후 그 결과를 바로
`summarize_priority_finding`으로 다듬으므로(요청당 LLM 호출 1회, 기존
VOE 코멘트 요약과 같은 비용), 이 캐시를 읽는 곳이 없어졌다 — 배치
단계·프롬프트 함수·폴백 함수·`KIND_PLANNING_NOTICE` 상수를 전부
`llm_analysis.py`에서 삭제했다(죽은 코드 방치 금지, §85/§227 관례).

### 4. 프론트 — `frontend/src/api/client.ts` + `HomePage.tsx`

`ImprovementPoint[]` 타입을 `ImprovementPriorityResult`(단일 객체,
`status`/`axis`/`area`/`point`/`evidence`/`direction`/`voe_summary`)로
교체. "개선 필요 포인트" 카드는 리스트(`<ul>` + `divide-y`)를 걷어내고
단일 항목 레이아웃(축 아이콘 배지 + "개선 필요 영역: .../핵심 포인트/
근거/개선 방향" 4줄)으로 재작성. §107이 추가했던 "시간 기준" 안내
문구는 이제 의미가 달라져(리스트가 아니라 우선순위 캐스케이드) "우선순위:
만족도 → VOE → 편성·운영 → 혼잡도 순으로 검토해 가장 급한 이슈 하나만
보여줍니다"로 교체했다. `status === "no_issue"`일 때는 기존과 같은
자리에 "특이사항 없음" 한 줄만(문구는 프롬프트 원문 그대로).

## 손대지 않는 것 (교차 확인)

- `corner_analysis`/`menu_performance`/`_compute_voe_by_category`/
  `_collect_planning_facts` — 전부 기존 계산 로직 그대로 재사용, 이번
  라운드는 그 결과를 어떻게 "고르고 보여줄지"만 바꿨다.
- `summarize_voe_comments`(VOE 카테고리 원문 코멘트 1~2문장 요약) —
  무변경, VOE 축이 선택됐을 때 그대로 재사용.
- `summarize_menu_trend`/`summarize_voe_briefing`(메뉴 하이라이트 원인,
  VOE AI 브리핑) — 이번 라운드와 무관, 무변경.
- `menu_highlights` 엔드포인트와 그 "원인" 캐시(`KIND_MENU_TREND`,
  §109에서 다룬 "특정하기 어렵다" 숨김 처리) — 무변경.
- `MenuPerformanceStats`/`DailyCornerStats` 등 하부 계산 테이블·배치
  스케줄 — 무변경, `refresh_llm_analyses`에서 편성 notice 단계만 삭제.

## 테스트/검증

- `backend/tests/test_improvement_points.py` 전면 재작성 — 4개
  `_find_*_finding` 각각의 선정/제외 조건(표본 게이트, 1건 무시, 근소한
  차이 무시 등)과 `select_priority_finding`의 캐스케이드 순서(1순위가
  있으면 나머지는 검토되지 않음, 전부 없으면 None)를 직접 검증. 최초
  구현에서 코너 단위 만족도 폴백이 근소한 차이(0.1점)에도 반응해 테스트가
  실패했다 — 5점 만점 기준 0.3점 미만 차이는 "억지로 문제를 만들지 말라"
  원칙에 따라 무시하도록 `_CORNER_SATISFACTION_GAP_THRESHOLD` 게이트를
  추가해 수정.
- `backend/tests/test_llm_analysis.py` — 삭제된 편성 notice 관련 테스트
  제거, `collect_planning_issues` 테스트는 test_improvement_points.py로
  이동(중복 제거).
- `backend/tests/test_api_ingest_and_analysis.py` — 기존 "3개 축이 배열에
  동시에 들어있다" 테스트를 "만족도가 우선순위를 가져가 혼잡도·VOE 조건이
  동시에 충족돼도 만족도 하나만 반환됨"과 "만족도 신호가 없을 때만 4순위
  혼잡도까지 내려감" 두 개로 교체 + "아무 이슈 없으면 no_issue" 신규 추가.
- `pytest` 전체 574개 통과(로컬 Postgres 기동 상태 유지, venv 재사용).
- `npx tsc -b` + `npx vite build` 클린.
- **로컬 uvicorn + vite dev 서버 + 실제 개발 DB로 Playwright 라이브
  검증**: `curl`로 실제 API 응답이 스펙 형식과 정확히 일치함을 먼저
  확인(만족도 축 — 그린미트 코너, 근거에 실제 수치 포함), 그다음 홈
  화면에서 새 카드가 "개선 필요 영역: 만족도" + 굵은 핵심 포인트 + 근거
  + 개선 방향 4줄로 렌더링됨을 라이트/다크 모드 둘 다 스크린샷으로
  확인(콘솔 에러 0건). `no_issue` 상태는 이 개발 DB의 실제 데이터로는
  재현이 안 돼(항상 어떤 축이든 이슈가 있음) 코드 리뷰 + 백엔드
  유닛테스트로 확인.
- 문서화(§110) 후 커밋·푸시.

## §111 — 소계/Take Out 표시 순서 · 메뉴 이력 검색 카드 삭제 · 저조 식수 규칙 실제 등장일 표시

### Context

담당자가 한 메시지로 3가지를 신고했다:
1. "코너별 조식/중식/석식 식수 현황"에서 "소계" 행이 Take Out보다 위에
   있어야 함 — 현재는 Take Out 아래에 있음.
2. "이번 주 메뉴 이력 검색(과거 만족도·코멘트)" 기능 삭제.
3. "주간 편성 규칙 검증"의 "최근 저조 식수(200식 이하) 재편성" 규칙이
   과거 저조했던 실제 날짜 대신 이번 주 재편성일과 같이 표시돼 마치
   "그 날짜에 저조했다"는 것처럼 보임(예: 실제로는 5/14에 143식이었는데,
   화면엔 7/14 재편성 슬롯 옆에 143식이 붙어 나옴) — 실제 등장일을
   보여줘야 함.

### 설계

**1. 소계/Take Out 순서** — `HomePage.tsx`의 표 `<tbody>`에서 "소계" 행을
"Take Out" 행보다 위로 옮겼다(take_in 코너 행들 → 소계 → Take Out → 합계).
백엔드 `corner_meal_type_headcount`가 계산하는 `subtotal`은 원래도
Take Out을 제외한 사내 코너 합이라(관련 로직 무변경) 순수 렌더링 순서만
바꿨다 — 소계 + Take Out = 합계라는 관계가 화면에서 자연스럽게 읽히도록.

**2. 메뉴 이력 검색 카드 삭제** — `HomePage.tsx`에서 `menuName`/
`searchedMenu` state, `menuHistory` 쿼리, "이번 주 메뉴 이력 검색(과거
만족도·코멘트)" `Card` 전체(검색 입력·버튼·표)를 삭제했다. `api.menuHistory`
클라이언트 함수 자체는 "금주 메뉴 과거 VOE" 집계(`weeklyVoeHistory`,
`Promise.all` 기반)가 여전히 쓰고 있어 `client.ts`는 무변경.

**3. 저조 식수 규칙 — 실제 등장일 표시** — 원인은 두 개의 서로 다른
헤드카운트 헬퍼가 있었기 때문: 기존 `_recent_avg_headcount_by_menu`는
180일 창 안의 **여러 등장일 평균**을 계산하는데, 화면은 그 평균 식수를
"이번 주 재편성 슬롯의 날짜"와 나란히 붙여 보여주고 있었다 — 두 값이
서로 다른 날짜의 정보인데 하나처럼 보인 것.

`backend/app/api/analysis.py`에 신규 헬퍼 `_last_appearance_headcount_by_menu(
db, menu_ids, history_start, history_end) -> dict[int, tuple[date, int]]`를
추가했다 — 메뉴별로 history 기간 안에서 **가장 최근 등장일 하루**와 그날의
실제 식수만 반환한다(날짜별 `MealLog` 카운트를 `menu_id, date(eaten_at)`로
묶어 최신 날짜만 남김). `weekly_menu_plan_rule_check`의 저조 식수 위반
블록이 이 헬퍼를 쓰도록 교체했고, 응답 필드도 `recent_avg_headcount`
(평균, 단일 숫자)에서 `last_appearance_date`/`last_appearance_headcount`
(실제 과거 등장일 + 그날 식수)로 바꿨다.

`_recent_avg_headcount_by_menu` 자체와 그 유일한 다른 호출부(`weekly_menu_rotation`
엔드포인트의 "재편성 Top5" 목록, `AnalysisPage.tsx`의 `r.recent_avg_headcount`
표시)는 이번 규칙과 무관한 별개 기능이라 손대지 않았다 — 그 기능은 의도적으로
평균을 원한다.

`frontend/src/api/client.ts`의 `LowHeadcountViolation` 인터페이스를
`last_appearance_date`/`last_appearance_headcount` 필드로 갱신하고,
`frontend/src/components/RuleCard.tsx`의 `buildLowHeadcountRuleCard`가
칩 라벨을 `"메뉴명(코너명, MM-DD에 N식)"`(등장이 없을 때) 또는
`"메뉴명(코너명, MM-DD에 N식 → MM-DD 재편성)"`(과거 저조일 → 이번 주
재편성일, 화살표로 명확히 구분)로 렌더링하도록 고쳤다.

### 손대지 않는 것 (교차 확인)

- 백엔드 `corner_meal_type_headcount`의 `subtotal`/`total` 계산 로직 —
  무변경, item 1은 순수 프론트 렌더링 순서만.
- `api.menuHistory` 클라이언트 함수·`GET /dashboard/menu-history/{name}`
  엔드포인트 — 무변경, "금주 메뉴 과거 VOE" 집계가 계속 사용.
- `_recent_avg_headcount_by_menu`와 `weekly_menu_rotation`의 "재편성
  Top5" 기능 — 무변경, 평균이 필요한 별개 기능.
- `menu_plan_rules.py`의 나머지 3개 규칙(해장/면류/매운 빨간국물) —
  무변경, 저조 식수 규칙만 대상.

### 테스트/검증

- `backend/tests/test_api_ingest_and_analysis.py`에 2개 신규 테스트:
  `test_weekly_menu_plan_rule_check_low_headcount_shows_actual_past_appearance_date`
  (7/14 재편성 슬롯 옆에 실제로는 61일 전 등장일이 표시되는지, 재편성일과
  다른지), `test_weekly_menu_plan_rule_check_low_headcount_uses_most_recent_appearance_only`
  (100일 전 300건 인기 등장 + 10일 전 3건 저조 등장이 섞여 있을 때, 평균이
  아니라 가장 최근 1회(10일 전, 3식)만 봐서 위반으로 잡히는지) — 둘 다
  통과.
- `pytest` 전체 578개 통과.
- `npx tsc -b` + `npx vite build` 클린(삭제된 카드가 쓰던 `QuadrantBadge`
  import 제거 필요 — 처리 완료).
- **실제 개발 DB + Playwright**: 코너별 조식/중식/석식 식수 현황 표에서
  소계 행이 Take Out 행보다 위에 오는 것을 스크린샷으로 확인, "이번 주
  메뉴 이력 검색" 카드가 화면에서 완전히 사라진 것을 확인(콘솔 에러 0건).

## §112 — 날씨 시나리오 예측 배수를 실측 데이터 기반으로 교체

### Context

담당자 질문: "시뮬레이션에서 날씨에 따른 추정치는 무슨 기준이야? 올해
데이터를 기준으로 분석한 결과를 보여줘야 함." 확인 결과 `simulation.py`의
`_WEATHER_MULTIPLIER`는 코드 주석에 이미 "v0 휴리스틱... 실측 근거 없음"
이라고 명시된 하드코딩 가정치 표였고(맑음 1.00/흐림 0.97/비 0.90/눈 0.85/
폭염 0.95/한파 0.95), `what_if()`(날씨 시나리오 예측 카드)와
`weekly_congestion_forecast()`(홈의 "금주 예상 식수") 둘 다 이 표를
그대로 곱해 쓰고 있었다.

### 설계

`Weather`(사용자에게 보여주는 6개 선택지: 맑음/흐림/비/눈/폭염/한파)와
`WeatherEvent`(실측 날씨를 분류하는 5개 유형, `weather_event.py`: 평상시/
비/폭설/폭염/한파)는 스키마가 다르다 — 관측 데이터(`DailyWeather`)에
구름량·일조량 필드가 없어 맑음과 흐림을 실측으로 구분할 방법이 없다.
그래서 맑음(기준선 1.0 그대로 유지)·흐림(v0 가정치 유지)은 손대지 않고,
`WeatherEvent`로 깔끔히 매핑되는 나머지 4개(비→RAIN, 눈→HEAVY_SNOW,
폭염→HEATWAVE, 한파→COLDWAVE)만 실측 배수로 계산한다.

`backend/app/api/simulation.py`에 `_data_driven_weather_multipliers(db,
meal_type) -> dict[Weather, float]`를 신규 추가:
1. 올해(1/1~오늘) `DailyWeather` 행을 전부 조회해 `classify_weather_event`로
   날짜별 `WeatherEvent`를 매긴다.
2. 같은 기간 `DailyCornerStats`를 `meal_type`으로 필터해 날짜별 전체
   코너 합산 식수를 구한다.
3. 날씨유형별로 그 날짜들의 식수를 모아 평균을 낸다. "평상시" 평균 대비
   각 유형 평균의 비율이 그 유형의 실측 배수가 된다(예: 비 오는 날 평균이
   평상시의 절반이면 배수 0.5).
4. **표본 부족 게이트** — 평상시 표본 자체가 `_MIN_WEATHER_EVENT_SAMPLE_DAYS`
   (5일) 미만이면 전부 v0로 폴백하고, 개별 유형(비/눈/폭염/한파)도 표본이
   5일 미만이면(예: 아직 그 해에 폭설이 없었던 경우) 그 유형만 v0 값을
   유지한다 — 하루이틀 표본으로 과적합된 배수를 쓰지 않기 위해(§110의
   `_CORNER_SATISFACTION_GAP_THRESHOLD` 게이트와 같은 원칙). 요청 하나
   에서 반복 호출될 수 있어 `db.info`에 캐시한다.

`what_if()`(코너 루프 밖에서 `meal_type` 하나로 한 번 계산)와
`weekly_congestion_forecast()`(날짜 루프 밖에서 한 번 계산)의 두 호출부
모두 `_WEATHER_MULTIPLIER[weather]` 직접 참조를
`_data_driven_weather_multipliers(db, meal_type)[weather]`로 교체했다.
두 엔드포인트의 응답 `"note"` 필드도 "날씨 배수는 올해 실측 데이터 기반
(표본 부족 유형은 v0 가정치로 대체) — 신메뉴/사내행사/연휴 전후 배수는
아직 v0 휴리스틱"으로 갱신해, 무엇이 실측 기반이고 무엇이 아직 가정치인지
명확히 구분했다.

`AnalysisPage.tsx`의 "날씨 시나리오 예측" 카드 캡션도 이 기준을 직접
설명하도록 확장했다("비·눈·폭염·한파 배수는 올해 실측 날씨·식수 데이터를
대조해 계산하며, 표본이 부족한 유형은 잠정 가정치로 대체됩니다. 맑음·흐림은
관측 데이터에 구름량이 없어 실측으로 구분할 수 없어 가정치를 유지합니다.")
— 담당자 질문에 화면에서 바로 답하도록.

### 손대지 않는 것 (교차 확인)

- 맑음(1.00 고정)·흐림(v0 0.97 유지) — 구름량 미관측으로 실측 구분 불가,
  의도적으로 v0 유지.
- 신메뉴 배수(`_MENU_QUADRANT_MULTIPLIER`/`_DEFAULT_NEW_MENU_MULTIPLIER`),
  사내행사 배수(0.90 고정), 연휴 전후 배수(`_HOLIDAY_ADJACENCY_MULTIPLIER`)
  — 이번 요청은 "날씨" 배수로 범위가 한정, 나머지는 여전히 v0 휴리스틱
  (주석·note 문구에 명시).
- `_baseline_headcount`/`_fetch_classification_history`(평일/휴일/
  패밀리데이 분류별 최근 이력 평균) — 무변경, 배수를 곱하는 대상인
  베이스라인 자체는 그대로.
- `weather_event.py`의 `classify_weather_event`/`WeatherEvent` — 무변경,
  §71에서 만든 기존 순수 함수를 그대로 재사용.

### 테스트/검증

- `backend/tests/test_api_ingest_and_analysis.py`에 2개 신규 테스트:
  `test_what_if_uses_data_driven_weather_multiplier_when_sample_sufficient`
  (평상시 5일(식수 20)·비 5일(식수 10) 실측을 시딩하면 예측 식수가
  베이스라인 × 실측 비율 0.5로 나오는지 — v0(0.90)를 썼다면 나오지 않을
  값), `test_what_if_falls_back_to_v0_weather_multiplier_when_sample_insufficient`
  (비 표본이 2일뿐이면 v0(0.90)로 폴백하는지) — 둘 다 통과. 기존
  `test_what_if_applies_cloudy_weather_multiplier`/
  `test_what_if_applies_snow_weather_multiplier`(실측 날씨 데이터를 심지
  않는 테스트)도 그대로 통과 — 실측 데이터가 없으면 전부 v0로 폴백하는
  경로가 검증됨.
- `pytest` 전체 578개 통과.
- `npx tsc -b` + `npx vite build` 클린.
- **실제 개발 DB + Playwright**: 개발 DB에는 2026년 6~8월 실측
  `daily_weather` 25건이 있어(6/1~6/5 비, 6/6~6/10 맑음 등) 표본 조건을
  이미 충족 — `curl`로 `/api/simulation/what-if`를 직접 호출해 응답의
  `"note"`가 새 문구("실측 데이터 기반...")로 바뀐 것을 확인. 프론트
  시뮬레이션 탭에서 새 캡션 문구가 정확히 렌더링되는 것을 스크린샷으로
  확인(콘솔 에러 0건). 실측 비율이 항상 "비가 오면 식수가 준다"는 직관과
  일치하지는 않았는데(개발 DB의 합성 데이터 특성상), 이는 코드 버그가
  아니라 설계 의도대로 "실제 데이터가 보여주는 그대로"를 반영한 결과다.
- 문서화(§111/§112) 후 커밋·푸시.

## §113 — 식수 추이 차트 숫자 표기 방식 개선(막대 구간·라인 라벨 + 천 단위 콤마)

### Context

담당자가 참고 이미지(외부 도구로 만든 코너별 누적 막대 + 총식수 꺾은선
차트, 각 막대 구간 안에 값이 숫자로 찍혀 있고 라인 위에도 매 지점마다
값이 찍혀 있으며 천 단위 콤마가 적용된 형태)를 주고 "식수 추이 그래프
이런 식으로 바꿔줘 숫자 표기 방식 등"이라고 요청했다. 홈의 "식수 추이"
차트(`headcountTrendOption`, §80 코너별 누적 막대 + §100 총식수 라인)는
구조는 이미 같았지만 숫자 라벨이 전혀 없었다(값은 툴팁을 호버해야만
보였고, 총식수 라인은 §100에서 추가한 "최고 N명" 핀 하나만 라벨이 있었다).

### 설계

`frontend/src/pages/HomePage.tsx`의 `headcountTrendOption`만 수정(백엔드
무변경 — 이미 내려주는 데이터를 다르게 그리기만 함):
- 코너/끼니/회사구분별 누적 막대 시리즈마다 `label: { show: true,
  position: "inside", color: "#fff", formatter: ... }`를 추가해 각 구간
  안에 흰 숫자로 값을 표기한다. 0인 구간은 formatter가 빈 문자열을
  반환해 숫자가 겹쳐 보이지 않게 한다.
- 총식수 라인 시리즈에 `label: { show: true, position: "top", ... }`를
  추가해 매 지점 위에 값을 표기한다. §100에서 추가했던 "최고 N명" 핀
  콜아웃(`markPoint`)은 이제 모든 점에 라벨이 붙어 중복이라 제거했다.
- 모든 숫자 라벨과 툴팁, y축 라벨에 `toLocaleString()`을 적용해 천 단위
  콤마를 표기한다(참고 이미지의 "3,331" 같은 표기 방식).
- 라벨이 늘어난 만큼 차트 높이를 320px → 380px로 늘리고, 핀이 없어져
  필요 없어진 상단 여백(top: 88 → 64)을 줄였다.

### 손대지 않는 것 (교차 확인)

- 백엔드 `headcount_trend`/`_period_bucket` — 무변경, 순수 프론트
  렌더링 변경.
- 참고 이미지의 x축 "MM.DD(요일)" 형식, 주말/공휴일 강조색 — 이번
  요청은 "숫자 표기 방식"에 집중된 요청이라 범위에서 제외했다. 현재
  x축은 granularity(일/주/월)에 따라 형식이 달라져(§104) 요일을 항상
  붙일 수 없는 경우가 있다 — 필요하면 별도 라운드에서 논의.
- 참고 이미지의 어두운 배경 — 이 앱은 이미 OS 설정 기반 다크모드를
  지원한다(§104 수동 토글 포함), 차트만 강제로 어둡게 하지 않는다.
- 코너 색상 팔레트(`--series-1~8`), 범례, 필터 UI — 무변경.

### 테스트/검증

- 백엔드 변경이 없어 `pytest` 재실행 불필요.
- `npx tsc -b` + `npx vite build` 클린.
- **실제 개발 DB + Playwright**: 홈 화면에서 조회 기간을 좁혀(2026-07-20
  ~07-26, 코너별 보기) 막대 구간 안에 흰 숫자(예: "16", "15")가, 총식수
  라인 위에 굵은 숫자(예: "31")가 표기되는 것을 스크린샷으로 확인
  (콘솔 에러 0건).
- 문서화(§113) 후 커밋·푸시.

## §114 — 날씨 시뮬레이션 캡션 축소 + "편성 빈도 × 성과" 기능 삭제

### Context

담당자가 두 가지를 요청했다: "날씨 시뮬레이션에서 지저분한 주석 제거",
"메뉴 편성운영에서 편성빈도성과 기능 제거".

**날씨 시뮬레이션 캡션**: §112에서 담당자의 "날씨 배수 기준이 뭐냐"는
질문에 답하려고 캡션에 실측 데이터 기반 계산 방식·표본 부족 폴백·맑음/
흐림 미구분 사유까지 3문장을 통째로 얹었는데, 담당자 기준으로는 화면에
쓰기엔 과한 구현 설명이었다. 캡션을 다시 한 문장으로 줄인다 — 배수가
실측 데이터 기반이라는 사실만 남기고, 나머지 구현 디테일은 이번 라운드
문서(§112)에 이미 기록돼 있으니 화면에서는 뺀다.

**"편성 빈도 × 성과"**: §86에서 만들어진 기능(그 메뉴 자체의 평균 편성
주기가 짧은 메뉴 Top10 / 평균 주기 대비 오래 안 나온 메뉴 목록)을
메뉴 편성·운영 화면에서 완전히 제거한다. "재편성 점검"(RotationCheckPanel,
재편성 Top5 + 편성 기준 초과 목록)과는 별개 기능이라 그쪽은 그대로 둔다.

### 설계

**캡션**: `frontend/src/pages/AnalysisPage.tsx`의
`WeatherScenarioForecastSection` 캡션을 "날씨·끼니·날짜를 골라 예상
식수를 시뮬레이션합니다(추정치). 배수는 올해 실측 데이터 기반입니다."
두 문장으로 줄였다. 표본 부족 폴백, 맑음/흐림 미구분 사유 등 구현
디테일은 화면에서 제거(문서 §112에는 그대로 남아있음).

**"편성 빈도 × 성과" 삭제** — 프론트/백엔드/테스트 전부에서 이 기능
전용 코드만 제거하고, "재편성 점검"과 공유하는 코드는 손대지 않았다:

- `frontend/src/pages/AnalysisPage.tsx`: `MenuPlanPerformanceSection`
  컴포넌트(§86 도입 컨텍스트 주석 포함)와 그 전용 헬퍼
  `PLAN_PERIOD_OPTIONS`/`usePlanPeriod`/`OVERDUE_PREVIEW_COUNT`를 통째로
  삭제. `MenuPlanningPage`에서 `<MenuPlanPerformanceSection />` 렌더
  호출 제거.
- `frontend/src/api/client.ts`: `ShortCycleMenuRow`/`OverdueMenuRow`
  인터페이스와 `MenuRotationResponse`의 `shortest_cycle_menus`/
  `overdue_menus` 필드 삭제. `items`/`overused` 필드와 `MenuRotationRow`
  (재편성 Top5가 씀)는 그대로.
- `backend/app/api/analysis.py`: `weekly_menu_rotation` 엔드포인트
  자체는 재편성 점검이 계속 쓰므로 유지하되, MAIN 전용 재빌드 블록
  (`main_planned`/`dates_by_corner_menu_main`/`shortest_cycle_menus`/
  `overdue_menus`)과 응답의 `"shortest_cycle_menus"`/`"overdue_menus"`
  키만 제거. `find_overdue_menus`/`rank_by_shortest_cycle` import 제거.
- `backend/app/services/menu_rotation.py`: `ShortCycleMenu`/
  `rank_by_shortest_cycle`/`OverdueMenu`/`find_overdue_menus`(§86 전용
  섹션 전체, 파일 끝 262~351행)를 삭제. `average_interval_days`/
  `LONG_ABSENT_RATIO`/`count_in_window`/`is_over_frequency` 등은 다른
  함수(`classify_rotation`, `items` 계산)와 공유라 그대로 둠.
- `backend/tests/test_menu_rotation.py`: §86 전용 테스트 블록(272~341행,
  `rank_by_shortest_cycle`/`find_overdue_menus` import 포함) 삭제.
- `backend/tests/test_api_ingest_and_analysis.py`:
  `test_weekly_menu_rotation_reports_shortest_cycle_menus`/
  `test_weekly_menu_rotation_reports_overdue_menus` 삭제.

### 손대지 않는 것 (교차 확인)

- `RotationCheckPanel`("재편성 점검" 탭, 재편성 Top5 + 편성 기준 초과
  목록) — `weekly_menu_rotation`의 `items`/`overused` 필드와
  `classify_rotation`을 그대로 씀, 무변경.
- `menu_rotation.py`의 `average_interval_days`/`LONG_ABSENT_RATIO`/
  `build_corner_menu_dates`/`count_in_window`/`is_over_frequency`/
  `max_in_window_for_role`/`find_overused_menus`/`classify_rotation` —
  전부 재편성 점검이 계속 쓰는 공유 로직, 무변경.
- `WeeklyMenuReviewTab`/`MenuDuplicationCheckSection`/`MenuComboSection`
  (메뉴 편성·운영 화면의 나머지 3개 섹션) — 무변경.
- `WeatherCorrelationSection`(날씨유형·계절 랭킹, 시뮬레이션 탭의 다른
  카드) — 캡션이 이미 짧아 손대지 않음.
- §112가 추가한 `_data_driven_weather_multipliers` 계산 로직 자체 —
  무변경, 화면 캡션 문구만 줄였다.

### 테스트/검증

- `pytest` 전체 569개 통과(578 − 9: `test_menu_rotation.py`에서 7개,
  `test_api_ingest_and_analysis.py`에서 2개 삭제).
- `npx tsc -b` + `npx vite build` 클린.
- `grep`으로 `shortest_cycle`/`overdue_menu`/`rank_by_shortest_cycle`/
  `find_overdue_menus`/`MenuPlanPerformanceSection`/`ShortCycleMenuRow`/
  `OverdueMenuRow` 전체 검색 — 코드베이스에 잔존 참조 0건 확인.
- **실제 개발 DB + Playwright**: 메뉴 편성·운영 화면에서 "편성 빈도"
  텍스트가 화면에 전혀 없는 것을 확인(스크린샷 — "메뉴 중복 점검" 카드
  바로 다음에 "부찬 조합별 만족도 비교" 카드가 이어짐, 그 사이 빈 공간
  없음). 시뮬레이션 탭에서 캡션이 두 문장으로 줄어든 것을 확인. 콘솔
  에러 0건.
- 문서화(§114) 후 커밋·푸시.
