import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type Classification, type Granularity, type MenuPerformanceRow } from "../api/client";
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
const DIVISION_ORDER = ["본사", "계열사", "기타"];
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
      name: division,
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
    <Card title="본사/계열사/기타 식수 (PRD 6.1)">
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
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          데이터가 없습니다. 배치 집계(daily_division_stats)가 먼저 필요합니다.
        </p>
      )}
      {rows.length > 0 && <ReactECharts option={option} style={{ height: 280 }} />}
      {rows.length > 0 && (
        <div className="mt-4">
          <Table
            columns={[
              { key: "period", label: "기간" },
              ...divisions.map((d) => ({ key: d, label: d, align: "right" as const })),
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
      }),
  });

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

  return (
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
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          데이터가 없습니다. 배치 집계(daily_corner_stats)가 먼저 필요합니다.
        </p>
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
        </>
      )}
    </Card>
  );
}

function MenuQuadrantTab() {
  const chartTheme = useChartTheme();
  const query = useQuery({
    queryKey: ["menu-performance", PERIOD_START, PERIOD_END],
    queryFn: () => api.menuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END }),
  });
  const recompute = () => api.recomputeMenuPerformance({ period_start: PERIOD_START, period_end: PERIOD_END });

  const rows = query.data ?? [];
  const demandThreshold = median(rows.map((r) => r.total_headcount / Math.max(r.appearance_count, 1)));
  const scoreThreshold = median(rows.map((r) => r.adjusted_score ?? 0));

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
          <Table
            columns={[
              { key: "menu", label: "메뉴" },
              { key: "appearance", label: "등장횟수", align: "right" },
              { key: "count", label: "평가건수", align: "right" },
              { key: "score", label: "만족도", align: "right" },
              { key: "quadrant", label: "4분면" },
            ]}
            rows={rows.map((r: MenuPerformanceRow) => ({
              menu: r.menu_name,
              appearance: r.appearance_count,
              count: r.evaluation_count,
              score: r.adjusted_score?.toFixed(2) ?? "-",
              quadrant: <QuadrantBadge label={r.quadrant} />,
            }))}
            rowKey={(r) => r.menu as string}
          />
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
      {tab === "menus" && <MenuQuadrantTab />}
      {tab === "corners" && <CornerAnalysisTab />}
      {tab === "users" && <UserAnalysisTab />}
    </div>
  );
}
