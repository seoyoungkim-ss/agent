import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import {
  api,
  type Classification,
  type CongestionForecastRow,
  type Division,
  type Granularity,
  type HeadcountGroupBy,
  type MealType,
  type Weather,
} from "../api/client";
import {
  Button,
  Card,
  ErrorState,
  Legend,
  LoadingState,
  QuadrantBadge,
  resolveColor,
  SegmentedControl,
  StatTile,
  Table,
  useChartTheme,
} from "../components/ui";
import { CornerMetricComparisonSection } from "./AnalysisPage";

function mondayOf(date: Date): string {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // 월=0 ... 일=6
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"];

// 예상 대기시간이 이 값을 넘으면 숫자를 믿을 수 없다고 본다 — 식사 시간대(약
// 2시간)보다 긴 대기는 물리적으로 성립하지 않고, 실제로는 서브속도 표본이 너무
// 적은 코너에서 (초과분 ÷ 아주 작은 처리량)으로 폭주한 값이다(2026-08).
const WAIT_MINUTES_PLAUSIBLE_MAX = 120;

// 니치 코너(Take Out/미캠회관/그린미트)를 범례에서 기본 숨기던 규칙은 제거됐다
// (2026-08 현황 재편) — 통합 추이 차트에 명시적인 "코너 필터"가 생겨, 숨겨진
// 기본값보다 사용자가 직접 고르는 쪽이 더 분명하다.

// x축 날짜를 "MM-DD(요일)"로 보여줘 월~일 순서가 한눈에 보이게 한다.
function weekdayLabel(dateIso: string): string {
  return `${dateIso.slice(5)}(${WEEKDAY_KO[new Date(dateIso).getDay()]})`;
}

// 메뉴 하이라이트 카드의 날짜 표시 — "YYYY-MM-DD" → "M/D".
function shortDate(dateIso: string): string {
  const [, m, d] = dateIso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

// 마우스를 올리면 나오는 숫자(차트 툴팁)는 소수점 2자리까지만 보여준다.
function formatTooltipNumber(value: number | string): string {
  return typeof value === "number" ? value.toFixed(2) : value;
}

function axisTooltipFormatter(
  params: { axisValueLabel?: string; axisValue?: string; marker: string; seriesName: string; value: unknown }[],
): string {
  const header = params[0]?.axisValueLabel ?? params[0]?.axisValue ?? "";
  const lines = params.map((p) => {
    const value = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
    return `${p.marker}${p.seriesName}: ${formatTooltipNumber(value as number | string)}`;
  });
  return [header, ...lines].join("<br/>");
}

function addDays(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

const RECOMPUTE_PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준
const RECOMPUTE_PERIOD_END = isoDaysAgo(0);

const CLASSIFICATION_OPTIONS: { label: string; value: Classification | "전체" }[] = [
  { label: "전체", value: "전체" },
  { label: "평일", value: "평일" },
  { label: "주말+공휴일", value: "주말+공휴일" },
  { label: "패밀리데이", value: "패밀리데이" },
];

const MEAL_TYPE_OPTIONS: MealType[] = ["조식", "중식", "석식"];

export function HomePage({ onOpenWeeklyVoe }: { onOpenWeeklyVoe?: () => void }) {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  // 토요일은 평일과 식수 규모가 달라 같은 추이 라인에 섞으면 오해하기 쉽다 —
  // 기본은 숨기고 버튼으로 켜서 볼 수 있게 한다("주간 식수 추이"/"코너별 주간
  // 식수 추이" 두 차트 공용 토글, 2026-07).
  const [showSaturday, setShowSaturday] = useState(false);
  // 조식만 체크하면 조식 기준, 조식+중식 체크하면 둘을 합친 식수 — 최소 1개는
  // 항상 체크돼 있어야 한다(다 끄면 "전체 합산"과 구분이 안 돼 혼동됨, 2026-07).
  const [mealTypeFilter, setMealTypeFilter] = useState<MealType[]>(MEAL_TYPE_OPTIONS);
  function toggleMealType(mealType: MealType) {
    setMealTypeFilter((prev) => {
      if (prev.includes(mealType)) {
        return prev.length > 1 ? prev.filter((m) => m !== mealType) : prev;
      }
      return [...prev, mealType];
    });
  }
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const [selectedMonday, setSelectedMonday] = useState(mondayOf(new Date()));
  // 식당은 일요일에 운영하지 않으므로 월~토 6일만 조회한다.
  const saturdayOfSelected = addDays(selectedMonday, 5);

  const weekly = useQuery({
    queryKey: ["weekly-summary", selectedMonday, saturdayOfSelected, classification, mealTypeFilter.join("|")],
    queryFn: () =>
      api.weeklySummary({
        start_date: selectedMonday,
        end_date: saturdayOfSelected,
        classification: classification === "전체" ? undefined : classification,
        meal_types: mealTypeFilter,
      }),
  });

  const menuHistory = useQuery({
    queryKey: ["menu-history", searchedMenu],
    queryFn: () => api.menuHistory(searchedMenu as string),
    enabled: !!searchedMenu,
  });

  const cornerSummary = useQuery({
    queryKey: ["corner-summary", selectedMonday, saturdayOfSelected],
    queryFn: () => api.cornerAnalysis({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });

  // ---- 통합 식수 추이 (2026-08 현황 재편) ----
  // 조·중·석식 × 코너 × 회사구분 3축을 한 그래프에서 필터한다. 기간 단위는
  // 조회 범위까지 같이 정한다(일=최근 30일 / 주=최근 12주 / 월=최근 12개월) —
  // 위 요약 카드들의 "선택한 주"와 달리 추이는 더 긴 흐름을 봐야 의미가 있다.
  const [trendGranularity, setTrendGranularity] = useState<Granularity>("daily");
  const [trendGroupBy, setTrendGroupBy] = useState<HeadcountGroupBy>("total");
  const [trendCornerIds, setTrendCornerIds] = useState<number[]>([]);
  const [trendDivisions, setTrendDivisions] = useState<Division[]>([]);
  const TREND_LOOKBACK_DAYS: Record<Granularity, number> = { daily: 30, weekly: 84, monthly: 365 };
  const trendPeriodStart = isoDaysAgo(TREND_LOOKBACK_DAYS[trendGranularity]);
  const trendPeriodEnd = isoDaysAgo(0);

  const cornerListQuery = useQuery({
    queryKey: ["corner-list"],
    queryFn: () => api.cornerList(),
  });

  // ---- 금주 예상 식수 / 점유율·대기시간 (2026-08 현황 재편) ----
  // 날씨는 기상청 연동이 없어 사용자가 고른다(협의 결정). 연휴 전후는 백엔드가
  // 공휴일 캘린더에서 자동 판정해 배수를 적용한다.
  const [forecastWeather, setForecastWeather] = useState<Weather>("맑음");
  const [forecastMealType, setForecastMealType] = useState<MealType>("중식");
  // 사내 행사(전사 워크숍·교육 등)는 시뮬레이션 탭의 what-if에 있던 유일한 실질
  // 입력이었다. 탭을 없애면서 이 토글만 여기로 흡수했다(2026-08).
  const [hasCompanyEvent, setHasCompanyEvent] = useState(false);
  const weeklyForecast = useQuery({
    queryKey: [
      "weekly-congestion-forecast",
      selectedMonday,
      saturdayOfSelected,
      forecastMealType,
      forecastWeather,
      hasCompanyEvent,
    ],
    queryFn: () =>
      api.weeklyCongestionForecast({
        period_start: selectedMonday,
        period_end: saturdayOfSelected,
        meal_type: forecastMealType,
        weather: forecastWeather,
        has_company_event: hasCompanyEvent,
      }),
  });
  // 점유율/대기시간은 주간 식단표 예측 요약을 그대로 재사용한다(백엔드 변경 없음).
  const predictedImpact = useQuery({
    queryKey: ["weekly-predicted-impact", selectedMonday, saturdayOfSelected],
    queryFn: () =>
      api.weeklyMenuPredictedImpactSummary({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });
  // 일간 × 코너별로 볼 때 툴팁에 그날 그 코너의 메인메뉴를 덧붙인다(2026-07 요청,
  // 코너별 주간 추이 차트에 있던 기능을 통합 차트로 옮겨옴). 그 조합일 때만 조회한다.
  const trendMainMenuEnabled = trendGranularity === "daily" && trendGroupBy === "corner";
  const cornerMainMenu = useQuery({
    queryKey: ["corner-main-menu-by-date", trendPeriodStart, trendPeriodEnd],
    queryFn: () => api.cornerMainMenuByDate({ period_start: trendPeriodStart, period_end: trendPeriodEnd }),
    enabled: trendMainMenuEnabled,
  });
  const headcountTrend = useQuery({
    queryKey: [
      "headcount-trend",
      trendPeriodStart,
      trendPeriodEnd,
      trendGranularity,
      trendGroupBy,
      mealTypeFilter.join("|"),
      trendCornerIds.join("|"),
      trendDivisions.join("|"),
      classification,
    ],
    queryFn: () =>
      api.headcountTrend({
        period_start: trendPeriodStart,
        period_end: trendPeriodEnd,
        granularity: trendGranularity,
        group_by: trendGroupBy,
        meal_types: mealTypeFilter,
        corner_ids: trendCornerIds.length > 0 ? trendCornerIds : undefined,
        divisions: trendDivisions.length > 0 ? trendDivisions : undefined,
        classification: classification === "전체" ? undefined : classification,
      }),
  });

  const recomputeDailyStats = useMutation({
    mutationFn: () =>
      api.recomputeDailyStats({ period_start: RECOMPUTE_PERIOD_START, period_end: RECOMPUTE_PERIOD_END }),
    onSuccess: () => {
      weekly.refetch();
      cornerSummary.refetch();
    },
  });

  const menuHighlights = useQuery({
    queryKey: ["menu-highlights"],
    queryFn: () => api.menuHighlights(),
  });
  const updateNewMenuStatus = useMutation({
    mutationFn: ({ menuName, isNew }: { menuName: string; isNew: boolean | null }) =>
      api.updateNewMenuStatus(menuName, isNew),
    onSuccess: () => menuHighlights.refetch(),
  });
  const [newMenuNameDraft, setNewMenuNameDraft] = useState("");

  const improvementPoints = useQuery({
    queryKey: ["improvement-points"],
    queryFn: () =>
      api.improvementPoints({ period_start: RECOMPUTE_PERIOD_START, period_end: RECOMPUTE_PERIOD_END }),
  });

  // 오늘 예상 총 식수 / 최고 혼잡 예상 코너 — 기존 혼잡도 예측(congestion-forecast,
  // 요일별 최근 8회 평균 baseline × 계획 메뉴 인기도 배수)을 재사용한다.
  const today = isoDaysAgo(0);
  const congestionForecast = useQuery({
    queryKey: ["congestion-forecast", today],
    queryFn: () => api.congestionForecast({ target_date: today, meal_type: "중식" }),
  });
  const totalPredictedHeadcount = (congestionForecast.data?.corners ?? []).reduce(
    (sum, c) => sum + c.predicted_headcount,
    0,
  );
  // Take Out은 착석 취식이 아니라 "혼잡"(줄서서 기다림) 개념과 안 맞아 제외한다
  // (corner_analysis의 exclude_take_out과 같은 이유, 여기선 이 카드 하나만 해당).
  const topCongestedCorner = (congestionForecast.data?.corners ?? [])
    .filter((c) => c.corner_name !== "Take Out")
    .reduce<CongestionForecastRow | null>(
      (max, c) => (max === null || c.expected_peak_headcount > max.expected_peak_headcount ? c : max),
      null,
    );

  // 금주 메뉴 과거 VOE — 이번 주 메인메뉴 중 과거 평가 이력(evaluation_count>0)이
  // 있는 메뉴 수. 이번 주 메뉴 수가 적어(보통 5~15개) 병렬 개별 호출로 v0 구현.
  const weeklyMenuQuery = useQuery({
    queryKey: ["weekly-menu-main", selectedMonday, saturdayOfSelected],
    queryFn: () => api.weeklyMenu({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });
  const weeklyMainMenuNames = [
    ...new Set((weeklyMenuQuery.data ?? []).map((s) => s.main?.menu_name).filter((n): n is string => !!n)),
  ];
  const weeklyVoeHistory = useQuery({
    queryKey: ["weekly-menu-voe-history", weeklyMainMenuNames.join("|")],
    queryFn: async () => {
      const results = await Promise.all(weeklyMainMenuNames.map((name) => api.menuHistory(name)));
      return weeklyMainMenuNames.filter((_, i) => results[i].some((h) => h.evaluation_count > 0)).length;
    },
    enabled: weeklyMainMenuNames.length > 0,
  });

  const totalHeadcount = weekly.data?.reduce((sum, d) => sum + d.headcount, 0) ?? 0;
  const chartTheme = useChartTheme();
  const seriesWeekday = resolveColor("var(--series-1)");
  const seriesHoliday = resolveColor("var(--series-2)");
  const seriesFamilyDay = resolveColor("var(--series-3)");
  const holidayColor = resolveColor("var(--critical)");
  const familyDayColor = resolveColor("var(--series-3)");

  // 패밀리데이 월별 추이 카드는 제거됐다(2026-08 현황 재편) — 아래 "식수 추이"
  // 통합 차트에서 classification=패밀리데이 + 기간단위=월간으로 같은 걸 볼 수 있다.

  // "주간 식수 추이" 차트 전용 — 토요일 토글이 꺼져 있으면 이 차트에서만
  // 토요일을 뺀다(누적 식수 스탯 타일은 영향 없음).
  const chartWeeklyData = showSaturday
    ? (weekly.data ?? [])
    : (weekly.data ?? []).filter((d) => new Date(d.date).getDay() !== 6);
  const classificationByDate = new Map(chartWeeklyData.map((d) => [d.date, d.classification]));
  const weekdayAxisLabel = {
    color: (value: string) => {
      const cls = classificationByDate.get(value);
      if (cls === "주말+공휴일") return holidayColor;
      if (cls === "패밀리데이") return familyDayColor;
      return chartTheme.text;
    },
    formatter: (value: string) => weekdayLabel(value),
  };
  function pointColorForClassification(cls: string): string {
    if (cls === "주말+공휴일") return seriesHoliday;
    if (cls === "패밀리데이") return seriesFamilyDay;
    return seriesWeekday;
  }

  const chartOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis", formatter: axisTooltipFormatter },
    xAxis: {
      type: "category",
      data: chartWeeklyData.map((d) => d.date),
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: weekdayAxisLabel,
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: "식수",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      {
        type: "line",
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { width: 2, color: seriesWeekday },
        data: chartWeeklyData.map((d) => ({
          value: d.headcount,
          itemStyle: { color: pointColorForClassification(d.classification) },
        })),
      },
    ],
  };

  // 금주 예상 식수 차트 — 날짜별 총 예상 식수(휴일은 응답에서 이미 빠져 있다).
  const forecastDays = weeklyForecast.data?.days ?? [];
  const forecastOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue?: string; marker: string; value: unknown }[]) => {
        const date = params[0]?.axisValue ?? "";
        const day = forecastDays.find((d) => d.target_date === date);
        const v = params[0]?.value;
        const lines = [date, `${params[0]?.marker}예상 식수: ${typeof v === "number" ? Math.round(v) : v}명`];
        if (day && day.holiday_adjacency !== "해당 없음") lines.push(`${day.holiday_adjacency} (배수 ${day.applied_multiplier})`);
        else if (day && day.applied_multiplier !== 1) lines.push(`날씨 배수 ${day.applied_multiplier}`);
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: forecastDays.map((d) => d.target_date),
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: { color: chartTheme.text, formatter: (v: string) => weekdayLabel(v) },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: "예상 식수",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      {
        name: "예상 식수",
        type: "line" as const,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { width: 2, color: resolveColor("var(--series-1)") },
        itemStyle: {
          // 연휴 전후인 날은 색을 달리해 "왜 낮은지"가 눈에 띄게 한다.
          color: (p: { dataIndex: number }) =>
            forecastDays[p.dataIndex]?.holiday_adjacency !== "해당 없음"
              ? resolveColor("var(--warning)")
              : resolveColor("var(--series-1)"),
          borderColor: resolveColor("var(--surface)"),
          borderWidth: 2,
        },
        data: forecastDays.map((d) => d.total_predicted_headcount),
      },
    ],
  };

  // 툴팁은 시리즈 "이름"(코너명)만 알 수 있는데 main-menu-by-date는 corner_id로
  // 오므로, 코너 목록으로 id→이름을 옮겨 코너명 기준 키로 맞춘다.
  const cornerNameById = new Map((cornerListQuery.data ?? []).map((c) => [c.corner_id, c.corner_name]));
  const mainMenuByCornerDate = new Map(
    (cornerMainMenu.data ?? []).map((r) => [
      `${cornerNameById.get(r.corner_id) ?? r.corner_id}|${r.plan_date}`,
      r.menu_name,
    ]),
  );

  // 통합 식수 추이 차트 — series_key로 시리즈를 가르고 period를 x축으로 쓴다.
  const trendRows = headcountTrend.data ?? [];
  const trendPeriods = [...new Set(trendRows.map((r) => r.period))].sort();
  const trendSeriesMeta = new Map<string, string>();
  for (const r of trendRows) trendSeriesMeta.set(r.series_key, r.series_label);
  const trendValueBySeries = new Map<string, Map<string, number>>();
  for (const r of trendRows) {
    if (!trendValueBySeries.has(r.series_key)) trendValueBySeries.set(r.series_key, new Map());
    trendValueBySeries.get(r.series_key)!.set(r.period, r.headcount);
  }
  // 시리즈가 많으면(코너별 등) 색이 뒤섞이지 않게 series_key 기준으로 색을 고정한다.
  const trendSeriesKeys = [...trendSeriesMeta.keys()].sort();
  const headcountTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue?: string; marker: string; seriesName: string; value: unknown }[]) => {
        const header = params[0]?.axisValue ?? "";
        const lines = params.map((p) => {
          const v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
          const menu = trendMainMenuEnabled ? mainMenuByCornerDate.get(`${p.seriesName}|${header}`) : undefined;
          const menuLine = menu ? `<br/>&nbsp;&nbsp;메뉴: ${menu}` : "";
          return `${p.marker}${p.seriesName}: ${typeof v === "number" ? Math.round(v) : v}명${menuLine}`;
        });
        return [header, ...lines].join("<br/>");
      },
    },
    legend: { top: 0, textStyle: { color: chartTheme.text }, data: trendSeriesKeys.map((k) => trendSeriesMeta.get(k)!) },
    xAxis: {
      type: "category",
      data: trendPeriods,
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: { color: chartTheme.text },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: "식수",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: trendSeriesKeys.map((key, i) => {
      const color = resolveColor(`var(--series-${(i % 8) + 1})`);
      return {
        name: trendSeriesMeta.get(key)!,
        type: "line" as const,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { width: 2, color },
        itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
        data: trendPeriods.map((p) => trendValueBySeries.get(key)?.get(p) ?? 0),
      };
    }),
  };

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${selectedMonday}&end_date=${saturdayOfSelected}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }${mealTypeFilter.map((m) => `&meal_types=${encodeURIComponent(m)}`).join("")}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">카페테리아 현황</h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {selectedMonday} ~ {saturdayOfSelected}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Button variant="secondary" onClick={() => setSelectedMonday((d) => addDays(d, -7))}>
              ◀ 이전 주
            </Button>
            <input
              type="date"
              className="rounded-md border px-3 py-2 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              value={selectedMonday}
              onChange={(e) => e.target.value && setSelectedMonday(mondayOf(new Date(e.target.value)))}
            />
            <Button variant="secondary" onClick={() => setSelectedMonday((d) => addDays(d, 7))}>
              다음 주 ▶
            </Button>
          </div>
          <SegmentedControl value={classification} options={CLASSIFICATION_OPTIONS} onChange={setClassification} />
          <div className="flex items-center gap-2 rounded-md border px-2.5 py-1.5" style={{ borderColor: "var(--border)" }}>
            {MEAL_TYPE_OPTIONS.map((mealType) => (
              <label key={mealType} className="flex items-center gap-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                <input
                  type="checkbox"
                  checked={mealTypeFilter.includes(mealType)}
                  onChange={() => toggleMealType(mealType)}
                />
                {mealType}
              </label>
            ))}
          </div>
          <Button variant="secondary" onClick={() => setShowSaturday((v) => !v)}>
            {showSaturday ? "토요일 숨기기" : "토요일 포함 보기"}
          </Button>
          <a href={exportUrl} download>
            <Button variant="secondary">엑셀 다운로드</Button>
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="선택한 주의 누적 식수" value={totalHeadcount.toLocaleString()} />
        <StatTile
          label="오늘 예상 총 식수"
          value={
            congestionForecast.isLoading ? "…" : Math.round(totalPredictedHeadcount).toLocaleString()
          }
          sub="요일별 최근 이력 + 계획 메뉴 인기도 기반"
        />
        <StatTile
          label="최고 혼잡 예상 코너"
          value={topCongestedCorner?.corner_name ?? "-"}
          sub={
            topCongestedCorner
              ? `예상 피크 식수 ${Math.round(topCongestedCorner.expected_peak_headcount).toLocaleString()}명`
              : "오늘 데이터 없음"
          }
          tone={topCongestedCorner ? "warning" : undefined}
        />
        <StatTile
          label="금주 메뉴 과거 VOE"
          value={weeklyVoeHistory.isLoading ? "…" : (weeklyVoeHistory.data ?? 0)}
          sub="클릭하면 메뉴별 상세를 볼 수 있어요"
          onClick={onOpenWeeklyVoe}
        />
      </div>

      <Card title="개선 필요 포인트 — 혼잡도 / 만족도 / VOE">
        {improvementPoints.isLoading && <LoadingState />}
        {improvementPoints.isError && <ErrorState error={improvementPoints.error} />}
        {improvementPoints.data && improvementPoints.data.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            특별한 이상 없음
          </p>
        )}
        {improvementPoints.data && improvementPoints.data.length > 0 && (
          <ul className="space-y-2">
            {improvementPoints.data.map((p, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: p.severity === "critical" ? "var(--critical)" : "var(--warning)" }}
                />
                <div>
                  <div className="text-[13px] font-medium">{p.title}</div>
                  <div className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    {p.detail}
                  </div>
                  {p.voe_summary && (
                    <div
                      className="mt-1 rounded border-l-2 pl-2 text-xs italic"
                      style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
                    >
                      "{p.voe_summary}"
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="주간 식수 추이">
        <div className="mb-3">
          <Legend
            items={[
              { label: "평일", color: "var(--series-1)" },
              { label: "주말+공휴일", color: "var(--series-2)" },
              { label: "패밀리데이", color: "var(--series-3)" },
            ]}
          />
        </div>
        {weekly.isLoading && <LoadingState />}
        {weekly.isError && <ErrorState error={weekly.error} />}
        {weekly.data && weekly.data.length > 0 && totalHeadcount === 0 && (
          <div className="mb-4 space-y-2">
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              선택한 주에 식수가 0으로 나옵니다. 취식 데이터를 과거 기간 한꺼번에 적재한 경우 배치 집계(daily_division_stats/daily_corner_stats)가
              아직 안 돼 있을 수 있습니다 — 스케줄러는 매일 새벽 전날치만 계산합니다.
            </p>
            <Button variant="secondary" onClick={() => recomputeDailyStats.mutate()} disabled={recomputeDailyStats.isPending}>
              {recomputeDailyStats.isPending ? "계산 중..." : "최근 180일 배치 집계 재계산"}
            </Button>
            {recomputeDailyStats.isError && <ErrorState error={recomputeDailyStats.error} />}
            {recomputeDailyStats.isSuccess && (
              <p className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                재계산 완료 — 그래도 0이면 이 기간에 실제로 적재된 취식 데이터가 없는 것입니다.
              </p>
            )}
          </div>
        )}
        {weekly.data && <ReactECharts option={chartOption} style={{ height: 280 }} />}
      </Card>

      <Card title="식수 추이 — 기간 단위 · 끼니 · 코너 · 회사구분">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          {trendPeriodStart} ~ {trendPeriodEnd} 기준입니다. 왼쪽에서 기간 단위와 "무엇을 선으로 나눠 볼지"를
          고르고, 오른쪽 필터로 범위를 좁힙니다 — 필터와 나누는 기준은 별개라 "계열사만 골라 코너별로 보기"
          같은 조합이 가능합니다. 끼니 필터와 평일/주말 구분은 위 "주간 식수 추이"와 공유합니다.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            기간 단위
            <SegmentedControl
              value={trendGranularity}
              options={[
                { label: "일간", value: "daily" as Granularity },
                { label: "주간", value: "weekly" as Granularity },
                { label: "월간", value: "monthly" as Granularity },
              ]}
              onChange={setTrendGranularity}
            />
          </label>
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            나누기
            <SegmentedControl
              value={trendGroupBy}
              options={[
                { label: "전체", value: "total" as HeadcountGroupBy },
                { label: "코너별", value: "corner" as HeadcountGroupBy },
                { label: "회사구분별", value: "division" as HeadcountGroupBy },
                { label: "끼니별", value: "meal_type" as HeadcountGroupBy },
              ]}
              onChange={setTrendGroupBy}
            />
          </label>
        </div>
        <div className="mb-3 flex flex-wrap items-start gap-x-6 gap-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              코너 필터
            </span>
            {(cornerListQuery.data ?? []).map((c) => {
              const active = trendCornerIds.includes(c.corner_id);
              return (
                <button
                  key={c.corner_id}
                  onClick={() =>
                    setTrendCornerIds((cur) =>
                      cur.includes(c.corner_id) ? cur.filter((id) => id !== c.corner_id) : [...cur, c.corner_id],
                    )
                  }
                  className="rounded border px-2 py-0.5 text-xs transition-colors"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    background: active ? "var(--surface-2)" : "var(--surface)",
                    color: active ? "var(--ink)" : "var(--ink-secondary)",
                  }}
                >
                  {c.corner_name}
                </button>
              );
            })}
            {trendCornerIds.length > 0 && (
              <button className="text-xs underline" style={{ color: "var(--ink-muted)" }} onClick={() => setTrendCornerIds([])}>
                전체
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              회사구분
            </span>
            {(["본사", "계열사", "기타"] as Division[]).map((d) => {
              const active = trendDivisions.includes(d);
              return (
                <button
                  key={d}
                  onClick={() =>
                    setTrendDivisions((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]))
                  }
                  className="rounded border px-2 py-0.5 text-xs transition-colors"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    background: active ? "var(--surface-2)" : "var(--surface)",
                    color: active ? "var(--ink)" : "var(--ink-secondary)",
                  }}
                >
                  {d}
                </button>
              );
            })}
            {trendDivisions.length > 0 && (
              <button className="text-xs underline" style={{ color: "var(--ink-muted)" }} onClick={() => setTrendDivisions([])}>
                전체
              </button>
            )}
          </div>
        </div>
        {headcountTrend.isLoading && <LoadingState />}
        {headcountTrend.isError && <ErrorState error={headcountTrend.error} />}
        {headcountTrend.data && trendPeriods.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 조건에 해당하는 취식 데이터가 없습니다.
          </p>
        )}
        {trendPeriods.length > 0 && <ReactECharts option={headcountTrendOption} style={{ height: 320 }} />}
      </Card>

      <Card title="금주 예상 식수 · 점유율 · 대기시간">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          과거 같은 분류(평일/패밀리데이)의 최근 이력에 계획 메뉴 인기도와 날씨·연휴 전후 배수를 곱해
          추정합니다. 식당이 쉬는 주말·공휴일은 빠집니다. <strong>날씨·연휴 전후 배수는 실측 보정 전
          가정치</strong>라 방향성 참고용입니다 — 연휴 표본이 쌓이면 보정이 필요합니다.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            끼니
            <SegmentedControl
              value={forecastMealType}
              options={MEAL_TYPE_OPTIONS.map((m) => ({ label: m, value: m }))}
              onChange={setForecastMealType}
            />
          </label>
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            날씨
            <SegmentedControl
              value={forecastWeather}
              options={[
                { label: "맑음", value: "맑음" as Weather },
                { label: "비", value: "비" as Weather },
                { label: "폭염", value: "폭염" as Weather },
                { label: "한파", value: "한파" as Weather },
              ]}
              onChange={setForecastWeather}
            />
          </label>
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            <input
              type="checkbox"
              checked={hasCompanyEvent}
              onChange={(e) => setHasCompanyEvent(e.target.checked)}
            />
            사내 행사 있음 (식수 −10% 가정)
          </label>
        </div>
        {weeklyForecast.isLoading && <LoadingState />}
        {weeklyForecast.isError && <ErrorState error={weeklyForecast.error} />}
        {weeklyForecast.data && forecastDays.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 주에는 예측할 영업일이 없습니다.
          </p>
        )}
        {forecastDays.length > 0 && <ReactECharts option={forecastOption} style={{ height: 260 }} />}

        <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            금주 메인메뉴별 예상 점유율 · 대기시간 (주간 식단표에 등록된 슬롯 기준)
          </p>
          {predictedImpact.isLoading && <LoadingState />}
          {predictedImpact.isError && <ErrorState error={predictedImpact.error} />}
          {predictedImpact.data && predictedImpact.data.length === 0 && (
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              이 주에 등록된 주간 식단표가 없습니다.
            </p>
          )}
          {predictedImpact.data && predictedImpact.data.length > 0 && (
            <Table
              columns={[
                { key: "date", label: "날짜" },
                { key: "corner", label: "코너" },
                { key: "menu", label: "메인메뉴" },
                { key: "share", label: "예상 점유율", align: "right" },
                { key: "headcount", label: "예상 식수", align: "right" },
                { key: "wait", label: "예상 대기", align: "right" },
              ]}
              rows={predictedImpact.data.map((r) => ({
                date: `${r.plan_date.slice(5)}(${WEEKDAY_KO[new Date(r.plan_date).getDay()]})`,
                corner: r.corner_name ?? "-",
                menu: r.menu_name ?? "-",
                share: `${(r.prediction.predicted_share * 100).toFixed(1)}%`,
                headcount: `${Math.round(r.prediction.predicted_headcount)}명`,
                // 서브속도 표본이 희박한 코너는 (초과분 ÷ 아주 작은 처리량)이라
                // 대기시간이 수백 분으로 폭주한다 — 중식 서비스 시간대보다 긴 값은
                // 물리적으로 무의미하므로 숫자 대신 표본 부족으로 표시한다.
                // 근본 해결(처리량 표본 하한)은 별도 과제(2026-08 발견).
                wait:
                  r.prediction.expected_wait_minutes == null
                    ? "데이터 부족"
                    : r.prediction.expected_wait_minutes > WAIT_MINUTES_PLAUSIBLE_MAX
                      ? "추정 불안정(표본 부족)"
                      : `${r.prediction.expected_wait_minutes}분`,
              }))}
              rowKey={(_, i) => `impact-${i}`}
            />
          )}
        </div>
      </Card>

      {/* 코너별 지표 비교 — 2026-08 재편으로 "분석 > 코너별" 탭에서 현황으로 옮겨왔다. */}
      <CornerMetricComparisonSection />

      <Card title="메뉴 하이라이트">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          메뉴별로 이번에 나온 시점을 그 직전 등장 시점과 비교합니다(메뉴는 매주 나오지 않으므로 달력 주
          단위가 아니라 메뉴별 직전 등장 대비입니다). 신메뉴는 최근 30일 내 처음 나온 메뉴의 초기 반응입니다.
        </p>
        {menuHighlights.isLoading && <LoadingState />}
        {menuHighlights.isError && <ErrorState error={menuHighlights.error} />}
        {menuHighlights.data && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  만족도 급상승
                </p>
                {menuHighlights.data.rising.length === 0 ? (
                  <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                    해당 없음
                  </p>
                ) : (
                  <Table
                    columns={[
                      { key: "menu", label: "메뉴" },
                      { key: "date", label: "날짜", align: "right" },
                      { key: "score", label: "만족도", align: "right" },
                    ]}
                    rows={menuHighlights.data.rising.map((r) => ({
                      menu: `${r.menu_name}${r.corner_name ? ` (${r.corner_name})` : ""}`,
                      date: shortDate(r.date),
                      score: `${r.prior_score.toFixed(2)} → ${r.recent_score.toFixed(2)}`,
                    }))}
                    rowKey={(r, i) => `${r.menu as string}-${i}`}
                  />
                )}
              </div>
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  만족도 급하락
                </p>
                {menuHighlights.data.falling.length === 0 ? (
                  <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                    해당 없음
                  </p>
                ) : (
                  <Table
                    columns={[
                      { key: "menu", label: "메뉴" },
                      { key: "date", label: "날짜", align: "right" },
                      { key: "score", label: "만족도", align: "right" },
                    ]}
                    rows={menuHighlights.data.falling.map((r) => ({
                      menu: `${r.menu_name}${r.corner_name ? ` (${r.corner_name})` : ""}`,
                      date: shortDate(r.date),
                      score: `${r.prior_score.toFixed(2)} → ${r.recent_score.toFixed(2)}`,
                    }))}
                    rowKey={(r, i) => `${r.menu as string}-${i}`}
                  />
                )}
              </div>
            </div>
            <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}>
              <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                신메뉴 반응 (최근 30일 자동판정 + 관리자 직접 지정)
              </p>
              <div className="mb-2 flex gap-2">
                <input
                  type="text"
                  value={newMenuNameDraft}
                  onChange={(e) => setNewMenuNameDraft(e.target.value)}
                  placeholder="메뉴명 (예: 제육볶음)"
                  className="min-w-0 flex-1 rounded border px-2 py-1 text-[13px]"
                  style={{ borderColor: "var(--border)" }}
                />
                <Button
                  disabled={!newMenuNameDraft.trim() || updateNewMenuStatus.isPending}
                  onClick={() => {
                    updateNewMenuStatus.mutate({ menuName: newMenuNameDraft.trim(), isNew: true });
                    setNewMenuNameDraft("");
                  }}
                >
                  신메뉴로 등록
                </Button>
              </div>
              {updateNewMenuStatus.isError && <ErrorState error={updateNewMenuStatus.error} />}
              {menuHighlights.data.new_menus.length === 0 ? (
                <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                  해당 없음
                </p>
              ) : (
                <Table
                  columns={[
                    { key: "menu", label: "메뉴" },
                    { key: "days", label: "도입 후 경과일", align: "right" },
                    { key: "score", label: "만족도(평가건수)", align: "right" },
                    { key: "action", label: "", align: "right" },
                  ]}
                  rows={menuHighlights.data.new_menus.map((r) => ({
                    menu: (
                      <>
                        {r.menu_name}
                        {r.corner_name ? ` (${r.corner_name})` : ""}
                        {r.is_manual && (
                          <span className="ml-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                            (관리자 지정)
                          </span>
                        )}
                      </>
                    ),
                    days: r.needs_attention ? (
                      <span style={{ color: "var(--warning)" }}>{r.days_since_introduction}일 · 반응 없음</span>
                    ) : (
                      `${r.days_since_introduction}일`
                    ),
                    score:
                      r.evaluation_count > 0
                        ? `${r.adjusted_score?.toFixed(2)} (${r.evaluation_count}건)`
                        : "평가 없음",
                    action: (
                      <button
                        className="text-xs underline"
                        style={{ color: "var(--ink-muted)" }}
                        onClick={() => updateNewMenuStatus.mutate({ menuName: r.menu_name, isNew: false })}
                      >
                        신메뉴 아님으로 표시
                      </button>
                    ),
                  }))}
                  rowKey={(_, i) => `new-menu-${i}`}
                />
              )}
            </div>
          </div>
        )}
      </Card>

      <Card title="이번 주 메뉴 이력 검색 (과거 만족도·코멘트)">
        <div className="mb-3 flex gap-2">
          <input
            className="w-64 rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            placeholder="메뉴명 (예: 제육볶음)"
            value={menuName}
            onChange={(e) => setMenuName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setSearchedMenu(menuName)}
          />
          <Button onClick={() => setSearchedMenu(menuName)}>검색</Button>
        </div>
        {menuHistory.isLoading && <LoadingState />}
        {menuHistory.isError && <ErrorState error={menuHistory.error} />}
        {menuHistory.data && menuHistory.data.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이력이 없습니다 (recompute가 필요할 수 있습니다).
          </p>
        )}
        {menuHistory.data && menuHistory.data.length > 0 && (
          <Table
            columns={[
              { key: "period", label: "기간" },
              { key: "score", label: "만족도(표본보정)", align: "right" },
              { key: "count", label: "평가건수", align: "right" },
              { key: "quadrant", label: "4분면" },
            ]}
            rows={menuHistory.data.map((h) => ({
              period: `${h.period_start} ~ ${h.period_end}`,
              score: h.adjusted_score?.toFixed(2) ?? "-",
              count: h.evaluation_count,
              quadrant: <QuadrantBadge label={h.quadrant} />,
            }))}
            rowKey={(r) => r.period as string}
          />
        )}
      </Card>

    </div>
  );
}
