import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type Classification, type CongestionForecastRow } from "../api/client";
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

// 이 3개 코너는 니치 코너(테이크아웃/소규모 별관/다이어트식)라 일반 코너
// 추이 비교에서 기본으로는 안 보이게 하고, 범례 맨 뒤로 보내 필요할 때만
// 클릭해서 켜게 한다(analysis.py::corner_analysis의 그린미트 정렬 관례와
// 같은 취지 — 니치 코너는 항상 뒤로).
const LOW_PRIORITY_CORNER_NAMES = new Set(["Take Out", "미캠회관(전골)", "그린미트"]);

// x축 날짜를 "MM-DD(요일)"로 보여줘 월~일 순서가 한눈에 보이게 한다.
function weekdayLabel(dateIso: string): string {
  return `${dateIso.slice(5)}(${WEEKDAY_KO[new Date(dateIso).getDay()]})`;
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
];

export function HomePage({ onOpenWeeklyVoe }: { onOpenWeeklyVoe?: () => void }) {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const [exportStart, setExportStart] = useState(isoDaysAgo(30));
  const [exportEnd, setExportEnd] = useState(isoDaysAgo(0));
  const [selectedMonday, setSelectedMonday] = useState(mondayOf(new Date()));
  // 식당은 일요일에 운영하지 않으므로 월~토 6일만 조회한다.
  const saturdayOfSelected = addDays(selectedMonday, 5);

  const weekly = useQuery({
    queryKey: ["weekly-summary", selectedMonday, saturdayOfSelected, classification],
    queryFn: () =>
      api.weeklySummary({
        start_date: selectedMonday,
        end_date: saturdayOfSelected,
        classification: classification === "전체" ? undefined : classification,
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

  const cornerTrend = useQuery({
    queryKey: ["corner-weekly-trend", selectedMonday, saturdayOfSelected, classification],
    queryFn: () =>
      api.cornerAnalysisTrend({
        period_start: selectedMonday,
        period_end: saturdayOfSelected,
        granularity: "daily",
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
  const topCongestedCorner = (congestionForecast.data?.corners ?? []).reduce<CongestionForecastRow | null>(
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
  const holidayColor = resolveColor("var(--critical)");
  const classificationByDate = new Map((weekly.data ?? []).map((d) => [d.date, d.classification]));
  const weekdayAxisLabel = {
    color: (value: string) => (classificationByDate.get(value) === "주말+공휴일" ? holidayColor : chartTheme.text),
    formatter: (value: string) => weekdayLabel(value),
  };

  const chartOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis", formatter: axisTooltipFormatter },
    xAxis: {
      type: "category",
      data: weekly.data?.map((d) => d.date) ?? [],
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
        data: (weekly.data ?? []).map((d) => ({
          value: d.headcount,
          itemStyle: { color: d.classification === "주말+공휴일" ? seriesHoliday : seriesWeekday },
        })),
      },
    ],
  };

  // 색은 코너 인기 순위가 아니라 corner_id 기준으로 고정한다(dataviz 스킬: 색은
  // 개체를 따라가야 하고 순위를 따라가면 안 된다) — cornerSummary.data는 이미
  // 백엔드에서 그린미트 항상 마지막 정렬로 온다(analysis.py::corner_analysis).
  const stableHomeCorners = [...(cornerSummary.data ?? [])].sort((a, b) => a.corner_id - b.corner_id);
  const homeCornerColor = new Map(stableHomeCorners.map((c, i) => [c.corner_id, `var(--series-${(i % 8) + 1})`]));
  const cornerTrendDays = weekly.data?.map((d) => d.date) ?? [];
  const trendByCornerHome = new Map<string, Map<string, number>>();
  for (const row of cornerTrend.data ?? []) {
    if (!trendByCornerHome.has(row.corner_name)) trendByCornerHome.set(row.corner_name, new Map());
    trendByCornerHome.get(row.corner_name)!.set(row.period, row.headcount);
  }
  // 니치 코너(LOW_PRIORITY_CORNER_NAMES)는 범례 맨 뒤로 보내고 기본 숨김 —
  // 나머지 코너는 기존 순서(corner_analysis 반환 순서) 그대로 유지.
  const trendCornersHome = [...(cornerSummary.data ?? [])]
    .filter((c) => trendByCornerHome.has(c.corner_name))
    .sort((a, b) => Number(LOW_PRIORITY_CORNER_NAMES.has(a.corner_name)) - Number(LOW_PRIORITY_CORNER_NAMES.has(b.corner_name)));
  const cornerLegendSelected = Object.fromEntries(
    trendCornersHome.map((c) => [c.corner_name, !LOW_PRIORITY_CORNER_NAMES.has(c.corner_name)]),
  );

  const cornerTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: "axis", formatter: axisTooltipFormatter },
    legend: {
      top: 0,
      textStyle: { color: chartTheme.text },
      data: trendCornersHome.map((c) => c.corner_name),
      selected: cornerLegendSelected,
    },
    xAxis: {
      type: "category",
      data: cornerTrendDays,
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
    series: trendCornersHome.map((c) => ({
      name: c.corner_name,
      type: "line" as const,
      symbol: "circle",
      symbolSize: 8,
      lineStyle: { width: 2, color: resolveColor(homeCornerColor.get(c.corner_id) ?? "var(--series-1)") },
      itemStyle: {
        color: resolveColor(homeCornerColor.get(c.corner_id) ?? "var(--series-1)"),
        borderColor: resolveColor("var(--surface)"),
        borderWidth: 2,
      },
      data: cornerTrendDays.map((d) => trendByCornerHome.get(c.corner_name)?.get(d) ?? 0),
    })),
  };

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${selectedMonday}&end_date=${saturdayOfSelected}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }`;

  const mealLogExportUrl = `/api/dashboard/meal-log/export?period_start=${exportStart}&period_end=${exportEnd}`;

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
        {weekly.data && weekly.data.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
              코너별 주간 식수 추이
            </p>
            {cornerTrend.isLoading && <LoadingState />}
            {cornerTrend.isError && <ErrorState error={cornerTrend.error} />}
            {cornerTrend.data && trendCornersHome.length > 0 && (
              <ReactECharts option={cornerTrendOption} style={{ height: 280 }} />
            )}
          </div>
        )}
      </Card>

      <Card title="메뉴 하이라이트">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          메뉴별로 이번에 나온 시점을 그 직전 등장 시점과 비교합니다(메뉴는 매주 나오지 않으므로 달력 주
          단위가 아니라 메뉴별 직전 등장 대비입니다). 신메뉴는 최근 30일 내 처음 나온 메뉴의 초기 반응입니다.
        </p>
        {menuHighlights.isLoading && <LoadingState />}
        {menuHighlights.isError && <ErrorState error={menuHighlights.error} />}
        {menuHighlights.data && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
                    { key: "score", label: "만족도", align: "right" },
                  ]}
                  rows={menuHighlights.data.rising.map((r) => ({
                    menu: `${r.menu_name}${r.corner_name ? ` (${r.corner_name})` : ""}`,
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
                    { key: "score", label: "만족도", align: "right" },
                  ]}
                  rows={menuHighlights.data.falling.map((r) => ({
                    menu: `${r.menu_name}${r.corner_name ? ` (${r.corner_name})` : ""}`,
                    score: `${r.prior_score.toFixed(2)} → ${r.recent_score.toFixed(2)}`,
                  }))}
                  rowKey={(r, i) => `${r.menu as string}-${i}`}
                />
              )}
            </div>
            <div>
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
