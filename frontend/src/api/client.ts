// 백엔드 API 클라이언트. 개발 중에는 vite.config.ts의 /api 프록시를 통해
// FastAPI(기본 8000포트)로 전달된다. 사내 배포 시에는 같은 오리진에서 서빙되므로
// BASE_URL을 "/api"로 고정해도 된다 (docker-compose에서 리버스 프록시 설정 시 조정).
const BASE_URL = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API 오류 ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

function qs(
  params: Record<string, string | number | boolean | string[] | number[] | undefined | null>,
): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      // corner_ids처럼 숫자 배열도 넘어온다 — FastAPI는 같은 키 반복을 리스트로 받는다.
      for (const item of v) usp.append(k, String(item));
    } else {
      usp.set(k, String(v));
    }
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ---- 타입 (backend/app/schemas, models.enums와 대응) ----

export type MealType = "조식" | "중식" | "석식";
export type Classification = "평일" | "주말+공휴일" | "패밀리데이";
export type Quadrant = "인기메뉴" | "숨은강자" | "개선시급" | "퇴출후보" | "표본부족";
export type Weather = "맑음" | "비" | "폭염" | "한파";

export interface WeeklySummaryDay {
  date: string;
  classification: Classification;
  headcount: number;
}

export interface MenuHistoryEntry {
  period_start: string;
  period_end: string;
  adjusted_score: number | null;
  evaluation_count: number;
  quadrant: Quadrant | null;
}

export interface VoeCluster {
  cluster_label: string;
  representative_comment: string | null;
  comment_count: number;
  keywords: string[];
}

export interface MenuCommentEntry {
  eaten_at: string;
  taste_score: string | null;
  comment: string;
}

export interface VoeCategoryComment {
  eaten_at: string;
  corner_name: string | null;
  menu_name: string | null;
  comment: string;
}

export interface VoeCategoryRow {
  category: string;
  count: number;
  comments: VoeCategoryComment[];
}

export interface VoeByCategoryResponse {
  total_comments: number;
  categories: VoeCategoryRow[];
}

export interface CornerAnalysisRow {
  corner_id: number;
  corner_name: string;
  is_diet_corner: boolean;
  headcount_total: number;
  avg_taste_score: number | null;
  avg_peak_throughput_per_min: number | null;
}

export interface MenuTrendEntry {
  menu_id: number;
  menu_name: string;
  corner_name: string | null;
  recent_score: number;
  prior_score: number;
  delta: number;
  evaluation_count: number;
  date: string; // 이 메뉴가 마지막으로 나온 주의 월요일(ISO)
  // ⚠️ 아래 둘은 **날짜가 아니라 ISO 주의 월요일**이다 — 메뉴가 매주 나오지
  // 않으므로 달력 주가 아니라 "그 메뉴가 나온 주"끼리 비교한다(§28).
  recent_week: string;
  prior_week: string;
  prior_evaluation_count: number;
  // 새벽 배치가 미리 계산해 둔 만족도 변화 원인. 배치 전이거나 대상이 아니면 없다.
  cause?: string;
  cause_computed_at?: string;
}

export interface NewMenuEntry {
  menu_id: number;
  menu_name: string;
  corner_name: string | null;
  adjusted_score: number | null;
  evaluation_count: number;
  days_since_introduction: number;
  needs_attention: boolean;
  is_manual: boolean;
}

export interface MenuHighlightsResponse {
  rising: MenuTrendEntry[];
  falling: MenuTrendEntry[];
  new_menus: NewMenuEntry[];
}

export interface ImprovementPoint {
  axis: "congestion" | "satisfaction" | "voe" | "planning";
  title: string;
  detail: string;
  severity: "warning" | "critical";
  voe_summary?: string | null;
}

export interface CornerTrendRow {
  period: string;
  corner_id: number;
  corner_name: string;
  is_diet_corner: boolean;
  headcount: number;
  avg_taste_score: number | null;
  avg_peak_throughput_per_min: number | null;
}

export interface CornerMainMenuByDateRow {
  corner_id: number;
  plan_date: string;
  menu_name: string;
}

export type TrendDirection = "상승" | "유지" | "하락";

export interface MenuPerformanceRow {
  menu_id: number;
  menu_name: string;
  corner_name: string | null;
  appearance_count: number;
  total_headcount: number;
  evaluation_count: number;
  evaluation_rate: number | null;
  raw_score: number | null;
  adjusted_score: number | null;
  share_of_traffic: number | null;
  quadrant: Quadrant | null;
  // 2026-07: 4분면 분류가 이 두 신호(직전 대비 만족도 추세, 로열티)에도
  // 의존하게 됨 — classifyQuadrantClient가 백엔드 로직을 그대로 미러링하려면
  // 슬라이더로 조절 안 되는 이 값들을 서버에서 받아와야 한다.
  satisfaction_trend: TrendDirection | null;
  has_loyal_following: boolean;
}

