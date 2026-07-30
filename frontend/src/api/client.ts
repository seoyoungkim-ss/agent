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

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ---- 타입 (backend/app/schemas, models.enums와 대응) ----

export type MealType = "조식" | "중식" | "석식";
export type Classification = "평일" | "주말+공휴일";
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

export interface VoeCategoryComment {
  eaten_at: string;
  corner_name: string | null;
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
  axis: "congestion" | "satisfaction" | "voe";
  title: string;
  detail: string;
  severity: "warning" | "critical";
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
}

export type Granularity = "daily" | "weekly" | "monthly";

export interface DivisionRow {
  period: string;
  division: string; // 본사 | 계열사 | 기타
  headcount: number;
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

export interface MenuPairRow {
  menu_a: string;
  menu_b: string;
  co_count: number;
  lift: number;
}

export interface CornerCoreLayerMenuPairsResponse {
  corner_id: number;
  corner_name: string;
  core_layer: {
    employee_count: number;
    min_visit_count: number;
    min_share: number;
    top_pairs: MenuPairRow[];
  };
  non_core: {
    employee_count: number;
    top_pairs: MenuPairRow[];
  };
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
  feedback_deadline: string;
  is_past_deadline: boolean;
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

export interface PredictedImpactResponse {
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
  };
  summary_comment: string;
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

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

// ---- API 함수 ----

export const api = {
  weeklySummary: (params: { start_date?: string; end_date?: string; classification?: Classification }) =>
    request<WeeklySummaryDay[]>(`/dashboard/weekly-summary${qs(params)}`),

  menuHistory: (menuName: string) =>
    request<MenuHistoryEntry[]>(`/dashboard/menu-history/${encodeURIComponent(menuName)}`),

  voeClusters: (period: string) => request<VoeCluster[]>(`/dashboard/voe-clusters${qs({ period })}`),

  voeByCategory: (period: string) =>
    request<VoeByCategoryResponse>(`/dashboard/voe-by-category${qs({ period })}`),

  recomputeVoeByCategory: (period: string) =>
    request<{ classified_comments: number }>(`/dashboard/voe-by-category/recompute${qs({ period })}`, {
      method: "POST",
    }),

  menuHighlights: () => request<MenuHighlightsResponse>("/dashboard/menu-highlights"),

  improvementPoints: (params: { period_start: string; period_end: string }) =>
    request<ImprovementPoint[]>(`/dashboard/improvement-points${qs(params)}`),

  cornerAnalysis: (params: {
    period_start: string;
    period_end: string;
    classification?: Classification;
    exclude_take_out?: boolean;
  }) => request<CornerAnalysisRow[]>(`/analysis/corners${qs(params)}`),

  cornerAnalysisTrend: (params: {
    period_start: string;
    period_end: string;
    granularity: "daily" | "weekly" | "monthly";
    classification?: Classification;
    exclude_take_out?: boolean;
  }) => request<CornerTrendRow[]>(`/analysis/corners/trend${qs(params)}`),

  divisionAnalysis: (params: {
    period_start: string;
    period_end: string;
    granularity?: Granularity;
    classification?: Classification;
  }) => request<DivisionRow[]>(`/analysis/divisions${qs(params)}`),

  recomputeDailyStats: (params: { period_start: string; period_end: string }) =>
    request<{ days_processed: number }>(`/analysis/daily-stats/recompute${qs(params)}`, {
      method: "POST",
    }),

  menuPerformance: (params: { period_start: string; period_end: string }) =>
    request<MenuPerformanceRow[]>(`/analysis/menu-performance${qs(params)}`),

  recomputeMenuPerformance: (params: { period_start: string; period_end: string }) =>
    request<{ updated_menus: number }>(`/analysis/menu-performance/recompute${qs(params)}`, {
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

  menuSideCombinations: (menuName: string, params: { period_start: string; period_end: string }) =>
    request<MenuCombinationsResponse>(
      `/analysis/menu-combinations/${encodeURIComponent(menuName)}${qs(params)}`,
    ),

  cornerCoreLayerMenuPairs: (
    cornerId: number,
    params: {
      period_start: string;
      period_end: string;
      min_visit_count?: number;
      min_share?: number;
      min_co_count?: number;
      top_n?: number;
    },
  ) =>
    request<CornerCoreLayerMenuPairsResponse>(
      `/analysis/corners/${cornerId}/core-layer-menu-pairs${qs(params)}`,
    ),

  cornerMenuThroughput: (
    cornerId: number,
    params: { period_start: string; period_end: string; min_day_count?: number },
  ) =>
    request<CornerMenuThroughputResponse>(`/analysis/corners/${cornerId}/menu-throughput${qs(params)}`),

  topMenuPairs: (params: { period_start: string; period_end: string; min_co_count?: number; top_n?: number }) =>
    request<MenuPairRow[]>(`/analysis/menu-pairs/top${qs(params)}`),

  menuFoodVectors: (params: { untagged_only?: boolean } = {}) =>
    request<MenuFoodVectorRow[]>(`/analysis/menus/food-vectors${qs(params)}`),

  updateMenuFoodVector: (menuId: number, vector: number[]) =>
    request<{ menu_id: number; food_vector: number[]; dimensions: string[]; source: FoodVectorSource }>(
      `/analysis/menus/${menuId}/food-vector`,
      { method: "PUT", body: JSON.stringify({ vector }) },
    ),

  tagMenusWithLlm: () =>
    request<{ tagged_menus: number }>(`/analysis/menus/tag-with-llm`, { method: "POST" }),

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
