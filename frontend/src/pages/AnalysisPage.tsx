import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import clsx from "clsx";
import {
  api,
  type Classification,
  type CornerAnalysisRow,
  type DailyMenuPlanRuleResult,
  type MealType,
  type MenuFoodVectorRow,
  type MenuPerformanceRow,
  type MenuRotationRow,
  type PredictedNumbersRow,
  type Season,
  type TrendDirection,
  type Weather,
  type WeatherCorrelationMetric,
  type WeatherEvent,
  type WeeklyMenuPlanItem,
  type WeeklyMenuSlot,
} from "../api/client";
import {
  Badge,
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

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const PERIOD_END = isoDaysAgo(0);
const PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준

// §83: 메뉴 중복 점검(재편성 간격 / 부찬 반복)은 6개월 전체보다 최근 한 달이
// 기본으로 더 유용하다는 피드백 — 이 두 패널만 30일 기본 기간을 쓴다.
const DUPLICATION_CHECK_PERIOD_START = isoDaysAgo(30);
const DUPLICATION_CHECK_PERIOD_END = isoDaysAgo(0);

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


// 코너별 지표 비교 — 2026-08 화면 재편으로 "분석 > 코너별" 탭이 사라지면서
// 현황(HomePage)으로 옮겼다. 그래서 탭이 아니라 export되는 섹션 컴포넌트다.
// §85: 추이 그래프(지표 선택형 듀얼축)는 지우고 표만 남긴다 — 컬럼별 정렬 가능.
export function CornerMetricComparisonSection() {
  // §86: 주말에 운영 안 하는 코너가 있어 "평일 기준"이 기본이 더 유용하다는
  // 피드백 — 기본값만 평일로 바꾸고, 다른 분류도 SegmentedControl로 볼 수 있게
  // 그대로 둔다.
  const [classification, setClassification] = useState<Classification | "전체">("평일");
  const [sortKey, setSortKey] = useState<"corner" | "headcount" | "score" | "throughput">("headcount");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  function toggleSort(key: typeof sortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }
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

  // §86: "누적 식수" 대신 "이 코너가 평일 페이스를 유지한다면 한 주에 낼
  // 식수" 추정치(평일 하루 평균 × 5)를 보여준다 — day_count는 조회 기간·
  // classification 필터가 이미 적용된 뒤의 실제 통계 일수다.
  const weeklyAvg = (row: CornerAnalysisRow) =>
    row.day_count > 0 ? Math.round((row.headcount_total / row.day_count) * 5) : null;

  const sortedCornerRows = [...(query.data ?? [])].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    if (sortKey === "corner") return a.corner_name.localeCompare(b.corner_name) * dir;
    const metricValue = (row: typeof a) =>
      sortKey === "headcount"
        ? (weeklyAvg(row) ?? -Infinity)
        : sortKey === "score"
          ? (row.avg_taste_score ?? -Infinity)
          : (row.avg_peak_throughput_per_min ?? -Infinity);
    return (metricValue(a) - metricValue(b)) * dir;
  });

  return (
    <div className="space-y-6">
      <Card title="코너별 분석 — 지표 비교 (식수 / 만족도 / 피크타임 서브속도)">
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
              이 기간 데이터가 없습니다 — 배치 집계가 안 됐을 수 있어요.
            </p>
            <Button variant="secondary" onClick={() => recomputeDailyStats.mutate()} disabled={recomputeDailyStats.isPending}>
              {recomputeDailyStats.isPending ? "계산 중..." : "최근 180일 배치 집계 재계산"}
            </Button>
            {recomputeDailyStats.isError && <ErrorState error={recomputeDailyStats.error} />}
          </div>
        )}
        {query.data && query.data.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-[13px]" style={{ color: "var(--ink)" }}>
              <thead>
                <tr>
                  <SortableHeader
                    label="코너"
                    active={sortKey === "corner"}
                    dir={sortDir}
                    onClick={() => toggleSort("corner")}
                  />
                  <SortableHeader
                    label="주간 평균 식수"
                    active={sortKey === "headcount"}
                    dir={sortDir}
                    align="right"
                    onClick={() => toggleSort("headcount")}
                  />
                  <SortableHeader
                    label="평균 만족도"
                    active={sortKey === "score"}
                    dir={sortDir}
                    align="right"
                    onClick={() => toggleSort("score")}
                  />
                  <SortableHeader
                    label="피크타임 분당 서브"
                    active={sortKey === "throughput"}
                    dir={sortDir}
                    align="right"
                    onClick={() => toggleSort("throughput")}
                  />
                </tr>
              </thead>
              <tbody>
                {sortedCornerRows.map((c) => (
                  <tr key={c.corner_name} className="border-b" style={{ borderColor: "var(--border)" }}>
                    <td className="py-2 pr-4">{c.corner_name}</td>
                    <td className="py-2 pr-4 text-right">{weeklyAvg(c)?.toLocaleString() ?? "-"}</td>
                    <td className="py-2 pr-4 text-right">{c.avg_taste_score?.toFixed(2) ?? "-"}</td>
                    <td className="py-2 pr-4 text-right">{c.avg_peak_throughput_per_min?.toFixed(2) ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
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
          className="rounded-xl border p-3 text-left transition-colors"
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

// 하나의 통합 산점도로 전체 메뉴를 한눈에 본다(2026-08, 사용자 결정: "한눈에
// 보고 싶은 게 더 큼" — 분면별 패널 분리(2026-07, 42.2/42.4)보다 한 화면에서
// 전체 분포를 보는 걸 우선). X축=만족도, Y축=수요(2026-08, 스펙 요청대로 축
// 반전 — 이전엔 X=수요/Y=만족도였다). 겹침 완화는 패널 분리 대신 이후 라운드에
// 추가된 labelLayout.hideOverlap(43번 라운드, 세로로 먼저 밀어보고 그래도
// 겹치면 숨김)에 의존한다 — 분면(색)별로 시리즈를 나눠 기존 범례 토글(화면
// 상단 분면 필터)이 그대로 동작하게 하고, 배경에 사분면 음영(markArea)과
// 기준값 십자선(markLine)을 별도의 빈 시리즈로 얹어 어느 분면인지 즉시 보이게
// 한다. 배경 음영은 순수 수요/만족도 임계값 기준이라, 만족도 추세 하락·로열티
// 등으로 실제 분류가 임계값과 다르게 override된 점은 점 색(진짜 분류)과 배경
// 음영(단순 임계값)이 어긋나 보일 수 있다 — 그 자체가 "왜 이 위치인데 이
// 분류지?"를 알아챌 수 있는 신호이므로 툴팁에 추세/로열티를 표기해 설명한다.
function buildUnifiedQuadrantOption(
  quadrantRows: Map<string, MenuQuadrantMetrics[]>,
  visibleLabels: readonly string[],
  quadrantLimitN: number,
  demandThreshold: number,
  scoreThreshold: number,
  maxDemand: number,
  chartTheme: ReturnType<typeof useChartTheme>,
) {
  const REAL_QUADRANTS = ["인기메뉴", "개선시급", "숨은강자", "퇴출후보"];

  function buildSeriesData(items: MenuQuadrantMetrics[]) {
    const ordered = [...items].sort((a, b) => b.appearance_count - a.appearance_count).slice(0, quadrantLimitN);
    const maxAppearance = Math.max(1, ...ordered.map((r) => r.appearance_count));
    return ordered.map((r) => {
      const isLowAppearance = r.appearance_count < LOW_APPEARANCE_THRESHOLD;
      const label = r.corner_name ? `${r.menu_name} (${r.corner_name})` : r.menu_name;
      return {
        name: label,
        value: [r.satisfaction, r.demand, r.appearance_count],
        satisfactionTrend: r.satisfaction_trend,
        hasLoyalFollowing: r.has_loyal_following,
        symbolSize: 8 + Math.sqrt(r.appearance_count / maxAppearance) * 22,
        itemStyle: {
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
  }

  const quadrantSeries = QUADRANT_LABELS.filter((label) => visibleLabels.includes(label)).map((label) => ({
    name: label,
    type: "scatter" as const,
    itemStyle: { color: resolveColor(quadrantColor(label)) },
    data: buildSeriesData(quadrantRows.get(label) ?? []),
    labelLayout: { moveOverlap: "shiftY" as const, hideOverlap: true },
  }));

  const backgroundSeries = {
    name: "__background",
    type: "scatter" as const,
    data: [] as unknown[],
    silent: true,
    tooltip: { show: false },
    markArea: {
      silent: true,
      label: { color: chartTheme.text, fontSize: 12, fontWeight: 600 as const },
      data: REAL_QUADRANTS.map((label) => {
        const isHighSatisfaction = label === "인기메뉴" || label === "숨은강자";
        const isHighDemand = label === "인기메뉴" || label === "개선시급";
        return [
          {
            name: label,
            xAxis: isHighSatisfaction ? scoreThreshold : 0,
            yAxis: isHighDemand ? demandThreshold : 0,
            itemStyle: { color: resolveColor(quadrantColor(label)), opacity: 0.06 },
          },
          {
            xAxis: isHighSatisfaction ? 5 : scoreThreshold,
            yAxis: isHighDemand ? maxDemand : demandThreshold,
          },
        ];
      }),
    },
    markLine: {
      silent: true,
      symbol: "none" as const,
      label: { show: false },
      lineStyle: { type: "dashed" as const, color: chartTheme.axis },
      data: [{ xAxis: scoreThreshold }, { yAxis: demandThreshold }],
    },
  };

  return {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 24, top: 16, bottom: 40 },
    tooltip: {
      formatter: (p: {
        seriesName?: string;
        data: {
          name: string;
          value: number[];
          satisfactionTrend: TrendDirection | null;
          hasLoyalFollowing: boolean;
        };
      }) => {
        const lines = [
          p.data.name,
          `분류: ${p.seriesName}`,
          `만족도: ${p.data.value[0].toFixed(2)}`,
          `수요: ${p.data.value[1].toFixed(2)}`,
          `제공 횟수: ${p.data.value[2]}회`,
        ];
        if (p.data.satisfactionTrend === "하락") lines.push("만족도 추세: 하락");
        if (p.data.hasLoyalFollowing) lines.push("고정 고객 있음");
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      name: "만족도",
      min: 0,
      max: 5,
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "value",
      name: "수요(1회 제공당 평균 식수)",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    series: [backgroundSeries, ...quadrantSeries],
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
        가로축 만족도 × 세로축 수요 기준값(중앙값, 슬라이더로 조절 가능)으로 4분류합니다.
        흐린 점은 최근 {LOW_APPEARANCE_THRESHOLD}회 미만 제공이라 수치가 불안정할 수 있습니다.
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
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-3 text-xs" style={{ color: "var(--ink-muted)" }}>
            {visibleQuadrantLabels.map((label) => {
              const total = quadrantRows.get(label)?.length ?? 0;
              const shown = Math.min(total, quadrantLimitN);
              return (
                <span key={label} className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: resolveColor(quadrantColor(label)) }}
                  />
                  {label} {total}개 중 {shown}개 표시
                </span>
              );
            })}
          </div>
          {visibleQuadrantLabels.every((label) => (quadrantRows.get(label)?.length ?? 0) === 0) ? (
            <p className="py-6 text-center text-[13px]" style={{ color: "var(--ink-muted)" }}>
              해당 없음
            </p>
          ) : (
            <ReactECharts
              option={buildUnifiedQuadrantOption(
                quadrantRows,
                visibleQuadrantLabels,
                quadrantLimitN,
                demandThreshold,
                scoreThreshold,
                maxDemand,
                chartTheme,
              )}
              style={{ height: 560 }}
            />
          )}
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
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
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
  const extractIngredients = useMutation({ mutationFn: () => api.extractIngredientsWithLlm() });

  const rows = query.data ?? [];
  const cornerGroups = groupByCorner(rows);

  return (
    <Card title="메뉴 음식벡터 관리 (개인 취향 벡터 계산의 기초 데이터)">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        신메뉴는 자동 태깅되고, 직접 조정하면 "관리자수동"으로 표시돼 재태깅에서 제외됩니다.
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
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => tagWithLlm.mutate()} disabled={tagWithLlm.isPending}>
            LLM으로 미태깅 메뉴 보강
          </Button>
          <Button
            variant="secondary"
            onClick={() => extractIngredients.mutate()}
            disabled={extractIngredients.isPending}
          >
            LLM으로 식재료 추출
          </Button>
        </div>
      </div>
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        "한 끼 구성 중복 점검"이 쓰는 값입니다. 매일 자동으로 채워지며, 방금 올린 식단표를 바로 반영하고 싶을 때만 누르세요.
      </p>
      {tagWithLlm.data && (
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          {tagWithLlm.data.tagged_menus}건 태깅됨
        </p>
      )}
      {extractIngredients.data && (
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          식재료 {extractIngredients.data.updated}건 추출됨
        </p>
      )}
      {tagWithLlm.isError && <ErrorState error={tagWithLlm.error} />}
      {extractIngredients.isError && <ErrorState error={extractIngredients.error} />}
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

/** 두 조합의 차이 — 어느 부찬이 빠지고 들어갔는지. 순수 함수라 테스트가 쉽다. */
function diffSides(best: (string | null)[], worst: (string | null)[]) {
  const b = new Set(best.filter(Boolean) as string[]);
  const w = new Set(worst.filter(Boolean) as string[]);
  return {
    onlyBest: [...b].filter((x) => !w.has(x)),
    onlyWorst: [...w].filter((x) => !b.has(x)),
    common: [...b].filter((x) => w.has(x)),
  };
}

/**
 * 조합을 칩으로 렌더링하되 **한쪽에만 있는 부찬을 음영으로 강조**한다
 * (2026-08 요청: "좋았던 조합과 나빴던 조합에서 변화된 부분을 눈에 띄게").
 * 텍스트만 나열하면 부찬이 3~4개일 때 뭐가 달라졌는지 눈으로 못 찾는다.
 */
function ComboChips({
  sides,
  highlight,
  tone,
}: {
  sides: (string | null)[];
  highlight: string[];
  tone: "good" | "critical";
}) {
  const names = sides.filter(Boolean) as string[];
  if (names.length === 0) {
    return (
      <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
        부찬 없음
      </span>
    );
  }
  const highlightSet = new Set(highlight);
  return (
    <span className="flex flex-wrap gap-1">
      {names.map((name) => {
        const isDiff = highlightSet.has(name);
        return (
          <span
            key={name}
            className="rounded px-1.5 py-0.5 text-xs"
            style={
              isDiff
                ? {
                    background: `color-mix(in srgb, var(--${tone}) 18%, transparent)`,
                    color: `var(--${tone})`,
                    fontWeight: 600,
                  }
                : { color: "var(--ink-muted)" }
            }
          >
            {name}
          </span>
        );
      })}
    </span>
  );
}

function MenuComboSection() {
  const [menuName, setMenuName] = useState("");
  const [searched, setSearched] = useState<string | null>(null);
  // 같은 메인이 여러 코너에서 다른 부찬과 나오면 조합이 섞여 비교가 흐려진다
  // → 코너로 좁혀 볼 수 있게 한다(2026-08 요청).
  const [comboCornerId, setComboCornerId] = useState<number | null>(null);
  const cornersQuery = useQuery({ queryKey: ["corner-list"], queryFn: () => api.cornerList() });
  // 검색해야만 보이면 "뭘 검색할지"부터 막힌다는 피드백(2026-08) → 조합에 따라
  // 만족도 편차가 큰 메인메뉴를 먼저 띄운다. 편차가 크다 = 부찬을 바꾸면
  // 만족도가 실제로 움직인다 = 손볼 가치가 있다.
  const rankingQuery = useQuery({
    queryKey: ["menu-combination-spread-ranking", comboCornerId],
    queryFn: () =>
      api.menuCombinationSpreadRanking({
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        ...(comboCornerId != null ? { corner_id: comboCornerId } : {}),
      }),
  });
  const query = useQuery({
    queryKey: ["menu-combinations", searched, comboCornerId],
    queryFn: () =>
      api.menuSideCombinations(searched as string, {
        period_start: PERIOD_START,
        period_end: PERIOD_END,
        ...(comboCornerId != null ? { corner_id: comboCornerId } : {}),
      }),
    enabled: !!searched,
    retry: false,
  });

  return (
    <Card title="부찬 조합별 만족도 비교 — 메인메뉴 기준">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        메인 메뉴명을 검색하면 부찬 조합별 평균 만족도를 비교합니다. 영양 프로필은 추정치입니다.
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
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          코너
        </span>
        <SegmentedControl
          value={comboCornerId != null ? String(comboCornerId) : ""}
          options={[
            { label: "전체", value: "" },
            ...(cornersQuery.data ?? []).map((c) => ({
              label: c.corner_name,
              value: String(c.corner_id),
            })),
          ]}
          onChange={(v) => setComboCornerId(v === "" ? null : Number(v))}
        />
      </div>
      <div className="mb-4 border-t pt-3" style={{ borderColor: "var(--border)" }}>
        <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
          <strong>부찬을 바꿀 때 효과가 큰 메인메뉴</strong> — 조합별 만족도 편차가 큰 순서입니다.
          음영은 한쪽에만 있는 부찬입니다. 행을 클릭하면 상세가 열립니다.
        </p>
        {rankingQuery.isLoading && <LoadingState />}
        {rankingQuery.isError && <ErrorState error={rankingQuery.error} />}
        {rankingQuery.data && rankingQuery.data.items.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            비교 가능한 조합(평가가 있는 조합 2개 이상)을 가진 메인메뉴가 아직 없습니다.
          </p>
        )}
        {rankingQuery.data && rankingQuery.data.items.length > 0 && (
          <Table
            columns={[
              { key: "menu", label: "메인메뉴" },
              { key: "spread", label: "만족도 편차", align: "right" },
              { key: "best", label: "가장 좋았던 조합" },
              { key: "worst", label: "가장 나빴던 조합" },
            ]}
            rows={rankingQuery.data.items.map((r) => ({
              menuId: r.menu_id,
              menuName: r.menu_name ?? "",
              menu: (
                <button
                  className="underline"
                  style={{ color: "var(--accent)" }}
                  onClick={() => {
                    setMenuName(r.menu_name ?? "");
                    setSearched(r.menu_name ?? "");
                  }}
                >
                  {r.menu_name}
                </button>
              ),
              spread: r.spread.toFixed(2),
              best: (
                <span className="flex items-center gap-1.5">
                  <ComboChips
                    sides={r.best.sides}
                    highlight={diffSides(r.best.sides, r.worst.sides).onlyBest}
                    tone="good"
                  />
                  <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    ({r.best.avg_satisfaction?.toFixed(2) ?? "-"})
                  </span>
                </span>
              ),
              worst: (
                <span className="flex items-center gap-1.5">
                  <ComboChips
                    sides={r.worst.sides}
                    highlight={diffSides(r.best.sides, r.worst.sides).onlyWorst}
                    tone="critical"
                  />
                  <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                    ({r.worst.avg_satisfaction?.toFixed(2) ?? "-"})
                  </span>
                </span>
              ),
            }))}
            rowKey={(r) => String(r.menuId)}
          />
        )}
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
            <div key={i} className="rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
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
      className="mt-2 rounded-xl border p-3 text-[13px]"
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
          {query.data.weather_reference.length > 0 && (
            <div>
              과거 날씨 참고:{" "}
              {query.data.weather_reference.map((r, i) => (
                <span key={r.event}>
                  {i > 0 && " · "}
                  {r.event} {r.avg_headcount}명({r.day_count}일)
                  {r.event !== "평상시" &&
                    (r.diff_vs_normal == null ? (
                      <span style={{ color: "var(--ink-muted)" }}> 표본 부족</span>
                    ) : (
                      <> {r.diff_vs_normal > 0 ? "+" : ""}{r.diff_vs_normal}</>
                    ))}
                </span>
              ))}
            </div>
          )}
          <div className="rounded p-2" style={{ background: "var(--surface)", color: "var(--ink-secondary)" }}>
            {query.data.summary_comment}
          </div>
        </div>
      )}
    </div>
  );
}

// §78: 규칙검증 패널이 월~금만 보여줄 때 쓰는 라벨 — weekdayDates는 월~토
// 6일이라 앞 5개만 슬라이스해서 짝을 맞춘다.
const WEEKDAY_LABELS_MON_FRI = ["월", "화", "수", "목", "금"];

function WeeklyMenuReviewTab() {
  const chartTheme = useChartTheme();
  const [selectedMonday, setSelectedMonday] = useState(weeklyMondayOf(new Date()));
  const sunday = weeklyAddDays(selectedMonday, 6);
  const weekdayDates = Array.from({ length: 6 }, (_, i) => weeklyAddDays(selectedMonday, i)); // 월~토(일요일 미운영)

  // §81: 규칙 라벨을 클릭하면 그 규칙의 이번 주 위반 매치 전체를 한 번에
  // 하이라이트해야 해서, 단일 문자열 대신 Set으로 다중 선택을 지원한다 —
  // 칩/셀 클릭(selectSlot)은 여전히 단일 선택으로 동작한다(그 안에서 Set을
  // 항상 크기 1로만 채운다).
  const [selectedSlotKeys, setSelectedSlotKeys] = useState<Set<string>>(new Set());
  const [isEditing, setIsEditing] = useState(false);
  const [showPrediction, setShowPrediction] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [predictedByPlanId, setPredictedByPlanId] = useState<Record<number, PredictedNumbersRow>>({});
  const [donutDay, setDonutDay] = useState(weekdayDates[0]);

  const selectSlot = (key: string) => {
    setSelectedSlotKeys((cur) => (cur.size === 1 && cur.has(key) ? new Set() : new Set([key])));
    setIsEditing(false);
    setShowPrediction(false);
  };

  // §81: 규칙 라벨 클릭 — 그 규칙의 이번 주 위반 매치 전체를 동시에 하이라이트.
  // 같은 집합이 이미 선택돼 있으면 토글 오프.
  const selectRuleMatches = (matches: { plan_date: string; corner_id: number }[]) => {
    const keys = matches.map((m) => `${m.plan_date}_${m.corner_id}`);
    setSelectedSlotKeys((cur) => {
      const next = new Set(keys);
      const same = cur.size === next.size && [...cur].every((k) => next.has(k));
      return same ? new Set() : next;
    });
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
  // §77: 담당자가 준 4개 편성 기준 — combination-check와 같은 기간으로 호출해
  // 화면에 보이는 주와 항상 일치시킨다.
  const ruleCheckQuery = useQuery({
    queryKey: ["weekly-menu-plan-rule-check", selectedMonday],
    queryFn: () => api.weeklyMenuPlanRuleCheck({ period_start: selectedMonday, period_end: sunday }),
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
  // 건강가든은 식단표 엑셀에 없어 담당자가 슬롯별로 직접 입력한다(2026-08).
  // 슬롯 단위 전체 교체라 PUT이고, 빈 문자열을 보내면 그 슬롯을 비운다.
  const [gardenDrafts, setGardenDrafts] = useState<Record<string, string>>({});
  const saveHealthGarden = useMutation({
    mutationFn: (params: { plan_date: string; corner_id: number; meal_type: MealType; menu_names_raw: string }) =>
      api.updateHealthGarden(params),
    onSuccess: () => slotsQuery.refetch(),
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
  // 상세/편집 패널은 슬롯이 정확히 1개 선택됐을 때만 의미가 있다 — 규칙 라벨
  // 클릭으로 여러 개가 한꺼번에 선택되면 이 패널 대신 격자 하이라이트만 보여준다.
  const singleSelectedSlotKey = selectedSlotKeys.size === 1 ? [...selectedSlotKeys][0] : null;
  const selectedSlot = slots.find((s) => `${s.plan_date}_${s.corner_id}` === singleSelectedSlotKey) ?? null;
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

  // §78: 규칙 위반 매치 클릭 시 아래 격자표의 해당 셀을 하이라이트 — 격자 셀
  // 키(`${plan_date}_${corner_id}`, selectSlot 토글)를 그대로 재사용한다.
  // §81: 규칙 라벨 자체를 클릭하면 그 규칙의 이번 주 위반 매치 전체를 한
  // 번에 하이라이트한다(selectRuleMatches).
  function renderDailyRuleRow(label: string, results: DailyMenuPlanRuleResult[]) {
    const byDate = new Map(results.map((r) => [r.plan_date, r]));
    const violatingMatches = results.filter((r) => !r.ok).flatMap((r) => r.matches);
    return (
      <div className="mb-2">
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <button
            className="font-medium underline decoration-dotted disabled:no-underline disabled:cursor-default"
            style={{ color: violatingMatches.length > 0 ? "var(--accent)" : undefined }}
            onClick={() => selectRuleMatches(violatingMatches)}
            disabled={violatingMatches.length === 0}
            title={violatingMatches.length > 0 ? "클릭하면 이번 주 위반 전체를 격자에서 하이라이트합니다" : undefined}
          >
            {label}
          </button>
          {weekdayDates.slice(0, 5).map((d, i) => {
            const r = byDate.get(d);
            if (!r) {
              return (
                <span key={d} className="text-xs" style={{ color: "var(--ink-muted)" }}>
                  {WEEKDAY_LABELS_MON_FRI[i]} -
                </span>
              );
            }
            return (
              <Badge key={d} tone={r.ok ? "good" : "critical"} label={`${WEEKDAY_LABELS_MON_FRI[i]} ${r.count}개`} />
            );
          })}
        </div>
        {violatingMatches.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-2 text-xs">
            {violatingMatches.map((m, i) => (
              <button
                key={i}
                className="underline"
                style={{ color: "var(--accent)" }}
                onClick={() => selectSlot(`${m.plan_date}_${m.corner_id}`)}
              >
                {m.menu_name}({m.corner_name}, {m.plan_date.slice(5)})
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card title="주간 식단표 관리">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          메인/부찬이 잘못 나뉘었으면 셀을 클릭해 고치세요. 개선의견은 해당 날짜 7일 전까지 제출 가능합니다.
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

        {ruleCheckQuery.data && (
          <div className="mb-4 rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
            <h3 className="mb-2 text-[13px] font-semibold">주간 편성 규칙 검증 (주중, 요일별)</h3>
            {renderDailyRuleRow("해장 메뉴 (하루 최소 1개)", ruleCheckQuery.data.hangover)}
            {renderDailyRuleRow("면류 (하루 최대 4개)", ruleCheckQuery.data.noodle)}
            {renderDailyRuleRow("매운(빨간국물) (하루 최대 4개)", ruleCheckQuery.data.spicy_red_broth)}
            <div className="mt-2 flex items-center gap-2 text-[13px]">
              {(() => {
                const allLowHeadcountMatches = ruleCheckQuery.data.low_headcount_reuse.violations.flatMap(
                  (v) => v.matches
                );
                return (
                  <button
                    className="font-medium underline decoration-dotted disabled:no-underline disabled:cursor-default"
                    style={{ color: allLowHeadcountMatches.length > 0 ? "var(--accent)" : undefined }}
                    onClick={() => selectRuleMatches(allLowHeadcountMatches)}
                    disabled={allLowHeadcountMatches.length === 0}
                    title={
                      allLowHeadcountMatches.length > 0
                        ? "클릭하면 이번 주 위반 전체를 격자에서 하이라이트합니다"
                        : undefined
                    }
                  >
                    최근 저조 식수(200식 이하) 재편성
                  </button>
                );
              })()}
              <Badge
                tone={ruleCheckQuery.data.low_headcount_reuse.ok ? "good" : "critical"}
                label={`${ruleCheckQuery.data.low_headcount_reuse.violations.length}건`}
              />
            </div>
            {!ruleCheckQuery.data.low_headcount_reuse.ok && (
              <div className="mt-1 flex flex-wrap gap-2 text-xs">
                {ruleCheckQuery.data.low_headcount_reuse.violations.map((v, vi) =>
                  v.matches.length > 0 ? (
                    v.matches.map((m, mi) => (
                      <button
                        key={`${vi}_${mi}`}
                        className="underline"
                        style={{ color: "var(--accent)" }}
                        onClick={() => selectSlot(`${m.plan_date}_${m.corner_id}`)}
                      >
                        {v.menu_name}({v.corner_name}, 최근 평균 {v.recent_avg_headcount}식, {m.plan_date.slice(5)})
                      </button>
                    ))
                  ) : (
                    <span key={vi} style={{ color: "var(--ink-muted)" }}>
                      {v.menu_name}({v.corner_name}, 최근 평균 {v.recent_avg_headcount}식)
                    </span>
                  )
                )}
              </div>
            )}
          </div>
        )}

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
                        const isSelected = selectedSlotKeys.has(key);
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

        {selectedSlotKeys.size > 1 && (
          <p className="mt-4 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {selectedSlotKeys.size}개 슬롯이 격자에서 강조 표시되어 있습니다. 규칙 라벨을 다시 클릭하면
            해제됩니다.
          </p>
        )}

        {selectedSlot &&
          (() => {
            const key = singleSelectedSlotKey as string;
            const dday = daysUntil(selectedSlot.feedback_deadline);
            return (
              <div className="mt-4 rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
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
                  {selectedSlot.health_garden.length > 0 && (
                    <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                      건강가든: {selectedSlot.health_garden.map((s) => s.menu_name).join(", ")}
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

                <div className="mt-2 border-t pt-2" style={{ borderColor: "var(--border)" }}>
                  <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                    건강가든 — 식단표 엑셀에 아직 안 들어와 직접 입력합니다. 쉼표나 줄바꿈으로 구분하세요.
                    저장하면 이 슬롯의 건강가든이 통째로 바뀝니다(비우려면 빈칸으로 저장).
                  </p>
                  <div className="flex gap-2">
                    <input
                      value={
                        gardenDrafts[key] ??
                        selectedSlot.health_garden.map((h) => h.menu_name).join(", ")
                      }
                      onChange={(e) => setGardenDrafts((g) => ({ ...g, [key]: e.target.value }))}
                      placeholder="예: 구운채소, 두부샐러드, 닭가슴살"
                      className="flex-1 rounded-md border px-2 py-1 text-[13px]"
                      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                    />
                    <Button
                      variant="secondary"
                      disabled={saveHealthGarden.isPending}
                      onClick={() =>
                        saveHealthGarden.mutate({
                          plan_date: selectedSlot.plan_date,
                          corner_id: selectedSlot.corner_id,
                          meal_type: selectedSlot.meal_type,
                          menu_names_raw:
                            gardenDrafts[key] ??
                            selectedSlot.health_garden.map((h) => h.menu_name).join(", "),
                        })
                      }
                    >
                      {saveHealthGarden.isPending ? "저장 중..." : "저장"}
                    </Button>
                  </div>
                  {saveHealthGarden.isError && <ErrorState error={saveHealthGarden.error} />}
                </div>

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

  const voeBriefing = useQuery({
    queryKey: ["voe-briefing-tab", period],
    queryFn: () => api.voeBriefing(`${period}-01`),
  });
  const recomputeVoeBriefing = useMutation({
    mutationFn: () => api.recomputeVoeBriefing(`${period}-01`),
    onSuccess: () => voeBriefing.refetch(),
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

  // "이달의 VOE 최다 코너/메뉴" — 새 백엔드 집계 없이 이미 받아온 카테고리별
  // 코멘트를 프론트에서 tally한다. 한 코멘트가 여러 카테고리에 동시에 걸릴 수
  // 있어(다중 라벨) 그대로 합치면 중복 카운트되므로 먼저 dedupe한다.
  const seenVoeKeys = new Set<string>();
  const uniqueVoeComments = (voeCategory.data?.categories ?? []).flatMap((c) => c.comments).filter((c) => {
    const key = `${c.eaten_at}|${c.corner_name}|${c.menu_name}|${c.comment}`;
    if (seenVoeKeys.has(key)) return false;
    seenVoeKeys.add(key);
    return true;
  });
  function topVoeEntry(getKey: (c: (typeof uniqueVoeComments)[number]) => string | null): { name: string; count: number } | null {
    const counts = new Map<string, number>();
    for (const c of uniqueVoeComments) {
      const key = getKey(c);
      if (!key) continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    let best: { name: string; count: number } | null = null;
    for (const [name, count] of counts) {
      if (!best || count > best.count) best = { name, count };
    }
    return best;
  }
  const topVoeCorner = topVoeEntry((c) => c.corner_name);
  const topVoeMenu = topVoeEntry((c) => c.menu_name);

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
            카테고리를 클릭하면 코멘트를 볼 수 있습니다. 매일 자동 분류되며, 즉시 반영하려면 재계산하세요.
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
            <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <StatTile
                label="이달의 VOE 최다 코너"
                value={topVoeCorner ? topVoeCorner.name : "-"}
                sub={topVoeCorner ? `${topVoeCorner.count}건` : undefined}
              />
              <StatTile
                label="이달의 VOE 최다 메뉴"
                value={topVoeMenu ? topVoeMenu.name : "-"}
                sub={topVoeMenu ? `${topVoeMenu.count}건` : undefined}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {voeCategory.data.categories.map((c) => (
                <button
                  key={c.category}
                  onClick={() => setSelectedVoeCategory((cur) => (cur === c.category ? null : c.category))}
                  className="rounded-xl border p-3 text-left transition-colors"
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
                        { key: "corner_menu", label: "코너·메뉴" },
                        { key: "comment", label: "코멘트" },
                      ]}
                      rows={selected.comments.map((c) => ({
                        eaten_at: c.eaten_at.replace("T", " "),
                        // 어떤 메뉴에 대한 의견인지 바로 알 수 있게 코너+메뉴를 함께 표기(2026-08).
                        corner_menu: c.corner_name
                          ? `${c.corner_name}${c.menu_name ? ` · ${c.menu_name}` : ""}`
                          : "-",
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

      <Card title="이달의 VOE AI 브리핑">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            아래 "월간 VOE 클러스터링" 결과를 요약합니다. 클러스터링이 먼저 계산돼 있어야 합니다.
          </p>
          <Button
            variant="secondary"
            onClick={() => recomputeVoeBriefing.mutate()}
            disabled={recomputeVoeBriefing.isPending}
          >
            {recomputeVoeBriefing.isPending ? "요약 중..." : "이번 달 재계산"}
          </Button>
        </div>
        {recomputeVoeBriefing.isError && <ErrorState error={recomputeVoeBriefing.error} />}
        {voeBriefing.isLoading && <LoadingState />}
        {voeBriefing.isError && <ErrorState error={voeBriefing.error} />}
        {voeBriefing.data && !voeBriefing.data.has_clusters && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            먼저 아래 "월간 VOE 클러스터링"을 계산하세요.
          </p>
        )}
        {voeBriefing.data && voeBriefing.data.has_clusters && !voeBriefing.data.briefing && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            아직 브리핑이 계산되지 않았습니다. "이번 달 재계산"을 눌러보세요.
          </p>
        )}
        {voeBriefing.data?.briefing && voeBriefing.data.has_clusters && (
          <div>
            <p className="whitespace-pre-line text-[13px]" style={{ color: "var(--ink-secondary)" }}>
              {voeBriefing.data.briefing}
            </p>
            {voeBriefing.data.briefing_computed_at && (
              <p className="mt-2 text-xs" style={{ color: "var(--ink-muted)" }}>
                {voeBriefing.data.briefing_computed_at.replace("T", " ")} 기준
              </p>
            )}
          </div>
        )}
      </Card>

      <Card title="월간 VOE 클러스터링 (주제·키워드 기반)">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            그 달 코멘트를 자유 주제로 묶은 군집입니다. 매일 자동 계산되며, 즉시 반영하려면 재계산하세요.
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
                className="rounded-xl border p-3"
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
            월별 VOE 코멘트 수 추이(최근 {VOE_TREND_MONTHS}개월).
          </p>
          {monthlyVolumeQuery.isLoading && <LoadingState />}
          {monthlyVolumeQuery.isError && <ErrorState error={monthlyVolumeQuery.error} />}
          {monthlyVolumeQuery.data && <ReactECharts option={volumeTrendOption} style={{ height: 220 }} />}
        </div>
      </Card>
    </div>
  );
}

// ---- 2026-08 화면 재편으로 생긴 최상위 화면 3개 ----
// 기존 "분석" 탭(서브탭 5개)을 해체하고, 담당자 협의에서 정한 5개 축
// (현황 / 메뉴 편성·운영 / 만족도·VoE / Agent 채팅 / 관리)에 맞춰 재배치했다.
// 컴포넌트 본문은 그대로 두고 조합만 바꾼다.

/** 메뉴 편성·운영 — "다음 주 식단을 어떻게 짤까"에 답하는 화면. */
// 메뉴 회전 이력 (2순위, 2026-08) — "이 메뉴 최근에 내보내지 않았나?"에 답한다.
// 판정 기준은 백엔드(app/services/menu_rotation.py)에 있고 여기선 표시만 한다.
const ROTATION_FLAG_TONE: Record<string, "critical" | "warning" | "accent" | "muted"> = {
  "같은 날 중복": "critical",
  "재편성 과다": "critical",
  "평소보다 이름": "warning",
  오랜만: "accent",
};

// 기간 선택 — 식단표 8개월치가 적재돼 PERIOD_START(180일 고정) 너머를 볼 수단이
// 필요해졌다(2026-08). 기본 6개월인 이유: 적재 이전 구간은 편성 이력이 비어 있어
// 편성 횟수가 실제보다 적게 나온다.
const PLAN_PERIOD_OPTIONS = [
  { label: "30일", value: "30" },
  { label: "60일", value: "60" },
  { label: "90일", value: "90" },
  { label: "6개월", value: "180" },
];

// 기본 90일 — 담당자 편성 기준이 "3개월에 2회"라 그 창과 맞춘다(2026-08 요청).
function usePlanPeriod(defaultDays = "90") {
  const [days, setDays] = useState(defaultDays);
  return {
    days,
    setDays,
    periodStart: isoDaysAgo(Number(days)),
    periodEnd: isoDaysAgo(0),
  };
}

// §81: 메인메뉴만 다룬다(담당자 확인: "메인만" — 부찬·건강가든은 이번
// 재설계 대상 밖).
const ROTATION_MAIN_ROLE = "메인";

/**
 * 재편성 점검 패널 — "이 메뉴 최근에 또 내보내지 않았나"(회전 이력)만 다룬다.
 * §82: `MenuDuplicationCheckSection`의 탭 하나로 합쳐지면서 카드 래퍼는
 * 벗겨내고 내부 로직은 그대로 옮겼다(원래 이름 `MenuRotationCheckSection`).
 *
 * §81: "너무 모든 내용이 다 뜬다"는 재신고로, 경고 있는 메뉴를 전부
 * 나열하던 방식(그룹별 역할 분리 + preview-cap)을 걷어내고 (1) 기간 내
 * 직전 편성 대비 가장 이르게 재편성된 메인 메뉴 Top5, (2) 담당자가 입력한
 * "편성 기준(일)"보다 짧게 재편성된 전체 목록, 이 두 가지만 기본으로
 * 보여준다. 각 항목의 편성이력(그 메뉴·코너의 전체 편성일)은 "이력 보기"로
 * 펼쳐야 볼 수 있다.
 */
function RotationCheckPanel() {
  const [rotationStart, setRotationStart] = useState(DUPLICATION_CHECK_PERIOD_START);
  const [rotationEnd, setRotationEnd] = useState(DUPLICATION_CHECK_PERIOD_END);
  const [gapThresholdInput, setGapThresholdInput] = useState("");
  const [showAllThresholdViolations, setShowAllThresholdViolations] = useState(false);
  const [expandedMenuKeys, setExpandedMenuKeys] = useState<Set<string>>(new Set());
  const ROTATION_PREVIEW_COUNT = 15;

  const rotation = useQuery({
    queryKey: ["weekly-menu-rotation", rotationStart, rotationEnd],
    queryFn: () => api.weeklyMenuRotation({ period_start: rotationStart, period_end: rotationEnd }),
  });

  const allRotationItems = rotation.data?.items ?? [];
  // 메인메뉴만, 그리고 직전 편성 대비 며칠 후인지(gap_days) 알 수 있는(=
  // 처음 나온 메뉴가 아닌) 슬롯만 "얼마나 이르게 재편성됐는지" 판단 대상이다.
  const mainItemsWithGap = allRotationItems.filter(
    (r) => r.menu_role === ROTATION_MAIN_ROLE && r.gap_days != null,
  );
  const top5Soonest = [...mainItemsWithGap]
    .sort((a, b) => (a.gap_days as number) - (b.gap_days as number))
    .slice(0, 5);

  const gapThreshold = gapThresholdInput === "" ? null : Number(gapThresholdInput);
  const hasValidThreshold = gapThreshold != null && !Number.isNaN(gapThreshold) && gapThreshold > 0;
  const thresholdViolationsAll = hasValidThreshold
    ? [...mainItemsWithGap]
        .filter((r) => (r.gap_days as number) < (gapThreshold as number))
        .sort((a, b) => (a.gap_days as number) - (b.gap_days as number))
    : [];
  const visibleThresholdViolations = showAllThresholdViolations
    ? thresholdViolationsAll
    : thresholdViolationsAll.slice(0, ROTATION_PREVIEW_COUNT);

  function toggleHistory(key: string) {
    setExpandedMenuKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function renderRotationRow(r: MenuRotationRow, rank?: number) {
    const key = `${r.corner_id}-${r.menu_id}`;
    const isExpanded = expandedMenuKeys.has(key);
    // 편성이력 — 같은 (코너, 메뉴)의 전체 편성일. 새 API 없이 이미 받은
    // items에서 클라이언트 필터링만 한다.
    const history = allRotationItems
      .filter((h) => h.corner_id === r.corner_id && h.menu_id === r.menu_id)
      .sort((a, b) => a.plan_date.localeCompare(b.plan_date));
    return (
      <div
        key={`${key}-${r.plan_date}`}
        className="rounded-xl border p-3"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[13px] font-medium">
            {rank != null && <span style={{ color: "var(--ink-muted)" }}>{rank}. </span>}
            {r.menu_name} <span style={{ color: "var(--ink-muted)" }}>({r.corner_name})</span>
          </div>
          <Badge tone={ROTATION_FLAG_TONE[r.flag] ?? "muted"} label={r.flag} />
        </div>
        <div
          className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4"
          style={{ color: "var(--ink-secondary)" }}
        >
          <div>
            만족도{" "}
            <span className="font-medium">
              {r.avg_satisfaction != null ? r.avg_satisfaction.toFixed(2) : "-"}
            </span>
          </div>
          <div>
            식수{" "}
            <span className="font-medium">
              {r.recent_avg_headcount != null ? `${Math.round(r.recent_avg_headcount)}명` : "-"}
            </span>
          </div>
          <div>
            평균 주기{" "}
            <span className="font-medium">{r.avg_interval_days != null ? `${r.avg_interval_days}일` : "-"}</span>
          </div>
          <div>
            직전 대비{" "}
            <span className="font-medium">
              {r.gap_days}일 후
              {r.previous_date ? ` (${weekdayLabel(r.previous_date)} → ${weekdayLabel(r.plan_date)})` : ""}
            </span>
          </div>
        </div>
        <button
          className="mt-2 text-xs underline"
          style={{ color: "var(--accent)" }}
          onClick={() => toggleHistory(key)}
        >
          {isExpanded ? "이력 접기" : `편성이력 보기 (${history.length}건)`}
        </button>
        {isExpanded && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="whitespace-nowrap py-1 pr-4 text-left font-medium" style={{ color: "var(--ink-muted)" }}>
                    날짜
                  </th>
                  <th className="whitespace-nowrap py-1 pr-4 text-left font-medium" style={{ color: "var(--ink-muted)" }}>
                    판정
                  </th>
                  <th className="whitespace-nowrap py-1 pr-4 text-right font-medium" style={{ color: "var(--ink-muted)" }}>
                    직전 이후
                  </th>
                  <th className="whitespace-nowrap py-1 text-right font-medium" style={{ color: "var(--ink-muted)" }}>
                    평균 주기
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={`${h.plan_date}-${i}`} style={{ borderTop: "1px solid var(--border)" }}>
                    <td className="whitespace-nowrap py-1 pr-4">{weekdayLabel(h.plan_date)}</td>
                    <td className="whitespace-nowrap py-1 pr-4">
                      <Badge tone={ROTATION_FLAG_TONE[h.flag] ?? "muted"} label={h.flag} />
                    </td>
                    <td className="whitespace-nowrap py-1 pr-4 text-right">
                      {h.gap_days == null
                        ? "-"
                        : `${h.gap_days}일 전${h.previous_date ? ` (${h.previous_date.slice(5)})` : ""}`}
                    </td>
                    <td className="whitespace-nowrap py-1 text-right">
                      {h.avg_interval_days == null ? "-" : `${h.avg_interval_days}일`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
        가장 이르게 재편성된 메인 메뉴 Top5입니다. "편성 기준(일)"을 입력하면 전체 목록도 볼 수 있습니다.
      </p>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          시작일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={rotationStart}
            max={rotationEnd}
            onChange={(e) => setRotationStart(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          종료일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={rotationEnd}
            min={rotationStart}
            onChange={(e) => setRotationEnd(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          편성 기준(일)
          <input
            type="number"
            min={1}
            placeholder="예: 21"
            className="w-28 rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={gapThresholdInput}
            onChange={(e) => {
              setGapThresholdInput(e.target.value);
              setShowAllThresholdViolations(false);
            }}
          />
        </label>
      </div>
      {rotation.isLoading && <LoadingState />}
      {rotation.isError && <ErrorState error={rotation.error} />}
      {rotation.data && mainItemsWithGap.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 기간에 재편성 이력이 있는 메인 메뉴가 없습니다.
        </p>
      )}
      {top5Soonest.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-[13px] font-semibold">가장 이르게 재편성된 메뉴 Top5</h3>
          <div className="space-y-3">{top5Soonest.map((r, i) => renderRotationRow(r, i + 1))}</div>
        </div>
      )}
      {hasValidThreshold && (
        <div>
          <h3 className="mb-2 text-[13px] font-semibold">
            편성 기준({gapThreshold}일) 미달 재편성 — {thresholdViolationsAll.length}건
          </h3>
          {thresholdViolationsAll.length === 0 ? (
            <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              기준보다 짧게 재편성된 메인 메뉴가 없습니다.
            </p>
          ) : (
            <>
              <div className="space-y-3">{visibleThresholdViolations.map((r) => renderRotationRow(r))}</div>
              {thresholdViolationsAll.length > ROTATION_PREVIEW_COUNT && (
                <button
                  className="mt-2 text-xs underline"
                  style={{ color: "var(--accent)" }}
                  onClick={() => setShowAllThresholdViolations((v) => !v)}
                >
                  {showAllThresholdViolations ? "접기" : `전체 ${thresholdViolationsAll.length}개 보기`}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}

/**
 * 부찬 반복 랭킹 패널 — 담당자: "부찬 중복 볼 때 보기가 너무 불편함,
 * 정말 자주 나오고 돌려막기한 부찬을 보고싶어". §79: 원래
 * `MenuRotationCheckSection` 카드 하단에 자기 기간·코너 필터를 따로 갖고
 * 붙어 있었는데("보기 힘듦" 신고) 회전 이력과는 독립된 도구라 별도
 * 카드로 뺐다. §82: 다시 `MenuDuplicationCheckSection`의 탭 하나로
 * 합쳐지면서 카드 래퍼만 벗겨냈다(원래 이름 `RepeatedSideDishRankingSection`).
 */
function RepeatedSideDishPanel() {
  const [repeatStart, setRepeatStart] = useState(DUPLICATION_CHECK_PERIOD_START);
  const [repeatEnd, setRepeatEnd] = useState(DUPLICATION_CHECK_PERIOD_END);
  const [repeatCornerId, setRepeatCornerId] = useState<number | null>(null);
  const [showAllRepeated, setShowAllRepeated] = useState(false);
  const REPEATED_PREVIEW_COUNT = 20;
  // §80: "어떤 부찬이 중복해서 나올 때마다 만족도가 떨어지는지 패턴을 파악하고
  // 싶다" — 횟수/연결 메인 만족도로 정렬 가능하게 한다.
  const [sortKey, setSortKey] = useState<"count" | "satisfaction">("count");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  function toggleSort(key: "count" | "satisfaction") {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }
  // 부찬 클릭 상세 — "단무지 클릭 → 8/01 신포짜장면 / 8/11 스냅스낵 신라면".
  const [selectedItemKey, setSelectedItemKey] = useState<string | null>(null);

  const repeatCorners = useQuery({ queryKey: ["corner-list"], queryFn: () => api.cornerList() });
  const repeated = useQuery({
    queryKey: ["weekly-menu-repeated-side-dishes", repeatStart, repeatEnd, repeatCornerId],
    queryFn: () =>
      api.weeklyMenuRepeatedSideDishes({
        period_start: repeatStart,
        period_end: repeatEnd,
        ...(repeatCornerId != null ? { corner_id: repeatCornerId } : {}),
      }),
  });
  const repeatedItems = [...(repeated.data?.items ?? [])].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    if (sortKey === "count") return (a.count - b.count) * dir;
    const av = a.avg_main_satisfaction;
    const bv = b.avg_main_satisfaction;
    if (av == null && bv == null) return 0;
    if (av == null) return 1; // 만족도 없는 행은 정렬 방향과 무관하게 맨 뒤
    if (bv == null) return -1;
    return (av - bv) * dir;
  });
  const visibleRepeatedItems = showAllRepeated
    ? repeatedItems
    : repeatedItems.slice(0, REPEATED_PREVIEW_COUNT);
  const selectedItem = repeatedItems.find((o) => `${o.corner_name}|${o.menu_name}` === selectedItemKey) ?? null;
  const sideDishDetail = useQuery({
    queryKey: ["weekly-menu-side-dish-detail", selectedItem?.corner_name, selectedItem?.menu_name, repeatStart, repeatEnd],
    queryFn: () =>
      api.weeklyMenuSideDishDetail({
        menu_name: selectedItem!.menu_name,
        corner_name: selectedItem!.corner_name,
        period_start: repeatStart,
        period_end: repeatEnd,
      }),
    enabled: selectedItem != null,
  });

  return (
    <>
      <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
        같은 코너 안에서만 반복으로 셉니다(건강가든은 코너 무관).
      </p>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          시작일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={repeatStart}
            max={repeatEnd}
            onChange={(e) => setRepeatStart(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          종료일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={repeatEnd}
            min={repeatStart}
            onChange={(e) => setRepeatEnd(e.target.value)}
          />
        </label>
        <div className="flex flex-col gap-1">
          <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            코너
          </span>
          <SegmentedControl
            value={repeatCornerId != null ? String(repeatCornerId) : ""}
            options={[
              { label: "전체", value: "" },
              ...(repeatCorners.data ?? []).map((c) => ({
                label: c.corner_name,
                value: String(c.corner_id),
              })),
            ]}
            onChange={(v) => setRepeatCornerId(v === "" ? null : Number(v))}
          />
        </div>
      </div>
      {repeated.isLoading && <LoadingState />}
      {repeated.isError && <ErrorState error={repeated.error} />}
      {repeated.data && repeatedItems.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 기간·코너에 반복 편성된 부찬이 없습니다.
        </p>
      )}
      {repeatedItems.length > 0 && (
        <>
          <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            메뉴명을 클릭하면 편성 상세를 볼 수 있습니다.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr>
                  <th
                    className="border-b py-2 pr-4 text-right font-medium"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                  >
                    순위
                  </th>
                  <th
                    className="border-b py-2 pr-4 text-left font-medium"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                  >
                    코너
                  </th>
                  <th
                    className="border-b py-2 pr-4 text-left font-medium"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                  >
                    메뉴
                  </th>
                  <th
                    className="border-b py-2 pr-4 text-left font-medium"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
                  >
                    역할
                  </th>
                  <SortableHeader
                    label="횟수"
                    active={sortKey === "count"}
                    dir={sortDir}
                    align="right"
                    onClick={() => toggleSort("count")}
                  />
                  <SortableHeader
                    label="연결 메인 만족도"
                    active={sortKey === "satisfaction"}
                    dir={sortDir}
                    align="right"
                    onClick={() => toggleSort("satisfaction")}
                  />
                </tr>
              </thead>
              <tbody>
                {visibleRepeatedItems.map((o, i) => {
                  const itemKey = `${o.corner_name}|${o.menu_name}`;
                  return (
                    <tr key={itemKey} className="border-b" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2 pr-4 text-right">{i + 1}</td>
                      <td className="py-2 pr-4">{o.corner_name}</td>
                      <td className="py-2 pr-4">
                        <button
                          className="underline"
                          style={{ color: "var(--accent)" }}
                          onClick={() => setSelectedItemKey((cur) => (cur === itemKey ? null : itemKey))}
                        >
                          {o.menu_name}
                        </button>
                      </td>
                      <td className="py-2 pr-4">{o.menu_role}</td>
                      <td className="py-2 pr-4 text-right">{o.count}회</td>
                      <td className="py-2 pr-4 text-right">
                        {o.avg_main_satisfaction != null ? o.avg_main_satisfaction.toFixed(2) : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {repeatedItems.length > REPEATED_PREVIEW_COUNT && (
            <button
              className="mt-2 text-xs underline"
              style={{ color: "var(--accent)" }}
              onClick={() => setShowAllRepeated((v) => !v)}
            >
              {showAllRepeated ? "접기" : `전체 ${repeatedItems.length}개 보기`}
            </button>
          )}
          {selectedItem && (
            <div className="mt-3 rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
              <p className="mb-2 text-[13px] font-medium">
                {selectedItem.menu_name} ({selectedItem.corner_name}) — 편성 상세
              </p>
              {sideDishDetail.isLoading && <LoadingState />}
              {sideDishDetail.isError && <ErrorState error={sideDishDetail.error} />}
              {sideDishDetail.data && sideDishDetail.data.pairings.length === 0 && (
                <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                  이 기간에 편성 이력이 없습니다.
                </p>
              )}
              {sideDishDetail.data && sideDishDetail.data.pairings.length > 0 && (
                <ul className="space-y-1 text-[13px]">
                  {sideDishDetail.data.pairings.map((p, i) => (
                    <li key={i}>
                      {weekdayLabel(p.plan_date)} {p.corner_name} — {p.main_menu_name ?? "메인 미배정"}
                      {p.main_avg_satisfaction != null && (
                        <span style={{ color: "var(--ink-muted)" }}> (만족도 {p.main_avg_satisfaction.toFixed(2)})</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}

/**
 * 한 끼 겹침 패널 — "이 한 끼 구성이 겹치지 않나"(슬롯 내 재료·특성
 * 중복). 회전 이력과 관심사가 달라 원래 별도 카드였다(2026-08 "너무
 * 복잡하게 나타남" 신고). §82: `MenuDuplicationCheckSection`의 탭
 * 하나로 합쳐지면서 카드 래퍼만 벗겨냈다(원래 이름 `MealClashCheckSection`).
 * 주간 네비게이션은 이 패널만 쓰므로 로컬 상태로 유지한다.
 */
// §79: 담당자 "메뉴 중복점검 보기가 힘듦" — 슬롯이 많으면 그룹·접기 없이
// 다 펼쳐지던 걸 요일별로 묶고 기본 상위 N일만 보여준다(RotationCheckPanel
// 의 ROTATION_PREVIEW_COUNT/showAll 관례를 그대로 따름).
const CLASH_DAY_PREVIEW_COUNT = 3;

function MealClashPanel() {
  const [selectedMonday, setSelectedMonday] = useState(() => weeklyMondayOf(new Date()));
  const periodEnd = weeklyAddDays(selectedMonday, 6);
  const [showAllClashDays, setShowAllClashDays] = useState(false);

  const clash = useQuery({
    queryKey: ["weekly-menu-combination-check", selectedMonday],
    queryFn: () =>
      api.weeklyMenuCombinationCheck({ period_start: selectedMonday, period_end: periodEnd }),
  });
  const clashSlots = (clash.data?.slots ?? []).filter(
    (s) => s.ingredient_clashes.length > 0 || s.vector_clashes.length > 0,
  );
  const ingredientClashCount = clashSlots.reduce((sum, s) => sum + s.ingredient_clashes.length, 0);
  const vectorClashCount = clashSlots.reduce((sum, s) => sum + s.vector_clashes.length, 0);

  // 요일별로 묶는다 — 이전엔 슬롯이 많으면 재료 중복·특성 중복 배지가 섞인
  // 카드가 그대로 다 펼쳐졌다.
  const slotsByDate = new Map<string, typeof clashSlots>();
  for (const s of clashSlots) {
    const list = slotsByDate.get(s.plan_date) ?? [];
    list.push(s);
    slotsByDate.set(s.plan_date, list);
  }
  const clashDates = Array.from(slotsByDate.keys()).sort();
  const visibleClashDates = showAllClashDays ? clashDates : clashDates.slice(0, CLASH_DAY_PREVIEW_COUNT);

  return (
    <>
      <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
        같은 날·코너·끼니 안에서 재료 또는 특성이 겹치는 조합을 보여줍니다.
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          onClick={() => {
            setSelectedMonday(weeklyAddDays(selectedMonday, -7));
            setShowAllClashDays(false);
          }}
        >
          ◀ 이전 주
        </Button>
        <span className="text-[13px] font-medium">
          {selectedMonday} ~ {periodEnd}
        </span>
        <Button
          variant="secondary"
          onClick={() => {
            setSelectedMonday(weeklyAddDays(selectedMonday, 7));
            setShowAllClashDays(false);
          }}
        >
          다음 주 ▶
        </Button>
      </div>
      {clash.data != null && clashSlots.length > 0 && (
        <div className="mb-3">
          <Badge
            tone="critical"
            label={`이번 주 재료 중복 ${ingredientClashCount}건, 특성 중복 ${vectorClashCount}건 (${clashSlots.length}개 끼니)`}
          />
        </div>
      )}
      {clash.data != null && clash.data.untagged_menu_count > 0 && (
        <div className="mb-3">
          <Badge
            tone="warning"
            label={`${clash.data.untagged_menu_count}개 메뉴는 음식벡터 미태깅이라 특성 중복을 못 봤습니다(관리 탭에서 태깅).`}
          />
        </div>
      )}
      {clash.isLoading && <LoadingState />}
      {clash.isError && <ErrorState error={clash.error} />}
      {clash.data && clashSlots.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          {clash.data.slots.length === 0
            ? "이 주에 등록된 식단표가 없습니다."
            : "구성 겹침이 발견되지 않았습니다."}
        </p>
      )}
      <div className="space-y-4">
        {visibleClashDates.map((plan_date) => {
          const daySlots = slotsByDate.get(plan_date) ?? [];
          return (
            <div key={plan_date}>
              <p className="mb-2 text-xs font-semibold" style={{ color: "var(--ink-secondary)" }}>
                {weekdayLabel(plan_date)}
              </p>
              <div className="space-y-2">
                {daySlots.map((s) => (
                  <div
                    key={`${s.plan_date}-${s.corner_id}-${s.meal_type}`}
                    className="rounded-xl border p-3"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <div className="text-[13px] font-medium">
                      {s.corner_name} ({s.meal_type})
                    </div>
                    <div className="mt-0.5 text-xs" style={{ color: "var(--ink-muted)" }}>
                      {s.main ?? "메인 미배정"}
                      {s.sides.length > 0 && ` · 부찬: ${s.sides.join(", ")}`}
                      {s.health_garden.length > 0 && ` · 건강가든: ${s.health_garden.join(", ")}`}
                    </div>
                    {s.ingredient_clashes.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {s.ingredient_clashes.map((c, i) => (
                          <li key={`ing-${i}`}>
                            <Badge
                              tone="critical"
                              label={`재료 중복 — ${c.menu_a} ↔ ${c.menu_b}: ${c.shared.join(", ")}`}
                            />
                          </li>
                        ))}
                      </ul>
                    )}
                    {s.vector_clashes.length > 0 && (
                      <ul className="mt-1 space-y-1">
                        {s.vector_clashes.map((c, i) => (
                          <li key={`vec-${i}`}>
                            <Badge tone="warning" label={`${c.label_ko} 중복 — ${c.menu_a} ↔ ${c.menu_b}`} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {clashDates.length > CLASH_DAY_PREVIEW_COUNT && (
        <button
          className="mt-3 text-xs underline"
          style={{ color: "var(--accent)" }}
          onClick={() => setShowAllClashDays((v) => !v)}
        >
          {showAllClashDays ? "접기" : `전체 ${clashDates.length}일 보기`}
        </button>
      )}
    </>
  );
}

/**
 * §82: "메뉴 중복 점검" 3개 카드(재편성 점검/부찬 반복 랭킹/한 끼 겹침)를
 * 담당자가 "1개로 통합해서 남김"으로 확정한 데 따라 하나의 카드 안 탭
 * 전환으로 묶었다 — 세 패널은 서로 상태를 공유하지 않고(날짜 범위도
 * 각자 관리) API 호출도 독립적이라 로직은 그대로 두고 카드 껍데기만
 * 합쳤다. 탭을 바꾸면 안 보이는 패널은 언마운트돼(다시 돌아오면 재요청)
 * 페이지 로드 시 동시에 나가던 쿼리가 3개에서 1개(기본 탭)로 준다.
 */
function MenuDuplicationCheckSection() {
  const [activeTab, setActiveTab] = useState<"rotation" | "repeated" | "clash">("rotation");
  return (
    <Card title="메뉴 중복 점검">
      <div className="mb-4">
        <SegmentedControl
          value={activeTab}
          options={[
            { label: "재편성 점검", value: "rotation" },
            { label: "부찬 반복 랭킹", value: "repeated" },
            { label: "한 끼 겹침", value: "clash" },
          ]}
          onChange={setActiveTab}
        />
      </div>
      {activeTab === "rotation" && <RotationCheckPanel />}
      {activeTab === "repeated" && <RepeatedSideDishPanel />}
      {activeTab === "clash" && <MealClashPanel />}
    </Card>
  );
}

// §86: "편성 빈도 × 성과"가 만족도·VoE 탭의 "메뉴별 분석"(4분면, 취식 데이터
// 기준 만족도×수요)과 겹쳐 보인다는 피드백 — 산점도/감편·증편 4분류는 완전히
// 지우고, 편성 주기 자체에 집중한 두 리스트로 바꾼다: 그 메뉴의 평균 편성
// 주기가 원래 짧은 메뉴, 그리고 평균 주기 대비 한참 안 나온(나올 때가 됐는데
// 안 나온) 메뉴. 둘 다 weekly_menu_plan(편성 이력) 기준이라 "재편성 점검"
// 탭(RotationCheckPanel)과 데이터 소스는 같지만, 그쪽은 "이번에 재편성된 게
// 얼마나 일렀나"(인스턴스 단위)를 보고 이 화면은 "그 메뉴 자체의 평균 주기가
// 짧은지" / "아예 재편성이 안 됐는지"(메뉴 단위)를 본다 — 서로 다른 질문이라
// 중복이 아니다.
const OVERDUE_PREVIEW_COUNT = 12;

function MenuPlanPerformanceSection() {
  const { days, setDays, periodStart, periodEnd } = usePlanPeriod();
  const [showAllOverdue, setShowAllOverdue] = useState(false);
  const query = useQuery({
    queryKey: ["menu-plan-rotation-frequency", periodStart, periodEnd],
    queryFn: () => api.weeklyMenuRotation({ period_start: periodStart, period_end: periodEnd }),
  });

  const shortestCycleMenus = query.data?.shortest_cycle_menus ?? [];
  const overdueMenus = query.data?.overdue_menus ?? [];

  return (
    <Card title="편성 빈도 × 성과 — 편성 주기 점검">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        메인메뉴 기준, 그 메뉴 자체의 평균 편성 주기로 봅니다.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          조회 기간
        </span>
        <SegmentedControl value={days} options={PLAN_PERIOD_OPTIONS} onChange={setDays} />
      </div>

      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && shortestCycleMenus.length === 0 && overdueMenus.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
          이 기간에 판정할 만한 편성 이력이 없습니다.
        </p>
      )}

      {query.data && shortestCycleMenus.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            편성 주기가 짧은 메뉴 (평균 주기 짧은 순)
          </p>
          <Table
            columns={[
              { key: "menu", label: "메뉴(코너)" },
              { key: "interval", label: "평균 주기", align: "right" },
              { key: "count", label: "편성 횟수", align: "right" },
              { key: "last", label: "최근 편성일", align: "right" },
            ]}
            rows={shortestCycleMenus.map((r) => ({
              menu: `${r.menu_name} (${r.corner_name})`,
              interval: `${r.avg_interval_days}일`,
              count: `${r.occurrence_count}회`,
              last: r.last_date.slice(5),
            }))}
            rowKey={(r) => r.menu as string}
          />
        </div>
      )}

      {query.data && overdueMenus.length > 0 && (
        <div>
          <p className="mb-2 text-xs" style={{ color: "var(--ink-muted)" }}>
            나올 때가 됐는데 안 나온 메뉴 (평균 주기 대비 오래 안 나온 순)
          </p>
          <Table
            columns={[
              { key: "menu", label: "메뉴(코너)" },
              { key: "interval", label: "평균 주기", align: "right" },
              { key: "last", label: "마지막 편성일", align: "right" },
              { key: "since", label: "경과일", align: "right" },
            ]}
            rows={(showAllOverdue ? overdueMenus : overdueMenus.slice(0, OVERDUE_PREVIEW_COUNT)).map((r) => ({
              menu: `${r.menu_name} (${r.corner_name})`,
              interval: `${r.avg_interval_days}일`,
              last: r.last_date.slice(5),
              since: `${r.days_since_last}일`,
            }))}
            rowKey={(r) => r.menu as string}
          />
          {overdueMenus.length > OVERDUE_PREVIEW_COUNT && (
            <button
              className="mt-2 text-xs underline"
              style={{ color: "var(--accent)" }}
              onClick={() => setShowAllOverdue((v) => !v)}
            >
              {showAllOverdue ? "접기" : `전체 ${overdueMenus.length}개 보기`}
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

// §75: 랭킹 표를 기본 top5 상승/top5 하락만 보여주고 나머지는 펼치기로 미룬다
// — 날씨유형·계절 랭킹 둘 다 같은 헬퍼로 일관되게 처리한다. 기존 |diff|
// 내림차순 정렬(rows)은 그대로 두고, 접힌 상태에서 보여줄 부분집합만 뽑는다.
function topMoversAndFallers<T>(rows: T[], getDiff: (row: T) => number | null, n = 5): T[] {
  const risers = rows
    .filter((r) => (getDiff(r) ?? 0) > 0)
    .sort((a, b) => (getDiff(b) as number) - (getDiff(a) as number))
    .slice(0, n);
  const fallers = rows
    .filter((r) => (getDiff(r) ?? 0) < 0)
    .sort((a, b) => (getDiff(a) as number) - (getDiff(b) as number))
    .slice(0, n);
  return [...risers, ...fallers];
}

// §71: 메인메뉴 × 날씨유형 랭킹 탭 — 담당자 요청 예시 그대로("비오면 김치찌개…
// 폭설이면… 폭염이면 메밀소바…") 네 유형을 눌러가며 훑어보는 멘탈모델.
const MENU_WEATHER_EVENT_TABS: WeatherEvent[] = ["비", "폭설", "폭염", "한파"];
// §72: 메인메뉴 × 계절 랭킹 탭 — "냉면은 여름에, 팥죽은 겨울에" 같은 계절
// 음식 패턴을 훑어보는 멘탈모델. 날씨유형과 별개 블록(비교 기준이 다름).
const MENU_SEASON_TABS: Season[] = ["봄", "여름", "가을", "겨울"];

// §84: 시나리오 선택기 6종(맑음/흐림/비/눈/폭염/한파) — 백엔드 Weather enum과
// 순서를 맞춘다.
const SCENARIO_WEATHER_OPTIONS: Weather[] = ["맑음", "흐림", "비", "눈", "폭염", "한파"];
const SCENARIO_MEAL_TYPES: MealType[] = ["조식", "중식", "석식"];

// §84: 랭킹 블록(WeatherCorrelationSection)의 WeatherEvent 분류는 과거 실측
// 이벤트(비/폭설/폭염/한파) 전용이라 시나리오의 "맑음"/"흐림"과 대응하는 항목이
// 없다 — 그 둘을 고르면 랭킹 탭은 동기화하지 않는다(Partial이라 자연히 처리됨).
const WEATHER_TO_EVENT: Partial<Record<Weather, WeatherEvent>> = {
  비: "비",
  폭염: "폭염",
  한파: "한파",
  눈: "폭설", // §84: Weather의 "눈"과 WeatherEvent의 "폭설"만 이름이 다르다
};

/** §84: 기존 고아 상태였던 POST /simulation/what-if 예측 엔진을 재사용해
 * 날씨 시나리오별 예상 식수를 보여준다. 선택한 날씨를 onWeatherChange로 부모에
 * 올려 아래 실측 랭킹 탭과 단방향 동기화한다. */
function WeatherScenarioForecastSection({ onWeatherChange }: { onWeatherChange?: (weather: Weather) => void }) {
  const [targetDate, setTargetDate] = useState(PERIOD_END);
  const [mealType, setMealType] = useState<MealType>("중식");
  const [selectedWeather, setSelectedWeather] = useState<Weather>("맑음");
  const [showCornerBreakdown, setShowCornerBreakdown] = useState(false);
  const chartTheme = useChartTheme();

  useEffect(() => {
    onWeatherChange?.(selectedWeather);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWeather]);

  const whatIfQuery = useQuery({
    queryKey: ["what-if-scenario", targetDate, mealType, selectedWeather],
    queryFn: () => api.whatIf({ target_date: targetDate, meal_type: mealType, weather: selectedWeather }),
  });

  const corners = whatIfQuery.data?.corners ?? [];
  const predictedSum = corners.reduce((sum, c) => sum + c.predicted_headcount, 0);
  const baselineSum = corners.reduce((sum, c) => sum + c.baseline_headcount, 0);
  const pctDiff = baselineSum > 0 ? ((predictedSum - baselineSum) / baselineSum) * 100 : null;
  const pctArrow = pctDiff == null ? "→" : pctDiff > 0.5 ? "↑" : pctDiff < -0.5 ? "↓" : "→";

  const sortedCorners = [...corners].sort((a, b) => b.predicted_headcount - a.predicted_headcount);
  const cornerBreakdownOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 8, right: 56, top: 8, bottom: 28, containLabel: true },
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
    xAxis: {
      type: "value" as const,
      name: "식수(명)",
      axisLabel: { color: chartTheme.text },
      splitLine: { lineStyle: { color: chartTheme.grid } },
    },
    yAxis: {
      type: "category" as const,
      inverse: true,
      data: sortedCorners.map((c) => c.corner_name),
      axisLabel: { color: chartTheme.text },
      axisLine: { lineStyle: { color: chartTheme.axis } },
    },
    series: [
      {
        name: "예상 식수",
        type: "bar" as const,
        itemStyle: { color: resolveColor("var(--series-1)") },
        label: { show: true, position: "right" as const, color: chartTheme.text, formatter: "{c}명" },
        data: sortedCorners.map((c) => Math.round(c.predicted_headcount * 10) / 10),
      },
    ],
  };

  return (
    <Card title="날씨 시나리오 예측">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        날씨·끼니·날짜를 골라 예상 식수를 시뮬레이션합니다(추정치).
      </p>
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          날씨
          <SegmentedControl
            value={selectedWeather}
            options={SCENARIO_WEATHER_OPTIONS.map((w) => ({ label: w, value: w }))}
            onChange={setSelectedWeather}
          />
        </div>
        <div className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          끼니
          <SegmentedControl
            value={mealType}
            options={SCENARIO_MEAL_TYPES.map((m) => ({ label: m, value: m }))}
            onChange={setMealType}
          />
        </div>
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          날짜
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
          />
        </label>
      </div>

      {whatIfQuery.isLoading && <LoadingState />}
      {whatIfQuery.isError && <ErrorState error={whatIfQuery.error} />}

      {whatIfQuery.data && (
        <>
          <StatTile
            label="예상 총 식수"
            value={`${Math.round(predictedSum).toLocaleString()}명`}
            sub={pctDiff == null ? "평시 데이터 없음" : `평시 대비 ${pctArrow} ${Math.abs(pctDiff).toFixed(1)}%`}
          />
          <button
            className="mt-3 text-xs underline"
            style={{ color: "var(--accent)" }}
            onClick={() => setShowCornerBreakdown((v) => !v)}
          >
            {showCornerBreakdown ? "코너별 예측 접기" : "코너별 예측 보기"}
          </button>
          {showCornerBreakdown && sortedCorners.length > 0 && (
            <ReactECharts
              option={cornerBreakdownOption}
              style={{ height: Math.max(160, sortedCorners.length * 32), marginTop: 12 }}
            />
          )}
        </>
      )}
    </Card>
  );
}

export function WeatherCorrelationSection({ syncedEvent }: { syncedEvent?: WeatherEvent } = {}) {
  const [periodStart, setPeriodStart] = useState(PERIOD_START);
  const [periodEnd, setPeriodEnd] = useState(PERIOD_END);
  const [selectedEvent, setSelectedEvent] = useState<WeatherEvent>("비");
  const [selectedSeason, setSelectedSeason] = useState<Season>("여름");
  const [showAllWeatherRanking, setShowAllWeatherRanking] = useState(false);
  const [showAllSeasonRanking, setShowAllSeasonRanking] = useState(false);
  const [correlationMetric, setCorrelationMetric] = useState<WeatherCorrelationMetric>("max_temp_c");
  const [showAllCorrelationRanking, setShowAllCorrelationRanking] = useState(false);

  // §84: 위 시나리오 선택기(WeatherScenarioForecastSection)가 넘긴 날씨를 이
  // 랭킹 탭에도 반영 — 대응하는 WeatherEvent가 없는 "맑음"/"흐림"을 고르면
  // syncedEvent가 undefined라 아무 일도 안 하고 현재 탭을 유지한다.
  useEffect(() => {
    if (syncedEvent) {
      setSelectedEvent(syncedEvent);
      setShowAllWeatherRanking(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncedEvent]);

  const menuRankingQuery = useQuery({
    queryKey: ["menu-weather-event-ranking", periodStart, periodEnd, selectedEvent],
    // §76: 담당자 요청으로 중식 고정 — 조/중/석식을 합쳐 보면 기저 식수 규모가
    // 달라 날씨유형 간 비교가 흐려진다는 문제의식(§75 timeline과 동일)과 같은
    // 맥락. 계절 랭킹(menuSeasonQuery)은 이번 요청 대상이 아니라 그대로 둔다.
    queryFn: () =>
      api.menuWeatherEventRanking({
        period_start: periodStart,
        period_end: periodEnd,
        event: selectedEvent,
        meal_type: "중식",
      }),
  });
  const menuRankingRows = menuRankingQuery.data?.rows ?? [];
  const extendedFieldsMissing = menuRankingQuery.data?.extended_fields_missing ?? false;
  const actualMetricLabel = menuRankingQuery.data?.actual_metric_label;
  const weatherRankingCollapsed = topMoversAndFallers(menuRankingRows, (r) => r.diff_vs_normal);
  const visibleWeatherRankingRows = showAllWeatherRanking ? menuRankingRows : weatherRankingCollapsed;

  const menuSeasonQuery = useQuery({
    queryKey: ["menu-season-ranking", periodStart, periodEnd, selectedSeason],
    queryFn: () =>
      api.menuSeasonRanking({ period_start: periodStart, period_end: periodEnd, season: selectedSeason }),
  });
  const menuSeasonRows = menuSeasonQuery.data?.rows ?? [];
  const seasonRankingCollapsed = topMoversAndFallers(menuSeasonRows, (r) => r.diff_vs_overall);
  const visibleSeasonRankingRows = showAllSeasonRanking ? menuSeasonRows : seasonRankingCollapsed;

  // §81: "기온/강수량이 오를수록 식수가 느는 메뉴가 있는지" — 연속값 상관계수
  // 랭킹. correlation 자체가 이미 -1~1 부호 있는 값이라 topMoversAndFallers를
  // 그대로 재사용해 양의 상관 top5 / 음의 상관 top5로 접는다.
  const correlationRankingQuery = useQuery({
    queryKey: ["menu-weather-correlation-ranking", periodStart, periodEnd, correlationMetric],
    queryFn: () =>
      api.menuWeatherCorrelationRanking({
        period_start: periodStart,
        period_end: periodEnd,
        metric: correlationMetric,
        meal_type: "중식",
      }),
  });
  const correlationRows = correlationRankingQuery.data?.rows ?? [];
  const correlationRankingCollapsed = topMoversAndFallers(correlationRows, (r) => r.correlation);
  const visibleCorrelationRows = showAllCorrelationRanking ? correlationRows : correlationRankingCollapsed;

  return (
    <Card title="날씨·계절별 메뉴 식수 랭킹">
      <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
        기간을 골라 날씨유형/계절/기온·강수량별 메뉴 식수 랭킹을 확인하세요.
      </p>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          시작일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={periodStart}
            max={periodEnd}
            onChange={(e) => setPeriodStart(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          종료일
          <input
            type="date"
            className="rounded-md border px-3 py-2 text-[13px]"
            style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            value={periodEnd}
            min={periodStart}
            onChange={(e) => setPeriodEnd(e.target.value)}
          />
        </label>
      </div>

      <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-[14px] font-semibold">메인메뉴 × 날씨유형 인기 랭킹 (중식 기준)</h3>
        <p className="mb-3 mt-1 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          메인메뉴가 그 날씨유형의 날 평상시 대비 식수가 얼마나 달랐는지 랭킹입니다(참고용).
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {MENU_WEATHER_EVENT_TABS.map((eventOption) => (
            <button
              key={eventOption}
              onClick={() => {
                setSelectedEvent(eventOption);
                setShowAllWeatherRanking(false);
              }}
              className="rounded-full border px-3 py-1.5 text-[13px] transition-colors"
              style={{
                borderColor: selectedEvent === eventOption ? "var(--accent)" : "var(--border)",
                background: selectedEvent === eventOption ? "var(--surface-2)" : "var(--surface)",
                fontWeight: selectedEvent === eventOption ? 600 : 400,
              }}
            >
              {eventOption}
            </button>
          ))}
        </div>

        {menuRankingQuery.isLoading && <LoadingState />}
        {menuRankingQuery.isError && <ErrorState error={menuRankingQuery.error} />}

        {menuRankingQuery.data && menuRankingRows.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {extendedFieldsMissing && selectedEvent !== "비" ? (
              <>
                적설량·기온 데이터가 아직 없습니다. <code>scripts/import_weather_csv.py backfill
                --write-db</code>로 날씨 데이터를 다시 백필해야 폭설/폭염/한파 분류가 가능합니다.
              </>
            ) : (
              `이 기간에 "${selectedEvent}" 유형인 날이 없거나, 그 날 취식 기록이 없습니다.`
            )}
          </p>
        )}

        {menuRankingRows.length > 0 && (
          <>
            <Table
              columns={[
                { key: "menu_name", label: "메뉴명" },
                { key: "event_avg_headcount", label: `${selectedEvent} 평균`, align: "right" },
                { key: "diff", label: "평상시 대비", align: "right" },
                { key: "actual_avg", label: actualMetricLabel ?? "실측 평균", align: "right" },
                { key: "event_days", label: "표본(일)", align: "right" },
              ]}
              rows={visibleWeatherRankingRows.map((r) => ({
                key: String(r.menu_id),
                menu_name: r.low_sample ? (
                  <span style={{ color: "var(--ink-muted)" }}>{r.menu_name ?? "이름 없음"}</span>
                ) : (
                  r.menu_name ?? "이름 없음"
                ),
                event_avg_headcount: `${r.event_avg_headcount}명`,
                diff:
                  r.diff_vs_normal == null ? (
                    <Badge label="표본 부족" tone="muted" />
                  ) : (
                    <Badge
                      label={`${r.diff_vs_normal > 0 ? "↑+" : r.diff_vs_normal < 0 ? "↓" : "→"}${r.diff_vs_normal}명`}
                      tone={Math.abs(r.diff_vs_normal) >= 3 ? (r.diff_vs_normal > 0 ? "good" : "critical") : "muted"}
                    />
                  ),
                actual_avg: r.actual_avg ?? "-",
                event_days: `${r.event_days}일`,
              }))}
              rowKey={(r) => r.key as string}
            />
            {menuRankingRows.length > weatherRankingCollapsed.length && (
              <button
                className="mt-2 text-xs underline"
                style={{ color: "var(--accent)" }}
                onClick={() => setShowAllWeatherRanking((v) => !v)}
              >
                {showAllWeatherRanking ? "접기" : `전체 ${menuRankingRows.length}개 보기`}
              </button>
            )}
          </>
        )}
      </div>

      <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-[14px] font-semibold">메인메뉴 × 계절 인기 랭킹</h3>
        <p className="mb-3 mt-1 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          메인메뉴가 그 계절에 전체 기간 평균 대비 식수가 얼마나 달랐는지 랭킹입니다(여러 해 합산).
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {MENU_SEASON_TABS.map((seasonOption) => (
            <button
              key={seasonOption}
              onClick={() => {
                setSelectedSeason(seasonOption);
                setShowAllSeasonRanking(false);
              }}
              className="rounded-full border px-3 py-1.5 text-[13px] transition-colors"
              style={{
                borderColor: selectedSeason === seasonOption ? "var(--accent)" : "var(--border)",
                background: selectedSeason === seasonOption ? "var(--surface-2)" : "var(--surface)",
                fontWeight: selectedSeason === seasonOption ? 600 : 400,
              }}
            >
              {seasonOption}
            </button>
          ))}
        </div>

        {menuSeasonQuery.isLoading && <LoadingState />}
        {menuSeasonQuery.isError && <ErrorState error={menuSeasonQuery.error} />}

        {menuSeasonQuery.data && menuSeasonRows.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 기간에 "{selectedSeason}"에 해당하는 취식 기록이 없습니다.
          </p>
        )}

        {menuSeasonRows.length > 0 && (
          <>
            <Table
              columns={[
                { key: "menu_name", label: "메뉴명" },
                { key: "season_avg_headcount", label: `${selectedSeason} 평균`, align: "right" },
                { key: "diff", label: "전체 평균 대비", align: "right" },
                { key: "season_days", label: "표본(일)", align: "right" },
              ]}
              rows={visibleSeasonRankingRows.map((r) => ({
                key: String(r.menu_id),
                menu_name: r.low_sample ? (
                  <span style={{ color: "var(--ink-muted)" }}>{r.menu_name ?? "이름 없음"}</span>
                ) : (
                  r.menu_name ?? "이름 없음"
                ),
                season_avg_headcount: `${r.season_avg_headcount}명`,
                diff:
                  r.diff_vs_overall == null ? (
                    <Badge label="표본 부족" tone="muted" />
                  ) : (
                    <Badge
                      label={`${r.diff_vs_overall > 0 ? "↑+" : r.diff_vs_overall < 0 ? "↓" : "→"}${r.diff_vs_overall}명`}
                      tone={Math.abs(r.diff_vs_overall) >= 3 ? (r.diff_vs_overall > 0 ? "good" : "critical") : "muted"}
                    />
                  ),
                season_days: `${r.season_days}일`,
              }))}
              rowKey={(r) => r.key as string}
            />
            {menuSeasonRows.length > seasonRankingCollapsed.length && (
              <button
                className="mt-2 text-xs underline"
                style={{ color: "var(--accent)" }}
                onClick={() => setShowAllSeasonRanking((v) => !v)}
              >
                {showAllSeasonRanking ? "접기" : `전체 ${menuSeasonRows.length}개 보기`}
              </button>
            )}
          </>
        )}
      </div>

      {/* §81: "기온/강수량이 높은 날 식수가 늘어나는 메뉴가 있는지" 담당자 질문에
          대한 답 — 위 두 랭킹(임계값 범주 비교)과 달리 연속값 상관계수를 낸다. */}
      <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-[14px] font-semibold">기온/강수량 × 식수 상관관계</h3>
        <p className="mb-3 mt-1 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          메인메뉴 식수와 기온·강수량의 상관계수(-1~1)입니다. 인과관계 아님 — 표본{" "}
          {correlationRankingQuery.data?.min_days ?? 5}일 미만은 제외했습니다.
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {(
            [
              ["max_temp_c", "최고기온"],
              ["precip_mm", "강수량"],
            ] as [WeatherCorrelationMetric, string][]
          ).map(([metricOption, metricLabel]) => (
            <button
              key={metricOption}
              onClick={() => {
                setCorrelationMetric(metricOption);
                setShowAllCorrelationRanking(false);
              }}
              className="rounded-full border px-3 py-1.5 text-[13px] transition-colors"
              style={{
                borderColor: correlationMetric === metricOption ? "var(--accent)" : "var(--border)",
                background: correlationMetric === metricOption ? "var(--surface-2)" : "var(--surface)",
                fontWeight: correlationMetric === metricOption ? 600 : 400,
              }}
            >
              {metricLabel}
            </button>
          ))}
        </div>

        {correlationRankingQuery.isLoading && <LoadingState />}
        {correlationRankingQuery.isError && <ErrorState error={correlationRankingQuery.error} />}

        {correlationRankingQuery.data && correlationRows.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 기간엔 표본이 충분한 메뉴가 없어 상관관계를 계산할 수 없습니다.
          </p>
        )}

        {correlationRows.length > 0 && (
          <>
            <Table
              columns={[
                { key: "menu_name", label: "메뉴명" },
                { key: "correlation", label: "상관계수", align: "right" },
                { key: "sample_size", label: "표본(일)", align: "right" },
              ]}
              rows={visibleCorrelationRows.map((r) => ({
                key: String(r.menu_id),
                menu_name: r.menu_name ?? "이름 없음",
                correlation: (
                  <Badge
                    label={`${r.correlation > 0 ? "↑+" : r.correlation < 0 ? "↓" : "→"}${r.correlation}`}
                    tone={Math.abs(r.correlation) >= 0.5 ? (r.correlation > 0 ? "good" : "critical") : "muted"}
                  />
                ),
                sample_size: `${r.sample_size}일`,
              }))}
              rowKey={(r) => r.key as string}
            />
            {correlationRows.length > correlationRankingCollapsed.length && (
              <button
                className="mt-2 text-xs underline"
                style={{ color: "var(--accent)" }}
                onClick={() => setShowAllCorrelationRanking((v) => !v)}
              >
                {showAllCorrelationRanking ? "접기" : `전체 ${correlationRows.length}개 보기`}
              </button>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

// ---- 2026-08 화면 재편으로 생긴 최상위 화면 3개 ----
// 기존 "분석" 탭(서브탭 5개)을 해체하고, 담당자 협의에서 정한 5개 축
// (현황 / 메뉴 편성·운영 / 만족도·VoE / Agent 채팅 / 관리)에 맞춰 재배치했다.

/** 메뉴 편성·운영 — "다음 주 식단을 어떻게 짤까"에 답하는 화면. */
export function MenuPlanningPage() {
  return (
    <div className="space-y-6">
      <WeeklyMenuReviewTab />
      <MenuDuplicationCheckSection />
      <MenuPlanPerformanceSection />
      <MenuComboSection />
    </div>
  );
}

/** 시뮬레이션 — 날씨 예측(시나리오 what-if) + 실측 검증/참고 화면. §77~§79에선
 * "메뉴 편성·운영" 탭 안에 라벨 섹션으로만 구분해뒀는데, 담당자가 진짜 별도
 * 탭을 요청해(§81) 여기로 옮겼다 — 2026-08에 없앴던 "시뮬레이션" 탭을 날씨
 * 콘텐츠 한정으로 되살린 것(그때 흡수된 "사내 행사" 토글 등 다른 기능은
 * 복원하지 않음). §84에서 고아 상태였던 what-if 예측 엔진을 시나리오 선택기로
 * 배선하고, 선택한 날씨를 아래 실측 랭킹 탭과 단방향으로 동기화한다. */
export function SimulationPage() {
  const [selectedWeather, setSelectedWeather] = useState<Weather>("맑음");
  return (
    <div className="space-y-6">
      <WeatherScenarioForecastSection onWeatherChange={setSelectedWeather} />
      <WeatherCorrelationSection syncedEvent={WEATHER_TO_EVENT[selectedWeather]} />
    </div>
  );
}

/** 만족도·VoE — "무엇이 좋았고 무엇이 불만인가"에 답하는 화면. */
export function SatisfactionVoePage() {
  return (
    <div className="space-y-6">
      <MenuQuadrantTab />
      <VoeAnalysisTab />
    </div>
  );
}

/**
 * 관리 — 일상 운영 동선에서 치워 둔 관리자용 도구 모음.
 * 주의: 이 앱에는 로그인/권한 체계가 없다. 이 탭은 **접근 제한이 아니라
 * 메인 화면 정리 목적**이며, 화면에도 그렇게 명시한다(협의 결정, 2026-08).
 */
export function AdminPage() {
  const [exportStart, setExportStart] = useState(isoDaysAgo(30));
  const [exportEnd, setExportEnd] = useState(isoDaysAgo(0));
  const mealLogExportUrl = `/api/dashboard/meal-log/export?period_start=${exportStart}&period_end=${exportEnd}`;
  return (
    <div className="space-y-6">
      <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
        자주 쓰지 않는 관리 기능 모음입니다.
      </p>
      <MenuFoodVectorAdminSection />
      <Card title="전체 취식 데이터 다운로드 (기간 선택)">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          선택한 기간의 개별 취식 기록을 엑셀로 내려받습니다.
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