export type Granularity = "daily" | "weekly" | "monthly";

export interface DivisionRow {
  period: string;
  division: string; // 본사 | 계열사 | 기타
  headcount: number;
}

export interface WeeklyForecastDay {
  target_date: string;
  classification: string;
  holiday_adjacency: string; // 연휴 전 | 연휴 후 | 해당 없음
  applied_multiplier: number;
  total_predicted_headcount: number;
  corners: CongestionForecastRow[];
}

export interface WeeklyForecastResponse {
  period_start: string;
  period_end: string;
  meal_type: MealType;
  weather: Weather;
  has_company_event: boolean;
  days: WeeklyForecastDay[];
  note: string;
}

export interface CornerListRow {
  corner_id: number;
  corner_name: string;
  is_diet_corner: boolean;
}

export type Division = "본사" | "계열사" | "기타";
// 현황 통합 추이 차트에서 "무엇을 선으로 그릴지" — 필터(끼니/코너/회사구분)와 별개 축.
export type HeadcountGroupBy = "total" | "corner" | "division" | "meal_type";

export interface HeadcountTrendRow {
  period: string;
  series_key: string;
  series_label: string;
  headcount: number;
}

// §75: 날짜별 원자료(가공된 교차표 아님) — 평일/주말+공휴일/패밀리데이 구분은
// classification 값으로 프론트에서 체크박스 필터링한다.
export interface WeatherHeadcountTimelineDay {
  stat_date: string;
  classification: Classification;
  headcount: number;
  precip_mm: number | null;
}

export interface WeatherHeadcountTimelineResponse {
  days: WeatherHeadcountTimelineDay[];
  days_missing_weather: number;
}

// §71: 메인메뉴 × 날씨유형(비/폭설/폭염/한파) 인기 랭킹. 부찬은 대상이 아니다.
export type WeatherEvent = "비" | "폭설" | "폭염" | "한파";

export interface MenuWeatherEventRow {
  menu_id: number;
  menu_name: string | null;
  event_avg_headcount: number;
  event_days: number;
  diff_vs_normal: number | null;
  low_sample: boolean;
  // §75: 이 메뉴가 그 유형을 겪은 날들의 실측치(강수량/적설/기온) 평균 —
  // 분류 결과를 실측값과 나란히 두고 검증할 수 있게. 실측치가 없으면 null.
  actual_avg: number | null;
}

export interface MenuWeatherEventRankingResponse {
  event: WeatherEvent;
  rows: MenuWeatherEventRow[];
  // §72: 그 기간 daily_weather에 snow_cm/max_temp_c/min_temp_c가 단 하나도
  // 없으면 true — "그런 날이 없어서"가 아니라 "재백필이 안 돼서" 폭설/폭염/
  // 한파가 안 나온다는 뜻이라 화면에서 구분해서 안내해야 한다.
  extended_fields_missing: boolean;
  // §75: actual_avg 열의 헤더 라벨(예: "평균 강수량(mm)"). 이벤트별로 다르다.
  actual_metric_label: string | null;
}

// §81: 메뉴별 일별 식수 × 기온/강수량 상관관계 랭킹. weather-event-ranking과
// 달리 임계값 범주가 아니라 연속값 상관계수(-1~1)를 낸다.
export type WeatherCorrelationMetric = "max_temp_c" | "precip_mm";

export interface MenuWeatherCorrelationRow {
  menu_id: number;
  menu_name: string | null;
  sample_size: number;
  correlation: number;
}

export interface MenuWeatherCorrelationRankingResponse {
  period_start: string;
  period_end: string;
  metric: WeatherCorrelationMetric;
  metric_label: string;
  min_days: number;
  rows: MenuWeatherCorrelationRow[];
}

// predicted-impact의 weather_reference — 슬롯 상세에서 그 메인메뉴 하나의
// 평상시 대비 날씨유형별(평상시 포함, 겪은 유형만) 참고치.
export interface MenuWeatherReferenceRow {
  event: "평상시" | WeatherEvent;
  avg_headcount: number;
  day_count: number;
  diff_vs_normal: number | null;
  low_sample: boolean;
}

// §72: 메인메뉴 × 계절(봄/여름/가을/겨울) 인기 랭킹 — "냉면은 여름에,
// 팥죽은 겨울에" 같은 계절 음식 패턴 참고용. 비교 기준이 날씨유형과 다르다
// (평상시 대비가 아니라 전체 기간 평균 대비 — 계절엔 "평상시" 같은 기본
// 그룹이 없어서).
export type Season = "봄" | "여름" | "가을" | "겨울";

