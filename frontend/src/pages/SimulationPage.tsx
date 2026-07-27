import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api, type MealType, type Weather, type WhatIfResponse } from "../api/client";
import { Button, Card, ErrorState, LoadingState } from "../components/ui";

const WEATHER_OPTIONS: Weather[] = ["맑음", "비", "폭염", "한파"];
const MEAL_TYPE_OPTIONS: MealType[] = ["조식", "중식", "석식"];

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

  const whatIfOption = result && {
    tooltip: { trigger: "axis" },
    legend: { data: ["평소(baseline)", "시뮬레이션 예측"] },
    xAxis: { type: "category", data: result.corners.map((c) => c.corner_name) },
    yAxis: { type: "value", name: "식수" },
    series: [
      { name: "평소(baseline)", type: "bar", data: result.corners.map((c) => c.baseline_headcount) },
      { name: "시뮬레이션 예측", type: "bar", data: result.corners.map((c) => c.predicted_headcount) },
    ],
  };

  return (
    <div className="space-y-6">
      <Card title="조건부 메뉴 시뮬레이션 (PRD 7.1) — 날씨 / 신메뉴 / 사내 행사">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-sm">
            날짜
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            />
          </label>
          <label className="flex flex-col text-sm">
            식사구분
            <select
              value={mealType}
              onChange={(e) => setMealType(e.target.value as MealType)}
              className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            >
              {MEAL_TYPE_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-sm">
            날씨
            <select
              value={weather}
              onChange={(e) => setWeather(e.target.value as Weather)}
              className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
            >
              {WEATHER_OPTIONS.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={hasEvent} onChange={(e) => setHasEvent(e.target.checked)} />
            사내 행사 있음
          </label>
          <Button onClick={() => whatIf.mutate()} disabled={whatIf.isPending}>
            시뮬레이션 실행
          </Button>
        </div>

        {whatIf.isPending && <LoadingState label="시뮬레이션 계산 중..." />}
        {whatIf.isError && <ErrorState error={whatIf.error} />}
        {result && (
          <>
            <ReactECharts option={whatIfOption} style={{ height: 320 }} />
            <p className="mt-2 text-xs text-slate-400">{result.note}</p>
          </>
        )}
      </Card>

      <Card title="코너별 혼잡도 예측 (PRD 7.2)">
        {forecast.isLoading && <LoadingState />}
        {forecast.isError && <ErrorState error={forecast.error} />}
        {forecast.data && (
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 pr-4">코너</th>
                <th className="py-1 pr-4">예상 식수</th>
                <th className="py-1 pr-4">평균 서브속도(분당)</th>
                <th className="py-1 pr-4">예상 대기시간(분)</th>
              </tr>
            </thead>
            <tbody>
              {forecast.data.corners.map((c) => (
                <tr key={c.corner_id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-4">{c.corner_name}</td>
                  <td className="py-1.5 pr-4">{c.predicted_headcount}</td>
                  <td className="py-1.5 pr-4">{c.avg_peak_throughput_per_min?.toFixed(1) ?? "-"}</td>
                  <td className="py-1.5 pr-4">
                    {c.expected_wait_minutes != null ? (
                      <span className={c.expected_wait_minutes > 15 ? "font-semibold text-rose-500" : ""}>
                        {c.expected_wait_minutes}
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-xs text-slate-400">
          혼잡이 예상되는 코너는 위 조건부 시뮬레이션에서 다른 코너에 신메뉴를 배치해보며 분산 효과를 비교하세요.
        </p>
      </Card>
    </div>
  );
}
