import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import clsx from "clsx";
import {
  api,
  type Classification,
  type CornerMenuThroughputResponse,
  type CornerTrendRow,
  type Granularity,
  type MealType,
  type MenuFoodVectorRow,
  type MenuPairRow,
  type MenuPerformanceRow,
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

type SubTab = "menus" | "corners" | "users" | "voe" | "weekly-menu";

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

// 본사/계열사/기타를 항상 이 순서·색으로 그린다 (팔레트 categorical 순서 고정 원칙).
// 데이터 키(division 필드값)는 그대로 "본사"를 쓰되, 본사=삼성전자뿐이라 화면
// 표시만 "삼성전자"로 바꾼다(사용자 확인, 2026-07).
const DIVISION_ORDER = ["본사", "계열사", "기타"];
const DIVISION_LABELS: Record<string, string> = { 본사: "삼성전자", 계열사: "계열사", 기타: "기타" };
const DIVISION_SERIES_VAR = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

function DivisionAnalysisSection() {
  const [granularity, setGranularity] = useState<Granularity>("weekly");
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const chartTheme = useChartTheme();

  const query = useQuery({
    queryKey: ["division-analysis", granularity, classification],
    queryFn: () =>
      api.divisionAnalysis({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        granularity,
        classification: classification === "전체" ? undefined : classification,
      }),
  });
  const recomputeDailyStats = useMutation({
    mutationFn: () => api.recomputeDailyStats({ period_start: PERIOD_START, period_end: PERIOD_END }),
    onSuccess: () => query.refetch(),
  });

  const rows = query.data ?? [];
  const periods = [...new Set(rows.map((r) => r.period))].sort();
  const byDivision: Record<string, Map<string, number>> = {};
  for (const r of rows) {
    (byDivision[r.division] ??= new Map()).set(r.period, r.headcount);
  }
  const divisions = DIVISION_ORDER.filter((d) => byDivision[d]);

  const option = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: "axis", formatter: axisTooltipFormatter },
    legend: { top: 0, textStyle: { color: chartTheme.text } },
    xAxis: {
      type: "category",
      data: periods,
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
    series: divisions.map((division) => ({
      name: DIVISION_LABELS[division] ?? division,
      type: "bar",
      barMaxWidth: 22,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: resolveColor(DIVISION_SERIES_VAR[DIVISION_ORDER.indexOf(division)]),
      },
      data: periods.map((p) => byDivision[division].get(p) ?? 0),
    })),
  };

  return (
    <Card title="삼성전자/계열사/기타 식수 (PRD 6.1)">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          value={granularity}
          options={[
            { label: "일간", value: "daily" },
            { label: "주간", value: "weekly" },
            { label: "월간", value: "monthly" },
          ]}
          onChange={setGranularity}
        />
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
      {rows.length === 0 && !query.isLoading && (
        <div className="space-y-2">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            데이터가 없습니다. 배치 집계(daily_division_stats)가 먼저 필요합니다 — 취식 데이터를 과거 기간 한꺼번에
            적재한 경우, 스케줄러는 매일 새벽 전날치만 계산하므로 최근 180일치를 한 번에 다시 계산해야 합니다.
          </p>
          <Button variant="secondary" onClick={() => recomputeDailyStats.mutate()} disabled={recomputeDailyStats.isPending}>
            {recomputeDailyStats.isPending ? "계산 중..." : "최근 180일 배치 집계 재계산"}
          </Button>
          {recomputeDailyStats.isError && <ErrorState error={recomputeDailyStats.error} />}
        </div>
      )}
      {rows.length > 0 && <ReactECharts option={option} style={{ height: 280 }} />}
      {rows.length > 0 && (
        <div className="mt-4">
          <Table
            columns={[
              { key: "period", label: "기간" },
              ...divisions.map((d) => ({ key: d, label: DIVISION_LABELS[d] ?? d, align: "right" as const })),
            ]}
            rows={periods.map((p) => ({
              period: p,
              ...Object.fromEntries(divisions.map((d) => [d, (byDivision[d].get(p) ?? 0).toLocaleString()])),
            }))}
            rowKey={(r) => r.period as string}
          />
        </div>
      )}
    </Card>
  );
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