export interface MenuSeasonRow {
  menu_id: number;
  menu_name: string | null;
  season_avg_headcount: number;
  season_days: number;
  diff_vs_overall: number | null;
  low_sample: boolean;
}

export interface MenuSeasonRankingResponse {
  season: Season;
  rows: MenuSeasonRow[];
}

export interface TasteProfile {
  employee_id: string;
  profile_vector: number[];
  dimensions: string[];
  sample_size: number;
  cluster_label: string | null;
}

export interface TasteCluster {
  id: number;
  label: string;
  size: number;
  centroid_vector: number[];
  dimensions: string[];
  avg_satisfaction: number | null;
  top_menus: string[];
  dominant_corner: string | null;
}

export interface MenuAffinityRow {
  menu_name: string;
  co_count: number;
  lift: number;
}

export interface CornerCoreLayerSummaryRow {
  corner_id: number;
  corner_name: string;
  core_employee_count: number;
  non_core_employee_count: number;
}

export interface MenuThroughputRow {
  menu_id: number;
  menu_name: string | null;
  avg_throughput: number;
  day_count: number;
}

export interface CornerMenuThroughputResponse {
  corner_id: number;
  corner_name: string;
  overall_avg_throughput: number | null;
  menus: MenuThroughputRow[];
}

export type FoodVectorSource = "규칙기반" | "LLM추정" | "관리자수동";

export interface MenuFoodVectorRow {
  menu_id: number;
  menu_name: string;
  corner_name: string | null;
  food_vector: number[] | null;
  dimensions: string[];
  source: FoodVectorSource | null;
}

export interface AverageFoodVectorResponse {
  dimensions: string[];
  labels_ko: Record<string, string>;
  average: number[];
  sample_size: number;
  bias_description: string | null;
}

export interface WeeklyMenuPlanItem {
  plan_id: number;
  menu_id: number;
  menu_name: string;
  role_source: FoodVectorSource; // "규칙기반" | "LLM추정" | "관리자수동" — food_vector와 동일한 3값
}

export interface WeeklyMenuSlot {
  plan_date: string;
  corner_id: number;
  corner_name: string;
  meal_type: MealType;
  main: WeeklyMenuPlanItem | null;
  sides: WeeklyMenuPlanItem[];
  // 건강가든은 식단표 엑셀에 없어 담당자가 화면에서 텍스트로 입력한다(2026-08).
  health_garden: WeeklyMenuPlanItem[];
  feedback_deadline: string;
  is_past_deadline: boolean;
}

// 메뉴 회전 이력 (2순위, 2026-08) — 같은 메뉴가 너무 자주 편성되는지 판정.
export type RotationFlag =
  | "같은 날 중복"
  | "재편성 과다"
  | "평소보다 이름"
  | "적정"
  | "오랜만"
  | "이력 없음";

export interface MenuRotationRow {
  plan_date: string;
  corner_id: number;
  corner_name: string;
  meal_type: MealType;
  menu_id: number;
  menu_name: string;
  menu_role: string; // "메인" | "부찬" | "건강가든"
  flag: RotationFlag;
  gap_days: number | null;
  avg_interval_days: number | null;
  previous_date: string | null;
  // 횟수 기준(담당자: "3개월에 2회까지는 무난") — 간격 기준과 별개 축이다.
  window_count: number;
  window_max: number;
  over_frequency: boolean;
  // §81: 메뉴 중복점검 재설계 — Top5/기준 미달 목록에 만족도·식수를 같이 보여준다.
  avg_satisfaction: number | null;
  recent_avg_headcount: number | null;
}

export interface MenuRotationResponse {
  period_start: string;
  period_end: string;
  lookback_days: number;
  min_rotation_gap_days: number;
  rotation_window_days: number;
  items: MenuRotationRow[];
  overused: { menu_name: string; menu_role: string; count: number; dates: string[] }[];
}

// 자주 반복되는 부찬 랭킹 — 담당자가 고른 임의 기간 하나로 코너 안 고유 날짜
// 기준 등장 횟수를 매긴다(2026-08, "부찬 중복 볼 때 보기가 너무 불편함" 신고).
export interface RepeatedSideDish {
  corner_name: string;
  menu_name: string;
  menu_role: string; // "부찬" | "건강가든"
  count: number;
  dates: string[];
  avg_main_satisfaction: number | null;
}

export interface RepeatedSideDishResponse {
  period_start: string;
  period_end: string;
  corner_id: number | null;
  items: RepeatedSideDish[];
}

export interface SideDishPairing {
  plan_date: string;
  corner_name: string;
  meal_type: MealType;
  main_menu_name: string | null;
  main_avg_satisfaction: number | null;
}

