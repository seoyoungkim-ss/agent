import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import {
  api,
  type Classification,
  type Division,
  type Granularity,
  type HeadcountGroupBy,
  type MealType,
  type MenuTrendEntry,
} from "../api/client";
import {
  Button,
  Card,
  ErrorState,
  LoadingState,
  QuadrantBadge,
  resolveColor,
  SegmentedControl,
  StatTile,
  Table,
  useChartTheme,
} from "../components/ui";
import { CornerMetricComparisonSection } from "./AnalysisPage";
import { addDays, isoDaysAgo, mondayOf } from "../lib/week";

// 니치 코너(Take Out/미캠회관/그린미트)를 범례에서 기본 숨기던 규칙은 제거됐다
// (2026-08 현황 재편) — 통합 추이 차트에 명시적인 "코너 필터"가 생겨, 숨겨진
// 기본값보다 사용자가 직접 고르는 쪽이 더 분명하다.

// 메뉴 하이라이트 카드의 날짜 표시 — "YYYY-MM-DD" → "M/D".
function shortDate(dateIso: string): string {
  const [, m, d] = dateIso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

const RECOMPUTE_PERIOD_START = isoDaysAgo(180); // PRD: 취식 데이터 6개월 누적 기준
const RECOMPUTE_PERIOD_END = isoDaysAgo(0);

const CLASSIFICATION_OPTIONS: { label: string; value: Classification | "전체" }[] = [
  { label: "전체", value: "전체" },
  { label: "평일", value: "평일" },
  { label: "주말+공휴일", value: "주말+공휴일" },
  { label: "패밀리데이", value: "패밀리데이" },
];

const MEAL_TYPE_OPTIONS: MealType[] = ["조식", "중식", "석식"];

/**
 * 만족도 급상승/급하락 목록.
 *
 * 양쪽 날짜를 다 보여준다(2026-08 요청) — "4.03이 언제, 4.27이 언제인지" 둘 다
 * 필요하다. ⚠️ 이 값은 **날짜가 아니라 그 메뉴가 나온 주**다(§28: 메뉴가 매주
 * 나오지 않아 달력 주가 아니라 등장 주끼리 비교한다). 그래서 "7/13 주"처럼
 * 주 단위임이 드러나게 쓴다 — 그냥 "7/13"이면 그날 평가된 걸로 오해한다.
 *
 * 원인은 새벽 배치가 미리 계산해 둔 것을 읽기만 한다(화면에서 LLM을 부르면
 * 홈 로드가 다시 느려진다, §50).
 */
// 백엔드 표본 보정(low_sample_threshold)과는 별개의 **화면 경고** 기준이다.
// 보정을 거쳐도 한 자릿수 표본의 주간 비교는 흔들린다.
const LOW_SAMPLE_WARN_COUNT = 5;

function MenuTrendList({ rows, tone }: { rows: MenuTrendEntry[]; tone: "good" | "critical" }) {
  if (rows.length === 0) {
    return (
      <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
        해당 메뉴가 없습니다.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div
          key={`${r.menu_id}-${i}`}
          className="rounded-md border p-2.5"
          style={{ borderColor: "var(--border)" }}
        >
          <div className="text-[13px] font-medium">
            {r.menu_name}
            {r.corner_name ? (
              <span className="font-normal" style={{ color: "var(--ink-muted)" }}>
                {" "}
                ({r.corner_name})
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 text-xs" style={{ color: "var(--ink-secondary)" }}>
            {r.prior_score.toFixed(2)}
            <span style={{ color: "var(--ink-muted)" }}>
              {" "}
              ({shortDate(r.prior_week)} 주 · {r.prior_evaluation_count}건)
            </span>
            {" → "}
            <span style={{ color: `var(--${tone})`, fontWeight: 600 }}>
              {r.recent_score.toFixed(2)}
            </span>
            <span style={{ color: "var(--ink-muted)" }}>
              {" "}
              ({shortDate(r.recent_week)} 주 · {r.evaluation_count}건)
            </span>
          </div>
          {/* 평가 건수가 한 자릿수면 변화폭이 커도 표본 노이즈일 수 있다 —
              담당자가 숫자만 보고 과잉 반응하지 않게 명시한다. */}
          {Math.min(r.prior_evaluation_count, r.evaluation_count) < LOW_SAMPLE_WARN_COUNT ? (
            <div className="mt-0.5 text-[11px]" style={{ color: "var(--warning)" }}>
              평가 표본이 적어 변화폭이 과장됐을 수 있습니다
            </div>
          ) : null}
          {r.cause ? (
            <p className="mt-1.5 text-xs" style={{ color: "var(--ink-muted)" }}>
              {r.cause}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function HomePage({ onOpenWeeklyVoe }: { onOpenWeeklyVoe?: (monday: string) => void }) {
  const [classification, setClassification] = useState<Classification | "전체">("전체");
  // 조식만 체크하면 조식 기준, 조식+중식 체크하면 둘을 합친 식수 — 최소 1개는
  // 항상 체크돼 있어야 한다(다 끄면 "전체 합산"과 구분이 안 돼 혼동됨, 2026-07).
  const [mealTypeFilter, setMealTypeFilter] = useState<MealType[]>(MEAL_TYPE_OPTIONS);
  function toggleMealType(mealType: MealType) {
    setMealTypeFilter((prev) => {
      if (prev.includes(mealType)) {
        return prev.length > 1 ? prev.filter((m) => m !== mealType) : prev;
      }
      return [...prev, mealType];
    });
  }
  const [menuName, setMenuName] = useState("");
  const [searchedMenu, setSearchedMenu] = useState<string | null>(null);
  const [selectedMonday, setSelectedMonday] = useState(mondayOf(new Date()));
  // 식당은 일요일에 운영하지 않으므로 월~토 6일만 조회한다.
  const saturdayOfSelected = addDays(selectedMonday, 5);

  const weekly = useQuery({
    queryKey: ["weekly-summary", selectedMonday, saturdayOfSelected, classification, mealTypeFilter.join("|")],
    queryFn: () =>
      api.weeklySummary({
        start_date: selectedMonday,
        end_date: saturdayOfSelected,
        classification: classification === "전체" ? undefined : classification,
        meal_types: mealTypeFilter,
      }),
  });

  // §83: "금주 예상 식수"(선택한 주 스코프의 실측 평균 합계) 대신, 어느 주를
  // 보고 있든 안 바뀌는 "최근 7일 식수" 스냅샷 — 분류/끼니 필터 없이 전체
  // 합산으로 오늘 기준 트레일링 7일 실측 식수를 낸다.
  const recentHeadcountQuery = useQuery({
    queryKey: ["recent-headcount-7d"],
    queryFn: () => api.weeklySummary({ start_date: isoDaysAgo(6), end_date: isoDaysAgo(0) }),
  });
  const recentHeadcountTotal = recentHeadcountQuery.data?.reduce((sum, d) => sum + d.headcount, 0) ?? 0;

  const menuHistory = useQuery({
    queryKey: ["menu-history", searchedMenu],
    queryFn: () => api.menuHistory(searchedMenu as string),
    enabled: !!searchedMenu,
  });

  const cornerSummary = useQuery({
    queryKey: ["corner-summary", selectedMonday, saturdayOfSelected],
    queryFn: () => api.cornerAnalysis({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });

  // ---- 통합 식수 추이 (2026-08 현황 재편) ----
  // 조·중·석식 × 코너 × 회사구분 3축을 한 그래프에서 필터한다. 기간 단위는
  // 조회 범위까지 같이 정한다(일=최근 30일 / 주=최근 12주 / 월=최근 12개월) —
  // 위 요약 카드들의 "선택한 주"와 달리 추이는 더 긴 흐름을 봐야 의미가 있다.
  // §81: 기본값을 일간·전체합산에서 주간·코너별로 바꿨다 — 담당자가 매번 켜야
  // 했던 조합을 기본으로 삼는다.
  const [trendGranularity, setTrendGranularity] = useState<Granularity>("weekly");
  const [trendGroupBy, setTrendGroupBy] = useState<HeadcountGroupBy>("corner");
  const [trendCornerIds, setTrendCornerIds] = useState<number[]>([]);
  const [trendDivisions, setTrendDivisions] = useState<Division[]>([]);
  // §80: "OO 일자간 일평균 식수" 요청 — 일간 단위에서만 의미가 있는 선택창.
  const [trendAvgWindow, setTrendAvgWindow] = useState<7 | 14 | 30>(7);
  const TREND_LOOKBACK_DAYS: Record<Granularity, number> = { daily: 30, weekly: 84, monthly: 365 };
  const trendPeriodStart = isoDaysAgo(TREND_LOOKBACK_DAYS[trendGranularity]);
  const trendPeriodEnd = isoDaysAgo(0);

  const cornerListQuery = useQuery({
    queryKey: ["corner-list"],
    queryFn: () => api.cornerList(),
  });

  // §81: 담당자가 지정한 7개 코너를 기본으로 켠 상태로 시작한다. 코너 목록은
  // DB 기반이라(하드코딩된 마스터 리스트 없음) cornerListQuery가 로드된 뒤
  // 이름으로 매칭해 1회만 세팅한다 — 이후 사용자가 직접 껐다 켰다 해도 이
  // 초기화가 다시 개입해 되돌리면 안 되므로 ref 플래그로 한 번만 실행한다.
  const DEFAULT_TREND_CORNER_NAMES = [
    "고슬고슬비빈",
    "모던키친",
    "싱푸차이나",
    "한식사계",
    "동방식객",
    "도담찌개",
  ];
  const trendCornerFilterInitialized = useRef(false);
  useEffect(() => {
    if (trendCornerFilterInitialized.current) return;
    if (!cornerListQuery.data) return;
    trendCornerFilterInitialized.current = true;
    const ids = cornerListQuery.data
      .filter((c) => DEFAULT_TREND_CORNER_NAMES.includes(c.corner_name))
      .map((c) => c.corner_id);
    if (ids.length > 0) setTrendCornerIds(ids);
  }, [cornerListQuery.data]);

  // ---- 코너-메뉴별 예상 식수(실측 평균) / 점유율·대기시간 (2026-08 현황 재편) ----
  // §80: "예상 식수는 오차 리스크가 있을 것 같다"는 담당자 피드백으로 날씨/
  // 메뉴배수 예측(weeklyCongestionForecast)을 걷어내고, 이번 주 편성된
  // 코너-메뉴를 최근 실측 평균 식수로 랭킹하는 가벼운 집계로 바꿨다 — 버튼
  // 게이팅 없이 바로 조회(예측처럼 과거 180일을 슬롯마다 다시 훑지 않음).
  const plannedHeadcountRanking = useQuery({
    queryKey: ["weekly-menu-planned-headcount-ranking", selectedMonday, saturdayOfSelected],
    queryFn: () =>
      api.weeklyMenuPlannedHeadcountRanking({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });
  // 일간 × 코너별로 볼 때 툴팁에 그날 그 코너의 메인메뉴를 덧붙인다(2026-07 요청,
  // 코너별 주간 추이 차트에 있던 기능을 통합 차트로 옮겨옴). 그 조합일 때만 조회한다.
  const trendMainMenuEnabled = trendGranularity === "daily" && trendGroupBy === "corner";
  const cornerMainMenu = useQuery({
    queryKey: ["corner-main-menu-by-date", trendPeriodStart, trendPeriodEnd],
    queryFn: () => api.cornerMainMenuByDate({ period_start: trendPeriodStart, period_end: trendPeriodEnd }),
    enabled: trendMainMenuEnabled,
  });
  const headcountTrend = useQuery({
    queryKey: [
      "headcount-trend",
      trendPeriodStart,
      trendPeriodEnd,
      trendGranularity,
      trendGroupBy,
      mealTypeFilter.join("|"),
      trendCornerIds.join("|"),
      trendDivisions.join("|"),
      classification,
    ],
    queryFn: () =>
      api.headcountTrend({
        period_start: trendPeriodStart,
        period_end: trendPeriodEnd,
        granularity: trendGranularity,
        group_by: trendGroupBy,
        meal_types: mealTypeFilter,
        corner_ids: trendCornerIds.length > 0 ? trendCornerIds : undefined,
        divisions: trendDivisions.length > 0 ? trendDivisions : undefined,
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

  // 패밀리데이 월별 추이 카드는 제거됐다(2026-08 현황 재편) — 아래 "식수 추이"
  // 통합 차트에서 classification=패밀리데이 + 기간단위=월간으로 같은 걸 볼 수 있다.

  // 코너-메뉴별 예상 식수 랭킹 가로막대 — §80: 이번 주 편성된 MAIN 슬롯을
  // 최근 실측 평균 식수(내림차순, 백엔드가 이미 정렬)로 그린다. 이력 없는
  // 신메뉴(recent_avg_headcount === null)는 막대 대신 별도 안내 문구로
  // 뺀다(0으로 그리면 "정말 안 먹힘"과 혼동된다).
  const plannedHeadcountRows = plannedHeadcountRanking.data?.rows ?? [];
  const plannedHeadcountBars = plannedHeadcountRows.filter((r) => r.recent_avg_headcount != null);
  // §83: "최고 혼잡 예상 코너/메뉴" 대신 실측 기준 최고 식수 코너/메뉴 —
  // 백엔드가 이미 recent_avg_headcount 내림차순으로 정렬해 주므로 첫 행이
  // 바로 최고 식수 행이다.
  const topPlannedHeadcountRow = plannedHeadcountBars[0] ?? null;

  // 툴팁은 시리즈 "이름"(코너명)만 알 수 있는데 main-menu-by-date는 corner_id로
  // 오므로, 코너 목록으로 id→이름을 옮겨 코너명 기준 키로 맞춘다.
  const cornerNameById = new Map((cornerListQuery.data ?? []).map((c) => [c.corner_id, c.corner_name]));
  const mainMenuByCornerDate = new Map(
    (cornerMainMenu.data ?? []).map((r) => [
      `${cornerNameById.get(r.corner_id) ?? r.corner_id}|${r.plan_date}`,
      r.menu_name,
    ]),
  );

  // 통합 식수 추이 차트 — series_key로 시리즈를 가르고 period를 x축으로 쓴다.
  const trendRows = headcountTrend.data ?? [];
  const trendPeriods = [...new Set(trendRows.map((r) => r.period))].sort();
  const trendSeriesMeta = new Map<string, string>();
  for (const r of trendRows) trendSeriesMeta.set(r.series_key, r.series_label);
  const trendValueBySeries = new Map<string, Map<string, number>>();
  for (const r of trendRows) {
    if (!trendValueBySeries.has(r.series_key)) trendValueBySeries.set(r.series_key, new Map());
    trendValueBySeries.get(r.series_key)!.set(r.period, r.headcount);
  }
  // 시리즈가 많으면(코너별 등) 색이 뒤섞이지 않게 series_key 기준으로 색을 고정한다.
  const trendSeriesKeys = [...trendSeriesMeta.keys()].sort();
  const headcountTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue?: string; marker: string; seriesName: string; value: unknown }[]) => {
        const header = params[0]?.axisValue ?? "";
        const lines = params.map((p) => {
          const v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
          const menu = trendMainMenuEnabled ? mainMenuByCornerDate.get(`${p.seriesName}|${header}`) : undefined;
          const menuLine = menu ? `<br/>&nbsp;&nbsp;메뉴: ${menu}` : "";
          return `${p.marker}${p.seriesName}: ${typeof v === "number" ? Math.round(v) : v}명${menuLine}`;
        });
        return [header, ...lines].join("<br/>");
      },
    },
    legend: { top: 0, textStyle: { color: chartTheme.text }, data: trendSeriesKeys.map((k) => trendSeriesMeta.get(k)!) },
    xAxis: {
      type: "category",
      data: trendPeriods,
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
    series: trendSeriesKeys.map((key, i) => {
      const color = resolveColor(`var(--series-${(i % 8) + 1})`);
      return {
        name: trendSeriesMeta.get(key)!,
        // §80: 담당자 요청으로 선그래프 대신 누적 막대그래프로 표현한다
        // (forecastByCornerOption에서 이미 쓰던 stack 패턴과 동일).
        type: "bar" as const,
        stack: "total",
        itemStyle: { color },
        data: trendPeriods.map((p) => trendValueBySeries.get(key)?.get(p) ?? 0),
      };
    }),
  };

  // §80: "OO 일자간 일평균 식수" — 일간 단위일 때만 최근 N일 평균을 보여준다
  // (이미 가져온 trendRows/trendPeriods를 클라이언트에서 합산하는 것뿐이라
  // 새 백엔드 호출이 필요 없다).
  const totalHeadcountByPeriod = new Map<string, number>();
  for (const r of trendRows) totalHeadcountByPeriod.set(r.period, (totalHeadcountByPeriod.get(r.period) ?? 0) + r.headcount);
  const trendRecentPeriods = trendPeriods.slice(-trendAvgWindow);
  const trendRecentAvg =
    trendRecentPeriods.length > 0
      ? trendRecentPeriods.reduce((sum, p) => sum + (totalHeadcountByPeriod.get(p) ?? 0), 0) / trendRecentPeriods.length
      : null;

  const exportUrl = `/api/dashboard/weekly-summary/export?start_date=${selectedMonday}&end_date=${saturdayOfSelected}${
    classification !== "전체" ? `&classification=${encodeURIComponent(classification)}` : ""
  }${mealTypeFilter.map((m) => `&meal_types=${encodeURIComponent(m)}`).join("")}`;

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
          <div className="flex items-center gap-2 rounded-md border px-2.5 py-1.5" style={{ borderColor: "var(--border)" }}>
            {MEAL_TYPE_OPTIONS.map((mealType) => (
              <label key={mealType} className="flex items-center gap-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                <input
                  type="checkbox"
                  checked={mealTypeFilter.includes(mealType)}
                  onChange={() => toggleMealType(mealType)}
                />
                {mealType}
              </label>
            ))}
          </div>
          <a href={exportUrl} download>
            <Button variant="secondary">엑셀 다운로드</Button>
          </a>
        </div>
      </div>

      {weekly.data && weekly.data.length > 0 && totalHeadcount === 0 && (
        <div className="space-y-2">
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 기간 식수가 0으로 나옵니다 — 배치 집계가 안 됐을 수 있어요.
          </p>
          <Button variant="secondary" onClick={() => recomputeDailyStats.mutate()} disabled={recomputeDailyStats.isPending}>
            {recomputeDailyStats.isPending ? "계산 중..." : "최근 180일 배치 집계 재계산"}
          </Button>
          {recomputeDailyStats.isError && <ErrorState error={recomputeDailyStats.error} />}
          {recomputeDailyStats.isSuccess && (
            <p className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
              재계산 완료 — 그래도 0이면 이 기간에 실제 적재된 데이터가 없는 것입니다.
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="선택한 주의 누적 식수" value={totalHeadcount.toLocaleString()} />
        <StatTile
          label="최근 7일 식수"
          value={recentHeadcountQuery.isLoading ? "…" : recentHeadcountTotal.toLocaleString()}
          sub="오늘 포함 최근 7일 실측 식수 합계(전체 코너·끼니)"
        />
        <StatTile
          label="최고 식수 코너/메뉴"
          value={
            topPlannedHeadcountRow
              ? `${topPlannedHeadcountRow.corner_name} · ${topPlannedHeadcountRow.menu_name}`
              : "-"
          }
          sub={
            topPlannedHeadcountRow
              ? `실측 평균 ${Math.round(topPlannedHeadcountRow.recent_avg_headcount as number).toLocaleString()}명`
              : "이번 주 데이터 없음"
          }
          tone={topPlannedHeadcountRow ? "warning" : undefined}
        />
        <StatTile
          label="금주 메뉴 과거 VOE"
          value={weeklyVoeHistory.isLoading ? "…" : (weeklyVoeHistory.data ?? 0)}
          sub="클릭하면 메뉴별 상세를 볼 수 있어요"
          onClick={onOpenWeeklyVoe ? () => onOpenWeeklyVoe(selectedMonday) : undefined}
        />
      </div>

      <Card title="개선 필요 포인트 — 혼잡도 / 만족도 / VOE / 편성·운영">
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

      <Card title="식수 추이 — 기간 단위 · 끼니 · 코너 · 회사구분">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          {trendPeriodStart} ~ {trendPeriodEnd} 기준. 기간 단위·나누기 기준을 고르고 필터로 범위를 좁히세요.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            기간 단위
            <SegmentedControl
              value={trendGranularity}
              options={[
                { label: "일간", value: "daily" as Granularity },
                { label: "주간", value: "weekly" as Granularity },
                { label: "월간", value: "monthly" as Granularity },
              ]}
              onChange={setTrendGranularity}
            />
          </label>
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            나누기
            <SegmentedControl
              value={trendGroupBy}
              options={[
                { label: "전체", value: "total" as HeadcountGroupBy },
                { label: "코너별", value: "corner" as HeadcountGroupBy },
                { label: "회사구분별", value: "division" as HeadcountGroupBy },
                { label: "끼니별", value: "meal_type" as HeadcountGroupBy },
              ]}
              onChange={setTrendGroupBy}
            />
          </label>
        </div>
        <div className="mb-3 flex flex-wrap items-start gap-x-6 gap-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              코너 필터
            </span>
            {(cornerListQuery.data ?? []).map((c) => {
              const active = trendCornerIds.includes(c.corner_id);
              return (
                <button
                  key={c.corner_id}
                  onClick={() =>
                    setTrendCornerIds((cur) =>
                      cur.includes(c.corner_id) ? cur.filter((id) => id !== c.corner_id) : [...cur, c.corner_id],
                    )
                  }
                  className="rounded border px-2 py-0.5 text-xs transition-colors"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    background: active ? "var(--surface-2)" : "var(--surface)",
                    color: active ? "var(--ink)" : "var(--ink-secondary)",
                  }}
                >
                  {c.corner_name}
                </button>
              );
            })}
            {trendCornerIds.length > 0 && (
              <button className="text-xs underline" style={{ color: "var(--ink-muted)" }} onClick={() => setTrendCornerIds([])}>
                전체
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              회사구분
            </span>
            {(["본사", "계열사", "기타"] as Division[]).map((d) => {
              const active = trendDivisions.includes(d);
              return (
                <button
                  key={d}
                  onClick={() =>
                    setTrendDivisions((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]))
                  }
                  className="rounded border px-2 py-0.5 text-xs transition-colors"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    background: active ? "var(--surface-2)" : "var(--surface)",
                    color: active ? "var(--ink)" : "var(--ink-secondary)",
                  }}
                >
                  {d}
                </button>
              );
            })}
            {trendDivisions.length > 0 && (
              <button className="text-xs underline" style={{ color: "var(--ink-muted)" }} onClick={() => setTrendDivisions([])}>
                전체
              </button>
            )}
          </div>
        </div>
        {headcountTrend.isLoading && <LoadingState />}
        {headcountTrend.isError && <ErrorState error={headcountTrend.error} />}
        {headcountTrend.data && trendPeriods.length === 0 && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이 조건에 해당하는 취식 데이터가 없습니다.
          </p>
        )}
        {trendGranularity === "daily" && trendRecentAvg != null && (
          <div className="mb-2 flex items-center gap-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            <span>
              최근 {trendAvgWindow}일 평균: <strong>{Math.round(trendRecentAvg).toLocaleString()}명</strong>
            </span>
            <SegmentedControl
              value={String(trendAvgWindow)}
              options={[
                { label: "7일", value: "7" },
                { label: "14일", value: "14" },
                { label: "30일", value: "30" },
              ]}
              onChange={(v) => setTrendAvgWindow(Number(v) as 7 | 14 | 30)}
            />
          </div>
        )}
        {trendPeriods.length > 0 && <ReactECharts option={headcountTrendOption} style={{ height: 320 }} />}
      </Card>


      {/* 코너별 지표 비교 — 2026-08 재편으로 "분석 > 코너별" 탭에서 현황으로 옮겨왔다. */}
      <CornerMetricComparisonSection />

      <Card title="메뉴 하이라이트">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          직전 등장 대비 변화입니다. 신메뉴는 최근 30일 내 첫 등장 기준입니다.
        </p>
        {menuHighlights.isLoading && <LoadingState />}
        {menuHighlights.isError && <ErrorState error={menuHighlights.error} />}
        {menuHighlights.data && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  만족도 급상승
                </p>
                <MenuTrendList rows={menuHighlights.data.rising} tone="good" />
              </div>
              <div>
                <p className="mb-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                  만족도 급하락
                </p>
                <MenuTrendList rows={menuHighlights.data.falling} tone="critical" />
              </div>
            </div>
            <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}>
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

    </div>
  );
}