function TasteClusterSection() {
  const chartTheme = useChartTheme();
  const query = useQuery({
    queryKey: ["taste-clusters"],
    queryFn: () => api.tasteClusters(),
  });
  const recompute = useMutation({
    mutationFn: () => api.recomputeTasteClusters(5),
    onSuccess: () => query.refetch(),
  });

  const clusters = query.data ?? [];
  const dimensions = clusters[0]?.dimensions ?? [];

  const heatmapOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 150, right: 90, top: 16, bottom: 70 },
    tooltip: {
      formatter: (p: { value: [number, number, number] }) =>
        `${clusters[p.value[1]].label}<br/>${dimensions[p.value[0]]}: ${p.value[2]}`,
    },
    xAxis: {
      type: "category",
      data: dimensions,
      axisLabel: { color: chartTheme.text, rotate: 40 },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: clusters.map((c) => `${c.label} (${c.size}명)`),
      axisLabel: { color: chartTheme.text },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      orient: "vertical" as const,
      right: 0,
      top: "middle" as const,
      itemHeight: 120,
      inRange: { color: SEQUENTIAL_BLUE_RAMP },
      textStyle: { color: chartTheme.text },
    },
    series: [
      {
        type: "heatmap",
        data: clusters.flatMap((c, ci) =>
          c.centroid_vector.map((v, di) => [di, ci, Number(v.toFixed(2))]),
        ),
        label: { show: false },
      },
    ],
  };

  return (
    <Card title="취향 군집 요약 — 사번 검색 없이 전체 경향 보기">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          전체 취향 벡터를 K-means로 묶어 몇 개의 취향 그룹으로 요약합니다.
        </p>
        <Button variant="secondary" onClick={() => recompute.mutate()} disabled={recompute.isPending}>
          재계산
        </Button>
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {recompute.isError && <ErrorState error={recompute.error} />}
      {clusters.length === 0 && !query.isLoading && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          군집 결과가 없습니다. 먼저 취향 프로필이 충분히 쌓인 뒤(사용자 분석 아래 "조회" 전 recompute 필요) "재계산"을
          눌러보세요 — 군집 5개를 만들려면 최소 10명의 취향 프로필이 필요합니다.
        </p>
      )}
      {clusters.length > 0 && (
        <ReactECharts option={heatmapOption} style={{ height: 100 + clusters.length * 40 }} />
      )}
      {clusters.length > 0 && (
        <div className="mt-4">
          <Table
            columns={[
              { key: "label", label: "그룹" },
              { key: "size", label: "인원수", align: "right" },
              { key: "satisfaction", label: "평균 만족도", align: "right" },
              { key: "corner", label: "주 이용 코너" },
              { key: "menus", label: "대표 메뉴" },
            ]}
            rows={clusters.map((c) => ({
              label: c.label,
              size: c.size,
              satisfaction: c.avg_satisfaction?.toFixed(2) ?? "-",
              corner: c.dominant_corner ?? "-",
              menus: c.top_menus.join(", ") || "-",
            }))}
            rowKey={(r) => r.label as string}
          />
        </div>
      )}
    </Card>
  );
}

