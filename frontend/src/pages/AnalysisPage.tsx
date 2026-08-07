import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import clsx from "clsx";
import {
  api,
  type Classification,
  type CornerTrendRow,
  type MealType,
  type MenuFoodVectorRow,
  type MenuPairRow,
  type MenuPerformanceRow,
  type MenuRotationRow,
  type PredictedNumbersRow,
  type TrendDirection,
  type WeeklyMenuPlanItem,
  type WeeklyMenuSlot,
} from "../api/client";
import {
  Button,
  Card,
  ErrorState,
  LoadingState,
  QuadrantBadge,
  resolveColor,
  SegmentedControl,
  StatTile,
  Table,
  quadrantColor,
  useChartTheme,
} from "../components/ui";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const PERIOD_END = isoDaysAgo(0);
const PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준

// 마우스를 올리면 나오는 숫자(차트 툴팁)는 표(.toFixed(2))와 자릿수를 맞춰
// 소수점 2자리까지만 보여준다 — axis-trigger 툴팁은 포맷터가 없으면 원본 값을
// 그대로 보여줘 자릿수가 길어질 수 있어 이 헬퍼로 통일한다.
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

// "YYYY-MM" 월 문자열 → 그 달의 [첫날, 마지막날] ISO 날짜 문자열.
function monthRange(period: string): [string, string] {
  const [y, m] = period.split("-").map(Number);
  const first = `${period}-01`;
  const last = new Date(y, m, 0).toISOString().slice(0, 10); // 다음달 0일 = 이번달 마지막날
  return [first, last];
}

// "YYYY-MM-DD" → "N주차 MM-DD" — 월을 주차 단위로 나눠 보여줄 때 쓴다.
function weekOfMonthLabel(dateIso: string): string {
  const day = Number(dateIso.slice(8, 10));
  const week = Math.ceil(day / 7);
  return `${week}주차 ${dateIso.slice(5)}`;
}

// 히트맵 값(0~1)이 낮음→높음으로 진해지는 단일 색상(blue) 시퀀셜 램프 —
// dataviz 스킬 palette.md의 sequential blue 램프 step 100/350/700과 동일한 값.
const SEQUENTIAL_BLUE_RAMP = ["#cde2fb", "#5598e7", "#0d366b"];

function hexToRgb(hex: string): [number, number, number] {
  const v = hex.replace("#", "");
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}

// share/maxShare를 0~1로 정규화해 SEQUENTIAL_BLUE_RAMP를 선형보간한다 — 주간
// 식단표 격자의 "전체 예측 비교" 배경 히트맵용(TasteClusterSection과 같은 램프,
// dataviz 스킬: sequential은 단일 색상 하나로만).
function shareToBackgroundRgb(share: number, maxShare: number): [number, number, number] | undefined {
  if (maxShare <= 0 || share <= 0) return undefined;
  const t = Math.max(0, Math.min(1, share / maxShare));
  const stops = SEQUENTIAL_BLUE_RAMP.map(hexToRgb);
  const scaled = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(scaled));
  const localT = scaled - i;
  const [r1, g1, b1] = stops[i];
  const [r2, g2, b2] = stops[i + 1];
  return [
    Math.round(r1 + (r2 - r1) * localT),
    Math.round(g1 + (g2 - g1) * localT),
    Math.round(b1 + (b2 - b1) * localT),
  ];
}

// WCAG 상대 명도/대비 계산(dataviz 스킬 validate_palette.js::contrast와 동일 공식) —
// 기존엔 share/maxShare > 0.55라는 임의 컷오프로 흰/회색/노란 텍스트를 골랐는데,
// 컷오프 아래(전체 셀의 절반 이상)에서 회색(--ink-muted)·노란색(--warning, 밝은
// 배경 대비 1.79:1로 사실상 안 보임)이 연한 파란 배경 위에 그대로 남아 대비가
// 낮았다 — 실제 배경색 명도로 흰색/기본잉크(--ink) 중 대비가 더 높은 쪽을 고른다.
function srgbChannelToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * srgbChannelToLinear(r) + 0.7152 * srgbChannelToLinear(g) + 0.0722 * srgbChannelToLinear(b);
}

function wcagContrast(a: [number, number, number], b: [number, number, number]): number {
  const [lumA, lumB] = [relativeLuminance(a), relativeLuminance(b)];
  const [hi, lo] = lumA > lumB ? [lumA, lumB] : [lumB, lumA];
  return (hi + 0.05) / (lo + 0.05);
}

const DARK_TEXT_RGB: [number, number, number] = [11, 11, 11]; // var(--ink)
const LIGHT_TEXT_RGB: [number, number, number] = [255, 255, 255];

function useLightTextOn(bgRgb: [number, number, number] | undefined): boolean {
  if (!bgRgb) return false;
  return wcagContrast(bgRgb, LIGHT_TEXT_RGB) > wcagContrast(bgRgb, DARK_TEXT_RGB);
}


// 코너별 분석 "코너별 비교" 통합 그래프의 지표 선택지 — 기존엔 (식수+만족도)/
// (서브속도+점유율) 두 고정 조합 그래프가 따로 있었는데(2026-07, 42.3), 사용자가
// 좌/우 축에 넣을 지표를 직접 고르는 그래프 하나로 재설계했다(2026-08).
type CornerMetricKey = "headcount" | "satisfaction" | "throughput" | "share";
const CORNER_METRIC_OPTIONS: { label: string; value: CornerMetricKey }[] = [
  { label: "식수", value: "headcount" },
  { label: "만족도", value: "satisfaction" },
  { label: "피크타임 서브속도", value: "throughput" },
  { label: "점유율", value: "share" },
];
const CORNER_METRIC_LABELS: Record<CornerMetricKey, string> = {
  headcount: "식수",
  satisfaction: "만족도",
  throughput: "피크타임 서브",
  share: "점유율(%)",
};
const CORNER_METRIC_AXIS: Record<CornerMetricKey, { name: string; min?: number; max?: number }> = {
  headcount: { name: "식수" },
  satisfaction: { name: "만족도", min: 0, max: 5 },
  throughput: { name: "피크타임 분당 서브" },
  share: { name: "점유율(%)", min: 0, max: 100 },
};

