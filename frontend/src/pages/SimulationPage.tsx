import { useState, type CSSProperties } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type MealType, type Weather, type WhatIfResponse } from "../api/client";
import { Button, Card, ErrorState, Legend, LoadingState, Table, resolveColor, useChartTheme } from "../components/ui";

const WEATHER_OPTIONS: Weather[] = ["맑음", "비", "폭염", "한파"];
const MEAL_TYPE_OPTIONS: MealType[] = ["조식", "중식", "석식"];

const inputStyle: CSSProperties = { borderColor: "var(--border)", background: "var(--surface)" };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SimulationPage() {
  const [targetDate, setTargetDate] = useState(todayIso());
  const [mealType, setMealType] = useState<MealType>("중식");
  const [weather, setWeather] = useState<Weather>("맑음");
  const [hasEvent, setHasEvent] = useState(false);
  const [result, setResult] = useState<WhatIfResponse | null>(null);

  const whatIf = useMutation({
    mutationFn: () =>
      api.whatIf({
        target_date: targetDate,
        meal_type: mealType,
        weather,
        has_company_event: hasEvent,
      }),
    onSuccess: setResult,
  });

  const forecast = useQuery({
    queryKey: ["congestion-forecast", targetDate, mealType],
    queryFn: () => api.congestionForecast({ target_date: targetDate, meal_type: mealType }),
  });

  const chartTheme = useChartTheme();
  const baselineColor = resolveColor("var(--chart-axis)");
  const predictedColor = resolveColor("var(--series-1)");

  const whatIfOption = result && {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: result.corners.map((c) => c.corner_name),
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
        name: "평소(baseline)",
        type: "bar",
        barMaxWidth: 24,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: baselineColor },
        data: result.corners.map((c) => c.baseline_headcount),
      },
      {
        name: "시뮬레이션 예측",
        type: "bar",
        barMaxWidth: 24,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: predictedColor },
        data: result.corners.map((c) => c.predicted_headcount),
      },
    ],
  };

  return (
    <div className="space-y-6">
      <Card title="조건부 메뉴 시뮬레이션 — 날씨 / 신메뉴 / 사내 행사">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            날짜
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="rounded-md border px-3 py-2"
              style={inputStyle}
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            식사구분
            <select
              value={mealType}
              onChange={(e) => setMealType(e.target.value as MealType)}
              className="rounded-md border px-3 py-2"
              style={inputStyle}
            >
              {MEAL_TYPE_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            날씨
            <select
              value={weather}
              onChange={(e) => setWeather(e.target.value as Weather)}
              className="rounded-md border px-3 py-2"
              style={inputStyle}
            >
              {WEATHER_OPTIONS.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            <input type="checkbox" checked={hasEvent} onChange={(e) => setHasEvent(e.target.checked)} />
            사내 행사 있음
          </label>
          <Button onClick={() => whatIf.mutate()} disabled={whatIf.isPending}>
            시뮬레이션 실행
          </Button>
        </div>

        {whatIf.isPending && <LoadingState label="시뮬레이션 계산 중" />}
        {whatIf.isError && <ErrorState error={whatIf.error} />}
        {result && (
          <>
            <div className="mb-2">
              <Legend
                items={[
                  { label: "평소(baseline)", color: "var(--chart-axis)" },
                  { label: "시뮬레이션 예측", color: "var(--series-1)" },
                ]}
              />
            </div>
            <ReactECharts option={whatIfOption} style={{ height: 280 }} />
            <p className="mt-2 text-xs" style={{ color: "var(--ink-muted)" }}>
              {result.note}
            </p>
          </>
        )}
      </Card>

      <Card title="코너별 혼잡도 예측">
        {forecast.isLoading && <LoadingState />}
        {forecast.isError && <ErrorState error={forecast.error} />}
        {forecast.data && (
          <Table
            columns={[
              { key: "corner", label: "코너" },
              { key: "headcount", label: "예상 식수", align: "right" },
              { key: "throughput", label: "평균 서브속도(분당)", align: "right" },
              { key: "wait", label: "예상 대기시간(분)", align: "right" },
            ]}
            rows={forecast.data.corners.map((c) => ({
              corner: c.corner_name,
              headcount:
                c.menu_popularity_multiplier != null ? (
                  <span>
                    {c.predicted_headcount}
                    <span className="ml-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                      (계획 메뉴 반영 ×{c.menu_popularity_multiplier.toFixed(2)})
                    </span>
                  </span>
                ) : (
                  c.predicted_headcount
                ),
              throughput: c.avg_peak_throughput_per_min?.toFixed(2) ?? "-",
              wait:
                c.expected_wait_minutes != null ? (
                  <span style={c.expected_wait_minutes > 15 ? { color: "var(--critical)", fontWeight: 600 } : undefined}>
                    {c.expected_wait_minutes}
                  </span>
                ) : (
                  "-"
                ),
            }))}
            rowKey={(r) => r.corner as string}
          />
        )}
        <p className="mt-3 text-xs" style={{ color: "var(--ink-muted)" }}>
          혼잡이 예상되는 코너는 위 조건부 시뮬레이션에서 다른 코너에 신메뉴를 배치해보며 분산 효과를 비교하세요.
        </p>
      </Card>
    </div>
  );
}