export interface SideDishDetailResponse {
  menu_name: string;
  corner_name: string;
  period_start: string;
  period_end: string;
  pairings: SideDishPairing[];
}

// 슬롯 내 재료·특성 중복 진단 (2026-08). menu_rotation과 축이 다르다 —
// 저쪽은 "이 메뉴 최근에 또 내보내지 않았나", 이쪽은 "이 한 끼 구성이 겹치지 않나".
export interface IngredientClash {
  menu_a: string;
  menu_b: string;
  shared: string[];
}

export interface VectorClash {
  menu_a: string;
  menu_b: string;
  dimension: string;
  label_ko: string;
  value_a: number;
  value_b: number;
}

export interface CombinationCheckSlot {
  plan_date: string;
  corner_id: number;
  corner_name: string;
  meal_type: MealType;
  main: string | null;
  sides: string[];
  health_garden: string[];
  ingredient_clashes: IngredientClash[];
  vector_clashes: VectorClash[];
  untagged: string[];
}

export interface CombinationCheckResponse {
  period_start: string;
  period_end: string;
  slots: CombinationCheckSlot[];
  untagged_menu_count: number;
}

// §77~§78: 주간 식단표 규칙 검증 — 해장/면류/매운(빨간국물)은 §78부터 한 주
// 합산이 아니라 요일별(하루 기준, 주중만) 판정이라 날짜별 결과 배열로 온다.
// 최근 식수 200식 이하 재편성(low_headcount_reuse)은 요일 개념이 아니라
// 메뉴 단위라 그대로 위반 목록 하나.
export interface MenuPlanRuleMatch {
  menu_name: string;
  corner_id: number;
  corner_name: string;
  plan_date: string;
}

export interface DailyMenuPlanRuleResult {
  plan_date: string;
  ok: boolean;
  count: number;
  limit: number | null;
  matches: MenuPlanRuleMatch[];
}

export interface LowHeadcountViolation {
  menu_name: string;
  corner_name: string;
  recent_avg_headcount: number;
}

export interface WeeklyMenuPlanRuleCheckResponse {
  period_start: string;
  period_end: string;
  hangover: DailyMenuPlanRuleResult[];
  noodle: DailyMenuPlanRuleResult[];
  spicy_red_broth: DailyMenuPlanRuleResult[];
  low_headcount_reuse: { ok: boolean; violations: LowHeadcountViolation[] };
}

export interface PlannedHeadcountRankingRow {
  plan_date: string;
  meal_type: MealType;
  corner_name: string;
  menu_name: string;
  recent_avg_headcount: number | null;
}

export interface WeeklyMenuPlannedHeadcountRankingResponse {
  period_start: string;
  period_end: string;
  rows: PlannedHeadcountRankingRow[];
}

export interface ComboSpreadEntry {
  sides: (string | null)[];
  avg_satisfaction: number | null;
  day_count: number;
}

export interface ComboSpreadRow {
  menu_id: number;
  menu_name: string | null;
  combo_count: number;
  spread: number;
  best: ComboSpreadEntry;
  worst: ComboSpreadEntry;
}

export interface ComboSpreadResponse {
  period_start: string;
  period_end: string;
  corner_id: number | null;
  min_day_count: number;
  items: ComboSpreadRow[];
}

export type PlanningAction =
  | "감편 검토"
  | "증편 후보"
  | "주력 유지"
  | "현행 유지"
  | "표본 부족"
  | "취식 기록 없음";

export interface PlanPerformanceRow {
  menu_id: number;
  menu_name: string;
  plan_count: number;
  total_headcount: number;
  headcount_per_plan: number;
  evaluation_count: number;
  avg_satisfaction: number | null;
  action: PlanningAction;
}

export interface PlanPerformanceResponse {
  period_start: string;
  period_end: string;
  median_headcount_per_plan: number;
  median_satisfaction: number;
  items: PlanPerformanceRow[];
  matching: { matched: number; plan_only: string[]; log_only: string[] };
}

export interface WeeklyMenuFeedbackRow {
  id: number;
  plan_date: string;
  corner_id: number;
  corner_name: string | null;
  comment: string;
  created_at: string;
}

export interface MenuComboRow {
  sides: (string | null)[];
  day_count: number;
  avg_satisfaction: number | null;
  avg_headcount: number;
  nutrition_profile: Record<string, number>;
}

export interface MenuCombinationsResponse {
  menu_id: number;
  menu_name: string;
  combos: MenuComboRow[];
}