function TasteProfileSection() {
  const [employeeId, setEmployeeId] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const profile = useQuery({
    queryKey: ["taste-profile", searched],
    queryFn: () => api.userTasteProfile(searched as string),
    enabled: !!searched,
    retry: false,
  });

  return (
    <Card title="사용자 입맛 분석 — 사번별 취향 벡터">
      <div className="mb-4 flex gap-2">
        <input
          className="w-48 rounded-md border px-3 py-2 text-[13px]"
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          placeholder="사번 (예: E12345)"
          value={employeeId}
          onChange={(e) => setEmployeeId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setSearched(employeeId)}
        />
        <Button onClick={() => setSearched(employeeId)}>조회</Button>
      </div>
      {profile.isLoading && <LoadingState />}
      {profile.isError && <ErrorState error={profile.error} />}
      {profile.data && (
        <div>
          <p className="mb-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            표본 {profile.data.sample_size}건 기반 취향 벡터 (메뉴 food_vector와 동일 차원)
            {profile.data.cluster_label && (
              <>
                {" "}
                ·{" "}
                <span className="rounded px-1.5 py-0.5" style={{ background: "var(--surface-2)" }}>
                  {profile.data.cluster_label}
                </span>
              </>
            )}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {profile.data.dimensions.map((dim, i) => (
              <div key={dim} className="rounded-md border p-2 text-center" style={{ borderColor: "var(--border)" }}>
                <div className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  {dim}
                </div>
                <div className="text-[13px] font-medium">{profile.data!.profile_vector[i]?.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function UserAnalysisTab() {
  return (
    <div className="space-y-6">
      <DivisionAnalysisSection />
      <TasteClusterSection />
      <TasteProfileSection />
    </div>
  );
}

function CornerAnalysisTab() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [showCornerTable, setShowCornerTable] = useState(false);
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

  // 코너 선택을 이 탭과 CornerLoyaltySection이 공유한다 — 피크타임 서브속도를
  // "코너별 비교"(아래 throughputTrendOption, 전체 코너)와 "메뉴별 비교"(선택된
  // 코너의 메뉴별, CornerLoyaltySection에도 있던 차트)로 오갈 때 코너 선택이
  // 서로 어긋나지 않게 한다(2026-07).
  const [selectedCornerId, setSelectedCornerId] = useState<number | null>(null);
  useEffect(() => {
    if (selectedCornerId == null && (query.data ?? []).length > 0) {
      setSelectedCornerId(query.data![0].corner_id);
    }
  }, [query.data, selectedCornerId]);
  const [throughputCompareMode, setThroughputCompareMode] = useState<"corner" | "menu">("corner");
  // corner-menu-throughput 쿼리키는 CornerLoyaltySection과 동일 — React Query
  // 캐시가 자동으로 중복 요청을 막아준다(이 레포에 이미 있는 패턴).
  const menuThroughputQuery = useQuery({
    queryKey: ["corner-menu-throughput", selectedCornerId],
    queryFn: () =>
      api.cornerMenuThroughput(selectedCornerId as number, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
      }),
    enabled: selectedCornerId != null && throughputCompareMode === "menu",
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

  const trendLegend = {
    top: 0,
    textStyle: { color: chartTheme.text },
    data: activeCorners.map((c) => c.corner_name),
  };
  const trendXAxis = {
    type: "category" as const,
    data: activePeriods,
    axisLine: { lineStyle: { color: chartTheme.axis } },
    axisTick: { show: false },
    axisLabel: isWeekOfMonth
      ? { color: chartTheme.text, formatter: (v: string) => weekOfMonthLabel(v) }
      : { color: chartTheme.text },
  };

  // 이용자 수(식수) & 만족도 — 별개 차트 대신 하나의 듀얼축 그래프로 겹쳐서 본다
  // (2026-07 사용자 요청: "이용자 수 & 만족도 수 그래프 1개로 같이"). 이전엔 이
  // 통합 그래프가 월간 고정이었는데, 아래 코너별 서브속도 추이와 같은 기간 단위
  // 선택(주간/월간/주차별)을 공유하도록 activePeriods/activeByCorner를 그대로 쓴다.
  const headcountSatisfactionTooltipFormatter = buildMetricTooltipFormatter({
    headcount: "식수",
    satisfaction: "만족도",
  });
  const headcountSatisfactionOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 56, right: 56, top: 40, bottom: 28 },
    tooltip: { trigger: "axis", formatter: headcountSatisfactionTooltipFormatter },
    legend: trendLegend,
    xAxis: trendXAxis,
    yAxis: [
      {
        type: "value",
        name: "식수",
        axisLabel: { color: chartTheme.text },
        splitLine: { lineStyle: { color: chartTheme.grid } },
      },
      {
        type: "value",
        name: "만족도",
        min: 0,
        max: 5,
        axisLabel: { color: chartTheme.text },
        splitLine: { show: false },
      },
    ],
    series: activeCorners.flatMap((c) => {
      const color = resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)");
      return [
        {
          id: `${c.corner_name}::headcount`,
          name: c.corner_name,
          type: "line" as const,
          yAxisIndex: 0,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2, color },
          itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
          data: activePeriods.map((p) => activeByCorner.get(c.corner_name)?.get(p)?.headcount ?? null),
        },
        {
          id: `${c.corner_name}::satisfaction`,
          name: c.corner_name,
          type: "line" as const,
          yAxisIndex: 1,
          symbol: "diamond",
          symbolSize: 8,
          lineStyle: { width: 2, type: "dashed" as const, color },
          itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
          data: activePeriods.map((p) => activeByCorner.get(c.corner_name)?.get(p)?.avg_taste_score ?? null),
        },
      ];
    }),
  };

  // 피크타임 서브속도 & 코너별 점유율 — 기존엔 점유율이 (기간 전체 누적 기준)
  // 파이차트로 따로 떨어져 있었는데, 서브속도 추이와 합쳐 기간별 꺾은선으로 본다
  // (2026-07 사용자 요청). 점유율은 이 두 차트에 공통인 shareEligibleCorners
  // (Take Out·그린미트·미캠회관(전골) 제외 — 착석 취식 코너 간 경쟁 비교 목적)
  // 기준으로 기간별 합계 대비 비율을 그때그때 계산한다(새 엔드포인트 불필요 —
  // cornerAnalysisTrend가 이미 코너·기간별 headcount를 반환함).
  const shareEligibleCorners = activeCorners.filter(
    (c) => !c.is_diet_corner && !SHARE_EXCLUDED_CORNER_NAMES.has(c.corner_name),
  );
  const periodShareTotals = new Map<string, number>();
  for (const p of activePeriods) {
    let total = 0;
    for (const c of shareEligibleCorners) total += activeByCorner.get(c.corner_name)?.get(p)?.headcount ?? 0;
    periodShareTotals.set(p, total);
  }
  const throughputShareTooltipFormatter = buildMetricTooltipFormatter({
    throughput: "피크타임 서브",
    share: "점유율(%)",
  });
  const throughputShareOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 56, top: 40, bottom: 28 },
    tooltip: { trigger: "axis", formatter: throughputShareTooltipFormatter },
    legend: {
      top: 0,
      textStyle: { color: chartTheme.text },
      data: shareEligibleCorners.map((c) => c.corner_name),
    },
    xAxis: trendXAxis,
    yAxis: [
      {
        type: "value",
        name: "피크타임 분당 서브",
        axisLabel: { color: chartTheme.text },
        splitLine: { lineStyle: { color: chartTheme.grid } },
      },
      {
        type: "value",
        name: "점유율(%)",
        min: 0,
        max: 100,
        axisLabel: { color: chartTheme.text },
        splitLine: { show: false },
      },
    ],
    series: shareEligibleCorners.flatMap((c) => {
      const color = resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)");
      return [
        {
          id: `${c.corner_name}::throughput`,
          name: c.corner_name,
          type: "line" as const,
          yAxisIndex: 0,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2, color },
          itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
          data: activePeriods.map((p) => activeByCorner.get(c.corner_name)?.get(p)?.avg_peak_throughput_per_min ?? null),
        },
        {
          id: `${c.corner_name}::share`,
          name: c.corner_name,
          type: "line" as const,
          yAxisIndex: 1,
          symbol: "diamond",
          symbolSize: 8,
          lineStyle: { width: 2, type: "dashed" as const, color },
          itemStyle: { color, borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
          data: activePeriods.map((p) => {
            const total = periodShareTotals.get(p) ?? 0;
            const headcount = activeByCorner.get(c.corner_name)?.get(p)?.headcount;
            return total > 0 && headcount != null ? Number(((headcount / total) * 100).toFixed(2)) : null;
          }),
        },
      ];
    }),
  };

  return (
    <div className="space-y-6">
      <Card title="코너별 분석 — 이용자 수 / 만족도 / 피크타임 서브속도">
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
            <div>
              <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                코너별 이용자 수 · 만족도 추이 (왼쪽 축=식수, 오른쪽 축=만족도 — 범례를 클릭하면 시리즈별로
                켜고 끌 수 있습니다)
              </p>
              {activeIsLoading && <LoadingState />}
              {activeIsError && <ErrorState error={activeError} />}
              {activePeriods.length > 0 && <ReactECharts option={headcountSatisfactionOption} style={{ height: 380 }} />}
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
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  피크타임 서브속도 · 코너별 점유율 추이 (왼쪽 축=서브속도, 오른쪽 축=점유율 — Take
                  Out·그린미트·미캠회관(전골)은 착석 취식 코너 간 경쟁 비교 목적상 제외)
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <SegmentedControl
                    value={throughputCompareMode}
                    options={[
                      { label: "코너별 비교", value: "corner" },
                      { label: "메뉴별 비교", value: "menu" },
                    ]}
                    onChange={setThroughputCompareMode}
                  />
                  {throughputCompareMode === "menu" && query.data && query.data.length > 0 && (
                    <SegmentedControl
                      value={selectedCornerId != null ? String(selectedCornerId) : ""}
                      options={query.data.map((c) => ({ label: c.corner_name, value: String(c.corner_id) }))}
                      onChange={(v) => setSelectedCornerId(Number(v))}
                    />
                  )}
                </div>
              </div>
              {throughputCompareMode === "corner" ? (
                <>
                  {activeIsLoading && <LoadingState />}
                  {activeIsError && <ErrorState error={activeError} />}
                  {activePeriods.length > 0 && shareEligibleCorners.length === 0 && (
                    <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                      비교할 코너가 없습니다.
                    </p>
                  )}
                  {activePeriods.length > 0 && shareEligibleCorners.length > 0 && (
                    <ReactECharts option={throughputShareOption} style={{ height: 380 }} />
                  )}
                </>
              ) : (
                <>
                  {menuThroughputQuery.isLoading && <LoadingState />}
                  {menuThroughputQuery.isError && <ErrorState error={menuThroughputQuery.error} />}
                  {menuThroughputQuery.data && menuThroughputQuery.data.menus.length === 0 && (
                    <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                      표본 부족
                    </p>
                  )}
                  {menuThroughputQuery.data && menuThroughputQuery.data.menus.length > 0 && (
                    <ReactECharts
                      option={buildMenuThroughputOption(menuThroughputQuery.data, chartTheme)}
                      style={{ height: Math.max(160, menuThroughputQuery.data.menus.length * 32) }}
                    />
                  )}
                </>
              )}
            </div>
          </>
        )}
      </Card>
      <CornerLoyaltySection
        corners={query.data ?? []}
        selectedCornerId={selectedCornerId}
        onSelectCorner={setSelectedCornerId}
      />
      <MenuPairAnalysisSection corners={query.data ?? []} />
      <MenuAffinitySection />
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
    label: { show: true, position: "right" as const, color: chartTheme.text, fontSize: 11 },
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

// 코너의 "그날 대표 메뉴"별 피크타임 처리량을 느린 순으로 보여준다 — 점선은
// 그 코너의 전체 평균(baseline), 기준선보다 느리면 warning, 아니면 good.
function buildMenuThroughputOption(
  data: CornerMenuThroughputResponse,
  chartTheme: { text: string; axis: string; grid: string },
) {
  const goodColor = resolveColor("var(--good)");
  const warnColor = resolveColor("var(--warning)");
  const baseline = data.overall_avg_throughput ?? 0;
  const menus = data.menus;

  return {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 100, right: 24, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" as const, formatter: axisTooltipFormatter },
    xAxis: {
      type: "value" as const,
      name: "평균 서브속도(분당)",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "category" as const,
      inverse: true,
      data: menus.map((m) => m.menu_name ?? "메뉴 미배정"),
      axisLine: { lineStyle: { color: chartTheme.axis } },
      axisLabel: { color: chartTheme.text },
      axisTick: { show: false },
    },
    series: [
      {
        name: "평균 서브속도",
        type: "bar" as const,
        barMaxWidth: 20,
        itemStyle: {
          borderRadius: [0, 4, 4, 0] as [number, number, number, number],
          color: (params: { dataIndex: number }) =>
            menus[params.dataIndex].avg_throughput < baseline ? warnColor : goodColor,
        },
        data: menus.map((m) => m.avg_throughput),
        markLine:
          data.overall_avg_throughput != null
            ? {
                symbol: "none" as const,
                label: { formatter: "전체 평균", color: chartTheme.text },
                lineStyle: { color: chartTheme.axis, type: "dashed" as const },
                data: [{ xAxis: data.overall_avg_throughput }],
              }
            : undefined,
      },
    ],
  };
}

// PRD 10-1: 코너 코어층 = "코너 충성도" 분석. 특정 코너를 반복적으로 찾는
// 이용자층 규모/특징만 본다 — 메뉴 동반 선택 쌍(10-2, 메뉴 선호 연관 분석)과는
// 목적이 다른 별개 화면으로 분리했다(2026-07, 기존엔 한 카드에 섞여 있었음).
function CornerLoyaltySection({
  corners,
  selectedCornerId,
  onSelectCorner,
}: {
  corners: { corner_id: number; corner_name: string }[];
  // 코너 선택은 부모(CornerAnalysisTab)와 공유한다 — "피크타임 서브속도"
  // 섹션의 "메뉴별 비교" 모드와 코너 선택이 어긋나지 않게 하기 위함(2026-07).
  selectedCornerId: number | null;
  onSelectCorner: (cornerId: number) => void;
}) {
  const chartTheme = useChartTheme();
  const [minVisitCount, setMinVisitCount] = useState(3);
  const [minShare, setMinShare] = useState(30);

  const cornerQuery = useQuery({
    queryKey: ["corner-core-layer-menu-pairs", selectedCornerId, minVisitCount, minShare],
    queryFn: () =>
      api.cornerCoreLayerMenuPairs(selectedCornerId as number, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        min_visit_count: minVisitCount,
        min_share: minShare / 100,
      }),
    enabled: selectedCornerId != null,
  });
  const throughputQuery = useQuery({
    queryKey: ["corner-menu-throughput", selectedCornerId],
    queryFn: () =>
      api.cornerMenuThroughput(selectedCornerId as number, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
      }),
    enabled: selectedCornerId != null,
  });
  // 코너간 비교 뷰 — "어디 코너 코어층은 몇 명이고 유동층은 몇 명인지" 전체를
  // 한눈에 보기 위한 요약(2026-07). 아래 코너 선택 컨트롤과 같은 min_visit_
  // count/min_share를 공유해 상세 뷰와 기준이 어긋나지 않게 한다.
  const summaryQuery = useQuery({
    queryKey: ["corner-core-layer-summary", minVisitCount, minShare],
    queryFn: () =>
      api.cornerCoreLayerSummary({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        min_visit_count: minVisitCount,
        min_share: minShare / 100,
      }),
  });

  if (corners.length === 0) return null;

  const pref = cornerQuery.data?.menu_controlled_preference;

  return (
    <Card title="코너 코어층 — 코너 충성도 분석">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        특정 코너를 습관적으로 찾는 이용자층을 두 기준으로 봅니다: ① 방문 횟수·비중이 유의미하게 높은
        경우, ② 같은 메인메뉴가 여러 코너에서 동시 제공된 날에도 이 코너를 고른 비율(메뉴가 같으니 코너
        선택은 순수한 코너 선호로 봅니다). 두 신호는 서로 다른 관점이라 따로 보여줍니다.
      </p>
      {summaryQuery.isLoading && <LoadingState />}
      {summaryQuery.isError && <ErrorState error={summaryQuery.error} />}
      {summaryQuery.data && (
        <div className="mb-5">
          <Table
            columns={[
              { key: "corner_name", label: "코너" },
              { key: "core", label: "코어 이용자", align: "right" },
              { key: "non_core", label: "유동층", align: "right" },
            ]}
            rows={summaryQuery.data.map((r) => ({
              corner_name: r.corner_name,
              core: `${r.core_employee_count}명`,
              non_core: `${r.non_core_employee_count}명`,
            }))}
            rowKey={(row) => row.corner_name as string}
          />
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl
          value={selectedCornerId != null ? String(selectedCornerId) : ""}
          options={corners.map((c) => ({ label: c.corner_name, value: String(c.corner_id) }))}
          onChange={(v) => onSelectCorner(Number(v))}
        />
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
      </div>
      {cornerQuery.isLoading && <LoadingState />}
      {cornerQuery.isError && <ErrorState error={cornerQuery.error} />}
      {cornerQuery.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatTile
            label="코어 이용자 (방문 빈도·비중 기준)"
            value={`${cornerQuery.data.core_layer.employee_count}명`}
            sub={`방문 ${minVisitCount}회↑ · 비중 ${minShare}%↑`}
          />
          <StatTile label="나머지 이용자" value={`${cornerQuery.data.non_core.employee_count}명`} />
          <StatTile
            label="메뉴 동일 상황에서도 이 코너 선택 비율"
            value={pref ? `${(pref.preference_ratio * 100).toFixed(0)}%` : "데이터 없음"}
            sub={
              pref
                ? `${pref.contested_occasions}건 중 ${pref.chosen_count}건`
                : "같은 날 같은 메인메뉴가 다른 코너와 동시 제공된 적이 없습니다"
            }
          />
        </div>
      )}
      <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
        <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
          메뉴별 피크타임 서브속도 — 그날 이 코너의 대표 메뉴 기준(점선은 전체 평균, 그보다 느리면 주황)
        </p>
        {throughputQuery.isLoading && <LoadingState />}
        {throughputQuery.isError && <ErrorState error={throughputQuery.error} />}
        {throughputQuery.data && throughputQuery.data.menus.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            표본 부족
          </p>
        )}
        {throughputQuery.data && throughputQuery.data.menus.length > 0 && (
          <ReactECharts
            option={buildMenuThroughputOption(throughputQuery.data, chartTheme)}
            style={{ height: Math.max(160, throughputQuery.data.menus.length * 32) }}
          />
        )}
      </div>
    </Card>
  );
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
          className="rounded-md border p-3 text-left transition-colors"
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

