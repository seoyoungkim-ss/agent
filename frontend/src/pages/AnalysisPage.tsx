import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type Classification, type MenuPerformanceRow } from "../api/client";
import { Button, Card, ErrorState, LoadingState, QuadrantBadge, SegmentedControl } from "../components/ui";

type SubTab = "users" | "corners" | "menus";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const PERIOD_END = isoDaysAgo(0);
const PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준

function UserAnalysisTab() {
  const [employeeId, setEmployeeId] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  const profile = useQuery({
    queryKey: ["taste-profile", searched],
    queryFn: () => api.userTasteProfile(searched as string),
    enabled: !!searched,
    retry: false,
  });

  return (
    <Card title="사용자 입맛 분석 — 사번별 취향 벡터 (PRD 6.1)">
      <div className="mb-4 flex gap-2">
        <input
          className="w-48 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
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
          <p className="mb-2 text-sm text-slate-500">
            표본 {profile.data.sample_size}건 기반 취향 벡터 (메뉴 food_vector와 동일 차원)
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {profile.data.dimensions.map((dim, i) => (
              <div key={dim} className="rounded-lg border border-slate-100 p-2 text-center dark:border-slate-800">
                <div className="text-xs text-slate-400">{dim}</div>
                <div className="font-mono text-sm">{profile.data!.profile_vector[i]?.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function CornerAnalysisTab() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const query = useQuery({
    queryKey: ["corner-analysis", classification],
    queryFn: () =>
      api.cornerAnalysis({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        classification: classification === "전체" ? undefined : classification,
      }),
  });

  const option = {
    tooltip: { trigger: "axis" },
    legend: { data: ["누적 식수", "평균 만족도(5점)"] },
    xAxis: { type: "category", data: query.data?.map((c) => c.corner_name) ?? [] },
    yAxis: [
      { type: "value", name: "식수" },
      { type: "value", name: "만족도", min: 0, max: 5 },
    ],
    series: [
      { name: "누적 식수", type: "bar", data: query.data?.map((c) => c.headcount_total) ?? [] },
      {
        name: "평균 만족도(5점)",
        type: "line",
        yAxisIndex: 1,
        data: query.data?.map((c) => c.avg_taste_score) ?? [],
      },
    ],
  };

  return (
    <Card title="코너별 분석 — 이용자 수 / 만족도 / 피크타임 서브속도 (PRD 6.2)">
      <div className="mb-3">
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
        <p className="text-sm text-slate-400">데이터가 없습니다. 배치 집계(daily_corner_stats)가 먼저 필요합니다.</p>
      )}
      {query.data && query.data.length > 0 && (
        <>
          <ReactECharts option={option} style={{ height: 300 }} />
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 pr-4">코너</th>
                <th className="py-1 pr-4">그린미트</th>
                <th className="py-1 pr-4">누적 식수</th>
                <th className="py-1 pr-4">평균 만족도</th>
                <th className="py-1 pr-4">피크타임 분당 서브</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((c) => (
                <tr key={c.corner_id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-4">{c.corner_name}</td>
                  <td className="py-1.5 pr-4">{c.is_diet_corner ? "예" : "-"}</td>
                  <td className="py-1.5 pr-4">{c.headcount_total.toLocaleString()}</td>
                  <td className="py-1.5 pr-4">{c.avg_taste_score?.toFixed(2) ?? "-"}</td>
                  <td className="py-1.5 pr-4">{c.avg_peak_throughput_per_min?.toFixed(1) ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}

function MenuQuadrantTab() {
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
    itemStyle: { color: quadrantColor(r.quadrant) },
  }));

  const option = {
    tooltip: {
      formatter: (p: { data: { name: string; value: number[] } }) =>
        `${p.data.name}<br/>1회 제공당 식수: ${p.data.value[0].toFixed(1)}<br/>만족도: ${p.data.value[1].toFixed(2)}`,
    },
    xAxis: { type: "value", name: "수요 (1회 제공당 평균 식수)" },
    yAxis: { type: "value", name: "만족도(표본보정, 5점)", min: 0, max: 5 },
    series: [
      {
        type: "scatter",
        symbolSize: 14,
        data: scatterData,
        markLine: {
          silent: true,
          lineStyle: { type: "dashed", color: "#94a3b8" },
          data: [{ xAxis: demandThreshold }, { yAxis: scoreThreshold }],
        },
      },
    ],
  };

  return (
    <Card title="메뉴 4분면 — 인기메뉴 / 숨은강자 / 개선시급 / 퇴출후보 (PRD 6.3.4)">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex gap-3 text-xs text-slate-400">
          <span>🟢 인기메뉴</span>
          <span>🔵 숨은강자</span>
          <span>🟠 개선시급</span>
          <span>🔴 퇴출후보</span>
          <span>⚪ 표본부족</span>
        </div>
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
        <p className="text-sm text-slate-400">
          데이터가 없습니다. 먼저 "재계산" 버튼으로 menu_performance_stats를 생성하세요.
        </p>
      )}
      {rows.length > 0 && <ReactECharts option={option} style={{ height: 380 }} />}
      {rows.length > 0 && (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1 pr-4">메뉴</th>
              <th className="py-1 pr-4">등장횟수</th>
              <th className="py-1 pr-4">평가건수</th>
              <th className="py-1 pr-4">만족도</th>
              <th className="py-1 pr-4">4분면</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: MenuPerformanceRow) => (
              <tr key={r.menu_id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1.5 pr-4">{r.menu_name}</td>
                <td className="py-1.5 pr-4">{r.appearance_count}</td>
                <td className="py-1.5 pr-4">{r.evaluation_count}</td>
                <td className="py-1.5 pr-4">{r.adjusted_score?.toFixed(2) ?? "-"}</td>
                <td className="py-1.5 pr-4">
                  <QuadrantBadge label={r.quadrant} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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

function quadrantColor(label: string | null): string {
  switch (label) {
    case "인기메뉴":
      return "#10b981";
    case "숨은강자":
      return "#0ea5e9";
    case "개선시급":
      return "#f59e0b";
    case "퇴출후보":
      return "#f43f5e";
    default:
      return "#94a3b8";
  }
}

export function AnalysisPage() {
  const [tab, setTab] = useState<SubTab>("menus");
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(
          [
            ["menus", "메뉴 4분면"],
            ["corners", "코너별 분석"],
            ["users", "사용자 분석"],
          ] as [SubTab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={
              "rounded-lg px-3 py-1.5 text-sm font-medium " +
              (tab === value
                ? "bg-indigo-600 text-white"
                : "border border-slate-200 text-slate-500 dark:border-slate-700")
            }
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "menus" && <MenuQuadrantTab />}
      {tab === "corners" && <CornerAnalysisTab />}
      {tab === "users" && <UserAnalysisTab />}
    </div>
  );
}