interface PredictedNumbers {
  plan_id: number;
  plan_date: string;
  meal_type: MealType;
  corner_id: number;
  corner_name: string | null;
  menu_id: number;
  menu_name: string | null;
  main_menu: {
    menu_id: number;
    menu_name: string | null;
    adjusted_score: number | null;
    total_headcount: number | null;
    evaluation_count: number | null;
  };
  combo_history: { day_count: number; avg_satisfaction: number | null; avg_headcount: number } | null;
  prediction: {
    predicted_headcount: number;
    predicted_share: number;
    menu_share_of_traffic: number | null;
    corner_avg_share_of_traffic: number | null;
    throughput_ratio: number | null;
    expected_wait_minutes: number | null;
  };
}

export type PredictedNumbersRow = PredictedNumbers;

export interface PredictedImpactResponse extends PredictedNumbers {
  summary_comment: string;
  // §71: 이 슬롯 메인메뉴의 날씨유형별 참고치 — predicted-impact-summary(대량
  // 조회)엔 없다(쿼리 비용 때문에 단건 전용, LLM 코멘트와 같은 이유).
  weather_reference: MenuWeatherReferenceRow[];
}

export interface WhatIfCornerResult {
  corner_id: number;
  corner_name: string;
  baseline_headcount: number;
  predicted_headcount: number;
}

export interface WhatIfResponse {
  target_date: string;
  classification: Classification;
  corners: WhatIfCornerResult[];
  note: string;
}

export interface CongestionForecastRow {
  corner_id: number;
  corner_name: string;
  predicted_headcount: number;
  expected_peak_headcount: number;
  avg_peak_throughput_per_min: number | null;
  expected_wait_minutes: number | null;
  planned_menu_id: number | null;
  menu_popularity_multiplier: number | null;
}

export interface CongestionForecastResponse {
  target_date: string;
  meal_type: MealType;
  corners: CongestionForecastRow[];
}

