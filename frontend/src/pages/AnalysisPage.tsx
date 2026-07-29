import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import {
  api,
  type Classification,
  type CornerTrendRow,
  type Granularity,
  type MenuFoodVectorRow,
  type MenuPairRow,
  type MenuPerformanceRow,
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
  Table,
  quadrantColor,
  useChartTheme,
} from "../components/ui";

type SubTab = "menus" | "corners" | "users";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const PERIOD_END = isoDaysAgo(0);
const PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준

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
    tooltip: { trigger: "axis" },
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

// 히트맵 값(0~1)이 낮음→높음으로 진해지는 단일 색상(blue) 시퀀셜 램프.
const SEQUENTIAL_BLUE_RAMP = ["#cde2fb", "#5598e7", "#0d366b"];

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
    <div className="space-y-4">
      <DivisionAnalysisSection />
      <TasteClusterSection />
      <TasteProfileSection />
    </div>
  );
}

function CornerAnalysisTab() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
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

  const shareRows = (query.data ?? []).filter(
    (c) => !c.is_diet_corner && !SHARE_EXCLUDED_CORNER_NAMES.has(c.corner_name),
  );

  const [trendGranularity, setTrendGranularity] = useState<"weekly" | "monthly">("weekly");
  // 기본은 하나만 크게 보여주고(가독성), 필요하면 둘 다 켜서 동시에 볼 수 있게 한다 —
  // 만족도(0~5점)와 서브속도는 단위가 달라 한 차트에 두 축으로 겹치지 않는다.
  const [visibleTrendMetrics, setVisibleTrendMetrics] = useState({ satisfaction: true, throughput: false });
  const toggleTrendMetric = (key: "satisfaction" | "throughput") =>
    setVisibleTrendMetrics((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      return next.satisfaction || next.throughput ? next : prev; // 최소 하나는 켜져 있어야 함
    });
  const trendQuery = useQuery({
    queryKey: ["corner-analysis-trend", classification, trendGranularity],
    queryFn: () =>
      api.cornerAnalysisTrend({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        granularity: trendGranularity,
        classification: classification === "전체" ? undefined : classification,
        exclude_take_out: true,
      }),
  });
  const trendPeriods = [...new Set((trendQuery.data ?? []).map((r) => r.period))].sort();
  const trendByCorner: Map<string, Map<string, CornerTrendRow>> = new Map();
  for (const row of trendQuery.data ?? []) {
    if (!trendByCorner.has(row.corner_name)) trendByCorner.set(row.corner_name, new Map());
    trendByCorner.get(row.corner_name)!.set(row.period, row);
  }
  // 시리즈 순서·색은 이미 정렬된 query.data(그린미트 항상 마지막) 순서를 그대로 따라간다.
  const trendCorners = (query.data ?? []).filter((c) => trendByCorner.has(c.corner_name));

  const axisStyle = {
    axisLine: { lineStyle: { color: chartTheme.axis } },
    axisLabel: { color: chartTheme.text },
    axisTick: { show: false },
  };

  const headcountOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: query.data?.map((c) => c.corner_name) ?? [], ...axisStyle },
    yAxis: {
      type: "value",
      name: "식수",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 32,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: resolveColor("var(--series-1)") },
        data: query.data?.map((c) => c.headcount_total) ?? [],
      },
    ],
  };

  const satisfactionOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: query.data?.map((c) => c.corner_name) ?? [], ...axisStyle },
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
        type: "bar",
        barMaxWidth: 32,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: resolveColor("var(--series-3)") },
        data: query.data?.map((c) => c.avg_taste_score) ?? [],
      },
    ],
  };

  const shareOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    tooltip: { trigger: "item", formatter: "{b}: {c}건 ({d}%)" },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: resolveColor("var(--surface)"), borderWidth: 2 },
        label: { color: chartTheme.text, formatter: "{b}\n{d}%" },
        labelLine: { lineStyle: { color: chartTheme.axis } },
        data: shareRows.map((c) => ({
          name: c.corner_name,
          value: c.headcount_total,
          itemStyle: { color: resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)") },
        })),
      },
    ],
  };

  const trendLegend = {
    top: 0,
    textStyle: { color: chartTheme.text },
    data: trendCorners.map((c) => c.corner_name),
  };
  const trendSeries = (field: "avg_taste_score" | "avg_peak_throughput_per_min") =>
    trendCorners.map((c) => ({
      name: c.corner_name,
      type: "line" as const,
      symbol: "circle",
      symbolSize: 8,
      lineStyle: { width: 2, color: resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)") },
      itemStyle: {
        color: resolveColor(cornerColor.get(c.corner_id) ?? "var(--series-1)"),
        borderColor: resolveColor("var(--surface)"),
        borderWidth: 2,
      },
      data: trendPeriods.map((p) => trendByCorner.get(c.corner_name)?.get(p)?.[field] ?? null),
    }));

  const satisfactionTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 40, right: 16, top: 40, bottom: 28 },
    tooltip: { trigger: "axis" },
    legend: trendLegend,
    xAxis: { type: "category", data: trendPeriods, ...axisStyle },
    yAxis: {
      type: "value",
      name: "만족도",
      min: 0,
      max: 5,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: trendSeries("avg_taste_score"),
  };

  const throughputTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 40, bottom: 28 },
    tooltip: { trigger: "axis" },
    legend: trendLegend,
    xAxis: { type: "category", data: trendPeriods, ...axisStyle },
    yAxis: {
      type: "value",
      name: "피크타임 분당 서브",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: trendSeries("avg_peak_throughput_per_min"),
  };

  return (
    <div className="space-y-4">
      <Card title="코너별 분석 — 이용자 수 / 만족도 / 피크타임 서브속도">
        <div className="mb-4">
          <SegmentedControl
            value={classification}
            options={[
              { label: "전체", value: "전체" },
              { label: "평일", value: "평일" },
              { label: "주말+공휴일", value: "주말+공휴일" },
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
            {/* 식수(건수)와 만족도(0~5점)는 단위가 달라 하나의 차트에 두 축으로 겹쳐 그리지 않고
                별도 차트 두 개로 분리한다 — 이중축 차트는 임의의 상관관계를 만들어 보여준다. */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  누적 식수
                </p>
                <ReactECharts option={headcountOption} style={{ height: 240 }} />
              </div>
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  평균 만족도 (5점 만점)
                </p>
                <ReactECharts option={satisfactionOption} style={{ height: 240 }} />
              </div>
            </div>
            <div className="mt-4">
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
                  throughput: c.avg_peak_throughput_per_min?.toFixed(1) ?? "-",
                }))}
                rowKey={(r) => r.corner as string}
              />
            </div>
            <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
              <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                코너별 점유율 (Take Out·그린미트·미캠회관(전골) 제외 — 착석 취식 코너 간 경쟁 비교 목적)
              </p>
              {shareRows.length === 0 ? (
                <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                  비교할 코너가 없습니다.
                </p>
              ) : (
                <ReactECharts option={shareOption} style={{ height: 280 }} />
              )}
            </div>
            <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  코너별 만족도·피크타임 서브속도 추이
                </p>
                <SegmentedControl
                  value={trendGranularity}
                  options={[
                    { label: "주간", value: "weekly" },
                    { label: "월간", value: "monthly" },
                  ]}
                  onChange={setTrendGranularity}
                />
              </div>
              <div className="mb-4 flex gap-2">
                <Button
                  variant={visibleTrendMetrics.satisfaction ? "primary" : "secondary"}
                  onClick={() => toggleTrendMetric("satisfaction")}
                >
                  평균 만족도
                </Button>
                <Button
                  variant={visibleTrendMetrics.throughput ? "primary" : "secondary"}
                  onClick={() => toggleTrendMetric("throughput")}
                >
                  피크타임 서브
                </Button>
              </div>
              {trendQuery.isLoading && <LoadingState />}
              {trendQuery.isError && <ErrorState error={trendQuery.error} />}
              {trendQuery.data && trendPeriods.length > 0 && (
                <div className="space-y-4">
                  {visibleTrendMetrics.satisfaction && (
                    <div>
                      <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                        평균 만족도 추이
                      </p>
                      <ReactECharts option={satisfactionTrendOption} style={{ height: 380 }} />
                    </div>
                  )}
                  {visibleTrendMetrics.throughput && (
                    <div>
                      <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                        피크타임 분당 서브 추이
                      </p>
                      <ReactECharts option={throughputTrendOption} style={{ height: 380 }} />
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </Card>
      <CornerCoreLayerSection corners={query.data ?? []} />
    </div>
  );
}

const ALL_MENUS_TAB = "전체";

function CornerCoreLayerSection({ corners }: { corners: { corner_id: number; corner_name: string }[] }) {
  const [selection, setSelection] = useState<string>(ALL_MENUS_TAB);
  const [minVisitCount, setMinVisitCount] = useState(3);
  const [minShare, setMinShare] = useState(30);
  const [minCoCount, setMinCoCount] = useState(3);

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

  const pairColumns = [
    { key: "pair", label: "메뉴 쌍" },
    { key: "co_count", label: "동반 인원", align: "right" as const },
    { key: "lift", label: "연관도(lift, 그룹 내부 기준)", align: "right" as const },
  ];
  const pairRows = (rows: MenuPairRow[]) =>
    rows.map((r) => ({ pair: `${r.menu_a} + ${r.menu_b}`, co_count: r.co_count, lift: r.lift.toFixed(2) }));

  if (corners.length === 0) return null;

  return (
    <Card title="코너 코어층 × 메뉴 동반 선택 쌍 비교">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        "전체"는 코너 구분 없이 전체 인원 기준 가장 흔한 메뉴 쌍을 보여줍니다. 코너를 선택하면 그 코너를
        반복적으로 이용하는 "코어층"과 나머지 인원이 각각 가장 흔하게 함께 고르는 메뉴 쌍을 나란히
        비교합니다(lift는 각 그룹 내부 기준이라 두 그룹 간 직접 비교는 동반 인원 수로 합니다).
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
            <Table columns={pairColumns} rows={pairRows(allQuery.data)} rowKey={(r) => r.pair as string} />
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
                  <Table
                    columns={pairColumns}
                    rows={pairRows(cornerQuery.data.core_layer.top_pairs)}
                    rowKey={(r) => r.pair as string}
                  />
                )}
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
                  <Table
                    columns={pairColumns}
                    rows={pairRows(cornerQuery.data.non_core.top_pairs)}
                    rowKey={(r) => r.pair as string}
                  />
                )}
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

