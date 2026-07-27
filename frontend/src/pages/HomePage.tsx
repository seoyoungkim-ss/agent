import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type Classification } from "../api/client";
import { Button, Card, ErrorState, LoadingState, QuadrantBadge, SegmentedControl, StatTile } from "../components/ui";

function mondayOf(date: Date): string {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // 월=0 ... 일=6
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

const CLASSIFICATION_OPTIONS: { label: string; value: Classification | "전체" }[] = [
  { label: "전체", value: "전체" },
  { label: "평일", value: "평일" },
  { label: "주말+공휴일", value: "주말+공휴일" },
];

export function HomePage() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const startDate = mondayOf(new Date());

  const weekly = useQuery({
    queryKey: ["weekly-summary", startDate, classification],
    queryFn: () =>
      api.weeklySummary({
        start_date: startDate,
        classification: classification === "전체" ? undefined : classification,
      }),
  });

  const menuHistory = useQuery({
    queryKey: ["menu-history", searchedMenu],
    queryFn: () => api.menuHistory(searchedMenu as string),
    enabled: !!searchedMenu,
  });

  const voe = useQuery({
    queryKey: ["voe-clusters", startDate.slice(0, 7)],
    queryFn: () => api.voeClusters(`${startDate.slice(0, 7)}-01`),
  });

  const totalHeadcount = weekly.data?.reduce((sum, d) => sum + d.headcount, 0) ?? 0;

  const chartOption = {
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: weekly.data?.map((d) => d.date) ?? [] },
    yAxis: { type: "value", name: "식수" },
    series: [
      {
        type: "bar",
        data: weekly.data?.map((d) => ({
          value: d.headcount,
          itemStyle: { color: d.classification === "주말+공휴일" ? "#f59e0b" : "#6366f1" },
        })) ?? [],
      },
    ],
  };

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${startDate}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold">이번 주 카페테리아 현황</h1>
        <div className="flex items-center gap-3">
          <SegmentedControl value={classification} options={CLASSIFICATION_OPTIONS} onChange={setClassification} />
          <a href={exportUrl} download>
            <Button variant="secondary">엑셀 다운로드</Button>
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="이번 주 누적 식수" value={totalHeadcount.toLocaleString()} />
        <StatTile
          label="집계 대상 일수"
          value={weekly.data?.length ?? 0}
          sub={classification === "전체" ? "평일+주말+공휴일" : classification}
        />
        <StatTile label="이번 달 VOE 클러스터 수" value={voe.data?.length ?? 0} />
      </div>

      <Card title="주간 식수 추이 (평일/주말+공휴일 색상 구분)">
        {weekly.isLoading && <LoadingState />}
        {weekly.isError && <ErrorState error={weekly.error} />}
        {weekly.data && <ReactECharts option={chartOption} style={{ height: 320 }} />}
      </Card>

      <Card title="이번 주 메뉴 이력 검색 (과거 만족도/코멘트)">
        <div className="mb-3 flex gap-2">
          <input
            className="w-64 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800"
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
          <p className="text-sm text-slate-400">이력이 없습니다 (recompute가 필요할 수 있습니다).</p>
        )}
        {menuHistory.data && menuHistory.data.length > 0 && (
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 pr-4">기간</th>
                <th className="py-1 pr-4">만족도(표본보정)</th>
                <th className="py-1 pr-4">평가건수</th>
                <th className="py-1 pr-4">4분면</th>
              </tr>
            </thead>
            <tbody>
              {menuHistory.data.map((h) => (
                <tr key={h.period_start} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-4">
                    {h.period_start} ~ {h.period_end}
                  </td>
                  <td className="py-1.5 pr-4">{h.adjusted_score?.toFixed(2) ?? "-"}</td>
                  <td className="py-1.5 pr-4">{h.evaluation_count}</td>
                  <td className="py-1.5 pr-4">
                    <QuadrantBadge label={h.quadrant} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="월간 VOE 클러스터 (사내 LLM 기반)">
        {voe.isLoading && <LoadingState />}
        {voe.isError && <ErrorState error={voe.error} />}
        {voe.data && voe.data.length === 0 && (
          <p className="text-sm text-slate-400">
            이번 달 클러스터링 결과가 없습니다. 사내 LLM 연동 후 배치(매월 1일)가 실행되면 표시됩니다.
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {voe.data?.map((c) => (
            <div key={c.cluster_label} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{c.cluster_label}</span>
                <span className="text-xs text-slate-400">{c.comment_count}건</span>
              </div>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{c.representative_comment}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.keywords.map((k) => (
                  <span
                    key={k}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                  >
                    #{k}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