export interface VoeBriefingResponse {
  has_clusters: boolean;
  briefing: string | null;
  briefing_computed_at: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

// ---- API 함수 ----

export const api = {
  weeklySummary: (params: {
    start_date?: string;
    end_date?: string;
    classification?: Classification;
    meal_types?: MealType[];
  }) => request<WeeklySummaryDay[]>(`/dashboard/weekly-summary${qs(params)}`),

  menuHistory: (menuName: string) =>
    request<MenuHistoryEntry[]>(`/dashboard/menu-history/${encodeURIComponent(menuName)}`),

  voeClusters: (period: string) => request<VoeCluster[]>(`/dashboard/voe-clusters${qs({ period })}`),

  recomputeVoeClusters: (period: string) =>
    request<{ clusters_created: number }>(`/dashboard/voe-clusters/recompute${qs({ period })}`, {
      method: "POST",
    }),

  voeBriefing: (period: string) => request<VoeBriefingResponse>(`/dashboard/voe-briefing${qs({ period })}`),

  recomputeVoeBriefing: (period: string) =>
    request<{ briefing: string; has_clusters: boolean }>(`/dashboard/voe-briefing/recompute${qs({ period })}`, {
      method: "POST",
    }),

  voeByCategory: (period: string) =>
    request<VoeByCategoryResponse>(`/dashboard/voe-by-category${qs({ period })}`),

  recomputeVoeByCategory: (period: string) =>
    request<{ classified_comments: number }>(`/dashboard/voe-by-category/recompute${qs({ period })}`, {
      method: "POST",
    }),

  menuComments: (menuName: string, limit = 20) =>
    request<MenuCommentEntry[]>(`/dashboard/menu-comments/${encodeURIComponent(menuName)}${qs({ limit })}`),

  menuHighlights: () => request<MenuHighlightsResponse>("/dashboard/menu-highlights"),

  improvementPoints: (params: { period_start: string; period_end: string }) =>
    request<ImprovementPoint[]>(`/dashboard/improvement-points${qs(params)}`),

  cornerAnalysis: (params: {
    period_start: string;
    period_end: string;
    classification?: Classification;
    exclude_take_out?: boolean;
    meal_types?: MealType[];
  }) => request<CornerAnalysisRow[]>(`/analysis/corners${qs(params)}`),

  cornerAnalysisTrend: (params: {
    period_start: string;
    period_end: string;
    granularity: "daily" | "weekly" | "monthly";
    classification?: Classification;
    exclude_take_out?: boolean;
    meal_types?: MealType[];
  }) => request<CornerTrendRow[]>(`/analysis/corners/trend${qs(params)}`),

  // 코너 목록만(통계 없음) — 배치 집계 상태와 무관하게 필터 선택지를 채우려는 용도.
  cornerList: () => request<CornerListRow[]>("/analysis/corners/list"),

  cornerMainMenuByDate: (params: { period_start: string; period_end: string }) =>
    request<CornerMainMenuByDateRow[]>(`/analysis/corners/main-menu-by-date${qs(params)}`),

  divisionAnalysis: (params: {
    period_start: string;
    period_end: string;
    granularity?: Granularity;
    classification?: Classification;
  }) => request<DivisionRow[]>(`/analysis/divisions${qs(params)}`),

  // 현황 통합 추이 — 조·중·석식 × 코너 × 회사구분 3축을 동시에 필터한다.
  // 집계 테이블엔 코너×회사구분 교차 셀이 없어 meal_log를 런타임 집계하는 신규
  // 엔드포인트다(2026-08). 배치 재계산에 의존하지 않는다.
  headcountTrend: (params: {
    period_start: string;
    period_end: string;
    granularity?: Granularity;
    group_by?: HeadcountGroupBy;
    meal_types?: MealType[];
    corner_ids?: number[];
    divisions?: Division[];
    classification?: Classification;
  }) => request<HeadcountTrendRow[]>(`/analysis/headcount-trend${qs(params)}`),

  // PRD 7.1 확장(2026-08, §75): 날짜별 실측 식수·강수량 원자료 — "비가 오면
  // 식수가 준다"는 기존 시뮬레이션 감(v0)을 실데이터로 검증하기 위한 참고용
  // 화면. 이 결과가 배수를 자동으로 바꾸지 않는다.
  weatherHeadcountTimeline: (params: { period_start: string; period_end: string }) =>
    request<WeatherHeadcountTimelineResponse>(`/analysis/weather-headcount-timeline${qs(params)}`),

  // §71: 메인메뉴가 지정한 날씨유형(비/폭설/폭염/한파)의 날 평상시 대비 식수가
  // 얼마나 달랐는지 랭킹. 부찬은 대상이 아니다 — 이 결과가 시뮬레이션 배수나
  // 주간 식단표 예측치를 자동으로 바꾸지 않는다(weatherHeadcountTimeline과 동일 원칙).
  menuWeatherEventRanking: (params: {
    period_start: string;
    period_end: string;
    event: WeatherEvent;
    meal_type?: MealType;
  }) => request<MenuWeatherEventRankingResponse>(`/analysis/menu-performance/weather-event-ranking${qs(params)}`),

  // §81: "기온/강수량이 오를수록 식수가 느는(또는 주는) 메뉴" — 연속값
  // 상관계수 랭킹. weather-event-ranking과 마찬가지로 참고용 정보 제공까지만.
  menuWeatherCorrelationRanking: (params: {
    period_start: string;
    period_end: string;
    metric?: WeatherCorrelationMetric;
    meal_type?: MealType;
  }) =>
    request<MenuWeatherCorrelationRankingResponse>(
      `/analysis/menu-performance/weather-correlation-ranking${qs(params)}`,
    ),

  // §72: 메인메뉴가 그 계절에 전체 기간 평균 대비 식수가 얼마나 달랐는지
  // 랭킹. weatherEventRanking과 같은 원칙(참고용, 부찬 무관) — 비교 기준만
  // 다르다(평상시 대비 대신 전체 기간 평균 대비).
  menuSeasonRanking: (params: {
    period_start: string;
    period_end: string;
    season: Season;
    meal_type?: MealType;
  }) => request<MenuSeasonRankingResponse>(`/analysis/menu-performance/season-ranking${qs(params)}`),

  recomputeDailyStats: (params: { period_start: string; period_end: string }) =>
    request<{ days_processed: number }>(`/analysis/daily-stats/recompute${qs(params)}`, {
      method: "POST",
    }),

  menuPerformance: (params: { period_start: string; period_end: string }) =>
    request<MenuPerformanceRow[]>(`/analysis/menu-performance${qs(params)}`),

  menuPerformanceByMealType: (params: { period_start: string; period_end: string; meal_type: MealType }) =>
    request<MenuPerformanceRow[]>(`/analysis/menu-performance/by-meal-type${qs(params)}`),

  recomputeMenuPerformance: (params: { period_start: string; period_end: string }) =>
    request<{ updated_menus: number }>(`/analysis/menu-performance/recompute${qs(params)}`, {
      method: "POST",
    }),

  // §78: 메뉴 하이라이트 LLM 원인 설명 캐시를 수동으로 채운다 — 평소엔 새벽
  // 배치(02:00)가 채우지만 로컬 개발 환경처럼 스케줄러가 안 떠 있으면 계속
  // 비어 있어 화면에 설명이 안 뜬다.
  recomputeLlmAnalyses: (params: { period_start: string; period_end: string }) =>
    request<{ menu_trend: number; planning_notice: number }>(`/analysis/llm-analyses/recompute${qs(params)}`, {
      method: "POST",
    }),

  menuDeclineDiagnosis: (
    menuId: number,
    params: { recent_start: string; recent_end: string; prior_start: string; prior_end: string },
  ) =>
    request<{ menu_id: number; diagnosis: string }>(
      `/analysis/menu-performance/${menuId}/decline-diagnosis${qs(params)}`,
    ),

  userTasteProfile: (employeeId: string) =>
    request<TasteProfile>(`/analysis/users/${encodeURIComponent(employeeId)}/taste-profile`),

  tasteClusters: () => request<TasteCluster[]>(`/analysis/users/taste-clusters`),

  recomputeTasteClusters: (k: number) =>
    request<{ clusters_created: number }>(`/analysis/users/taste-clusters/recompute${qs({ k })}`, {
      method: "POST",
    }),

  menuAffinity: (
    menuName: string,
    params: { period_start: string; period_end: string; min_co_count?: number; top_n?: number },
  ) => request<MenuAffinityRow[]>(`/analysis/menu-affinity/${encodeURIComponent(menuName)}${qs(params)}`),

  menuSideCombinations: (
    menuName: string,
    params: { period_start: string; period_end: string; corner_id?: number },
  ) =>
    request<MenuCombinationsResponse>(
      `/analysis/menu-combinations/${encodeURIComponent(menuName)}${qs(params)}`,
    ),

  weeklyMenuCombinationCheck: (params: { period_start: string; period_end: string }) =>
    request<CombinationCheckResponse>(`/analysis/weekly-menu/combination-check${qs(params)}`),

  // §77: 담당자가 준 4개 기준(해장/면류/매운빨간국물/최근 저조 식수 재편성)으로
  // 그 주 편성을 검증해 경고한다. combination-check와 같은 period_start/end로
  // 호출해 화면에 보이는 주와 항상 일치시킨다.
  weeklyMenuPlanRuleCheck: (params: { period_start: string; period_end: string }) =>
    request<WeeklyMenuPlanRuleCheckResponse>(`/analysis/weekly-menu/plan-rule-check${qs(params)}`),

  // §80: "금주 예상 식수"를 날씨/메뉴배수 예측 대신 최근 실측 평균 기반
  // 코너-메뉴 랭킹으로 보여준다.
  weeklyMenuPlannedHeadcountRanking: (params: { period_start: string; period_end: string }) =>
    request<WeeklyMenuPlannedHeadcountRankingResponse>(
      `/analysis/weekly-menu/planned-headcount-ranking${qs(params)}`,
    ),

  menuCombinationSpreadRanking: (params: {
    period_start: string;
    period_end: string;
    min_day_count?: number;
    top_n?: number;
    corner_id?: number;
  }) => request<ComboSpreadResponse>(`/analysis/menu-combinations/spread-ranking${qs(params)}`),

  menuPlanPerformance: (params: {
    period_start: string;
    period_end: string;
    meal_type?: MealType;
    corner_id?: number;
  }) => request<PlanPerformanceResponse>(`/analysis/menu-plan/performance${qs(params)}`),

  weeklyMenuRotation: (params: { period_start: string; period_end: string; lookback_days?: number }) =>
    request<MenuRotationResponse>(`/analysis/weekly-menu/rotation${qs(params)}`),

  weeklyMenuRepeatedSideDishes: (params: { period_start: string; period_end: string; corner_id?: number }) =>
    request<RepeatedSideDishResponse>(`/analysis/weekly-menu/repeated-side-dishes${qs(params)}`),

  // §80: 부찬 클릭 상세 — 어느 날짜·코너·메인메뉴와 함께 편성됐는지.
  weeklyMenuSideDishDetail: (params: {
    menu_name: string;
    corner_name: string;
    period_start: string;
    period_end: string;
  }) => request<SideDishDetailResponse>(`/analysis/weekly-menu/side-dish-detail${qs(params)}`),

  updateHealthGarden: (body: {
    plan_date: string;
    corner_id: number;
    meal_type: MealType;
    menu_names_raw: string;
  }) =>
    request<{ plan_date: string; corner_id: number; meal_type: MealType; items: { plan_id: number; menu_id: number; menu_name: string | null }[] }>(
      "/analysis/weekly-menu/health-garden",
      { method: "PUT", body: JSON.stringify(body) },
    ),

  cornerCoreLayerSummary: (params: {
    period_start: string;
    period_end: string;
    min_visit_count?: number;
    min_share?: number;
  }) => request<CornerCoreLayerSummaryRow[]>(`/analysis/corners/core-layer-summary${qs(params)}`),

  cornerMenuThroughput: (
    cornerId: number,
    params: { period_start: string; period_end: string; min_day_count?: number },
  ) =>
    request<CornerMenuThroughputResponse>(`/analysis/corners/${cornerId}/menu-throughput${qs(params)}`),

  menuFoodVectors: (params: { untagged_only?: boolean } = {}) =>
    request<MenuFoodVectorRow[]>(`/analysis/menus/food-vectors${qs(params)}`),

  averageMenuFoodVector: () => request<AverageFoodVectorResponse>("/analysis/menus/food-vectors/average"),

  updateMenuFoodVector: (menuId: number, vector: number[]) =>
    request<{ menu_id: number; food_vector: number[]; dimensions: string[]; source: FoodVectorSource }>(
      `/analysis/menus/${menuId}/food-vector`,
      { method: "PUT", body: JSON.stringify({ vector }) },
    ),

  tagMenusWithLlm: () =>
    request<{ tagged_menus: number }>(`/analysis/menus/tag-with-llm`, { method: "POST" }),

  // 식재료가 비어 있는 메뉴만 LLM으로 채운다. 한 끼 구성 중복 판정이 쓰는 값이라
  // food_vector와 별개다(같은 규칙→LLM→수동 3단계).
  extractIngredientsWithLlm: () =>
    request<{ updated: number }>(`/analysis/menus/extract-ingredients-with-llm`, { method: "POST" }),

  updateNewMenuStatus: (menuName: string, isNew: boolean | null) =>
    request<{ menu_id: number; menu_name: string; new_menu_override: boolean | null; new_menu_marked_on: string | null }>(
      `/analysis/menus/new-menu-status`,
      { method: "PUT", body: JSON.stringify({ menu_name: menuName, is_new: isNew }) },
    ),

  weeklyMenu: (params: { period_start: string; period_end: string }) =>
    request<WeeklyMenuSlot[]>(`/analysis/weekly-menu${qs(params)}`),

  updateWeeklyMenuRole: (planId: number, menuRole: "메인" | "부찬") =>
    request<{ plan_id: number; menu_role: string; role_source: FoodVectorSource }>(
      `/analysis/weekly-menu/${planId}/role`,
      { method: "PUT", body: JSON.stringify({ menu_role: menuRole }) },
    ),

  weeklyMenuPredictedImpact: (planId: number) =>
    request<PredictedImpactResponse>(`/analysis/weekly-menu/${planId}/predicted-impact`),

  weeklyMenuPredictedImpactSummary: (params: { period_start: string; period_end: string }) =>
    request<PredictedNumbersRow[]>(`/analysis/weekly-menu/predicted-impact-summary${qs(params)}`),

  reclassifyWeeklyMenuRolesWithLlm: (params: { period_start: string; period_end: string }) =>
    request<{ reclassified_slots: number }>(
      `/analysis/weekly-menu/reclassify-roles-with-llm${qs(params)}`,
      { method: "POST" },
    ),

  createWeeklyMenuFeedback: (payload: { plan_date: string; corner_id: number; comment: string }) =>
    request<WeeklyMenuFeedbackRow>(`/analysis/weekly-menu/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  weeklyMenuFeedback: (params: { period_start: string; period_end: string }) =>
    request<WeeklyMenuFeedbackRow[]>(`/analysis/weekly-menu/feedback${qs(params)}`),

  whatIf: (payload: {
    target_date: string;
    meal_type: MealType;
    weather: Weather;
    new_menu_corner_id?: number | null;
    has_company_event?: boolean;
  }) =>
    request<WhatIfResponse>(`/simulation/what-if`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  congestionForecast: (params: { target_date: string; meal_type: MealType }) =>
    request<CongestionForecastResponse>(`/simulation/congestion-forecast${qs(params)}`),

  // 현황 "금주 예상 식수" — 날짜별 반복 호출 대신 백엔드가 기간 루프를 돈다.
  // 휴일은 응답에서 빠지고, 날씨·연휴 전후 배수가 반영된 값이 온다.
  weeklyCongestionForecast: (params: {
    period_start: string;
    period_end: string;
    meal_type: MealType;
    weather?: Weather;
    has_company_event?: boolean;
  }) => request<WeeklyForecastResponse>(`/simulation/congestion-forecast/weekly${qs(params)}`),

  async *chatStream(messages: ChatMessage[]): AsyncGenerator<string> {
    const res = await fetch(`${BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`채팅 API 오류 ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        // 줄 앞뒤 개행만 제거하고, data 내용의 의미 있는 공백(단어 사이 구분)은
        // 보존해야 한다 — 여기서 trim()하면 스트리밍 단어들이 서로 붙어버린다.
        const withoutNewlines = line.replace(/^\n+|\n+$/g, "");
        if (!withoutNewlines.startsWith("data:")) continue;
        let data = withoutNewlines.slice("data:".length);
        if (data.startsWith(" ")) data = data.slice(1);
        if (data === "[DONE]") return;
        yield data;
      }
    }
  },
};