// 분면별로 따로 떼어 그리면(원래 전체를 한 좌표에 겹쳐 그리던 것과 달리)
// 분면 하나당 항목 수가 적어 점끼리 겹칠 일이 크게 줄어든다 — 점(산점도)
// 옆에 "메뉴명 (코너명)" 라벨을 항상 붙여서(2026-07, 같은 메뉴명이 여러
// 코너에서 나올 수 있어 코너명까지 표기해야 구분됨) 어떤 점인지 바로 알 수
// 있게 한다. 그래도 점이 많으면 라벨이 겹칠 수 있어 labelLayout으로 먼저
// 세로로 밀어보고(moveOverlap), 그래도 겹치면 아예 숨긴다(hideOverlap —
// 겹쳐서 글씨를 못 알아보는 것보다 일부만 보이는 게 낫다, 2026-07 피드백).
// 표본이 더 믿을만한(제공 횟수가 많아 원이 큰) 점의 라벨이 우선 살아남도록
// appearance_count 내림차순으로 정렬해 넘긴다(hideOverlap은 배열 뒤쪽 요소의
// 라벨을 먼저 숨김).
function buildQuadrantScatterOption(
  items: MenuQuadrantMetrics[],
  color: string,
  chartTheme: ReturnType<typeof useChartTheme>,
) {
  const ordered = [...items].sort((a, b) => b.appearance_count - a.appearance_count);
  const maxAppearance = Math.max(1, ...ordered.map((r) => r.appearance_count));
  const data = ordered.map((r) => {
    const isLowAppearance = r.appearance_count < LOW_APPEARANCE_THRESHOLD;
    const label = r.corner_name ? `${r.menu_name} (${r.corner_name})` : r.menu_name;
    return {
      name: label,
      value: [r.demand, r.satisfaction, r.appearance_count],
      satisfactionTrend: r.satisfaction_trend,
      hasLoyalFollowing: r.has_loyal_following,
      symbolSize: 8 + Math.sqrt(r.appearance_count / maxAppearance) * 22,
      itemStyle: {
        color,
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
  return {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 24, top: 16, bottom: 40 },
    tooltip: {
      formatter: (p: {
        data: {
          name: string;
          value: number[];
          satisfactionTrend: TrendDirection | null;
          hasLoyalFollowing: boolean;
        };
      }) => {
        const lines = [
          p.data.name,
          `수요: ${p.data.value[0].toFixed(2)}`,
          `만족도: ${p.data.value[1].toFixed(2)}`,
          `제공 횟수: ${p.data.value[2]}회`,
        ];
        if (p.data.satisfactionTrend === "하락") lines.push("만족도 추세: 하락");
        if (p.data.hasLoyalFollowing) lines.push("고정 고객 있음");
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      name: "수요(1회 제공당 평균 식수)",
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
      {
        type: "scatter" as const,
        data,
        labelLayout: { moveOverlap: "shiftY" as const, hideOverlap: true },
      },
    ],
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
        가로축(1회 제공당 평균 식수)과 세로축(만족도)이 각각 기준값보다 큰지 작은지로
        네 가지로 나눕니다. 기준값은 기본적으로 전체 메뉴의 중앙값이며, 아래 슬라이더로
        직접 조절할 수 있습니다(표본부족 판정은 평가건수 기준으로 별도 처리되어 조절
        대상이 아닙니다). 분류별로 그래프를 따로 그려 점끼리 겹치는 걸 줄였고, 점 옆에
        "메뉴명 (코너명)"을 표기합니다(흐린 점 = 최근 {LOW_APPEARANCE_THRESHOLD}회
        미만 제공이라 수요 수치가 우연한 결과로 튈 수 있음, 원 크기는 제공 횟수). 점이
        너무 몰려 라벨이 겹치면 일부는 자동으로 숨겨지는데, 안 보이는 점도 마우스를
        올리면 툴팁으로 확인할 수 있습니다. 아래 범례를 클릭하면 보고 싶은 분류만 골라
        볼 수 있고, "표시 개수"로 분류별 표시 개수를 조절할 수 있습니다.
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
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {visibleQuadrantLabels.map((label) => {
            const items = (quadrantRows.get(label) ?? []).slice().sort((a, b) => b.demand - a.demand);
            const limited = items.slice(0, quadrantLimitN);
            return (
              <div key={label} className="rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[13px] font-medium">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: resolveColor(quadrantColor(label)) }}
                    />
                    {label}
                  </div>
                  <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    {items.length}개 중 {limited.length}개 표시
                  </span>
                </div>
                {limited.length === 0 ? (
                  <p className="py-6 text-center text-[13px]" style={{ color: "var(--ink-muted)" }}>
                    해당 없음
                  </p>
                ) : (
                  <ReactECharts
                    option={buildQuadrantScatterOption(limited, resolveColor(quadrantColor(label)), chartTheme)}
                    style={{ height: Math.max(280, Math.min(560, 60 + limited.length * 22)) }}
                  />
                )}
              </div>
            );
          })}
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

function MenuAffinitySection() {
  const [menuName, setMenuName] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["menu-affinity", searched],
    queryFn: () =>
      api.menuAffinity(searched as string, { period_start: PERIOD_START, period_end: PERIOD_END }),
    enabled: !!searched,
    retry: false,
  });

  return (
    <Card title="메뉴 동반 선택 경향성 — 같이/대신 자주 고르는 메뉴">
      <div className="mb-3 flex gap-2">
        <input
          className="w-48 rounded-md border px-3 py-2 text-[13px]"
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}
          placeholder="메뉴명 (예: 떡볶이)"
          value={menuName}
          onChange={(e) => setMenuName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setSearched(menuName)}
        />
        <Button onClick={() => setSearched(menuName)}>조회</Button>
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && query.data.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          유의미한 동반 선택 메뉴가 없습니다 (표본이 너무 적거나 연관성이 낮음).
        </p>
      )}
      {query.data && query.data.length > 0 && (
        <Table
          columns={[
            { key: "menu", label: "메뉴" },
            { key: "co_count", label: "동반 인원", align: "right" },
            { key: "lift", label: "연관도(lift)", align: "right" },
          ]}
          rows={query.data.map((r) => ({
            menu: r.menu_name,
            co_count: r.co_count,
            lift: r.lift.toFixed(2),
          }))}
          rowKey={(r) => r.menu as string}
        />
      )}
      <p className="mt-3 text-xs" style={{ color: "var(--ink-muted)" }}>
        lift가 1보다 크면 우연히 같이 나오는 것보다 더 자주 동반 선택된다는 뜻입니다.
      </p>
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
    <div className="rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
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

function CampusAverageFoodVectorSection() {
  const chartTheme = useChartTheme();
  const query = useQuery({
    queryKey: ["menu-food-vectors-average"],
    queryFn: () => api.averageMenuFoodVector(),
  });

  const data = query.data;
  const labels = data ? data.dimensions.map((d) => data.labels_ko[d] ?? d) : [];
  const accentColor = resolveColor("var(--accent)");

  const option = data && {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    tooltip: {},
    legend: {
      bottom: 0,
      textStyle: { color: chartTheme.text },
      data: ["캠퍼스 평균", "중립 기준(0.5)"],
    },
    radar: {
      indicator: labels.map((name) => ({ name, min: 0, max: 1 })),
      axisName: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: chartTheme.axis } },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            name: "캠퍼스 평균",
            value: data.average,
            areaStyle: { color: accentColor, opacity: 0.25 },
            lineStyle: { color: accentColor, width: 2 },
            itemStyle: { color: accentColor },
          },
          {
            name: "중립 기준(0.5)",
            value: data.dimensions.map(() => 0.5),
            lineStyle: { type: "dashed" as const, color: chartTheme.axis },
            itemStyle: { color: chartTheme.axis },
            areaStyle: { opacity: 0 },
          },
        ],
      },
    ],
  };

  return (
    <Card title="캠퍼스 메인메뉴 평균 음식벡터 — 어떤 맛으로 쏠려 있는가">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        현재 음식벡터가 태깅된 메인메뉴 전체를 축별로 평균 낸 값입니다(부찬은 제외). 점선(중립 기준
        0.5)보다 바깥으로 나온 축이 캠퍼스 메뉴 구성이 쏠려 있는 방향입니다.
      </p>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {data && data.sample_size === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          태깅된 메인메뉴 음식벡터가 아직 없습니다.
        </p>
      )}
      {data && data.sample_size > 0 && option && (
        <>
          <p className="mb-2 text-[13px]" style={{ color: "var(--ink)" }}>
            {data.bias_description}
            <span className="ml-2 text-xs" style={{ color: "var(--ink-muted)" }}>
              (메인메뉴 {data.sample_size}개 기준)
            </span>
          </p>
          <ReactECharts option={option} style={{ height: 360 }} />
        </>
      )}
    </Card>
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
        <Button variant="secondary" onClick={() => tagWithLlm.mutate()} disabled={tagWithLlm.isPending}>
          LLM으로 미태깅 메뉴 보강
        </Button>
      </div>
      {tagWithLlm.data && (
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          {tagWithLlm.data.tagged_menus}건 태깅됨
        </p>
      )}
      {tagWithLlm.isError && <ErrorState error={tagWithLlm.error} />}
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

