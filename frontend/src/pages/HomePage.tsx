import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
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

export function HomePage() {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const [exportStart, setExportStart] = useState(isoDaysAgo(30));
  const [exportEnd, setExportEnd] = useState(isoDaysAgo(0));
  const [selectedMonday, setSelectedMonday] = useState(mondayOf(new Date()));
  const [selectedVoeCategory, setSelectedVoeCategory] = useState<string | null>(null);
  const sundayOfSelected = addDays(selectedMonday, 6);

  const weekly = useQuery({
    queryKey: ["weekly-summary", selectedMonday, classification],
    queryFn: () =>
      api.weeklySummary({
        start_date: selectedMonday,
        classification: classification === "전체" ? undefined : classification,
      }),
  });

  const menuHistory = useQuery({
    queryKey: ["menu-history", searchedMenu],
    queryFn: () => api.menuHistory(searchedMenu as string),
    enabled: !!searchedMenu,
  });

  const voeCategory = useQuery({
    queryKey: ["voe-by-category", selectedMonday.slice(0, 7)],
    queryFn: () => api.voeByCategory(`${selectedMonday.slice(0, 7)}-01`),
  });

  const cornerSummary = useQuery({
    queryKey: ["corner-summary", selectedMonday, sundayOfSelected],
    queryFn: () => api.cornerAnalysis({ period_start: selectedMonday, period_end: sundayOfSelected }),
  });

  const recomputeDailyStats = useMutation({
    mutationFn: () =>
      api.recomputeDailyStats({ period_start: RECOMPUTE_PERIOD_START, period_end: RECOMPUTE_PERIOD_END }),
    onSuccess: () => {
      weekly.refetch();
      cornerSummary.refetch();
    },
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

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${selectedMonday}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }`;

  const mealLogExportUrl = `/api/dashboard/meal-log/export?period_start=${exportStart}&period_end=${exportEnd}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">카페테리아 현황</h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {selectedMonday} ~ {sundayOfSelected}
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="선택한 주 누적 식수" value={totalHeadcount.toLocaleString()} />
        <StatTile
          label="집계 대상 일수"
          value={weekly.data?.length ?? 0}
          sub={classification === "전체" ? "평일 + 주말+공휴일" : classification}
        />
        <StatTile label="선택한 달 VOE 코멘트 수" value={voeCategory.data?.total_comments ?? 0} />
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

      <Card title="월간 VOE 분류 (맛·간·위생·서비스)">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          카테고리를 클릭하면 해당 분류의 코멘트를 볼 수 있습니다. 한 코멘트가 여러 분류에 동시에 잡힐 수 있습니다.
        </p>
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

      <Card title="코너별 식수 (선택한 주)">
        {cornerSummary.isLoading && <LoadingState />}
        {cornerSummary.isError && <ErrorState error={cornerSummary.error} />}
        {cornerSummary.data && cornerSummary.data.length === 0 && (
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
        {cornerSummary.data && cornerSummary.data.length > 0 && (
          <Table
            columns={[
              { key: "corner", label: "코너" },
              { key: "headcount", label: "식수", align: "right" },
            ]}
            rows={cornerSummary.data.map((c) => ({
              corner: c.corner_name,
              headcount: c.headcount_total.toLocaleString(),
            }))}
            rowKey={(r) => r.corner as string}
          />
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