function MenuQuadrantTab() {
  const chartTheme = useChartTheme();
  const [expandedCorner, setExpandedCorner] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["menu-performance", PERIOD_START, PERIOD_END],
    queryFn: () => api.menuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END }),
  });
  const recompute = () => api.recomputeMenuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END });

  const rows = query.data ?? [];
  const demandThreshold = median(rows.map((r) => r.total_headcount / Math.max(r.appearance_count, 1)));
  const scoreThreshold = median(rows.map((r) => r.adjusted_score ?? 0));
  const cornerGroups = groupByCorner(rows);

  const scatterData = rows.map((r) => ({
    name: r.menu_name,
    value: [r.total_headcount / Math.max(r.appearance_count, 1), r.adjusted_score ?? 0],
    itemStyle: { color: resolveColor(quadrantColor(r.quadrant)) },
  }));

  const option = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 24, top: 16, bottom: 40 },
    tooltip: {
      formatter: (p: { data: { name: string; value: number[] } }) =>
        `${p.data.name}<br/>1회 제공당 식수: ${p.data.value[0].toFixed(1)}<br/>만족도: ${p.data.value[1].toFixed(2)}`,
    },
    xAxis: {
      type: "value",
      name: "수요 (1회 제공당 평균 식수)",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "value",
      name: "만족도(표본보정, 5점)",
      min: 0,
      max: 5,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: 12,
        data: scatterData,
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: chartTheme.axis, width: 1 },
          label: { show: false },
          data: [{ xAxis: demandThreshold }, { yAxis: scoreThreshold }],
        },
      },
    ],
  };

  return (
    <Card title="메뉴 4분면 — 인기메뉴 / 숨은강자 / 개선시급 / 퇴출후보">
      <div className="mb-3 flex items-center justify-between">
        <Legend
          items={[
            { label: "인기메뉴", color: "var(--good)" },
            { label: "숨은강자", color: "var(--series-1)" },
            { label: "개선시급", color: "var(--warning)" },
            { label: "퇴출후보", color: "var(--critical)" },
            { label: "표본부족", color: "var(--ink-muted)" },
          ]}
        />
        <Button
          variant="secondary"
          onClick={async () => {
            await recompute();
            query.refetch();
          }}
        >
          재계산
        </Button>
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {rows.length === 0 && !query.isLoading && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          데이터가 없습니다. 먼저 "재계산" 버튼으로 menu_performance_stats를 생성하세요.
        </p>
      )}
      {rows.length > 0 && <ReactECharts option={option} style={{ height: 340 }} />}
      {rows.length > 0 && (
        <div className="mt-4">
          <CornerCardGrid
            groups={cornerGroups}
            selected={expandedCorner}
            onSelect={(c) => setExpandedCorner((cur) => (cur === c ? null : c))}
          />
          {expandedCorner && (
            <div className="mt-4">
              <Table
                columns={[
                  { key: "menu", label: "메뉴" },
                  { key: "appearance", label: "등장횟수", align: "right" },
                  { key: "count", label: "평가건수", align: "right" },
                  { key: "score", label: "만족도", align: "right" },
                  { key: "quadrant", label: "4분면" },
                ]}
                rows={(cornerGroups.find(([c]) => c === expandedCorner)?.[1] ?? []).map(
                  (r: MenuPerformanceRow) => ({
                    menu: r.menu_name,
                    appearance: r.appearance_count,
                    count: r.evaluation_count,
                    score: r.adjusted_score?.toFixed(2) ?? "-",
                    quadrant: <QuadrantBadge label={r.quadrant} />,
                  }),
                )}
                rowKey={(r) => r.menu as string}
              />
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

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function AnalysisPage() {
  const [tab, setTab] = useState<SubTab>("menus");
  const tabs: { value: SubTab; label: string }[] = [
    { value: "menus", label: "메뉴 4분면" },
    { value: "corners", label: "코너별 분석" },
    { value: "users", label: "사용자 분석" },
  ];
  return (
    <div className="space-y-4">
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
        <div className="space-y-4">
          <MenuQuadrantTab />
          <MenuAffinitySection />
          <MenuFoodVectorAdminSection />
        </div>
      )}
      {tab === "corners" && <CornerAnalysisTab />}
      {tab === "users" && <UserAnalysisTab />}
    </div>
  );
}