// 코너별 지표 비교 그래프 — 2026-08 화면 재편으로 "분석 > 코너별" 탭이 사라지면서
// 현황(HomePage)으로 옮겼다. 그래서 탭이 아니라 export되는 섹션 컴포넌트다.
export function CornerMetricComparisonSection() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [showCornerTable, setShowCornerTable] = useState(false);
  const [leftMetric, setLeftMetric] = useState<CornerMetricKey>("headcount");
  const [rightMetric, setRightMetric] = useState<CornerMetricKey>("satisfaction");
  function handleLeftMetricChange(v: CornerMetricKey) {
    if (v === rightMetric) setRightMetric(leftMetric);
    setLeftMetric(v);
  }
  function handleRightMetricChange(v: CornerMetricKey) {
    if (v === leftMetric) setLeftMetric(rightMetric);
    setRightMetric(v);
  }
  const chartTheme = useChartTheme();
  const query = useQuery({
    queryKey: ["corner-analysis", classification],
    queryFn: () =>
      api.cornerAnalysis({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        classification: classification === "전체" ? undefined : classification,
        exclude_take_out: true, // Take Out은 착석 취식이 아니라 혼잡도/만족도 분석 대상이 아님(홈 화면 식수 추이엔 남김)
      }),
  });
  const recomputeDailyStats = useMutation({
    mutationFn: () => api.recomputeDailyStats({ period_start: PERIOD_START, period_end: PERIOD_END }),
    onSuccess: () => query.refetch(),
  });

  // 파이차트·꺾은선그래프 색상을 코너 인기 순위가 아니라 코너 자체(corner_id)에 고정한다
  // (dataviz 스킬: "색은 순위가 아니라 개체를 따라간다" — 기간별로 랭킹이 바뀌어도 같은 코너는 같은 색).
  const SHARE_EXCLUDED_CORNER_NAMES = new Set(["미캠회관(전골)"]); // 그린미트(is_diet_corner)와 함께 점유율 비교에서 제외
  const stableCorners = [...(query.data ?? [])].sort((a, b) => a.corner_id - b.corner_id);
  const cornerColor = new Map(stableCorners.map((c, i) => [c.corner_id, `var(--series-${(i % 8) + 1})`]));

  const [trendGranularity, setTrendGranularity] = useState<"weekly" | "monthly" | "weekly-of-month">("weekly");
  const [weekOfMonthPeriod, setWeekOfMonthPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const isWeekOfMonth = trendGranularity === "weekly-of-month";
  const trendQuery = useQuery({
    queryKey: ["corner-analysis-trend", classification, trendGranularity],
    queryFn: () =>
      api.cornerAnalysisTrend({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        granularity: trendGranularity === "weekly-of-month" ? "weekly" : trendGranularity,
        classification: classification === "전체" ? undefined : classification,
        exclude_take_out: true,
      }),
    enabled: !isWeekOfMonth,
  });
  const trendPeriods = [...new Set((trendQuery.data ?? []).map((r) => r.period))].sort();
  const trendByCorner: Map<string, Map<string, CornerTrendRow>> = new Map();
  for (const row of trendQuery.data ?? []) {
    if (!trendByCorner.has(row.corner_name)) trendByCorner.set(row.corner_name, new Map());
    trendByCorner.get(row.corner_name)!.set(row.period, row);
  }
  // 시리즈 순서·색은 이미 정렬된 query.data(그린미트 항상 마지막) 순서를 그대로 따라간다.
  const trendCorners = (query.data ?? []).filter((c) => trendByCorner.has(c.corner_name));

  // "주차별" 모드 — 선택한 한 달을 일간 데이터로 받아 주차 라벨로 보여준다(값 자체는
  // 일간, 라벨만 "N주차"로 묶어 보여주는 방식 — 이래야 날짜별 데이터 포인트가
  // 그대로 남아 hover 시 그날의 메인메뉴를 붙일 수 있다).
  const [womPeriodStart, womPeriodEnd] = monthRange(weekOfMonthPeriod);
  const womQuery = useQuery({
    queryKey: ["corner-analysis-week-of-month", classification, weekOfMonthPeriod],
    queryFn: () =>
      api.cornerAnalysisTrend({
        period_start: womPeriodStart,
        period_end: womPeriodEnd,
        granularity: "daily",
        classification: classification === "전체" ? undefined : classification,
        exclude_take_out: true,
      }),
    enabled: isWeekOfMonth,
  });
  const womMainMenuQuery = useQuery({
    queryKey: ["corner-main-menu-by-date", weekOfMonthPeriod],
    queryFn: () => api.cornerMainMenuByDate({ period_start: womPeriodStart, period_end: womPeriodEnd }),
    enabled: isWeekOfMonth,
  });
  const womPeriods = [...new Set((womQuery.data ?? []).map((r) => r.period))].sort();
  const womByCorner: Map<string, Map<string, CornerTrendRow>> = new Map();
  for (const row of womQuery.data ?? []) {
    if (!womByCorner.has(row.corner_name)) womByCorner.set(row.corner_name, new Map());
    womByCorner.get(row.corner_name)!.set(row.period, row);
  }
  const womCorners = (query.data ?? []).filter((c) => womByCorner.has(c.corner_name));
  const cornerIdByName = new Map((query.data ?? []).map((c) => [c.corner_name, c.corner_id]));
  const mainMenuByCornerDate = new Map((womMainMenuQuery.data ?? []).map((r) => [`${r.corner_id}|${r.plan_date}`, r.menu_name]));

  // 두 모드(달력 전체 주간/월간 vs 선택한 한 달의 일별) 중 실제로 화면에 쓸 데이터를
  // 하나로 통일해서 아래 옵션 빌더가 모드를 신경 안 쓰게 한다.
  const activePeriods = isWeekOfMonth ? womPeriods : trendPeriods;
  const activeByCorner = isWeekOfMonth ? womByCorner : trendByCorner;
  const activeCorners = isWeekOfMonth ? womCorners : trendCorners;
  const activeIsLoading = isWeekOfMonth ? womQuery.isLoading || womMainMenuQuery.isLoading : trendQuery.isLoading;
  const activeIsError = isWeekOfMonth ? womQuery.isError : trendQuery.isError;
  const activeError = isWeekOfMonth ? womQuery.error : trendQuery.error;

  // 지표별 시리즈가 범례 단순화를 위해 코너명 하나를 공유하므로(2026-07,
  // "{코너} 식수"/"{코너} 만족도"로 항목이 2배라 보기 힘들다는 피드백), seriesId
  // (`"{코너}::headcount"` 등)로 지표를 구분해 툴팁에 라벨을 붙인다. 주차별 모드에선
  // 그날의 메인메뉴도 함께 보여준다.
  function buildMetricTooltipFormatter(metricLabels: Record<string, string>) {
    return (
      params: { axisValue?: string; marker: string; seriesName: string; seriesId?: string; value: unknown }[],
    ): string => {
      const date = params[0]?.axisValue ?? "";
      const header = isWeekOfMonth ? weekOfMonthLabel(date) : date;
      const lines = params.map((p) => {
        const value = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
        const suffix = p.seriesId?.split("::")[1];
        const metricLabel = suffix ? (metricLabels[suffix] ?? suffix) : "";
        const cornerId = cornerIdByName.get(p.seriesName);
        const menu = isWeekOfMonth && cornerId != null ? mainMenuByCornerDate.get(`${cornerId}|${date}`) : undefined;
        return `${p.marker}${p.seriesName}${metricLabel ? ` ${metricLabel}` : ""}: ${formatTooltipNumber(
          value as number | string,
        )}${menu ? ` (메인: ${menu})` : ""}`;
      });
      return [header, ...lines].join("<br/>");
    };
  }

  const trendXAxis = {
    type: "category" as const,
    data: activePeriods,
    axisLine: { lineStyle: { color: chartTheme.axis } },
    axisTick: { show: false },
    axisLabel: isWeekOfMonth
      ? { color: chartTheme.text, formatter: (v: string) => weekOfMonthLabel(v) }
      : { color: chartTheme.text },
  };

  // 점유율(share) 계산 대상 코너 — Take Out·그린미트·미캠회관(전골) 제외(착석
  // 취식 코너 간 경쟁 비교 목적, 2026-07). 점유율은 새 엔드포인트 없이 프론트에서
  // 그때그때 계산한다(cornerAnalysisTrend가 이미 코너·기간별 headcount를 반환).
  const shareEligibleCorners = activeCorners.filter(
    (c) => !c.is_diet_corner && !SHARE_EXCLUDED_CORNER_NAMES.has(c.corner_name),
  );
  const periodShareTotals = new Map<string, number>();
  for (const p of activePeriods) {
    let total = 0;
    for (const c of shareEligibleCorners) total += activeByCorner.get(c.corner_name)?.get(p)?.headcount ?? 0;
    periodShareTotals.set(p, total);
  }

  // 지표 선택형 통합 그래프 — 기존엔 (식수+만족도)/(서브속도+점유율) 고정 조합
  // 그래프 두 개가 따로 있었는데(2026-07, 42.3 — 그때는 비슷한 그래프가 여러 개
  // 나오는 걸 줄이려 이렇게 통합했었다), 사용자가 좌/우 축에 넣을 지표를 직접
  // 고르는 그래프 하나로 재설계했다(2026-08) — "이용자수 vs 서브속도"처럼 새
  // 조합도 그래프를 새로 안 만들고 그대로 볼 수 있다.
  function cornerMetricValue(metric: CornerMetricKey, cornerName: string, period: string): number | null {
    const row = activeByCorner.get(cornerName)?.get(period);
    if (metric === "headcount") return row?.headcount ?? null;
    if (metric === "satisfaction") return row?.avg_taste_score ?? null;
    if (metric === "throughput") return row?.avg_peak_throughput_per_min ?? null;
    const total = periodShareTotals.get(period) ?? 0;
    const headcount = row?.headcount;
    return total > 0 && headcount != null ? Number(((headcount / total) * 100).toFixed(2)) : null;
  }
  const cornerMetricCorners =
    leftMetric === "share" || rightMetric === "share" ? shareEligibleCorners : activeCorners;
  const cornerMetricTooltipFormatter = buildMetricTooltipFormatter({
    [leftMetric]: CORNER_METRIC_LABELS[leftMetric],
    [rightMetric]: CORNER_METRIC_LABELS[rightMetric],
  });
  // 서브속도가 축 중 하나면 전체 평균을 회색 점선으로 항상 표시한다(기존
  // buildMenuThroughputOption의 "전체 평균" 패턴과 동일한 취지) — 코너별
  // 시리즈 각각에 markLine을 달면 겹쳐 중복 렌더링되므로, 데이터 없는 전용
  // 시리즈 하나에만 붙인다.
  const overallThroughputAvg = (() => {
    if (leftMetric !== "throughput" && rightMetric !== "throughput") return null;
    const values: number[] = [];
    for (const c of cornerMetricCorners) {
      for (const p of activePeriods) {
        const v = activeByCorner.get(c.corner_name)?.get(p)?.avg_peak_throughput_per_min;
        if (v != null) values.push(v);
      }
    }
    return values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;
  })();
  const throughputMarkLineSeries =
    overallThroughputAvg != null
      ? [
          {
            name: "전체 평균(서브속도)",
            type: "line" as const,
            yAxisIndex: leftMetric === "throughput" ? 0 : 1,
            data: [] as number[],
            silent: true,
            symbol: "none" as const,
            lineStyle: { opacity: 0 },
            markLine: {
              symbol: "none" as const,
              label: { formatter: "전체 평균", color: chartTheme.text },
              lineStyle: { color: chartTheme.axis, type: "dashed" as const },
              data: [{ yAxis: overallThroughputAvg }],
            },
          },
        ]
      : [];
  const cornerMetricOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 56, right: 56, top: 40, bottom: 28 },
    tooltip: { trigger: "axis", formatter: cornerMetricTooltipFormatter },
    legend: { top: 0, textStyle: { color: chartTheme.text }, data: cornerMetricCorners.map((c) => c.corner_name) },
    xAxis: trendXAxis,
    yAxis: [
      {
        type: "value",
        ...CORNER_METRIC_AXIS[leftMetric],
        axisLabel: { color: chartTheme.text },
        splitLine: { lineStyle: { color: chartTheme.grid } },
      },
      {
        type: "value",
        ...CORNER_METRIC_AXIS[rightMetric],
        axisLabel: { color: chartTheme.text },
        splitLine: { show: false },
      },
    ],
    series: [
      ...cornerMetricCorners.flatMap((c) => {
        const color = resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)");
        return [
          {
            id: `${c.corner_name}::${leftMetric}`,
            name: c.corner_name,
            type: "line" as const,
            yAxisIndex: 0,
            symbol: "circle",
            symbolSize: 8,
            lineStyle: { width: 2, color },
            itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
            data: activePeriods.map((p) => cornerMetricValue(leftMetric, c.corner_name, p)),
          },
          {
            id: `${c.corner_name}::${rightMetric}`,
            name: c.corner_name,
            type: "line" as const,
            yAxisIndex: 1,
            symbol: "diamond",
            symbolSize: 8,
            lineStyle: { width: 2, type: "dashed" as const, color },
            itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
            data: activePeriods.map((p) => cornerMetricValue(rightMetric, c.corner_name, p)),
          },
        ];
      }),
      ...throughputMarkLineSeries,
    ],
  };

  return (
    <div className="space-y-6">
      <Card title="코너별 분석 — 지표 비교 (식수 / 만족도 / 피크타임 서브속도 / 점유율)">
        <div className="mb-4">
          <SegmentedControl
            value={classification}
            options={[
              { label: "전체", value: "전체" },
              { label: "평일", value: "평일" },
              { label: "주말+공휴일", value: "주말+공휴일" },
              { label: "패밀리데이", value: "패밀리데이" },
            ]}
            onChange={setClassification}
          />
        </div>
        {query.isLoading && <LoadingState />}
        {query.isError && <ErrorState error={query.error} />}
        {query.data && query.data.length === 0 && (
          <div className="space-y-2">
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              데이터가 없습니다. 배치 집계(daily_corner_stats)가 먼저 필요합니다 — 취식 데이터를 과거 기간
              한꺼번에 적재한 경우, 스케줄러는 매일 새벽 전날치만 계산하므로 최근 180일치를 한 번에 다시
              계산해야 합니다.
            </p>
            <Button variant="secondary" onClick={() => recomputeDailyStats.mutate()} disabled={recomputeDailyStats.isPending}>
              {recomputeDailyStats.isPending ? "계산 중..." : "최근 180일 배치 집계 재계산"}
            </Button>
            {recomputeDailyStats.isError && <ErrorState error={recomputeDailyStats.error} />}
          </div>
        )}
        {query.data && query.data.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
                기간 단위 — 아래 두 추이 그래프에 공통 적용됩니다.
                {isWeekOfMonth && " 그래프의 각 점에 마우스를 올리면 그날의 메인메뉴가 함께 표시됩니다."}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {isWeekOfMonth && (
                  <input
                    type="month"
                    value={weekOfMonthPeriod}
                    onChange={(e) => e.target.value && setWeekOfMonthPeriod(e.target.value)}
                    className="rounded-md border px-3 py-2 text-[13px]"
                    style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                  />
                )}
                <SegmentedControl
                  value={trendGranularity}
                  options={[
                    { label: "주간", value: "weekly" },
                    { label: "월간", value: "monthly" },
                    { label: "주차별", value: "weekly-of-month" },
                  ]}
                  onChange={setTrendGranularity}
                />
              </div>
            </div>
            <div className="mt-4">
              <Button variant="secondary" onClick={() => setShowCornerTable((v) => !v)}>
                {showCornerTable ? "표 숨기기" : "표로 보기"}
              </Button>
              {showCornerTable && (
                <div className="mt-3">
                  <Table
                    columns={[
                      { key: "corner", label: "코너" },
                      { key: "diet", label: "그린미트" },
                      { key: "headcount", label: "누적 식수", align: "right" },
                      { key: "score", label: "평균 만족도", align: "right" },
                      { key: "throughput", label: "피크타임 분당 서브", align: "right" },
                    ]}
                    rows={query.data.map((c) => ({
                      corner: c.corner_name,
                      diet: c.is_diet_corner ? "예" : "-",
                      headcount: c.headcount_total.toLocaleString(),
                      score: c.avg_taste_score?.toFixed(2) ?? "-",
                      throughput: c.avg_peak_throughput_per_min?.toFixed(2) ?? "-",
                    }))}
                    rowKey={(r) => r.corner as string}
                  />
                </div>
              )}
            </div>
            <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
              <div className="mb-3">
                <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  왼쪽/오른쪽 축에 넣을 지표를 각각 고르세요 — 점유율은 Take Out·그린미트·미캠회관(전골)을 제외한
                  착석 취식 코너 기준입니다. 범례를 클릭하면 코너별로 켜고 끌 수 있습니다.
                </p>
              </div>
              <>
                  <div className="mb-3 flex flex-wrap items-center gap-3 text-[13px]">
                    <label className="flex items-center gap-1.5" style={{ color: "var(--ink-secondary)" }}>
                      왼쪽 축
                      <select
                        value={leftMetric}
                        onChange={(e) => handleLeftMetricChange(e.target.value as CornerMetricKey)}
                        className="rounded-md border px-2 py-1 text-[13px]"
                        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                      >
                        {CORNER_METRIC_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5" style={{ color: "var(--ink-secondary)" }}>
                      오른쪽 축
                      <select
                        value={rightMetric}
                        onChange={(e) => handleRightMetricChange(e.target.value as CornerMetricKey)}
                        className="rounded-md border px-2 py-1 text-[13px]"
                        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                      >
                        {CORNER_METRIC_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {activeIsLoading && <LoadingState />}
                  {activeIsError && <ErrorState error={activeError} />}
                  {activePeriods.length > 0 && cornerMetricCorners.length === 0 && (
                    <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                      비교할 코너가 없습니다.
                    </p>
                  )}
                  {activePeriods.length > 0 && cornerMetricCorners.length > 0 && (
                    <ReactECharts option={cornerMetricOption} style={{ height: 380 }} />
                  )}
                </>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

const ALL_MENUS_TAB = "전체";

// 메뉴 쌍을 표(정확한 수치)와 함께 관계도(연결성)로도 보여준다 — 노드 크기는
// 그 메뉴가 관련된 쌍들의 동반 인원 합, 엣지 굵기는 lift(연관 강도)에 비례.
function buildMenuPairGraphOption(
  pairs: MenuPairRow[],
  nodeColor: string,
  chartTheme: { text: string },
) {
  const nodeWeight = new Map<string, number>();
  for (const p of pairs) {
    nodeWeight.set(p.menu_a, (nodeWeight.get(p.menu_a) ?? 0) + p.co_count);
    nodeWeight.set(p.menu_b, (nodeWeight.get(p.menu_b) ?? 0) + p.co_count);
  }
  const maxWeight = Math.max(1, ...nodeWeight.values());
  const maxLift = Math.max(1, ...pairs.map((p) => p.lift));

  const nodes = [...nodeWeight.entries()].map(([name, weight]) => ({
    name,
    symbolSize: 14 + (weight / maxWeight) * 22,
    itemStyle: { color: nodeColor },
    // formatter를 안 주면 ECharts가 값(숫자)을 찍는다 — 메뉴명이 나와야 한다.
    label: {
      show: true,
      position: "right" as const,
      color: chartTheme.text,
      fontSize: 11,
      formatter: (p: { name: string }) => p.name,
    },
  }));
  const edges = pairs.map((p) => ({
    source: p.menu_a,
    target: p.menu_b,
    value: p.lift,
    co_count: p.co_count,
    lineStyle: { width: 1 + (p.lift / maxLift) * 4, color: nodeColor, opacity: 0.4, curveness: 0.1 },
  }));

  return {
    tooltip: {
      formatter: (params: {
        dataType?: string;
        name?: string;
        data?: { source?: string; target?: string; value?: number; co_count?: number };
      }) => {
        if (params.dataType === "edge") {
          const d = params.data ?? {};
          return `${d.source} + ${d.target}<br/>동반 인원: ${d.co_count}<br/>lift: ${formatTooltipNumber(d.value ?? 0)}`;
        }
        return params.name ?? "";
      },
    },
    series: [
      {
        type: "graph" as const,
        layout: "force" as const,
        roam: true,
        draggable: true,
        force: { repulsion: 140, edgeLength: [40, 100] },
        edgeSymbol: ["none", "none"],
        nodes,
        edges,
      },
    ],
  };
}

type PairSortKey = "co_count" | "lift";

// PRD 10-2: 메뉴 동반 선택 쌍 = "메뉴 선호 연관 분석"(장바구니 분석과 같은 개념).
// "부대찌개+참치김치찌개"처럼 자명한 조합(같은 카테고리)은 기본으로 숨기고,
// 연관도(lift) 기준으로 정렬하면 "부대찌개를 선호하는 사람이 떡볶이도 유의미하게
// 선호한다" 같은 직관적이지 않은 조합이 먼저 보인다.
function MenuPairAnalysisSection({ corners }: { corners: { corner_id: number; corner_name: string }[] }) {
  const chartTheme = useChartTheme();
  const [selection, setSelection] = useState<string>(ALL_MENUS_TAB);
  const [minVisitCount, setMinVisitCount] = useState(3);
  const [minShare, setMinShare] = useState(30);
  const [minCoCount, setMinCoCount] = useState(3);
  const [sortKey, setSortKey] = useState<PairSortKey>("co_count");
  const [showObviousPairs, setShowObviousPairs] = useState(false);

  const isAll = selection === ALL_MENUS_TAB;
  const effectiveCornerId = isAll ? null : Number(selection);

  const cornerQuery = useQuery({
    queryKey: ["corner-core-layer-menu-pairs", effectiveCornerId, minVisitCount, minShare],
    queryFn: () =>
      api.cornerCoreLayerMenuPairs(effectiveCornerId as number, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        min_visit_count: minVisitCount,
        min_share: minShare / 100,
      }),
    enabled: !isAll && effectiveCornerId != null,
  });

  const allQuery = useQuery({
    queryKey: ["top-menu-pairs", minCoCount],
    queryFn: () =>
      api.topMenuPairs({ period_start: PERIOD_START, period_end: PERIOD_END, min_co_count: minCoCount }),
    enabled: isAll,
  });

  function filterAndSort(rows: MenuPairRow[]): MenuPairRow[] {
    const filtered = showObviousPairs ? rows : rows.filter((r) => r.is_obvious_pair !== true);
    return [...filtered].sort((a, b) => (sortKey === "lift" ? b.lift - a.lift : b.co_count - a.co_count));
  }

  const pairColumns = [
    { key: "pair", label: "메뉴 쌍" },
    { key: "co_count", label: "동반 인원", align: "right" as const },
    { key: "lift", label: "연관도(lift, 그룹 내부 기준)", align: "right" as const },
  ];
  const pairRows = (rows: MenuPairRow[]) =>
    filterAndSort(rows).map((r) => ({
      pair: r.is_obvious_pair ? `${r.menu_a} + ${r.menu_b} (자명)` : `${r.menu_a} + ${r.menu_b}`,
      co_count: r.co_count,
      lift: r.lift.toFixed(2),
    }));

  const crossPairColumns = [
    { key: "pair", label: "메뉴 쌍" },
    { key: "corners", label: "코너 조합" },
    { key: "co_count", label: "동반 인원", align: "right" as const },
    { key: "lift", label: "연관도(lift, 그룹 내부 기준)", align: "right" as const },
  ];
  const crossPairRows = (rows: MenuPairRow[]) =>
    filterAndSort(rows).map((r) => ({
      pair: r.is_obvious_pair ? `${r.menu_a} + ${r.menu_b} (자명)` : `${r.menu_a} + ${r.menu_b}`,
      corners: `${r.corner_a ?? "-"} ↔ ${r.corner_b ?? "-"}`,
      co_count: r.co_count,
      lift: r.lift.toFixed(2),
    }));

  const sortAndFilterControls = (
    <>
      <SegmentedControl
        value={sortKey}
        options={[
          { label: "동반 인원순", value: "co_count" },
          { label: "연관도(lift)순", value: "lift" },
        ]}
        onChange={setSortKey}
      />
      <label className="flex items-center gap-1.5 text-xs" style={{ color: "var(--ink-muted)" }}>
        <input
          type="checkbox"
          checked={showObviousPairs}
          onChange={(e) => setShowObviousPairs(e.target.checked)}
        />
        자명한 조합도 보기
      </label>
    </>
  );

  if (corners.length === 0) return null;

  return (
    <Card title="메뉴 동반 선택 쌍 — 메뉴 선호 연관 분석">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        "전체"는 코너 구분 없이 전체 인원 기준, 코너를 선택하면 그 코너 코어층/나머지가 각각 가장 흔하게
        함께 고르는 메뉴 쌍을 봅니다(lift는 각 그룹 내부 기준이라 그룹 간 직접 비교는 동반 인원 수로
        합니다). 자명한 조합(같은 음식 카테고리, food_vector 유사도 기준)은 기본으로 숨겨 뻔하지 않은
        연관관계가 먼저 보이게 합니다.
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl
          value={selection}
          options={[
            { label: ALL_MENUS_TAB, value: ALL_MENUS_TAB },
            ...corners.map((c) => ({ label: c.corner_name, value: String(c.corner_id) })),
          ]}
          onChange={setSelection}
        />
        {isAll ? (
          <label className="flex items-center gap-1 text-xs" style={{ color: "var(--ink-muted)" }}>
            최소 동반 인원
            <input
              type="number"
              min={1}
              className="w-14 rounded-md border px-2 py-1 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              value={minCoCount}
              onChange={(e) => setMinCoCount(Number(e.target.value))}
            />
          </label>
        ) : (
          <>
            <label className="flex items-center gap-1 text-xs" style={{ color: "var(--ink-muted)" }}>
              최소 방문횟수
              <input
                type="number"
                min={1}
                className="w-14 rounded-md border px-2 py-1 text-[13px]"
                style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                value={minVisitCount}
                onChange={(e) => setMinVisitCount(Number(e.target.value))}
              />
            </label>
            <label className="flex items-center gap-1 text-xs" style={{ color: "var(--ink-muted)" }}>
              최소 비중(%)
              <input
                type="number"
                min={0}
                max={100}
                className="w-14 rounded-md border px-2 py-1 text-[13px]"
                style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                value={minShare}
                onChange={(e) => setMinShare(Number(e.target.value))}
              />
            </label>
          </>
        )}
        {sortAndFilterControls}
      </div>

      {isAll ? (
        <>
          {allQuery.isLoading && <LoadingState />}
          {allQuery.isError && <ErrorState error={allQuery.error} />}
          {allQuery.data && allQuery.data.length === 0 && (
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              표본 부족
            </p>
          )}
          {allQuery.data && allQuery.data.length > 0 && (
            <>
              <ReactECharts
                option={buildMenuPairGraphOption(
                  filterAndSort(allQuery.data),
                  resolveColor("var(--accent)"),
                  chartTheme,
                )}
                style={{ height: 320 }}
              />
              <Table columns={pairColumns} rows={pairRows(allQuery.data)} rowKey={(r) => r.pair as string} />
            </>
          )}
        </>
      ) : (
        <>
          {cornerQuery.isLoading && <LoadingState />}
          {cornerQuery.isError && <ErrorState error={cornerQuery.error} />}
          {cornerQuery.data && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  코어층 ({cornerQuery.data.core_layer.employee_count}명)
                </p>
                {cornerQuery.data.core_layer.top_pairs.length === 0 ? (
                  <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                    표본 부족
                  </p>
                ) : (
                  <>
                    <ReactECharts
                      option={buildMenuPairGraphOption(
                        filterAndSort(cornerQuery.data.core_layer.top_pairs),
                        resolveColor("var(--series-1)"),
                        chartTheme,
                      )}
                      style={{ height: 260 }}
                    />
                    <Table
                      columns={pairColumns}
                      rows={pairRows(cornerQuery.data.core_layer.top_pairs)}
                      rowKey={(r) => r.pair as string}
                    />
                  </>
                )}
                <div className="mt-4">
                  <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                    다른 코너 조합 Top {cornerQuery.data.core_layer.cross_corner_pairs.length} — 같은 코너
                    조합에 묻히지 않게 따로 모았습니다
                  </p>
                  {cornerQuery.data.core_layer.cross_corner_pairs.length === 0 ? (
                    <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                      표본 부족
                    </p>
                  ) : (
                    <Table
                      columns={crossPairColumns}
                      rows={crossPairRows(cornerQuery.data.core_layer.cross_corner_pairs)}
                      rowKey={(r) => r.pair as string}
                    />
                  )}
                </div>
              </div>
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  나머지 ({cornerQuery.data.non_core.employee_count}명)
                </p>
                {cornerQuery.data.non_core.top_pairs.length === 0 ? (
                  <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                    표본 부족
                  </p>
                ) : (
                  <>
                    <ReactECharts
                      option={buildMenuPairGraphOption(
                        filterAndSort(cornerQuery.data.non_core.top_pairs),
                        resolveColor("var(--series-2)"),
                        chartTheme,
                      )}
                      style={{ height: 260 }}
                    />
                    <Table
                      columns={pairColumns}
                      rows={pairRows(cornerQuery.data.non_core.top_pairs)}
                      rowKey={(r) => r.pair as string}
                    />
                  </>
                )}
                <div className="mt-4">
                  <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                    다른 코너 조합 Top {cornerQuery.data.non_core.cross_corner_pairs.length} — 같은 코너
                    조합에 묻히지 않게 따로 모았습니다
                  </p>
                  {cornerQuery.data.non_core.cross_corner_pairs.length === 0 ? (
                    <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                      표본 부족
                    </p>
                  ) : (
                    <Table
                      columns={crossPairColumns}
                      rows={crossPairRows(cornerQuery.data.non_core.cross_corner_pairs)}
                      rowKey={(r) => r.pair as string}
                    />
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

const UNASSIGNED_CORNER = "코너 미배정";

// 메뉴가 너무 많아 표 하나로는 훑어보기 어려우므로, 코너별로 묶어 카드 그리드로
// 보여주고 클릭한 코너의 상세만 펼치는 패턴을 여러 섹션(메뉴 4분면, 음식벡터
// 관리)에서 공유한다 — HomePage.tsx의 VOE 분류 타일과 같은 클릭-확장 컨벤션.
function groupByCorner<T extends { corner_name: string | null }>(rows: T[]): [string, T[]][] {
  const byCorner = new Map<string, T[]>();
  for (const r of rows) {
    const key = r.corner_name ?? UNASSIGNED_CORNER;
    if (!byCorner.has(key)) byCorner.set(key, []);
    byCorner.get(key)!.push(r);
  }
  return [...byCorner.entries()].sort((a, b) => b[1].length - a[1].length);
}

function CornerCardGrid({
  groups,
  selected,
  onSelect,
}: {
  groups: [string, unknown[]][];
  selected: string | null;
  onSelect: (cornerName: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {groups.map(([cornerName, items]) => (
        <button
          key={cornerName}
          onClick={() => onSelect(cornerName)}
          className="rounded-xl border p-3 text-left transition-colors"
          style={{
            borderColor: selected === cornerName ? "var(--accent)" : "var(--border)",
            background: selected === cornerName ? "var(--surface-2)" : "var(--surface)",
          }}
        >
          <div className="text-[13px] font-medium">{cornerName}</div>
          <div className="mt-1 text-lg font-semibold">{items.length}개 메뉴</div>
        </button>
      ))}
    </div>
  );
}

const QUADRANT_LABELS = ["인기메뉴", "숨은강자", "개선시급", "퇴출후보", "표본부족"] as const;

// 제공 횟수(appearance_count)가 이 미만이면 "1회 제공당 평균 식수"가 하루
// 우연한 결과에 크게 흔들릴 수 있다 — 버블을 작게 그리고 점선 테두리로
// 표시해 표본이 적다는 걸 한눈에 알 수 있게 한다(축 계산식 자체는 그대로,
// 시각적 구분만 추가 — 2026-07 사용자 확정).
const LOW_APPEARANCE_THRESHOLD = 3;

type MenuQuadrantMetrics = MenuPerformanceRow & {
  demand: number;
  satisfaction: number;
  isLowSample: boolean;
  effectiveQuadrant: string;
};

// 백엔드 classify_menu_quadrant(app/services/menu_performance.py)와 동일한 규칙을
// 프론트에서 재현한다 — 표본부족 판정(evaluation_count 기준)과 만족도 추세/
// 로열티(satisfactionTrend/hasLoyalFollowing, 2026-07)는 슬라이더로 조절할 수
// 없는 서버 계산값이라 그대로 받아 쓰고, 수요/만족도 기준값만 화면에서 바꾼다.
function classifyQuadrantClient(
  demand: number,
  satisfaction: number,
  isLowSample: boolean,
  demandThreshold: number,
  scoreThreshold: number,
  satisfactionTrend: TrendDirection | null,
  hasLoyalFollowing: boolean,
): string {
  if (isLowSample) return "표본부족";
  const highDemand = demand >= demandThreshold;
  const satisfactionOk = satisfaction >= scoreThreshold && satisfactionTrend !== "하락";
  if (highDemand) return satisfactionOk ? "인기메뉴" : "개선시급";
  if (hasLoyalFollowing) return "숨은강자";
  return satisfactionOk ? "숨은강자" : "퇴출후보";
}

const QUADRANT_LIMIT_OPTIONS: { label: string; value: "5" | "10" | "20" | "all" }[] = [
  { label: "5개", value: "5" },
  { label: "10개", value: "10" },
  { label: "20개", value: "20" },
  { label: "전체", value: "all" },
];

// 하나의 통합 산점도로 전체 메뉴를 한눈에 본다(2026-08, 사용자 결정: "한눈에
// 보고 싶은 게 더 큼" — 분면별 패널 분리(2026-07, 42.2/42.4)보다 한 화면에서
// 전체 분포를 보는 걸 우선). X축=만족도, Y축=수요(2026-08, 스펙 요청대로 축
// 반전 — 이전엔 X=수요/Y=만족도였다). 겹침 완화는 패널 분리 대신 이후 라운드에
// 추가된 labelLayout.hideOverlap(43번 라운드, 세로로 먼저 밀어보고 그래도
// 겹치면 숨김)에 의존한다 — 분면(색)별로 시리즈를 나눠 기존 범례 토글(화면
// 상단 분면 필터)이 그대로 동작하게 하고, 배경에 사분면 음영(markArea)과
// 기준값 십자선(markLine)을 별도의 빈 시리즈로 얹어 어느 분면인지 즉시 보이게
// 한다. 배경 음영은 순수 수요/만족도 임계값 기준이라, 만족도 추세 하락·로열티
// 등으로 실제 분류가 임계값과 다르게 override된 점은 점 색(진짜 분류)과 배경
// 음영(단순 임계값)이 어긋나 보일 수 있다 — 그 자체가 "왜 이 위치인데 이
// 분류지?"를 알아챌 수 있는 신호이므로 툴팁에 추세/로열티를 표기해 설명한다.
function buildUnifiedQuadrantOption(
  quadrantRows: Map<string, MenuQuadrantMetrics[]>,
  visibleLabels: readonly string[],
  quadrantLimitN: number,
  demandThreshold: number,
  scoreThreshold: number,
  maxDemand: number,
  chartTheme: ReturnType<typeof useChartTheme>,
) {
  const REAL_QUADRANTS = ["인기메뉴", "개선시급", "숨은강자", "퇴출후보"];

  function buildSeriesData(items: MenuQuadrantMetrics[]) {
    const ordered = [...items].sort((a, b) => b.appearance_count - a.appearance_count).slice(0, quadrantLimitN);
    const maxAppearance = Math.max(1, ...ordered.map((r) => r.appearance_count));
    return ordered.map((r) => {
      const isLowAppearance = r.appearance_count < LOW_APPEARANCE_THRESHOLD;
      const label = r.corner_name ? `${r.menu_name} (${r.corner_name})` : r.menu_name;
      return {
        name: label,
        value: [r.satisfaction, r.demand, r.appearance_count],
        satisfactionTrend: r.satisfaction_trend,
        hasLoyalFollowing: r.has_loyal_following,
        symbolSize: 8 + Math.sqrt(r.appearance_count / maxAppearance) * 22,
        itemStyle: {
          opacity: isLowAppearance ? 0.45 : 0.9,
          borderColor: isLowAppearance ? resolveColor("var(--ink-muted)") : "transparent",
          borderWidth: isLowAppearance ? 1.5 : 0,
          borderType: isLowAppearance ? ("dashed" as const) : ("solid" as const),
        },
        label: {
          show: true,
          formatter: label,
          position: "right" as const,
          color: chartTheme.text,
          fontSize: 11,
        },
      };
    });
  }

  const quadrantSeries = QUADRANT_LABELS.filter((label) => visibleLabels.includes(label)).map((label) => ({
    name: label,
    type: "scatter" as const,
    itemStyle: { color: resolveColor(quadrantColor(label)) },
    data: buildSeriesData(quadrantRows.get(label) ?? []),
    labelLayout: { moveOverlap: "shiftY" as const, hideOverlap: true },
  }));

  const backgroundSeries = {
    name: "__background",
    type: "scatter" as const,
    data: [] as unknown[],
    silent: true,
    tooltip: { show: false },
    markArea: {
      silent: true,
      label: { color: chartTheme.text, fontSize: 12, fontWeight: 600 as const },
      data: REAL_QUADRANTS.map((label) => {
        const isHighSatisfaction = label === "인기메뉴" || label === "숨은강자";
        const isHighDemand = label === "인기메뉴" || label === "개선시급";
        return [
          {
            name: label,
            xAxis: isHighSatisfaction ? scoreThreshold : 0,
            yAxis: isHighDemand ? demandThreshold : 0,
            itemStyle: { color: resolveColor(quadrantColor(label)), opacity: 0.06 },
          },
          {
            xAxis: isHighSatisfaction ? 5 : scoreThreshold,
            yAxis: isHighDemand ? maxDemand : demandThreshold,
          },
        ];
      }),
    },
    markLine: {
      silent: true,
      symbol: "none" as const,
      label: { show: false },
      lineStyle: { type: "dashed" as const, color: chartTheme.axis },
      data: [{ xAxis: scoreThreshold }, { yAxis: demandThreshold }],
    },
  };

  return {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 24, top: 16, bottom: 40 },
    tooltip: {
      formatter: (p: {
        seriesName?: string;
        data: {
          name: string;
          value: number[];
          satisfactionTrend: TrendDirection | null;
          hasLoyalFollowing: boolean;
        };
      }) => {
        const lines = [
          p.data.name,
          `분류: ${p.seriesName}`,
          `만족도: ${p.data.value[0].toFixed(2)}`,
          `수요: ${p.data.value[1].toFixed(2)}`,
          `제공 횟수: ${p.data.value[2]}회`,
        ];
        if (p.data.satisfactionTrend === "하락") lines.push("만족도 추세: 하락");
        if (p.data.hasLoyalFollowing) lines.push("고정 고객 있음");
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      name: "만족도",
      min: 0,
      max: 5,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "value",
      name: "수요(1회 제공당 평균 식수)",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [backgroundSeries, ...quadrantSeries],
  };
}

type SortKey = "menu" | "appearance" | "count" | "score";

function SortableHeader({
  label,
  active,
  dir,
  align,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: "asc" | "desc";
  align?: "left" | "right";
  onClick: () => void;
}) {
  return (
    <th
      className={clsx(
        "cursor-pointer select-none border-b py-2 pr-4 font-medium",
        align === "right" && "text-right",
      )}
      style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
      onClick={onClick}
    >
      {label}
      <span style={{ color: active ? "var(--ink-secondary)" : "transparent" }}> {dir === "asc" ? "▲" : "▼"}</span>
    </th>
  );
}

function MenuQuadrantTab() {
  const chartTheme = useChartTheme();
  const [expandedCorner, setExpandedCorner] = useState<string | null>(null);
  const [demandThresholdOverride, setDemandThresholdOverride] = useState<number | null>(null);
  const [scoreThresholdOverride, setScoreThresholdOverride] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("appearance");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [visibleQuadrants, setVisibleQuadrants] = useState<Set<string>>(new Set(QUADRANT_LABELS));
  const [quadrantLimit, setQuadrantLimit] = useState<(typeof QUADRANT_LIMIT_OPTIONS)[number]["value"]>("10");
  // 조식/중식/석식마다 나오는 메뉴가 달라 전체로 묶어 보면 비교가 안 맞는다 —
  // "전체"는 기존 사전 recompute된 MenuPerformanceStats, 특정 끼니는 그 자리에서
  // 계산하는 by-meal-type 엔드포인트로 전환한다(2026-07).
  const [mealTypeFilter, setMealTypeFilter] = useState<MealType | "전체">("전체");
  const query = useQuery({
    queryKey: ["menu-performance", PERIOD_START, PERIOD_END, mealTypeFilter],
    queryFn: () =>
      mealTypeFilter === "전체"
        ? api.menuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END })
        : api.menuPerformanceByMealType({
            period_start: PERIOD_START,
            period_end: PERIOD_END,
            meal_type: mealTypeFilter,
          }),
  });
  const recompute = () => api.recomputeMenuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END });

  const rows = query.data ?? [];
  const metrics: MenuQuadrantMetrics[] = rows.map((r) => ({
    ...r,
    demand: r.total_headcount / Math.max(r.appearance_count, 1),
    satisfaction: r.adjusted_score ?? 0,
    isLowSample: r.quadrant === "표본부족",
    effectiveQuadrant: "",
  }));

  const autoDemandThreshold = median(metrics.map((r) => r.demand));
  const autoScoreThreshold = median(metrics.map((r) => r.satisfaction));
  const demandThreshold = demandThresholdOverride ?? autoDemandThreshold;
  const scoreThreshold = scoreThresholdOverride ?? autoScoreThreshold;
  const maxDemand = Math.max(1, ...metrics.map((r) => r.demand));

  const classified: MenuQuadrantMetrics[] = metrics.map((r) => ({
    ...r,
    effectiveQuadrant: classifyQuadrantClient(
      r.demand,
      r.satisfaction,
      r.isLowSample,
      demandThreshold,
      scoreThreshold,
      r.satisfaction_trend,
      r.has_loyal_following,
    ),
  }));
  const cornerGroups = groupByCorner(classified);

  function toggleQuadrant(label: string) {
    setVisibleQuadrants((cur) => {
      const next = new Set(cur);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  // 분면별로 따로 떼어 보여준다(겹치는 산점도 대신 분면당 패널 하나) — 각 패널은
  // demand 내림차순으로 정렬해 quadrantLimit개까지만 보여준다(2026-07).
  const quadrantRows = new Map<string, MenuQuadrantMetrics[]>();
  for (const label of QUADRANT_LABELS) quadrantRows.set(label, []);
  for (const r of classified) quadrantRows.get(r.effectiveQuadrant)?.push(r);
  const quadrantLimitN = quadrantLimit === "all" ? Infinity : Number(quadrantLimit);
  const visibleQuadrantLabels = QUADRANT_LABELS.filter((label) => visibleQuadrants.has(label));

  const expandedRows = (cornerGroups.find(([c]) => c === expandedCorner)?.[1] ?? []).filter((r) =>
    visibleQuadrants.has(r.effectiveQuadrant),
  );
  const sortedExpandedRows = [...expandedRows].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "menu") cmp = a.menu_name.localeCompare(b.menu_name, "ko");
    else if (sortKey === "appearance") cmp = a.appearance_count - b.appearance_count;
    else if (sortKey === "count") cmp = a.evaluation_count - b.evaluation_count;
    else if (sortKey === "score") cmp = a.satisfaction - b.satisfaction;
    return sortDir === "asc" ? cmp : -cmp;
  });

  return (
    <Card title="메뉴별 분석 — 인기메뉴 / 숨은강자 / 개선시급 / 퇴출후보">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        가로축(만족도)과 세로축(1회 제공당 평균 식수, 수요)이 각각 기준값보다 큰지
        작은지로 네 가지로 나눠 배경 음영과 점선 십자선으로 표시합니다. 기준값은
        기본적으로 전체 메뉴의 중앙값이며, 아래 슬라이더로 직접 조절할 수 있습니다
        (표본부족 판정은 평가건수 기준으로 별도 처리되어 조절 대상이 아닙니다). 점
        옆에 "메뉴명 (코너명)"을 표기합니다(흐린 점 = 최근 {LOW_APPEARANCE_THRESHOLD}
        회 미만 제공이라 수요 수치가 우연한 결과로 튈 수 있음, 원 크기는 제공 횟수).
        점이 너무 몰려 라벨이 겹치면 일부는 자동으로 숨겨지는데, 안 보이는 점도
        마우스를 올리면 툴팁으로 확인할 수 있습니다(만족도 추세가 하락 중이거나
        고정 고객이 있으면 배경 음영과 다른 분류로 표시될 수 있는데, 그 이유도
        툴팁에 나옵니다). 위 분류 버튼을 클릭하면 보고 싶은 분류만 골라 볼 수
        있고, "표시 개수"로 분류별 표시 개수를 조절할 수 있습니다.
      </p>
      <div className="mb-3">
        <SegmentedControl
          value={mealTypeFilter}
          options={[
            { label: "전체", value: "전체" },
            { label: "조식", value: "조식" },
            { label: "중식", value: "중식" },
            { label: "석식", value: "석식" },
          ]}
          onChange={setMealTypeFilter}
        />
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          {QUADRANT_LABELS.map((label) => {
            const active = visibleQuadrants.has(label);
            return (
              <button
                key={label}
                onClick={() => toggleQuadrant(label)}
                className="inline-flex items-center gap-1.5 rounded px-1 py-0.5 transition-opacity"
                style={{ color: "var(--ink-secondary)", opacity: active ? 1 : 0.35 }}
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: resolveColor(quadrantColor(label)) }}
                />
                {label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            <span>표시 개수</span>
            <SegmentedControl value={quadrantLimit} options={QUADRANT_LIMIT_OPTIONS} onChange={setQuadrantLimit} />
          </div>
          {mealTypeFilter === "전체" && (
            <Button
              variant="secondary"
              onClick={async () => {
                await recompute();
                query.refetch();
              }}
            >
              재계산
            </Button>
          )}
        </div>
      </div>
      <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <div className="mb-1 flex items-center justify-between text-xs" style={{ color: "var(--ink-muted)" }}>
            <span>수요 기준값 (1회 제공당 평균 식수)</span>
            <span>
              {demandThreshold.toFixed(1)}명
              {demandThresholdOverride !== null && (
                <button className="ml-2 underline" onClick={() => setDemandThresholdOverride(null)}>
                  초기화
                </button>
              )}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={maxDemand}
            step={maxDemand > 20 ? 1 : 0.1}
            value={demandThreshold}
            onChange={(e) => setDemandThresholdOverride(Number(e.target.value))}
            className="w-full"
          />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-xs" style={{ color: "var(--ink-muted)" }}>
            <span>만족도 기준값 (5점 만점)</span>
            <span>
              {scoreThreshold.toFixed(2)}점
              {scoreThresholdOverride !== null && (
                <button className="ml-2 underline" onClick={() => setScoreThresholdOverride(null)}>
                  초기화
                </button>
              )}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={5}
            step={0.1}
            value={scoreThreshold}
            onChange={(e) => setScoreThresholdOverride(Number(e.target.value))}
            className="w-full"
          />
        </div>
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {rows.length === 0 && !query.isLoading && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          데이터가 없습니다. 먼저 "재계산" 버튼으로 menu_performance_stats를 생성하세요.
        </p>
      )}
      {rows.length > 0 && (
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            {visibleQuadrantLabels.map((label) => {
              const total = quadrantRows.get(label)?.length ?? 0;
              const shown = Math.min(total, quadrantLimitN);
              return (
                <span key={label} className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: resolveColor(quadrantColor(label)) }}
                  />
                  {label} {total}개 중 {shown}개 표시
                </span>
              );
            })}
          </div>
          {visibleQuadrantLabels.every((label) => (quadrantRows.get(label)?.length ?? 0) === 0) ? (
            <p className="py-6 text-center text-[13px]" style={{ color: "var(--ink-muted)" }}>
              해당 없음
            </p>
          ) : (
            <ReactECharts
              option={buildUnifiedQuadrantOption(
                quadrantRows,
                visibleQuadrantLabels,
                quadrantLimitN,
                demandThreshold,
                scoreThreshold,
                maxDemand,
                chartTheme,
              )}
              style={{ height: 560 }}
            />
          )}
        </div>
      )}
      {rows.length > 0 && (
        <div className="mt-4">
          <CornerCardGrid
            groups={cornerGroups}
            selected={expandedCorner}
            onSelect={(c) => setExpandedCorner((cur) => (cur === c ? null : c))}
          />
          {expandedCorner && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-[13px]" style={{ color: "var(--ink)" }}>
                <thead>
                  <tr>
                    <SortableHeader
                      label="메뉴"
                      active={sortKey === "menu"}
                      dir={sortDir}
                      onClick={() => toggleSort("menu")}
                    />
                    <SortableHeader
                      label="등장횟수"
                      active={sortKey === "appearance"}
                      dir={sortDir}
                      align="right"
                      onClick={() => toggleSort("appearance")}
                    />
                    <SortableHeader
                      label="평가건수"
                      active={sortKey === "count"}
                      dir={sortDir}
                      align="right"
                      onClick={() => toggleSort("count")}
                    />
                    <SortableHeader
                      label="만족도"
                      active={sortKey === "score"}
                      dir={sortDir}
                      align="right"
                      onClick={() => toggleSort("score")}
                    />
                    <th
                      className="border-b py-2 pr-4 font-medium"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                    >
                      4분면
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedExpandedRows.map((r) => (
                    <tr key={r.menu_name} className="border-b" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2 pr-4">{r.menu_name}</td>
                      <td className="py-2 pr-4 text-right">{r.appearance_count}</td>
                      <td className="py-2 pr-4 text-right">{r.evaluation_count}</td>
                      <td className="py-2 pr-4 text-right">{r.adjusted_score?.toFixed(2) ?? "-"}</td>
                      <td className="py-2 pr-4">
                        <QuadrantBadge label={r.effectiveQuadrant} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sortedExpandedRows.length === 0 && (
                <p className="py-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
                  선택한 분류에 해당하는 메뉴가 없습니다.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function MenuFoodVectorEditor({ row, onSaved }: { row: MenuFoodVectorRow; onSaved: () => void }) {
  const dims = row.dimensions;
  const [expanded, setExpanded] = useState(false);
  const [values, setValues] = useState<number[]>(row.food_vector ?? dims.map(() => 0.2));
  const save = useMutation({
    mutationFn: () => api.updateMenuFoodVector(row.menu_id, values),
    onSuccess: () => {
      onSaved();
      setExpanded(false);
    },
  });

  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[13px] font-medium">{row.menu_name}</span>
          <span className="ml-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            {row.source ?? "미태깅"}
          </span>
        </div>
        <Button variant="secondary" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "닫기" : "조정"}
        </Button>
      </div>
      {expanded && (
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {dims.map((dim, i) => (
              <label
                key={dim}
                className="flex flex-col gap-1 text-center text-xs"
                style={{ color: "var(--ink-muted)" }}
              >
                {dim}
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  className="rounded-md border px-2 py-1 text-center text-[13px]"
                  style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                  value={values[i]}
                  onChange={(e) =>
                    setValues((v) => v.map((x, j) => (j === i ? Number(e.target.value) : x)))
                  }
                />
              </label>
            ))}
          </div>
          {save.isError && <ErrorState error={save.error} />}
          <div className="mt-3 flex justify-end">
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              저장 (관리자수동으로 잠김)
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function MenuFoodVectorAdminSection() {
  const [untaggedOnly, setUntaggedOnly] = useState(false);
  const [expandedCorner, setExpandedCorner] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["menu-food-vectors", untaggedOnly],
    queryFn: () => api.menuFoodVectors({ untagged_only: untaggedOnly }),
  });
  const tagWithLlm = useMutation({
    mutationFn: () => api.tagMenusWithLlm(),
    onSuccess: () => query.refetch(),
  });
  const extractIngredients = useMutation({ mutationFn: () => api.extractIngredientsWithLlm() });

  const rows = query.data ?? [];
  const cornerGroups = groupByCorner(rows);

  return (
    <Card title="메뉴 음식벡터 관리 (개인 취향 벡터 계산의 기초 데이터)">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        신메뉴는 이름 키워드 규칙으로 1차 자동 태깅되고, 규칙이 못 잡은 메뉴는 아래 버튼으로 사내 LLM에 보강
        요청할 수 있습니다. 값을 직접 조정하면 "관리자수동"으로 표시되어 이후 자동 재태깅 대상에서 제외됩니다.
      </p>
      <div className="mb-3 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          <input
            type="checkbox"
            checked={untaggedOnly}
            onChange={(e) => setUntaggedOnly(e.target.checked)}
          />
          미태깅 메뉴만 보기
        </label>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => tagWithLlm.mutate()} disabled={tagWithLlm.isPending}>
            LLM으로 미태깅 메뉴 보강
          </Button>
          <Button
            variant="secondary"
            onClick={() => extractIngredients.mutate()}
            disabled={extractIngredients.isPending}
          >
            LLM으로 식재료 추출
          </Button>
        </div>
      </div>
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        식재료는 "한 끼 구성 중복 점검"이 쓰는 별도 값입니다(음식벡터와 다름). 새벽 배치가 매일 비어 있는
        메뉴만 채우므로 평소엔 누르지 않아도 되고, 식단표를 방금 올린 직후 바로 반영하고 싶을 때 씁니다.
      </p>
      {tagWithLlm.data && (
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          {tagWithLlm.data.tagged_menus}건 태깅됨
        </p>
      )}
      {extractIngredients.data && (
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          식재료 {extractIngredients.data.updated}건 추출됨
        </p>
      )}
      {tagWithLlm.isError && <ErrorState error={tagWithLlm.error} />}
      {extractIngredients.isError && <ErrorState error={extractIngredients.error} />}
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {rows.length === 0 && !query.isLoading && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          {untaggedOnly ? "미태깅 메뉴가 없습니다." : "메뉴 데이터가 없습니다."}
        </p>
      )}
      {rows.length > 0 && (
        <>
          <CornerCardGrid
            groups={cornerGroups}
            selected={expandedCorner}
            onSelect={(c) => setExpandedCorner((cur) => (cur === c ? null : c))}
          />
          {expandedCorner && (
            <div className="mt-4 space-y-2">
              {(cornerGroups.find(([c]) => c === expandedCorner)?.[1] ?? []).map((row) => (
                <MenuFoodVectorEditor key={row.menu_id} row={row} onSaved={() => query.refetch()} />
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/** 두 조합의 차이 — 어느 부찬이 빠지고 들어갔는지. 순수 함수라 테스트가 쉽다. */
function diffSides(best: (string | null)[], worst: (string | null)[]) {
  const b = new Set(best.filter(Boolean) as string[]);
  const w = new Set(worst.filter(Boolean) as string[]);
  return {
    onlyBest: [...b].filter((x) => !w.has(x)),
    onlyWorst: [...w].filter((x) => !b.has(x)),
    common: [...b].filter((x) => w.has(x)),
  };
}

/**
 * 조합을 칩으로 렌더링하되 **한쪽에만 있는 부찬을 음영으로 강조**한다
 * (2026-08 요청: "좋았던 조합과 나빴던 조합에서 변화된 부분을 눈에 띄게").
 * 텍스트만 나열하면 부찬이 3~4개일 때 뭐가 달라졌는지 눈으로 못 찾는다.
 */
function ComboChips({
  sides,
  highlight,
  tone,
}: {
  sides: (string | null)[];
  highlight: string[];
  tone: "good" | "critical";
}) {
  const names = sides.filter(Boolean) as string[];
  if (names.length === 0) {
    return (
      <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
        부찬 없음
      </span>
    );
  }
  const highlightSet = new Set(highlight);
  return (
    <span className="flex flex-wrap gap-1">
      {names.map((name) => {
        const isDiff = highlightSet.has(name);
        return (
          <span
            key={name}
            className="rounded px-1.5 py-0.5 text-xs"
            style={
              isDiff
                ? {
                    background: `color-mix(in srgb, var(--${tone}) 18%, transparent)`,
                    color: `var(--${tone})`,
                    fontWeight: 600,
                  }
                : { color: "var(--ink-muted)" }
            }
          >
            {name}
          </span>
        );
      })}
    </span>
  );
}

function MenuComboSection() {
  const [menuName, setMenuName] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  // 같은 메인이 여러 코너에서 다른 부찬과 나오면 조합이 섞여 비교가 흐려진다
  // → 코너로 좁혀 볼 수 있게 한다(2026-08 요청).
  const [comboCornerId, setComboCornerId] = useState<number | null>(null);
  const cornersQuery = useQuery({ queryKey: ["corner-list"], queryFn: () => api.cornerList() });
  // 검색해야만 보이면 "뭘 검색할지"부터 막힌다는 피드백(2026-08) → 조합에 따라
  // 만족도 편차가 큰 메인메뉴를 먼저 띄운다. 편차가 크다 = 부찬을 바꾸면
  // 만족도가 실제로 움직인다 = 손볼 가치가 있다.
  const rankingQuery = useQuery({
    queryKey: ["menu-combination-spread-ranking", comboCornerId],
    queryFn: () =>
      api.menuCombinationSpreadRanking({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        ...(comboCornerId != null ? { corner_id: comboCornerId } : {}),
      }),
  });
  const query = useQuery({
    queryKey: ["menu-combinations", searched, comboCornerId],
    queryFn: () =>
      api.menuSideCombinations(searched as string, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        ...(comboCornerId != null ? { corner_id: comboCornerId } : {}),
      }),
    enabled: !!searched,
    retry: false,
  });

  return (
    <Card title="부찬 조합별 만족도 비교 — 메인메뉴 기준">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        메인 메뉴명을 검색하면, 그동안 짝지어 나온 부찬 조합별로 그 날짜의 평균 만족도를 비교합니다.
        영양 프로필은 실제 칼로리·영양성분이 아니라 메뉴 특성(매운맛/단백질/채소 비중 등) 기반
        추정치입니다.
      </p>
      <div className="mb-3 flex gap-2">
        <input
          className="w-48 rounded-md border px-3 py-2 text-[13px]"
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          placeholder="메뉴명 (예: 제육볶음)"
          value={menuName}
          onChange={(e) => setMenuName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setSearched(menuName)}
        />
        <Button onClick={() => setSearched(menuName)}>조회</Button>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          코너
        </span>
        <SegmentedControl
          value={comboCornerId != null ? String(comboCornerId) : ""}
          options={[
            { label: "전체", value: "" },
            ...(cornersQuery.data ?? []).map((c) => ({
              label: c.corner_name,
              value: String(c.corner_id),
            })),
          ]}
          onChange={(v) => setComboCornerId(v === "" ? null : Number(v))}
        />
      </div>
      <div className="mb-4 border-t pt-3" style={{ borderColor: "var(--border)" }}>
        <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
          <strong>부찬을 바꿀 때 효과가 큰 메인메뉴</strong> — 조합에 따라 만족도가 크게 갈리는 순서입니다.
          편차가 작은 메뉴는 뭘 붙여도 결과가 같으니 손볼 필요가 없습니다. <strong>한쪽에만 있는
          부찬은 음영으로 표시</strong>했습니다 — 그게 실제로 달라진 부분입니다. 행을 클릭하면 아래에
          상세가 열립니다.
        </p>
        {rankingQuery.isLoading && <LoadingState />}
        {rankingQuery.isError && <ErrorState error={rankingQuery.error} />}
        {rankingQuery.data && rankingQuery.data.items.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            비교 가능한 조합(평가가 있는 조합 2개 이상)을 가진 메인메뉴가 아직 없습니다.
          </p>
        )}
        {rankingQuery.data && rankingQuery.data.items.length > 0 && (
          <Table
            columns={[
              { key: "menu", label: "메인메뉴" },
              { key: "spread", label: "만족도 편차", align: "right" },
              { key: "best", label: "가장 좋았던 조합" },
              { key: "worst", label: "가장 나빴던 조합" },
            ]}
            rows={rankingQuery.data.items.map((r) => ({
              menuId: r.menu_id,
              menuName: r.menu_name ?? "",
              menu: (
                <button
                  className="underline"
                  style={{ color: "var(--accent)" }}
                  onClick={() => {
                    setMenuName(r.menu_name ?? "");
                    setSearched(r.menu_name ?? "");
                  }}
                >
                  {r.menu_name}
                </button>
              ),
              spread: r.spread.toFixed(2),
              best: (
                <span className="flex items-center gap-1.5">
                  <ComboChips
                    sides={r.best.sides}
                    highlight={diffSides(r.best.sides, r.worst.sides).onlyBest}
                    tone="good"
                  />
                  <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    ({r.best.avg_satisfaction?.toFixed(2) ?? "-"})
                  </span>
                </span>
              ),
              worst: (
                <span className="flex items-center gap-1.5">
                  <ComboChips
                    sides={r.worst.sides}
                    highlight={diffSides(r.best.sides, r.worst.sides).onlyWorst}
                    tone="critical"
                  />
                  <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    ({r.worst.avg_satisfaction?.toFixed(2) ?? "-"})
                  </span>
                </span>
              ),
            }))}
            rowKey={(r) => String(r.menuId)}
          />
        )}
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && query.data.combos.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 메뉴가 메인으로 나온 부찬 조합 기록이 없습니다.
        </p>
      )}
      {query.data && query.data.combos.length > 0 && (
        <div className="space-y-2">
          {query.data.combos.map((c, i) => (
            <div key={i} className="rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-medium">
                  {c.sides.filter(Boolean).join(" + ") || "부찬 없음"}
                </span>
                <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  {c.day_count}일 등장
                </span>
              </div>
              <div className="mt-1 text-[13px]">
                만족도: {c.avg_satisfaction != null ? c.avg_satisfaction.toFixed(2) : "평가 없음"} · 평균 식수:{" "}
                {c.avg_headcount.toFixed(1)}명
              </div>
              {Object.keys(c.nutrition_profile).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  {Object.entries(c.nutrition_profile).map(([label, value]) => (
                    <span key={label}>
                      {label} {value.toFixed(2)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function weeklyMondayOf(date: Date): string {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // 월=0 ... 일=6
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

function weeklyAddDays(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function daysUntil(iso: string): number {
  const target = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

const WEEKLY_WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"];

// 일반인도 바로 이해할 수 있는 설명 — "혼잡 예상" 배지가 정확히 뭘 뜻하는지
// (요약 카드 캡션 + 배지 title 툴팁에서 공유).
const CONGESTION_EXPLANATION =
  "혼잡 예상 배지는 피크타임(11:40~12:20)에 처리 가능한 인원보다 예상 식수가 많을 때, " +
  "그 초과 인원을 처리하는 데 걸리는 예상 추가 시간입니다.";

function weekdayLabel(dateIso: string): string {
  return `${dateIso.slice(5)}(${WEEKLY_WEEKDAY_KO[new Date(dateIso).getDay()]})`;
}

function WeeklyMenuRoleRow({
  item,
  label,
  onChangeRole,
}: {
  item: WeeklyMenuPlanItem;
  label: "메인" | "부찬";
  onChangeRole: (role: "메인" | "부찬") => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-[13px]">
      <span>
        {item.menu_name}
        {item.role_source !== "관리자수동" && (
          <span className="ml-1.5 text-xs" style={{ color: "var(--ink-muted)" }}>
            (자동분류·{item.role_source})
          </span>
        )}
      </span>
      <select
        value={label}
        onChange={(e) => onChangeRole(e.target.value as "메인" | "부찬")}
        className="rounded border px-1.5 py-0.5 text-xs"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <option value="메인">메인</option>
        <option value="부찬">부찬</option>
      </select>
    </div>
  );
}

function PredictedImpactPanel({ planId }: { planId: number }) {
  const query = useQuery({
    queryKey: ["weekly-menu-predicted-impact", planId],
    queryFn: () => api.weeklyMenuPredictedImpact(planId),
  });

  return (
    <div
      className="mt-2 rounded-xl border p-3 text-[13px]"
      style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
    >
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && (
        <div className="space-y-1.5">
          <div>
            기존 만족도:{" "}
            {query.data.main_menu.adjusted_score != null ? query.data.main_menu.adjusted_score.toFixed(2) : "이력 없음"}
            {" · "}
            기존 식수: {query.data.main_menu.total_headcount ?? "이력 없음"}
          </div>
          <div>
            이 부찬 조합 이력:{" "}
            {query.data.combo_history
              ? `${query.data.combo_history.day_count}일 등장, 만족도 ${
                  query.data.combo_history.avg_satisfaction != null
                    ? query.data.combo_history.avg_satisfaction.toFixed(2)
                    : "평가 없음"
                }, 평균 식수 ${query.data.combo_history.avg_headcount.toFixed(1)}명`
              : "이 정확한 조합의 과거 이력 없음"}
          </div>
          <div>
            예상 식수: {query.data.prediction.predicted_headcount.toFixed(1)}명 · 예상 점유율:{" "}
            {(query.data.prediction.predicted_share * 100).toFixed(1)}%
            {query.data.prediction.expected_wait_minutes != null && query.data.prediction.expected_wait_minutes > 0 && (
              <> · 예상 대기시간: 약 {query.data.prediction.expected_wait_minutes}분</>
            )}
          </div>
          <div className="rounded p-2" style={{ background: "var(--surface)", color: "var(--ink-secondary)" }}>
            {query.data.summary_comment}
          </div>
        </div>
      )}
    </div>
  );
}

function WeeklyMenuReviewTab() {
  const chartTheme = useChartTheme();
  const [selectedMonday, setSelectedMonday] = useState(weeklyMondayOf(new Date()));
  const sunday = weeklyAddDays(selectedMonday, 6);
  const weekdayDates = Array.from({ length: 6 }, (_, i) => weeklyAddDays(selectedMonday, i)); // 월~토(일요일 미운영)

  const [selectedSlotKey, setSelectedSlotKey] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [showPrediction, setShowPrediction] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [predictedByPlanId, setPredictedByPlanId] = useState<Record<number, PredictedNumbersRow>>({});
  const [donutDay, setDonutDay] = useState(weekdayDates[0]);

  const selectSlot = (key: string) => {
    setSelectedSlotKey((cur) => (cur === key ? null : key));
    setIsEditing(false);
    setShowPrediction(false);
  };

  const slotsQuery = useQuery({
    queryKey: ["weekly-menu", selectedMonday],
    queryFn: () => api.weeklyMenu({ period_start: selectedMonday, period_end: sunday }),
  });
  const feedbackQuery = useQuery({
    queryKey: ["weekly-menu-feedback", selectedMonday],
    queryFn: () => api.weeklyMenuFeedback({ period_start: selectedMonday, period_end: sunday }),
  });
  const updateRole = useMutation({
    mutationFn: (params: { planId: number; menuRole: "메인" | "부찬" }) =>
      api.updateWeeklyMenuRole(params.planId, params.menuRole),
    onSuccess: () => slotsQuery.refetch(),
  });
  const reclassifyWithLlm = useMutation({
    mutationFn: () => api.reclassifyWeeklyMenuRolesWithLlm({ period_start: selectedMonday, period_end: sunday }),
    onSuccess: () => slotsQuery.refetch(),
  });
  const submitFeedback = useMutation({
    mutationFn: (params: { plan_date: string; corner_id: number; comment: string }) =>
      api.createWeeklyMenuFeedback(params),
    onSuccess: () => feedbackQuery.refetch(),
  });
  // 건강가든은 식단표 엑셀에 없어 담당자가 슬롯별로 직접 입력한다(2026-08).
  // 슬롯 단위 전체 교체라 PUT이고, 빈 문자열을 보내면 그 슬롯을 비운다.
  const [gardenDrafts, setGardenDrafts] = useState<Record<string, string>>({});
  const saveHealthGarden = useMutation({
    mutationFn: (params: { plan_date: string; corner_id: number; meal_type: MealType; menu_names_raw: string }) =>
      api.updateHealthGarden(params),
    onSuccess: () => slotsQuery.refetch(),
  });
  const compareAll = useMutation({
    mutationFn: () => api.weeklyMenuPredictedImpactSummary({ period_start: selectedMonday, period_end: sunday }),
    onSuccess: (rows) => {
      const map: Record<number, PredictedNumbersRow> = {};
      for (const r of rows) map[r.plan_id] = r;
      setPredictedByPlanId(map);
    },
  });

  const slots = slotsQuery.data ?? [];
  const cornerRows = groupByCorner(slots)
    .map(([cornerName, items]) => [cornerName, items as WeeklyMenuSlot[]] as const)
    .slice()
    .sort((a, b) => a[0].localeCompare(b[0]));
  const selectedSlot = slots.find((s) => `${s.plan_date}_${s.corner_id}` === selectedSlotKey) ?? null;
  const effectiveDonutDay = weekdayDates.includes(donutDay) ? donutDay : weekdayDates[0];

  // dataviz 스킬: "색은 순위가 아니라 개체를 따라간다" — corner_id 고정 순서로
  // 배정(CornerAnalysisTab의 cornerColor와 동일 컨벤션), 도넛/추이 차트가 공유.
  const cornerList = cornerRows
    .map(([cornerName, items]) => ({ corner_id: items[0].corner_id, corner_name: cornerName }))
    .sort((a, b) => a.corner_id - b.corner_id);
  const cornerColor = new Map(cornerList.map((c, i) => [c.corner_id, `var(--series-${(i % 8) + 1})`]));

  const predictedRows = Object.values(predictedByPlanId);
  const maxShare = predictedRows.reduce((m, r) => Math.max(m, r.prediction.predicted_share), 0);
  const waitValues = predictedRows
    .map((r) => r.prediction.expected_wait_minutes)
    .filter((w): w is number => w != null && w > 0);
  const medianWait = median(waitValues);
  const topPredicted =
    predictedRows.length > 0
      ? predictedRows.reduce((a, b) => (b.prediction.predicted_share > a.prediction.predicted_share ? b : a))
      : null;
  const shareByCornerDate = new Map(predictedRows.map((r) => [`${r.corner_id}_${r.plan_date}`, r.prediction.predicted_share]));

  const donutRows = predictedRows.filter((r) => r.plan_date === effectiveDonutDay);
  const donutOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    tooltip: { trigger: "item" as const, formatter: "{b}: {d}%" },
    series: [
      {
        type: "pie" as const,
        radius: ["45%", "70%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
        label: { color: chartTheme.text, formatter: "{b}\n{d}%" },
        labelLine: { lineStyle: { color: chartTheme.axis } },
        data: donutRows.map((r) => ({
          name: r.corner_name ?? "-",
          value: r.prediction.predicted_share,
          itemStyle: { color: resolveColor(cornerColor.get(r.corner_id) ?? "var(--series-1)") },
        })),
      },
    ],
  };

  const trendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 40 },
    legend: { top: 0, textStyle: { color: chartTheme.text } },
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { axisValueLabel?: string; marker: string; seriesName: string; value: number | null }[]) => {
        const header = params[0]?.axisValueLabel ?? "";
        const lines = params
          .filter((p) => p.value != null)
          .map((p) => `${p.marker}${p.seriesName}: ${((p.value as number) * 100).toFixed(1)}%`);
        return [header, ...lines].join("<br/>");
      },
    },
    xAxis: {
      type: "category" as const,
      data: weekdayDates.map(weekdayLabel),
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: { color: chartTheme.text },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value" as const,
      name: "점유율",
      axisLabel: { color: chartTheme.text, formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: cornerList.map((c) => ({
      name: c.corner_name,
      type: "line" as const,
      symbol: "circle",
      symbolSize: 8,
      connectNulls: false,
      lineStyle: { width: 2, color: resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)") },
      itemStyle: {
        color: resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)"),
        borderColor: resolveColor("var(--surface)"),
        borderWidth: 2,
      },
      data: weekdayDates.map((d) => shareByCornerDate.get(`${c.corner_id}_${d}`) ?? null),
    })),
  };

  return (
    <div className="space-y-6">
      <Card title="주간 식단표 관리">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          식당에서 2주 전에 전달한 식단표를 확인하고, 셀 병합 등으로 메인/부찬이 잘못 나뉘었으면
          셀을 클릭해 직접 고치세요. 각 날짜의 개선의견은 그 날짜의 7일 전(마감)까지 제출할 수 있습니다.
        </p>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => setSelectedMonday((d) => weeklyAddDays(d, -7))}>
            ◀ 이전 주
          </Button>
          <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            {selectedMonday} ~ {sunday}
          </span>
          <Button variant="secondary" onClick={() => setSelectedMonday((d) => weeklyAddDays(d, 7))}>
            다음 주 ▶
          </Button>
          <Button
            variant="secondary"
            onClick={() => reclassifyWithLlm.mutate()}
            disabled={reclassifyWithLlm.isPending}
          >
            {reclassifyWithLlm.isPending ? "재분류 중..." : "일괄 자동 분류(LLM)"}
          </Button>
          <Button variant="secondary" onClick={() => compareAll.mutate()} disabled={compareAll.isPending}>
            {compareAll.isPending ? "예측 계산 중..." : "전체 예측 비교"}
          </Button>
        </div>
        {slotsQuery.isLoading && <LoadingState />}
        {slotsQuery.isError && <ErrorState error={slotsQuery.error} />}
        {compareAll.isError && <ErrorState error={compareAll.error} />}
        {!slotsQuery.isLoading && slots.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 기간에 등록된 주간 식단표가 없습니다.
          </p>
        )}
        {cornerRows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr>
                  <th
                    className="border-b py-2 pr-4 text-left font-medium"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                  >
                    코너
                  </th>
                  {weekdayDates.map((d) => (
                    <th
                      key={d}
                      className="border-b py-2 px-3 text-left font-medium"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                    >
                      {weekdayLabel(d)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cornerRows.map(([cornerName, items]) => {
                  const byDate = new Map(items.map((s) => [s.plan_date, s]));
                  return (
                    <tr key={cornerName} className="border-b" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2 pr-4 align-top font-medium">{cornerName}</td>
                      {weekdayDates.map((d) => {
                        const slot = byDate.get(d);
                        if (!slot) {
                          return (
                            <td key={d} className="py-2 px-3 align-top" style={{ color: "var(--ink-muted)" }}>
                              -
                            </td>
                          );
                        }
                        const key = `${slot.plan_date}_${slot.corner_id}`;
                        const isSelected = key === selectedSlotKey;
                        const predicted = slot.main ? predictedByPlanId[slot.main.plan_id] : undefined;
                        const share = predicted?.prediction.predicted_share;
                        const heatBgRgb = share != null ? shareToBackgroundRgb(share, maxShare) : undefined;
                        const heatBg = heatBgRgb ? `rgb(${heatBgRgb[0]}, ${heatBgRgb[1]}, ${heatBgRgb[2]})` : undefined;
                        const useLightText = useLightTextOn(heatBgRgb);
                        const waitMinutes = predicted?.prediction.expected_wait_minutes;
                        const isCongested = waitValues.length > 1 && waitMinutes != null && waitMinutes > medianWait;
                        return (
                          <td
                            key={d}
                            role="button"
                            tabIndex={0}
                            onClick={() => selectSlot(key)}
                            onKeyDown={(e) => e.key === "Enter" && selectSlot(key)}
                            className="cursor-pointer py-2 px-3 align-top"
                            style={{
                              background: isSelected ? "var(--surface-2)" : heatBg,
                              boxShadow: isSelected ? "inset 2px 0 0 var(--accent)" : undefined,
                            }}
                          >
                            <div className="font-medium" style={{ color: useLightText ? "#fff" : "var(--ink)" }}>
                              {slot.main ? slot.main.menu_name : "미배정"}
                            </div>
                            {slot.sides.length > 0 && (
                              <div
                                className="mt-0.5 text-xs"
                                style={{ color: useLightText ? "rgba(255,255,255,0.85)" : "rgba(11,11,11,0.72)" }}
                              >
                                {slot.sides.map((s) => s.menu_name).join(", ")}
                              </div>
                            )}
                            {predicted && share != null && (
                              <div
                                className="mt-0.5 text-xs"
                                style={{ color: useLightText ? "rgba(255,255,255,0.9)" : "rgba(11,11,11,0.72)" }}
                              >
                                점유율 {(share * 100).toFixed(1)}%
                              </div>
                            )}
                            {isCongested && (
                              // 혼잡 경고는 색(--warning)만으로 신호하지 않는다 — 밝은
                              // 배경에서 대비가 낮기도 하고(1.79:1), dataviz 스킬 원칙상
                              // 상태색은 항상 아이콘+라벨과 함께여야 한다. ⚠ 이모지가
                              // 아이콘 역할을 하므로 글자색은 본문과 같은 대비색을 쓴다.
                              <div
                                className="mt-0.5 text-xs font-medium"
                                style={{ color: useLightText ? "#fff" : "var(--ink)" }}
                                title={CONGESTION_EXPLANATION}
                              >
                                ⚠ 혼잡 예상 · 대기 ~{waitMinutes}분
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {selectedSlot &&
          (() => {
            const key = selectedSlotKey as string;
            const dday = daysUntil(selectedSlot.feedback_deadline);
            return (
              <div className="mt-4 rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium">
                    {weekdayLabel(selectedSlot.plan_date)} · {selectedSlot.corner_name} ({selectedSlot.meal_type})
                  </span>
                  <span
                    className="text-xs"
                    style={{ color: selectedSlot.is_past_deadline ? "var(--ink-muted)" : "var(--warning)" }}
                  >
                    {selectedSlot.is_past_deadline ? "마감" : `의견 제출 D-${dday}`}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-semibold">
                    {selectedSlot.main ? selectedSlot.main.menu_name : "메인메뉴 미배정"}
                  </span>
                  {selectedSlot.sides.length > 0 && (
                    <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                      부찬: {selectedSlot.sides.map((s) => s.menu_name).join(", ")}
                    </span>
                  )}
                  {selectedSlot.health_garden.length > 0 && (
                    <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                      건강가든: {selectedSlot.health_garden.map((s) => s.menu_name).join(", ")}
                    </span>
                  )}
                  {selectedSlot.main && (
                    <button
                      className="text-xs underline"
                      style={{ color: "var(--accent)" }}
                      onClick={() => setShowPrediction((v) => !v)}
                    >
                      {showPrediction ? "예측 닫기" : "예측 보기"}
                    </button>
                  )}
                  <button
                    className="ml-auto text-xs underline"
                    style={{ color: "var(--ink-muted)" }}
                    onClick={() => setIsEditing((v) => !v)}
                  >
                    {isEditing ? "수정 닫기" : "수정"}
                  </button>
                </div>

                {selectedSlot.main && showPrediction && <PredictedImpactPanel planId={selectedSlot.main.plan_id} />}

                <div className="mt-2 border-t pt-2" style={{ borderColor: "var(--border)" }}>
                  <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                    건강가든 — 식단표 엑셀에 아직 안 들어와 직접 입력합니다. 쉼표나 줄바꿈으로 구분하세요.
                    저장하면 이 슬롯의 건강가든이 통째로 바뀝니다(비우려면 빈칸으로 저장).
                  </p>
                  <div className="flex gap-2">
                    <input
                      value={
                        gardenDrafts[key] ??
                        selectedSlot.health_garden.map((h) => h.menu_name).join(", ")
                      }
                      onChange={(e) => setGardenDrafts((g) => ({ ...g, [key]: e.target.value }))}
                      placeholder="예: 구운채소, 두부샐러드, 닭가슴살"
                      className="flex-1 rounded-md border px-2 py-1 text-[13px]"
                      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                    />
                    <Button
                      variant="secondary"
                      disabled={saveHealthGarden.isPending}
                      onClick={() =>
                        saveHealthGarden.mutate({
                          plan_date: selectedSlot.plan_date,
                          corner_id: selectedSlot.corner_id,
                          meal_type: selectedSlot.meal_type,
                          menu_names_raw:
                            gardenDrafts[key] ??
                            selectedSlot.health_garden.map((h) => h.menu_name).join(", "),
                        })
                      }
                    >
                      {saveHealthGarden.isPending ? "저장 중..." : "저장"}
                    </Button>
                  </div>
                  {saveHealthGarden.isError && <ErrorState error={saveHealthGarden.error} />}
                </div>

                {isEditing && (
                  <div className="mt-2 space-y-1 border-t pt-2" style={{ borderColor: "var(--border)" }}>
                    {selectedSlot.main && (
                      <WeeklyMenuRoleRow
                        item={selectedSlot.main}
                        label="메인"
                        onChangeRole={(role) =>
                          updateRole.mutate({ planId: selectedSlot.main!.plan_id, menuRole: role })
                        }
                      />
                    )}
                    {selectedSlot.sides.map((item) => (
                      <WeeklyMenuRoleRow
                        key={item.plan_id}
                        item={item}
                        label="부찬"
                        onChangeRole={(role) => updateRole.mutate({ planId: item.plan_id, menuRole: role })}
                      />
                    ))}
                  </div>
                )}

                <div className="mt-2 flex gap-2">
                  <input
                    value={commentDrafts[key] ?? ""}
                    onChange={(e) => setCommentDrafts((c) => ({ ...c, [key]: e.target.value }))}
                    placeholder="개선의견 (예: 이 부찬 조합 별로예요)"
                    className="flex-1 rounded-md border px-2 py-1 text-[13px]"
                    style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                  />
                  <Button
                    variant="secondary"
                    disabled={!commentDrafts[key]}
                    onClick={() => {
                      submitFeedback.mutate({
                        plan_date: selectedSlot.plan_date,
                        corner_id: selectedSlot.corner_id,
                        comment: commentDrafts[key],
                      });
                      setCommentDrafts((c) => ({ ...c, [key]: "" }));
                    }}
                  >
                    등록
                  </Button>
                </div>
              </div>
            );
          })()}
      </Card>

      {predictedRows.length > 0 && topPredicted && (
        <Card title="이번 주 예측 요약">
          <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {CONGESTION_EXPLANATION}
          </p>
          <div className="mb-4">
            <StatTile
              label="이번 주 예상 최고 점유율"
              value={`${topPredicted.corner_name ?? "-"} · ${topPredicted.menu_name ?? "-"}`}
              sub={`${weekdayLabel(topPredicted.plan_date)} · 점유율 ${(topPredicted.prediction.predicted_share * 100).toFixed(1)}%`}
            />
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                  요일별 코너 점유율 구성
                </p>
                <SegmentedControl
                  value={effectiveDonutDay}
                  options={weekdayDates.map((d) => ({ label: weekdayLabel(d), value: d }))}
                  onChange={setDonutDay}
                />
              </div>
              {donutRows.length > 0 ? (
                <ReactECharts option={donutOption} style={{ height: 280 }} />
              ) : (
                <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                  이 날짜엔 예측 데이터가 없습니다.
                </p>
              )}
            </div>
            <div>
              <p className="mb-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                요일별 점유율 추이
              </p>
              <ReactECharts option={trendOption} style={{ height: 280 }} />
            </div>
          </div>
        </Card>
      )}

      <Card title="등록된 개선의견">
        {feedbackQuery.isLoading && <LoadingState />}
        {feedbackQuery.isError && <ErrorState error={feedbackQuery.error} />}
        {feedbackQuery.data && feedbackQuery.data.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 기간에 등록된 개선의견이 없습니다.
          </p>
        )}
        {feedbackQuery.data && feedbackQuery.data.length > 0 && (
          <Table
            columns={[
              { key: "plan_date", label: "날짜" },
              { key: "corner", label: "코너" },
              { key: "comment", label: "의견" },
            ]}
            rows={feedbackQuery.data.map((f) => ({
              plan_date: f.plan_date,
              corner: f.corner_name ?? "-",
              comment: f.comment,
            }))}
            rowKey={(r, i) => `${r.plan_date as string}-${i}`}
          />
        )}
      </Card>
    </div>
  );
}

const VOE_TREND_MONTHS = 6;

function monthsBefore(period: string, n: number): string {
  const [y, m] = period.split("-").map(Number);
  const d = new Date(y, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// PRD 5-2: "주관식 VOE" 서브탭 — 홈 화면에 있던 "월간 VOE 분류"(고정 카테고리)를
// 여기로 옮기고, 백엔드엔 이미 있었지만 어느 화면에도 안 붙어있던 voe-clusters
// (자유 주제 클러스터링)를 추가로 붙인다.
function VoeAnalysisTab() {
  const chartTheme = useChartTheme();
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const [selectedVoeCategory, setSelectedVoeCategory] = useState<string | null>(null);

  const voeCategory = useQuery({
    queryKey: ["voe-by-category-tab", period],
    queryFn: () => api.voeByCategory(`${period}-01`),
  });
  const recomputeVoeCategory = useMutation({
    mutationFn: () => api.recomputeVoeByCategory(`${period}-01`),
    onSuccess: () => voeCategory.refetch(),
  });

  const voeClusters = useQuery({
    queryKey: ["voe-clusters-tab", period],
    queryFn: () => api.voeClusters(`${period}-01`),
  });
  const recomputeVoeClusters = useMutation({
    mutationFn: () => api.recomputeVoeClusters(`${period}-01`),
    onSuccess: () => voeClusters.refetch(),
  });

  const trendMonths = Array.from({ length: VOE_TREND_MONTHS }, (_, i) => monthsBefore(period, VOE_TREND_MONTHS - 1 - i));
  const monthlyVolumeQuery = useQuery({
    queryKey: ["voe-monthly-volume", period],
    queryFn: async () => {
      const results = await Promise.all(trendMonths.map((m) => api.voeByCategory(`${m}-01`)));
      return trendMonths.map((m, i) => ({ month: m, total: results[i].total_comments }));
    },
  });
  const volumeTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" as const, formatter: axisTooltipFormatter },
    xAxis: {
      type: "category" as const,
      data: trendMonths,
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: { color: chartTheme.text },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value" as const,
      name: "코멘트 수",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      {
        name: "VOE 코멘트 수",
        type: "line" as const,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { width: 2, color: resolveColor("var(--series-1)") },
        itemStyle: { color: resolveColor("var(--series-1)") },
        data: (monthlyVolumeQuery.data ?? []).map((d) => d.total),
      },
    ],
  };

  // "이달의 VOE 최다 코너/메뉴" — 새 백엔드 집계 없이 이미 받아온 카테고리별
  // 코멘트를 프론트에서 tally한다. 한 코멘트가 여러 카테고리에 동시에 걸릴 수
  // 있어(다중 라벨) 그대로 합치면 중복 카운트되므로 먼저 dedupe한다.
  const seenVoeKeys = new Set<string>();
  const uniqueVoeComments = (voeCategory.data?.categories ?? []).flatMap((c) => c.comments).filter((c) => {
    const key = `${c.eaten_at}|${c.corner_name}|${c.menu_name}|${c.comment}`;
    if (seenVoeKeys.has(key)) return false;
    seenVoeKeys.add(key);
    return true;
  });
  function topVoeEntry(getKey: (c: (typeof uniqueVoeComments)[number]) => string | null): { name: string; count: number } | null {
    const counts = new Map<string, number>();
    for (const c of uniqueVoeComments) {
      const key = getKey(c);
      if (!key) continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    let best: { name: string; count: number } | null = null;
    for (const [name, count] of counts) {
      if (!best || count > best.count) best = { name, count };
    }
    return best;
  }
  const topVoeCorner = topVoeEntry((c) => c.corner_name);
  const topVoeMenu = topVoeEntry((c) => c.menu_name);

  return (
    <div className="space-y-6">
      <Card title="주관식 VOE">
        <label className="flex items-center gap-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          조회 월
          <input
            type="month"
            value={period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)}
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          />
        </label>
      </Card>

      <Card title="월간 VOE 분류 (맛·간·위생·서비스)">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            카테고리를 클릭하면 해당 분류의 코멘트를 볼 수 있습니다. 한 코멘트가 여러 분류에 동시에 잡힐 수
            있습니다. 매달 새벽에 사내 LLM이 자동으로 분류하며, 이번 달을 바로 반영하려면 재계산하세요.
          </p>
          <Button
            variant="secondary"
            onClick={() => recomputeVoeCategory.mutate()}
            disabled={recomputeVoeCategory.isPending}
          >
            {recomputeVoeCategory.isPending ? "분류 중..." : "이번 달 재계산"}
          </Button>
        </div>
        {recomputeVoeCategory.isError && <ErrorState error={recomputeVoeCategory.error} />}
        {voeCategory.isLoading && <LoadingState />}
        {voeCategory.isError && <ErrorState error={voeCategory.error} />}
        {voeCategory.data && voeCategory.data.total_comments === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이번 달 코멘트가 없습니다.
          </p>
        )}
        {voeCategory.data && voeCategory.data.total_comments > 0 && (
          <>
            <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <StatTile
                label="이달의 VOE 최다 코너"
                value={topVoeCorner ? topVoeCorner.name : "-"}
                sub={topVoeCorner ? `${topVoeCorner.count}건` : undefined}
              />
              <StatTile
                label="이달의 VOE 최다 메뉴"
                value={topVoeMenu ? topVoeMenu.name : "-"}
                sub={topVoeMenu ? `${topVoeMenu.count}건` : undefined}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {voeCategory.data.categories.map((c) => (
                <button
                  key={c.category}
                  onClick={() => setSelectedVoeCategory((cur) => (cur === c.category ? null : c.category))}
                  className="rounded-xl border p-3 text-left transition-colors"
                  style={{
                    borderColor: selectedVoeCategory === c.category ? "var(--accent)" : "var(--border)",
                    background: selectedVoeCategory === c.category ? "var(--surface-2)" : "var(--surface)",
                  }}
                >
                  <div className="text-[13px] font-medium">{c.category}</div>
                  <div className="mt-1 text-lg font-semibold">{c.count}</div>
                </button>
              ))}
            </div>
            {selectedVoeCategory && (
              <div className="mt-4">
                {(() => {
                  const selected = voeCategory.data.categories.find((c) => c.category === selectedVoeCategory);
                  if (!selected || selected.comments.length === 0) {
                    return (
                      <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                        해당 분류의 코멘트가 없습니다.
                      </p>
                    );
                  }
                  return (
                    <Table
                      columns={[
                        { key: "eaten_at", label: "취식일시" },
                        { key: "corner_menu", label: "코너·메뉴" },
                        { key: "comment", label: "코멘트" },
                      ]}
                      rows={selected.comments.map((c) => ({
                        eaten_at: c.eaten_at.replace("T", " "),
                        // 어떤 메뉴에 대한 의견인지 바로 알 수 있게 코너+메뉴를 함께 표기(2026-08).
                        corner_menu: c.corner_name
                          ? `${c.corner_name}${c.menu_name ? ` · ${c.menu_name}` : ""}`
                          : "-",
                        comment: c.comment,
                      }))}
                      rowKey={(r, i) => `${r.eaten_at as string}-${i}`}
                    />
                  );
                })()}
              </div>
            )}
          </>
        )}
      </Card>

      <Card title="월간 VOE 클러스터링 (주제·키워드 기반)">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            고정 카테고리가 아니라 그 달 코멘트 내용 자체를 사내 LLM 임베딩으로 묶은 자유 주제 군집입니다.
            매달 새벽 자동으로 계산되며, 이번 달을 바로 반영하려면 재계산하세요.
          </p>
          <Button
            variant="secondary"
            onClick={() => recomputeVoeClusters.mutate()}
            disabled={recomputeVoeClusters.isPending}
          >
            {recomputeVoeClusters.isPending ? "계산 중..." : "이번 달 재계산"}
          </Button>
        </div>
        {recomputeVoeClusters.isError && <ErrorState error={recomputeVoeClusters.error} />}
        {voeClusters.isLoading && <LoadingState />}
        {voeClusters.isError && <ErrorState error={voeClusters.error} />}
        {voeClusters.data && voeClusters.data.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이번 달 클러스터 결과가 없습니다. "이번 달 재계산"을 눌러보세요.
          </p>
        )}
        {voeClusters.data && voeClusters.data.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {voeClusters.data.map((c, i) => (
              <div
                key={i}
                className="rounded-xl border p-3"
                style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[13px] font-medium">{c.cluster_label}</div>
                  <div className="shrink-0 text-xs" style={{ color: "var(--ink-muted)" }}>
                    {c.comment_count}건
                  </div>
                </div>
                {c.keywords.length > 0 && (
                  <div className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                    {c.keywords.join(", ")}
                  </div>
                )}
                {c.representative_comment && (
                  <div className="mt-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                    "{c.representative_comment}"
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
          <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
            월별 VOE 코멘트 수 추이(최근 {VOE_TREND_MONTHS}개월) — 군집 라벨은 매달 새로 계산돼 주제 이름이
            달마다 바뀔 수 있어, 여기서는 코멘트 총량 추이만 비교합니다.
          </p>
          {monthlyVolumeQuery.isLoading && <LoadingState />}
          {monthlyVolumeQuery.isError && <ErrorState error={monthlyVolumeQuery.error} />}
          {monthlyVolumeQuery.data && <ReactECharts option={volumeTrendOption} style={{ height: 220 }} />}
        </div>
      </Card>
    </div>
  );
}

// ---- 2026-08 화면 재편으로 생긴 최상위 화면 3개 ----
// 기존 "분석" 탭(서브탭 5개)을 해체하고, 담당자 협의에서 정한 5개 축
// (현황 / 메뉴 편성·운영 / 만족도·VoE / Agent 채팅 / 관리)에 맞춰 재배치했다.
// 컴포넌트 본문은 그대로 두고 조합만 바꾼다.

/** 메뉴 편성·운영 — "다음 주 식단을 어떻게 짤까"에 답하는 화면. */
// 메뉴 회전 이력 (2순위, 2026-08) — "이 메뉴 최근에 내보내지 않았나?"에 답한다.
// 판정 기준은 백엔드(app/services/menu_rotation.py)에 있고 여기선 표시만 한다.
const ROTATION_FLAG_COLOR: Record<string, string> = {
  "같은 날 중복": "var(--critical)",
  "재편성 과다": "var(--critical)",
  "평소보다 이름": "var(--warning)",
  오랜만: "var(--accent)",
};
// 기본값은 "고칠 것만 보기" — 적정/이력 없음까지 다 띄우면 한 주에 수십 줄이라
// 정작 봐야 할 경고가 묻힌다.
// "같은 날 중복"(코너 간 같은 날 중복 편성)은 담당자가 볼 필요 없다고 해서
// 기본 경고에서 뺐다(2026-08). 백엔드 판정은 그대로라 되살리려면 여기만 고치면 된다.
const ROTATION_WARNING_FLAGS = new Set(["재편성 과다", "평소보다 이름"]);

// 기간 선택 — 식단표 8개월치가 적재돼 PERIOD_START(180일 고정) 너머를 볼 수단이
// 필요해졌다(2026-08). 기본 6개월인 이유: 적재 이전 구간은 편성 이력이 비어 있어
// 편성 횟수가 실제보다 적게 나온다.
const PLAN_PERIOD_OPTIONS = [
  { label: "30일", value: "30" },
  { label: "60일", value: "60" },
  { label: "90일", value: "90" },
  { label: "6개월", value: "180" },
];

// 기본 90일 — 담당자 편성 기준이 "3개월에 2회"라 그 창과 맞춘다(2026-08 요청).
function usePlanPeriod(defaultDays = "90") {
  const [days, setDays] = useState(defaultDays);
  return {
    days,
    setDays,
    periodStart: isoDaysAgo(Number(days)),
    periodEnd: isoDaysAgo(0),
  };
}

/**
 * 중복 점검 — 축이 둘이다.
 *  왼쪽: 기간 내 같은 메뉴 반복 ("이 메뉴 최근에 또 내보내지 않았나")
 *  오른쪽: 슬롯 내 재료·특성 중복 ("이 한 끼 구성이 겹치지 않나")
 * 주 이동 컨트롤을 하나만 두는 이유: 카드가 따로면 주가 어긋나 "회전 이력은
 * 이번 주, 조합은 지난 주"를 보게 된다(2026-08).
 */
function DuplicationCheckSection() {
  const [selectedMonday, setSelectedMonday] = useState(() => weeklyMondayOf(new Date()));
  const [warningsOnly, setWarningsOnly] = useState(true);
  const periodEnd = weeklyAddDays(selectedMonday, 6);

  // 자주 반복되는 부찬 랭킹 — 담당자: "부찬 중복 볼 때 보기가 너무 불편함, 정말
  // 자주 나오고 돌려막기한 부찬을 보고싶어". 위 주간 회전표는 한 주씩 넘기는
  // 구조라 "지난 몇 달간 자주 반복됐다"는 그림이 안 나온다 — 그래서 이 서브
  // 섹션만 독립된 기간(직접 선택 가능)과 코너 필터를 쓴다.
  const [repeatStart, setRepeatStart] = useState(PERIOD_START);
  const [repeatEnd, setRepeatEnd] = useState(PERIOD_END);
  const [repeatCornerId, setRepeatCornerId] = useState<number | null>(null);
  const [showAllRepeated, setShowAllRepeated] = useState(false);
  const REPEATED_PREVIEW_COUNT = 20;

  const rotation = useQuery({
    queryKey: ["weekly-menu-rotation", selectedMonday],
    queryFn: () => api.weeklyMenuRotation({ period_start: selectedMonday, period_end: periodEnd }),
  });
  const clash = useQuery({
    queryKey: ["weekly-menu-combination-check", selectedMonday],
    queryFn: () =>
      api.weeklyMenuCombinationCheck({ period_start: selectedMonday, period_end: periodEnd }),
  });
  const repeatCorners = useQuery({ queryKey: ["corner-list"], queryFn: () => api.cornerList() });
  const repeated = useQuery({
    queryKey: ["weekly-menu-repeated-side-dishes", repeatStart, repeatEnd, repeatCornerId],
    queryFn: () =>
      api.weeklyMenuRepeatedSideDishes({
        period_start: repeatStart,
        period_end: repeatEnd,
        ...(repeatCornerId != null ? { corner_id: repeatCornerId } : {}),
      }),
  });
  const repeatedItems = repeated.data?.items ?? [];
  const visibleRepeatedItems = showAllRepeated
    ? repeatedItems
    : repeatedItems.slice(0, REPEATED_PREVIEW_COUNT);

  // 경고는 두 축이다 — 간격(직전 이후 며칠)과 횟수(3개월에 몇 번).
  // "14일은 넘겼지만 분기에 3번"은 간격만 봐선 안 잡힌다.
  const isRotationWarning = (r: MenuRotationRow) =>
    ROTATION_WARNING_FLAGS.has(r.flag) || r.over_frequency;
  const rotationItems = (rotation.data?.items ?? []).filter(
    (r) => !warningsOnly || isRotationWarning(r),
  );
  // 담당자 우선순위: 메인 과다 편성이 1순위, 부찬은 그다음.
  const mainRotation = rotationItems.filter((r) => r.menu_role === "메인");
  const sideRotation = rotationItems.filter((r) => r.menu_role !== "메인");
  const rotationWarnings = (rotation.data?.items ?? []).filter(isRotationWarning).length;
  const mainWarnings = (rotation.data?.items ?? []).filter(
    (r) => r.menu_role === "메인" && isRotationWarning(r),
  ).length;
  const clashSlots = (clash.data?.slots ?? []).filter(
    (s) => s.ingredient_clashes.length > 0 || s.vector_clashes.length > 0,
  );

  return (
    <Card title="중복 점검 — 같은 메뉴 반복 · 한 끼 구성 겹침">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => setSelectedMonday(weeklyAddDays(selectedMonday, -7))}>
          ◀ 이전 주
        </Button>
        <span className="text-[13px] font-medium">
          {selectedMonday} ~ {periodEnd}
        </span>
        <Button variant="secondary" onClick={() => setSelectedMonday(weeklyAddDays(selectedMonday, 7))}>
          다음 주 ▶
        </Button>
        <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          <input type="checkbox" checked={warningsOnly} onChange={(e) => setWarningsOnly(e.target.checked)} />
          경고만 보기
        </label>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 축 1 — 기간 내 같은 메뉴 반복 */}
        <div>
          <p className="mb-1 text-[13px] font-medium">이 메뉴 최근에 또 내보내지 않았나</p>
          <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            두 축으로 봅니다 — <strong>간격</strong>(직전 편성 이후
            {rotation.data ? ` ${rotation.data.min_rotation_gap_days}` : " 14"}일 미만이면 "재편성 과다")과
            <strong>횟수</strong>(최근 {rotation.data ? rotation.data.rotation_window_days : 90}일에 메인은
            2회, 부찬은 6회까지 무난). "14일은 넘겼지만 분기에 3번"은 간격만으론 안 잡힙니다.
            <strong>메인 과다 편성이 1순위 문제</strong>라 위에 따로 놓았습니다.
          </p>
          {rotation.data && (
            <p
              className="mb-2 text-xs"
              style={{ color: rotationWarnings > 0 ? "var(--critical)" : "var(--ink-muted)" }}
            >
              경고 {rotationWarnings}건(메인 {mainWarnings}건) / 편성 {rotation.data.items.length}건
            </p>
          )}
          {rotation.isLoading && <LoadingState />}
          {rotation.isError && <ErrorState error={rotation.error} />}
          {rotation.data && rotationItems.length === 0 && (
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              {rotation.data.items.length === 0
                ? "이 주에 등록된 식단표가 없습니다."
                : "반복 편성 경고가 없습니다."}
            </p>
          )}
          {(["메인", "부찬·건강가든"] as const).map((group) => {
            const rows = group === "메인" ? mainRotation : sideRotation;
            if (rows.length === 0) return null;
            const isMain = group === "메인";
            return (
              <div key={group} className="mb-3">
                <p
                  className="mb-1 text-xs font-medium"
                  style={{ color: isMain ? "var(--critical)" : "var(--ink-secondary)" }}
                >
                  {isMain ? "메인메뉴 (1순위)" : "부찬 · 건강가든"}
                </p>
                <Table
                  columns={[
                    { key: "date", label: "날짜" },
                    { key: "menu", label: "메뉴" },
                    { key: "flag", label: "판정" },
                    { key: "gap", label: "직전 이후", align: "right" },
                    { key: "freq", label: "3개월", align: "right" },
                  ]}
                  rows={rows.map((r, i) => ({
                    key: `${r.plan_date}-${r.corner_id}-${r.menu_id}-${i}`,
                    date: weekdayLabel(r.plan_date),
                    menu: `${r.menu_name} (${r.corner_name})`,
                    flag: (
                      <span style={{ color: ROTATION_FLAG_COLOR[r.flag] ?? "var(--ink-muted)" }}>
                        {r.flag}
                      </span>
                    ),
                    gap:
                      r.gap_days == null
                        ? "-"
                        : `${r.gap_days}일 전${r.previous_date ? ` (${r.previous_date.slice(5)})` : ""}`,
                    freq: (
                      <span
                        style={{
                          color: r.over_frequency
                            ? isMain
                              ? "var(--critical)"
                              : "var(--warning)"
                            : "var(--ink-muted)",
                        }}
                      >
                        {r.window_count}/{r.window_max}회
                      </span>
                    ),
                  }))}
                  rowKey={(r) => r.key as string}
                />
              </div>
            );
          })}
          <div className="mt-3 border-t pt-3" style={{ borderColor: "var(--border)" }}>
            <p className="mb-1 text-[13px] font-medium">자주 반복되는 부찬 랭킹</p>
            <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
              위 표와 달리 기간을 직접 골라 볼 수 있습니다 — "지난 3개월 동안 이 부찬이 유독 자주
              돌아갔다" 같은 그림은 한 주씩 넘겨선 안 보이기 때문입니다. 같은 코너 안에서만
              세고(다른 코너에 같은 반찬이 나온 건 중복이 아님), 건강가든은 공용이라 어느 코너와
              겹쳐도 셉니다.
            </p>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                시작일
                <input
                  type="date"
                  className="rounded-md border px-3 py-2 text-[13px]"
                  style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                  value={repeatStart}
                  max={repeatEnd}
                  onChange={(e) => setRepeatStart(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                종료일
                <input
                  type="date"
                  className="rounded-md border px-3 py-2 text-[13px]"
                  style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                  value={repeatEnd}
                  min={repeatStart}
                  onChange={(e) => setRepeatEnd(e.target.value)}
                />
              </label>
              <div className="flex flex-col gap-1">
                <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                  코너
                </span>
                <SegmentedControl
                  value={repeatCornerId != null ? String(repeatCornerId) : ""}
                  options={[
                    { label: "전체", value: "" },
                    ...(repeatCorners.data ?? []).map((c) => ({
                      label: c.corner_name,
                      value: String(c.corner_id),
                    })),
                  ]}
                  onChange={(v) => setRepeatCornerId(v === "" ? null : Number(v))}
                />
              </div>
            </div>
            {repeated.isLoading && <LoadingState />}
            {repeated.isError && <ErrorState error={repeated.error} />}
            {repeated.data && repeatedItems.length === 0 && (
              <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                이 기간·코너에 반복 편성된 부찬이 없습니다.
              </p>
            )}
            {repeatedItems.length > 0 && (
              <>
                <Table
                  columns={[
                    { key: "rank", label: "순위", align: "right" },
                    { key: "corner", label: "코너" },
                    { key: "menu", label: "메뉴" },
                    { key: "role", label: "역할" },
                    { key: "count", label: "횟수", align: "right" },
                  ]}
                  rows={visibleRepeatedItems.map((o, i) => ({
                    key: `${o.corner_name}-${o.menu_name}`,
                    rank: i + 1,
                    corner: o.corner_name,
                    menu: o.menu_name,
                    role: o.menu_role,
                    count: `${o.count}회`,
                  }))}
                  rowKey={(r) => r.key as string}
                />
                {repeatedItems.length > REPEATED_PREVIEW_COUNT && (
                  <button
                    className="mt-2 text-xs underline"
                    style={{ color: "var(--accent)" }}
                    onClick={() => setShowAllRepeated((v) => !v)}
                  >
                    {showAllRepeated ? "접기" : `전체 ${repeatedItems.length}개 보기`}
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* 축 2 — 슬롯 내 재료·특성 중복 */}
        <div>
          <p className="mb-1 text-[13px] font-medium">이 한 끼 구성이 겹치지 않나</p>
          <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            같은 날·같은 코너·같은 끼니 안에서 메인·부찬·건강가든끼리 재료가 겹치거나(콩나물국밥 +
            콩나물무침) 특성이 겹치는지(둘 다 매움, 둘 다 탄수화물) 봅니다. 재료 판정은 키워드 사전
            기반이라 사전에 없는 재료는 못 잡습니다.
          </p>
          {clash.data != null && clash.data.untagged_menu_count > 0 && (
            <p className="mb-2 text-xs" style={{ color: "var(--warning)" }}>
              {clash.data.untagged_menu_count}개 메뉴는 음식벡터 미태깅이라 특성 중복을 못 봤습니다
              (관리 탭에서 태깅).
            </p>
          )}
          {clash.isLoading && <LoadingState />}
          {clash.isError && <ErrorState error={clash.error} />}
          {clash.data && clashSlots.length === 0 && (
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              {clash.data.slots.length === 0
                ? "이 주에 등록된 식단표가 없습니다."
                : "구성 겹침이 발견되지 않았습니다."}
            </p>
          )}
          <div className="space-y-2">
            {clashSlots.map((s) => (
              <div
                key={`${s.plan_date}-${s.corner_id}-${s.meal_type}`}
                className="rounded-xl border p-3"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="text-[13px] font-medium">
                  {weekdayLabel(s.plan_date)} · {s.corner_name} ({s.meal_type})
                </div>
                <div className="mt-0.5 text-xs" style={{ color: "var(--ink-muted)" }}>
                  {s.main ?? "메인 미배정"}
                  {s.sides.length > 0 && ` · 부찬: ${s.sides.join(", ")}`}
                  {s.health_garden.length > 0 && ` · 건강가든: ${s.health_garden.join(", ")}`}
                </div>
                <ul className="mt-2 space-y-1 text-xs">
                  {s.ingredient_clashes.map((c, i) => (
                    <li key={`ing-${i}`} style={{ color: "var(--critical)" }}>
                      재료 중복 — {c.menu_a} ↔ {c.menu_b}: {c.shared.join(", ")}
                    </li>
                  ))}
                  {s.vector_clashes.map((c, i) => (
                    <li key={`vec-${i}`} style={{ color: "var(--warning)" }}>
                      {c.label_ko} 중복 — {c.menu_a} ↔ {c.menu_b}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

const PLANNING_ACTION_COLOR: Record<string, string> = {
  "감편 검토": "var(--critical)",
  "증편 후보": "var(--good)",
  "주력 유지": "var(--accent)",
  "취식 기록 없음": "var(--warning)",
};

/**
 * 편성 빈도 × 성과 — "다음 주 뭘 빼고 뭘 넣을까".
 * 기존 4분면(/menu-performance)의 X축은 meal_log의 취식 발생 일수라 편성만 되고
 * 아무도 안 먹은 메뉴가 아예 안 나타난다. 이 화면은 weekly_menu_plan 기준이라
 * 그게 보이고, 그게 가장 강한 감편 신호다(2026-08).
 */
function MenuPlanPerformanceSection() {
  const { days, setDays, periodStart, periodEnd } = usePlanPeriod();
  const chartTheme = useChartTheme();
  const query = useQuery({
    queryKey: ["menu-plan-performance", periodStart, periodEnd],
    queryFn: () => api.menuPlanPerformance({ period_start: periodStart, period_end: periodEnd }),
  });

  const items = query.data?.items ?? [];
  const medianPlan = query.data?.median_plan_count ?? 0;
  const medianScore = query.data?.median_satisfaction ?? 0;
  const maxPerPlan = Math.max(1, ...items.map((r) => r.headcount_per_plan));

  // 판정별로 시리즈를 나눈다 — 그래야 범례가 생기고, 범례를 눌러 한 분류만
  // 골라 볼 수 있다. 예전엔 시리즈 하나에 색만 달라서 "이 색이 무슨 뜻인지"를
  // 알 방법이 없었다(2026-08 "그래프가 직관적이지 않음" 피드백).
  const PLOTTED_ACTIONS = ["감편 검토", "증편 후보", "주력 유지", "현행 유지"] as const;
  const actionSeries = PLOTTED_ACTIONS.map((action) => ({
    name: action,
    type: "scatter" as const,
    itemStyle: { color: resolveColor(PLANNING_ACTION_COLOR[action] ?? "var(--ink-muted)") },
    symbolSize: (v: number[]) => 8 + Math.sqrt(v[2] / maxPerPlan) * 22,
    // 점마다 메뉴명을 상시 표시하고 겹치면 자동으로 비킨다 — 4분면 차트(§42)와
    // 같은 처리라 두 화면의 조작감이 같다.
    // formatter를 안 주면 ECharts가 값(숫자)을 찍는다 — 메뉴명이 나와야 한다.
    label: {
      show: true,
      position: "right" as const,
      color: chartTheme.text,
      fontSize: 11,
      formatter: (p: { name: string }) => p.name,
    },
    labelLayout: { moveOverlap: "shiftY" as const, hideOverlap: true },
    data: items
      .filter((r) => r.action === action && r.avg_satisfaction != null)
      .map((r) => ({
        name: r.menu_name,
        value: [r.plan_count, r.avg_satisfaction as number, r.headcount_per_plan],
      })),
  })).filter((serie) => serie.data.length > 0);

  // 사분면 배경 음영 + 모서리 이름. 중앙값 십자선만 있으면 "어느 쪽이 감편인지"를
  // 매번 머리로 계산해야 한다.
  const maxPlan = Math.max(medianPlan * 2, ...items.map((r) => r.plan_count), 1);
  const quadrantMarkArea = {
    silent: true,
    itemStyle: { opacity: 0.06 },
    label: {
      show: true,
      position: "inside" as const,
      color: chartTheme.text,
      fontSize: 11,
      opacity: 0.9,
    },
    data: [
      // 자주 편성 + 반응 낮음 → 감편
      [
        { xAxis: medianPlan, yAxis: 0, itemStyle: { color: resolveColor("var(--critical)") },
          label: { formatter: "감편 검토\n(자주 내는데 반응 낮음)", position: "insideBottomRight" as const } },
        { xAxis: maxPlan, yAxis: medianScore },
      ],
      // 드물게 편성 + 반응 높음 → 증편
      [
        { xAxis: 0, yAxis: medianScore, itemStyle: { color: resolveColor("var(--good)") },
          label: { formatter: "증편 후보\n(드문데 반응 좋음)", position: "insideTopLeft" as const } },
        { xAxis: medianPlan, yAxis: 5 },
      ],
      // 자주 + 높음 → 주력 유지
      [
        { xAxis: medianPlan, yAxis: medianScore, itemStyle: { color: resolveColor("var(--accent)") },
          label: { formatter: "주력 유지", position: "insideTopRight" as const } },
        { xAxis: maxPlan, yAxis: 5 },
      ],
    ],
  };

  const option = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 56, right: 40, top: 44, bottom: 48 },
    legend: { top: 0, textStyle: { color: chartTheme.text } },
    tooltip: {
      trigger: "item",
      formatter: (p: { name: string; value: number[]; seriesName: string }) =>
        `${p.name} · ${p.seriesName}<br/>편성 ${p.value[0]}회 · 만족도 ${p.value[1].toFixed(2)}` +
        `<br/>1회 편성당 ${p.value[2]}명 (점 크기)`,
    },
    xAxis: {
      type: "value",
      name: "편성 횟수 →",
      nameLocation: "middle",
      nameGap: 28,
      min: 0,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "value",
      name: "만족도",
      min: 0,
      max: 5,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      ...actionSeries,
      {
        // 사분면 배경 + 중앙값 십자선 전용(데이터 없는 시리즈) — 각 산점도
        // 시리즈에 붙이면 분류 수만큼 겹쳐 그려진다.
        name: "기준선",
        type: "scatter" as const,
        data: [],
        silent: true,
        markArea: quadrantMarkArea,
        markLine: {
          silent: true,
          symbol: "none" as const,
          lineStyle: { color: chartTheme.axis, type: "dashed" as const },
          label: { color: chartTheme.text, fontSize: 10, position: "insideEndTop" as const },
          data: [
            { xAxis: medianPlan, label: { formatter: "편성 중앙값" } },
            { yAxis: medianScore, label: { formatter: "만족도 중앙값" } },
          ],
        },
      },
    ],
  };

  const actionRows = items.filter((r) => r.action === "감편 검토" || r.action === "증편 후보");
  const noIntake = items.filter((r) => r.action === "취식 기록 없음");

  return (
    <Card title="편성 빈도 × 성과 — 다음 주 편성 조정">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        식단표에 <strong>몇 번 올렸는지</strong>(편성 횟수)와 실제 반응(만족도·1회 편성당 식수)을
        교차합니다. 편성 횟수는 담당자가 직접 통제하는 변수라 다음 주에 바꿀 수 있습니다. 기준선은 그
        기간 전체의 중앙값이며, 취식 데이터가 메인메뉴 기준이라 <strong>메인메뉴만</strong> 봅니다.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          조회 기간
        </span>
        <SegmentedControl value={days} options={PLAN_PERIOD_OPTIONS} onChange={setDays} />
      </div>

      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && items.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 기간에 등록된 식단표가 없습니다.
        </p>
      )}

      {query.data && items.length > 0 && (
        <>
          <div
            className="mb-3 rounded-md border p-2 text-xs"
            style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
          >
            식단표↔취식기록 매칭: 이어진 메뉴 {query.data.matching.matched}개 · 편성만 되고 취식 0인 메뉴{" "}
            {query.data.matching.plan_only.length}개 · 취식만 있고 식단표에 없는 메뉴{" "}
            {query.data.matching.log_only.length}개.{" "}
            <strong>취식 0은 진짜 안 팔린 것일 수도, 메뉴명 표기가 달라 매칭이 안 된 것일 수도</strong>{" "}
            있으니 아래 목록에서 확인하세요.
          </div>
          {actionSeries.length > 0 && <ReactECharts option={option} style={{ height: 400 }} />}

          {actionRows.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
                편성 조정 후보
              </p>
              <Table
                columns={[
                  { key: "menu", label: "메뉴" },
                  { key: "action", label: "판정" },
                  { key: "plans", label: "편성", align: "right" },
                  { key: "score", label: "만족도", align: "right" },
                  { key: "perPlan", label: "1회당 식수", align: "right" },
                ]}
                rows={actionRows.map((r) => ({
                  menu: r.menu_name,
                  action: (
                    <span style={{ color: PLANNING_ACTION_COLOR[r.action] ?? "var(--ink-muted)" }}>
                      {r.action}
                    </span>
                  ),
                  plans: `${r.plan_count}회`,
                  score: r.avg_satisfaction?.toFixed(2) ?? "-",
                  perPlan: `${r.headcount_per_plan}명`,
                }))}
                rowKey={(r) => r.menu as string}
              />
            </div>
          )}

          {noIntake.length > 0 && (
            <div className="mt-4 border-t pt-3" style={{ borderColor: "var(--border)" }}>
              <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
                편성됐지만 취식 기록이 0인 메뉴 — 기존 "메뉴별 분석" 4분면에는 아예 안 나타나는
                메뉴들입니다. 메뉴명 표기 불일치가 아닌지 먼저 확인하세요.
              </p>
              <div className="flex flex-wrap gap-2">
                {noIntake.map((r) => (
                  <span
                    key={r.menu_id}
                    className="rounded-md border px-2 py-1 text-xs"
                    style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
                  >
                    {r.menu_name} · {r.plan_count}회 편성
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/** 코너별 레퍼토리 진단 — 몇 종을 돌렸고 얼마나 쏠렸나. */
function MenuRepertoireSection() {
  const { days, setDays, periodStart, periodEnd } = usePlanPeriod();
  const query = useQuery({
    queryKey: ["menu-plan-repertoire", periodStart, periodEnd],
    queryFn: () => api.menuPlanRepertoire({ period_start: periodStart, period_end: periodEnd }),
  });

  return (
    <Card title="코너별 레퍼토리 — 메뉴 다양성 진단">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        코너가 그 기간에 <strong>몇 종을 돌렸고</strong> 상위 5개에 얼마나 쏠렸는지 봅니다. 집중도(HHI)는
        0에 가까울수록 고르게 분산된 것입니다. 종수가 적어도 고르게 돌리면 체감 다양성은 나쁘지 않고,
        종수가 많아도 몇 개에 쏠리면 단조롭게 느껴지므로 두 지표를 같이 봅니다.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          조회 기간
        </span>
        <SegmentedControl value={days} options={PLAN_PERIOD_OPTIONS} onChange={setDays} />
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && query.data.items.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 기간에 등록된 식단표가 없습니다.
        </p>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(query.data?.items ?? []).map((r) => (
          <div
            key={`${r.corner_name}-${r.menu_role}`}
            className="rounded-xl border p-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] font-medium">
                {r.corner_name} · {r.menu_role}
              </span>
              <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                {r.unique_menus}종 / {r.total_slots}회 편성
              </span>
            </div>
            <div className="mt-1 text-xs" style={{ color: "var(--ink-secondary)" }}>
              상위 5개 비중 {(r.top_share * 100).toFixed(0)}% · 집중도(HHI) {r.hhi.toFixed(3)}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {r.top_menus.map((m) => (
                <span
                  key={m.menu_name}
                  className="rounded-md border px-1.5 py-0.5 text-xs"
                  style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                >
                  {m.menu_name} {m.count}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}


// ---- 2026-08 화면 재편으로 생긴 최상위 화면 3개 ----
// 기존 "분석" 탭(서브탭 5개)을 해체하고, 담당자 협의에서 정한 5개 축
// (현황 / 메뉴 편성·운영 / 만족도·VoE / Agent 채팅 / 관리)에 맞춰 재배치했다.

/** 메뉴 편성·운영 — "다음 주 식단을 어떻게 짤까"에 답하는 화면. */
export function MenuPlanningPage() {
  // 메뉴 동반 선택 쌍은 코너 목록이 필요한데, 배치 집계(daily_corner_stats)에
  // 의존하지 않는 마스터 기반 목록을 쓴다(집계 전에도 코너가 보이도록).
  const cornersQuery = useQuery({ queryKey: ["corner-list"], queryFn: () => api.cornerList() });
  return (
    <div className="space-y-6">
      <WeeklyMenuReviewTab />
      <DuplicationCheckSection />
      <MenuPlanPerformanceSection />
      <MenuComboSection />
      <MenuRepertoireSection />
      <MenuPairAnalysisSection corners={cornersQuery.data ?? []} />
    </div>
  );
}

/** 만족도·VoE — "무엇이 좋았고 무엇이 불만인가"에 답하는 화면. */
export function SatisfactionVoePage() {
  return (
    <div className="space-y-6">
      <MenuQuadrantTab />
      <VoeAnalysisTab />
    </div>
  );
}

/**
 * 관리 — 일상 운영 동선에서 치워 둔 관리자용 도구 모음.
 * 주의: 이 앱에는 로그인/권한 체계가 없다. 이 탭은 **접근 제한이 아니라
 * 메인 화면 정리 목적**이며, 화면에도 그렇게 명시한다(협의 결정, 2026-08).
 */
export function AdminPage() {
  const [exportStart, setExportStart] = useState(isoDaysAgo(30));
  const [exportEnd, setExportEnd] = useState(isoDaysAgo(0));
  const mealLogExportUrl = `/api/dashboard/meal-log/export?period_start=${exportStart}&period_end=${exportEnd}`;
  return (
    <div className="space-y-6">
      <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
        자주 쓰지 않는 관리 기능을 모아 둔 화면입니다. <strong>접근 권한이 걸려 있지는 않으며</strong>
        (이 앱에는 로그인 체계가 없습니다), 일상 화면을 단순하게 유지하기 위해 분리해 둔 것입니다.
      </p>
      <MenuFoodVectorAdminSection />
      <Card title="전체 취식 데이터 다운로드 (기간 선택)">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          요약이 아닌 개별 취식 기록(취식일시·사번·구분·회사명·식사구분·코너·메뉴·맛평가·의견)을 선택한 기간 그대로 엑셀로 내려받습니다.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            시작일
            <input
              type="date"
              className="rounded-md border px-3 py-2 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              value={exportStart}
              max={exportEnd}
              onChange={(e) => setExportStart(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            종료일
            <input
              type="date"
              className="rounded-md border px-3 py-2 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              value={exportEnd}
              min={exportStart}
              max={isoDaysAgo(0)}
              onChange={(e) => setExportEnd(e.target.value)}
            />
          </label>
          <a href={mealLogExportUrl} download>
            <Button variant="secondary">엑셀 다운로드</Button>
          </a>
        </div>
      </Card>
    </div>
  );
}
