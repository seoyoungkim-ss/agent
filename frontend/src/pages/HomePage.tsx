import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type Classification } from "../api/client";
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

const CLASSIFICATION_OPTIONS: { label: string; value: Classification | "전체" }[] = [
  { label: "전체", value: "전체" },
  { label: "평일", value: "평일" },
  { label: "주말+공휴일", value: "주말+공휴일" },
];

export function HomePage() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const [exportStart, setExportStart] = useState(isoDaysAgo(30));
  const [exportEnd, setExportEnd] = useState(isoDaysAgo(0));
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
  const chartTheme = useChartTheme();
  const seriesWeekday = resolveColor("var(--series-1)");
  const seriesHoliday = resolveColor("var(--series-2)");

  const chartOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: weekly.data?.map((d) => d.date.slice(5)) ?? [],
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
    series: [
      {
        type: "bar",
        barMaxWidth: 28,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (params: { dataIndex: number }) => {
            const d = weekly.data?.[params.dataIndex];
            return d?.classification === "주말+공휴일" ? seriesHoliday : seriesWeekday;
          },
        },
        data: weekly.data?.map((d) => d.headcount) ?? [],
      },
    ],
  };

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${startDate}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }`;

  const mealLogExportUrl = `/api/dashboard/meal-log/export?period_start=${exportStart}&period_end=${exportEnd}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">이번 주 카페테리아 현황</h1>
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
          sub={classification === "전체" ? "평일 + 주말+공휴일" : classification}
        />
        <StatTile label="이번 달 VOE 클러스터 수" value={voe.data?.length ?? 0} />
      </div>

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
        {weekly.data && <ReactECharts option={chartOption} style={{ height: 280 }} />}
        {weekly.data && weekly.data.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <Table
              columns={[
                { key: "date", label: "날짜" },
                { key: "classification", label: "구분" },
                { key: "headcount", label: "식수", align: "right" },
              ]}
              rows={weekly.data.map((d) => ({
                date: d.date,
                classification: d.classification,
                headcount: d.headcount.toLocaleString(),
              }))}
              rowKey={(r) => r.date as string}
            />
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

      <Card title="월간 VOE 클러스터 (사내 LLM 기반)">
        {voe.isLoading && <LoadingState />}
        {voe.isError && <ErrorState error={voe.error} />}
        {voe.data && voe.data.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이번 달 클러스터링 결과가 없습니다. 사내 LLM 연동 후 배치(매월 1일)가 실행되면 표시됩니다.
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {voe.data?.map((c) => (
            <div key={c.cluster_label} className="rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-medium">{c.cluster_label}</span>
                <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  {c.comment_count}건
                </span>
              </div>
              <p className="mt-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
                {c.representative_comment}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.keywords.map((k) => (
                  <span
                    key={k}
                    className="rounded px-1.5 py-0.5 text-xs"
                    style={{ background: "var(--surface-2)", color: "var(--ink-secondary)" }}
                  >
                    {k}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
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