function MenuComboSection() {
  const [menuName, setMenuName] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["menu-combinations", searched],
    queryFn: () =>
      api.menuSideCombinations(searched as string, { period_start: PERIOD_START, period_end: PERIOD_END }),
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
            <div key={i} className="rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
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
      className="mt-2 rounded-md border p-3 text-[13px]"
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
              <div className="mt-4 rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
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
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {voeCategory.data.categories.map((c) => (
                <button
                  key={c.category}
                  onClick={() => setSelectedVoeCategory((cur) => (cur === c.category ? null : c.category))}
                  className="rounded-md border p-3 text-left transition-colors"
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
                        { key: "corner_name", label: "코너" },
                        { key: "comment", label: "코멘트" },
                      ]}
                      rows={selected.comments.map((c) => ({
                        eaten_at: c.eaten_at.replace("T", " "),
                        corner_name: c.corner_name ?? "-",
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
                className="rounded-md border p-3"
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

export function AnalysisPage() {
  const [tab, setTab] = useState<SubTab>("menus");
  const tabs: { value: SubTab; label: string }[] = [
    { value: "menus", label: "메뉴별 분석" },
    { value: "corners", label: "코너별 분석" },
    { value: "users", label: "사용자 분석" },
    { value: "voe", label: "주관식 VOE" },
    { value: "weekly-menu", label: "주간 식단표 관리" },
  ];
  return (
    <div className="space-y-6">
      <div className="flex gap-5 border-b" style={{ borderColor: "var(--border)" }}>
        {tabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className="border-b-2 py-2 text-[13px] font-medium"
            style={{
              borderColor: tab === t.value ? "var(--accent)" : "transparent",
              color: tab === t.value ? "var(--ink)" : "var(--ink-secondary)",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "menus" && (
        <div className="space-y-6">
          <MenuQuadrantTab />
          <MenuComboSection />
          <CampusAverageFoodVectorSection />
          <MenuFoodVectorAdminSection />
        </div>
      )}
      {tab === "corners" && <CornerAnalysisTab />}
      {tab === "users" && <UserAnalysisTab />}
      {tab === "voe" && <VoeAnalysisTab />}
      {tab === "weekly-menu" && <WeeklyMenuReviewTab />}
    </div>
  );
}
