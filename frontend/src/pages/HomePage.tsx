import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import type { LucideIcon } from "lucide-react";
import { ClipboardList, MessageSquare, Smile, Users } from "lucide-react";
import {
  api,
  type Classification,
  type Division,
  type Granularity,
  type HeadcountGroupBy,
  type ImprovementPoint,
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
import { addDays, daysBetweenInclusive, isoDaysAgo, mondayOf, toIsoDate } from "../lib/week";
import { CornerLogo } from "../components/CornerLogo";

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

// §102: "개선 필요 포인트" 카드를 피드 느낌의 세로 리스트로 다듬을 때
// 항목마다 축(axis)을 한눈에 구분할 아이콘.
const ICON_BY_AXIS: Record<ImprovementPoint["axis"], LucideIcon> = {
  congestion: Users,
  satisfaction: Smile,
  voe: MessageSquare,
  planning: ClipboardList,
};

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
          {r.cause_keywords && r.cause_keywords.length > 0 ? (
            <div className="mt-1 flex flex-wrap gap-1">
              {r.cause_keywords.map((k) => (
                <span
                  key={k}
                  className="rounded-full border px-2 py-0.5 text-[11px]"
                  style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink-muted)" }}
                >
                  {k}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function HomePage({
  onOpenWeeklyVoe,
  onOpenWeeklyRuleCheck,
}: {
  onOpenWeeklyVoe?: (monday: string) => void;
  onOpenWeeklyRuleCheck?: (monday: string) => void;
}) {
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

  // §92: "금일 식수"/"금일 맛평가 점수" 스탯타일 — daily_corner_stats(나이트
  // 배치)는 어제까지만 채워져 "오늘" 수치가 항상 비므로, headcount_trend와
  // 같은 방식으로 meal_log를 그때그때 집계하는 전용 엔드포인트를 쓴다.
  // 트레일링 7일(오늘 포함) 범위를 한 번에 받아 오늘 값과 일평균을 함께 낸다.
  const homeDailySummaryQuery = useQuery({
    queryKey: ["home-daily-summary-7d"],
    queryFn: () => api.homeDailySummary({ period_start: isoDaysAgo(6), period_end: isoDaysAgo(0) }),
  });
  const homeDailySummaryDays = homeDailySummaryQuery.data ?? [];
  const todayDailySummary = homeDailySummaryDays.find((d) => d.date === isoDaysAgo(0));
  const todayHeadcount = todayDailySummary?.headcount ?? 0;
  const weeklyAvgHeadcount =
    homeDailySummaryDays.length > 0
      ? homeDailySummaryDays.reduce((sum, d) => sum + d.headcount, 0) / homeDailySummaryDays.length
      : null;
  const daysWithScore = homeDailySummaryDays.filter((d) => d.avg_taste_score != null);
  const weeklyAvgTasteScore =
    daysWithScore.length > 0
      ? daysWithScore.reduce((sum, d) => sum + (d.avg_taste_score as number), 0) / daysWithScore.length
      : null;

  // §98(3단계): "금일 식수"/"금일 맛평가 점수" KPI 카드의 증감 화살표+스파크라인.
  // 이미 받아온 트레일링 7일 데이터로만 계산 — 새 API 호출 없음. 오차/노이즈로
  // 화살표가 계속 깜빡이지 않게 작은 변화(식수 ±1%, 맛평가 ±0.05점)는 "―"로 둔다.
  const sortedDailySummaryDays = [...homeDailySummaryDays].sort((a, b) => a.date.localeCompare(b.date));
  const headcountSparkline = sortedDailySummaryDays.map((d) => d.headcount);
  const tasteScoreSparkline = sortedDailySummaryDays
    .filter((d) => d.avg_taste_score != null)
    .map((d) => d.avg_taste_score as number);
  const todayHeadcountTrend =
    weeklyAvgHeadcount != null && weeklyAvgHeadcount > 0
      ? (() => {
          const diffPct = ((todayHeadcount - weeklyAvgHeadcount) / weeklyAvgHeadcount) * 100;
          const direction: "up" | "down" | "flat" = diffPct > 1 ? "up" : diffPct < -1 ? "down" : "flat";
          const tone: "good" | "warning" | "neutral" = direction === "up" ? "good" : direction === "down" ? "warning" : "neutral";
          return { direction, tone, text: `평균 대비 ${diffPct >= 0 ? "+" : ""}${diffPct.toFixed(0)}%` };
        })()
      : undefined;
  const tasteScoreTrend =
    todayDailySummary?.avg_taste_score != null && weeklyAvgTasteScore != null
      ? (() => {
          const diff = todayDailySummary.avg_taste_score! - weeklyAvgTasteScore;
          const direction: "up" | "down" | "flat" = diff > 0.05 ? "up" : diff < -0.05 ? "down" : "flat";
          const tone: "good" | "warning" | "neutral" = direction === "up" ? "good" : direction === "down" ? "warning" : "neutral";
          return { direction, tone, text: `평균 대비 ${diff >= 0 ? "+" : ""}${diff.toFixed(2)}점` };
        })()
      : undefined;

  // §92: "금주 메뉴 편성 규칙 이상 여부" — 이미 있는 규칙검증 엔드포인트(주간
  // 식단표 관리 탭의 검증 패널과 동일)를 선택한 주로 그대로 호출해, 위반 유무만
  // 요약해서 보여준다.
  const weeklyRuleCheckQuery = useQuery({
    queryKey: ["weekly-menu-plan-rule-check", selectedMonday, saturdayOfSelected],
    queryFn: () => api.weeklyMenuPlanRuleCheck({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });
  const ruleViolationCount = weeklyRuleCheckQuery.data
    ? weeklyRuleCheckQuery.data.hangover.filter((d) => !d.ok).length +
      weeklyRuleCheckQuery.data.noodle.filter((d) => !d.ok).length +
      weeklyRuleCheckQuery.data.spicy_red_broth.filter((d) => !d.ok).length +
      weeklyRuleCheckQuery.data.low_headcount_reuse.violations.length
    : 0;

  // §98(3단계): "금주 메뉴 편성 규칙 이상 여부" 카드의 "지난 주 대비" 화살표 —
  // 같은 엔드포인트를 지난 주 기간으로 한 번 더 호출한다(선택한 주가 바뀌어도
  // 캐시 키가 같이 바뀌어 자연스럽게 재조회됨). 위반 건수는 늘면 나쁜 신호라
  // direction="up"일 때 tone="critical"로, 다른 KPI 카드와 색 의미가 반대다.
  const prevMonday = addDays(selectedMonday, -7);
  const prevSaturday = addDays(prevMonday, 5);
  const prevWeeklyRuleCheckQuery = useQuery({
    queryKey: ["weekly-menu-plan-rule-check", prevMonday, prevSaturday],
    queryFn: () => api.weeklyMenuPlanRuleCheck({ period_start: prevMonday, period_end: prevSaturday }),
  });
  const prevRuleViolationCount = prevWeeklyRuleCheckQuery.data
    ? prevWeeklyRuleCheckQuery.data.hangover.filter((d) => !d.ok).length +
      prevWeeklyRuleCheckQuery.data.noodle.filter((d) => !d.ok).length +
      prevWeeklyRuleCheckQuery.data.spicy_red_broth.filter((d) => !d.ok).length +
      prevWeeklyRuleCheckQuery.data.low_headcount_reuse.violations.length
    : null;
  const ruleViolationTrend =
    prevRuleViolationCount != null && weeklyRuleCheckQuery.data
      ? (() => {
          const direction: "up" | "down" | "flat" =
            ruleViolationCount > prevRuleViolationCount ? "up" : ruleViolationCount < prevRuleViolationCount ? "down" : "flat";
          const tone: "good" | "critical" | "neutral" =
            direction === "up" ? "critical" : direction === "down" ? "good" : "neutral";
          return { direction, tone, text: `지난 주 ${prevRuleViolationCount}건` };
        })()
      : undefined;

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
  // §95: 조회 기간을 기간 단위(일/주/월)에서 자동으로 정하던 것(§81)을 사용자가
  // 직접 고르는 방식으로 바꿨다 — 기본값은 "최근 한 주"(오늘 포함 7일).
  const [trendPeriodStart, setTrendPeriodStart] = useState(() => isoDaysAgo(6));
  const [trendPeriodEnd, setTrendPeriodEnd] = useState(() => isoDaysAgo(0));
  const TREND_PERIOD_PRESETS: { label: string; days: number }[] = [
    { label: "최근 1주", days: 6 },
    { label: "최근 4주", days: 27 },
    { label: "최근 3개월", days: 89 },
    { label: "최근 6개월", days: 179 },
  ];

  const cornerListQuery = useQuery({
    queryKey: ["corner-list"],
    queryFn: () => api.cornerList(),
  });

  // §91: 코너별 조식/중식/석식 식수 현황 — 담당자가 준 리포트(스크린샷) 양식을
  // 그대로 재현한다. daily_corner_stats(나이트 배치)와 달리 meal_log를 그때
  // 그때 집계하는 엔드포인트라 오늘 날짜도 바로 볼 수 있다.
  const [mealTypeHeadcountDate, setMealTypeHeadcountDate] = useState(isoDaysAgo(0));
  const cornerMealTypeHeadcountQuery = useQuery({
    queryKey: ["corner-meal-type-headcount", mealTypeHeadcountDate],
    queryFn: () => api.cornerMealTypeHeadcount({ target_date: mealTypeHeadcountDate }),
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

  // §104: 선택한 기간이 기간 단위 하나(주 7일/월 28일)보다 짧으면 여러 날이
  // 같은 버킷(같은 ISO 주 월요일 또는 같은 "YYYY-MM")으로 접혀 x축이
  // 하나로 뭉쳐 보인다("5일 골라도 하루치만 나옴" 신고) — 이럴 땐 실제
  // 조회에만 일 단위로 자동 전환한다(SegmentedControl에 보이는 선택 자체는
  // 안 바뀜). 백엔드 headcount_trend/_period_bucket은 무변경 — "daily"는
  // 이미 지원되는 값이다.
  const trendRangeDays = daysBetweenInclusive(trendPeriodStart, trendPeriodEnd);
  const effectiveTrendGranularity: Granularity =
    (trendGranularity === "weekly" && trendRangeDays < 7) ||
    (trendGranularity === "monthly" && trendRangeDays < 28)
      ? "daily"
      : trendGranularity;

  const headcountTrend = useQuery({
    queryKey: [
      "headcount-trend",
      trendPeriodStart,
      trendPeriodEnd,
      effectiveTrendGranularity,
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
        granularity: effectiveTrendGranularity,
        group_by: trendGroupBy,
        meal_types: mealTypeFilter,
        corner_ids: trendCornerIds.length > 0 ? trendCornerIds : undefined,
        divisions: trendDivisions.length > 0 ? trendDivisions : undefined,
        classification: classification === "전체" ? undefined : classification,
      }),
  });

  // 총식수 꺾은선 전용 — 코너/회사구분/끼니/구분 필터(토글)와 무관하게 항상
  // 전체 식수를 보여달라는 요청(2026-08)이라, 위 headcountTrend와 별개로
  // 아무 필터도 안 걸고 group_by="total"만 써서 부른다.
  const totalHeadcountTrend = useQuery({
    queryKey: ["headcount-trend-total", trendPeriodStart, trendPeriodEnd, effectiveTrendGranularity],
    queryFn: () =>
      api.headcountTrend({
        period_start: trendPeriodStart,
        period_end: trendPeriodEnd,
        granularity: effectiveTrendGranularity,
        group_by: "total",
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
  // 막대(코너/끼니/회사구분별 분해) 위에 총식수 꺾은선을 겹쳐서 보여준다 — 코너
  // 필터 등 토글이 꺼져 있어도 항상 전체 식수를 나타내야 하므로, 필터가 걸린
  // trendRows가 아니라 별도로 부른 totalHeadcountTrend(무필터)를 쓴다.
  // "OO 일자간 일평균 식수" 계산도 같은 값을 쓴다.
  const totalHeadcountByPeriod = new Map<string, number>();
  for (const r of totalHeadcountTrend.data ?? []) totalHeadcountByPeriod.set(r.period, r.headcount);
  const headcountTrendOption = {
    textStyle: { fontFamily: "inherit", color: chartTheme.text },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue?: string; marker: string; seriesName: string; value: unknown }[]) => {
        const header = params[0]?.axisValue ?? "";
        const lines = params.map((p) => {
          const v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
          return `${p.marker}${p.seriesName}: ${typeof v === "number" ? Math.round(v) : v}명`;
        });
        return [header, ...lines].join("<br/>");
      },
    },
    legend: {
      top: 0,
      textStyle: { color: chartTheme.text },
      data: [...trendSeriesKeys.map((k) => trendSeriesMeta.get(k)!), "총식수"],
    },
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
    series: [
      ...trendSeriesKeys.map((key, i) => {
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
      {
        // 코너/끼니/회사구분별로 쪼갠 막대 위에 총식수 흐름을 겹쳐서 한눈에 보이게.
        name: "총식수",
        type: "line" as const,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { color: resolveColor("var(--ink)"), width: 2 },
        itemStyle: { color: resolveColor("var(--ink)") },
        z: 10,
        data: trendPeriods.map((p) => totalHeadcountByPeriod.get(p) ?? 0),
        // §100: 이 기간 중 총식수가 가장 높았던 지점을 핀 콜아웃으로 자동
        // 표시. type:"max"는 데이터가 바뀔 때마다(필터·기간 변경) 자동
        // 재계산되어 별도 상태 관리가 필요 없다.
        markPoint: {
          symbol: "pin",
          symbolSize: 36,
          itemStyle: { color: resolveColor("var(--accent)") },
          // 핀 안쪽(기본 label.position)은 텍스트가 잘려 보여 핀 위쪽으로 뺀다.
          label: {
            position: "top" as const,
            distance: 8,
            color: resolveColor("var(--ink)"),
            fontSize: 11,
            fontWeight: "bold" as const,
            formatter: (p: { value: number }) => `최고 ${Math.round(p.value).toLocaleString()}명`,
          },
          data: [{ type: "max" as const, name: "최고" }],
        },
      },
    ],
  };

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
        <StatTile
          label="금일 식수"
          value={homeDailySummaryQuery.isLoading ? "…" : todayHeadcount.toLocaleString()}
          sub={weeklyAvgHeadcount != null ? `최근 7일 일평균 ${Math.round(weeklyAvgHeadcount).toLocaleString()}명` : undefined}
          trend={homeDailySummaryQuery.isLoading ? undefined : todayHeadcountTrend}
          sparkline={homeDailySummaryQuery.isLoading ? undefined : headcountSparkline}
          variant="dark"
        />
        <StatTile
          label="금일 맛평가 점수"
          value={
            homeDailySummaryQuery.isLoading
              ? "…"
              : (todayDailySummary?.avg_taste_score != null ? todayDailySummary.avg_taste_score.toFixed(2) : "-")
          }
          sub={weeklyAvgTasteScore != null ? `최근 7일 일평균 ${weeklyAvgTasteScore.toFixed(2)}점` : "최근 7일 평가 없음"}
          trend={homeDailySummaryQuery.isLoading ? undefined : tasteScoreTrend}
          sparkline={homeDailySummaryQuery.isLoading ? undefined : tasteScoreSparkline}
        />
        <StatTile
          label="금주 메뉴 과거 VOE"
          value={weeklyVoeHistory.isLoading ? "…" : (weeklyVoeHistory.data ?? 0)}
          sub="클릭하면 메뉴별 상세를 볼 수 있어요"
          onClick={onOpenWeeklyVoe ? () => onOpenWeeklyVoe(selectedMonday) : undefined}
        />
        <StatTile
          label="금주 메뉴 편성 규칙 이상 여부"
          value={
            weeklyRuleCheckQuery.isLoading ? "…" : ruleViolationCount > 0 ? `이상 ${ruleViolationCount}건` : "이상 없음"
          }
          sub="해장·면류·매운맛 편성 기준 + 저조 식수 재편성 · 클릭하면 상세를 볼 수 있어요"
          tone={weeklyRuleCheckQuery.isLoading ? undefined : ruleViolationCount > 0 ? "critical" : "good"}
          trend={weeklyRuleCheckQuery.isLoading ? undefined : ruleViolationTrend}
          onClick={onOpenWeeklyRuleCheck ? () => onOpenWeeklyRuleCheck(selectedMonday) : undefined}
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
          // §102: 세로 피드 느낌으로 — 항목마다 축(axis) 아이콘 배지 +
          // 구분선(divide-y). 데이터/문구는 그대로, 스타일만 다듬는다.
          <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
            {improvementPoints.data.map((p, i) => {
              const Icon = ICON_BY_AXIS[p.axis];
              const severityColor = p.severity === "critical" ? "var(--critical)" : "var(--warning)";
              return (
                <li key={i} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  <span
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                    style={{ background: "var(--surface-2)" }}
                  >
                    <Icon size={14} style={{ color: severityColor }} />
                  </span>
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
              );
            })}
          </ul>
        )}
      </Card>

      <Card title="식수 추이 — 기간 단위 · 끼니 · 코너 · 회사구분">
        <p className="mb-3 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          기간 단위·나누기 기준을 고르고 필터로 범위를 좁히세요. 기본은 최근 한 주입니다.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
              조회 기간
            </span>
            <input
              type="date"
              value={trendPeriodStart}
              max={trendPeriodEnd}
              onChange={(e) => e.target.value && setTrendPeriodStart(e.target.value)}
              className="rounded-md border px-2 py-1.5 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            />
            <span className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
              ~
            </span>
            <input
              type="date"
              value={trendPeriodEnd}
              min={trendPeriodStart}
              max={isoDaysAgo(0)}
              onChange={(e) => e.target.value && setTrendPeriodEnd(e.target.value)}
              className="rounded-md border px-2 py-1.5 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            />
            {TREND_PERIOD_PRESETS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => {
                  setTrendPeriodStart(isoDaysAgo(preset.days));
                  setTrendPeriodEnd(isoDaysAgo(0));
                }}
                className="rounded-md border px-2 py-1.5 text-xs transition-colors"
                style={{ borderColor: "var(--border)", background: "var(--surface)", color: "var(--ink-secondary)" }}
              >
                {preset.label}
              </button>
            ))}
            {trendGranularity === "monthly" && (
              <input
                type="month"
                value={trendPeriodStart.slice(0, 7)}
                max={isoDaysAgo(0).slice(0, 7)}
                onChange={(e) => {
                  if (!e.target.value) return;
                  const [y, m] = e.target.value.split("-").map(Number);
                  const lastDay = toIsoDate(new Date(y, m, 0)); // 다음달 0일 = 이번달 마지막날
                  setTrendPeriodStart(`${e.target.value}-01`);
                  setTrendPeriodEnd(lastDay > isoDaysAgo(0) ? isoDaysAgo(0) : lastDay);
                }}
                className="rounded-md border px-2 py-1.5 text-[13px]"
                style={{ borderColor: "var(--border)", background: "var(--surface)" }}
              />
            )}
          </div>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
            기간 단위
            <SegmentedControl
              value={trendGranularity}
              options={[
                { label: "주간", value: "weekly" as Granularity },
                { label: "월간", value: "monthly" as Granularity },
              ]}
              onChange={setTrendGranularity}
            />
            {trendGranularity !== effectiveTrendGranularity && (
              <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
                선택 기간이 짧아 일 단위로 표시 중
              </span>
            )}
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
                  <CornerLogo cornerName={c.corner_name} height={14} />
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
        {trendPeriods.length > 0 && <ReactECharts option={headcountTrendOption} style={{ height: 320 }} />}
      </Card>

      <Card title="코너별 조식/중식/석식 식수 현황">
        <div className="mb-3 flex items-center gap-2 text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          <label className="flex items-center gap-1.5">
            날짜
            <input
              type="date"
              value={mealTypeHeadcountDate}
              max={isoDaysAgo(0)}
              onChange={(e) => setMealTypeHeadcountDate(e.target.value)}
              className="rounded border px-2 py-1 text-[13px]"
              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
            />
          </label>
        </div>
        {cornerMealTypeHeadcountQuery.isLoading && <LoadingState />}
        {cornerMealTypeHeadcountQuery.isError && <ErrorState error={cornerMealTypeHeadcountQuery.error} />}
        {cornerMealTypeHeadcountQuery.data && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr>
                  <th
                    rowSpan={2}
                    className="border px-2 py-1.5 text-left align-bottom"
                    style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
                  >
                    구분
                  </th>
                  {MEAL_TYPE_OPTIONS.map((mt) => (
                    <th
                      key={mt}
                      colSpan={3}
                      className="border px-2 py-1.5 text-center"
                      style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
                    >
                      {mt}
                    </th>
                  ))}
                </tr>
                <tr>
                  {MEAL_TYPE_OPTIONS.map((mt) => (
                    <Fragment key={mt}>
                      <th
                        className="border px-2 py-1 text-center font-normal"
                        style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                      >
                        메뉴
                      </th>
                      <th
                        className="border px-2 py-1 text-center font-normal"
                        style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                      >
                        수량
                      </th>
                      <th
                        className="border px-2 py-1 text-center font-normal"
                        style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                      >
                        식수율
                      </th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cornerMealTypeHeadcountQuery.data.take_in.map((row) => (
                  <tr key={row.corner_id}>
                    <td className="border px-2 py-1.5" style={{ borderColor: "var(--border)" }}>
                      <CornerLogo cornerName={row.corner_name} />
                    </td>
                    {MEAL_TYPE_OPTIONS.map((mt) => {
                      const cell = row.meals[mt];
                      return (
                        <Fragment key={mt}>
                          <td
                            className="border px-2 py-1.5"
                            style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
                          >
                            {cell?.menu_name ?? "-"}
                          </td>
                          <td className="border px-2 py-1.5 text-right" style={{ borderColor: "var(--border)" }}>
                            {(cell?.headcount ?? 0).toLocaleString()}
                          </td>
                          <td
                            className="border px-2 py-1.5 text-right"
                            style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                          >
                            {cell?.share_of_traffic != null ? `${(cell.share_of_traffic * 100).toFixed(1)}%` : "-"}
                          </td>
                        </Fragment>
                      );
                    })}
                  </tr>
                ))}
                {cornerMealTypeHeadcountQuery.data.take_out && (
                  <tr>
                    <td
                      className="border px-2 py-1.5 font-medium"
                      style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
                    >
                      <CornerLogo cornerName={cornerMealTypeHeadcountQuery.data.take_out.corner_name} />
                    </td>
                    {MEAL_TYPE_OPTIONS.map((mt) => {
                      const cell = cornerMealTypeHeadcountQuery.data!.take_out!.meals[mt];
                      return (
                        <Fragment key={mt}>
                          <td
                            className="border px-2 py-1.5"
                            style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink-secondary)" }}
                          >
                            {cell?.menu_name ?? "-"}
                          </td>
                          <td
                            className="border px-2 py-1.5 text-right"
                            style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
                          >
                            {(cell?.headcount ?? 0).toLocaleString()}
                          </td>
                          <td
                            className="border px-2 py-1.5 text-right"
                            style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink-muted)" }}
                          >
                            {cell?.share_of_traffic != null ? `${(cell.share_of_traffic * 100).toFixed(1)}%` : "-"}
                          </td>
                        </Fragment>
                      );
                    })}
                  </tr>
                )}
                <tr>
                  <td className="border px-2 py-1.5 font-medium" style={{ borderColor: "var(--border)" }}>
                    소계
                  </td>
                  {MEAL_TYPE_OPTIONS.map((mt) => {
                    const bucket = cornerMealTypeHeadcountQuery.data!.subtotal[mt];
                    return (
                      <Fragment key={mt}>
                        <td className="border px-2 py-1.5" style={{ borderColor: "var(--border)" }} />
                        <td
                          className="border px-2 py-1.5 text-right font-medium"
                          style={{ borderColor: "var(--border)" }}
                        >
                          {(bucket?.headcount ?? 0).toLocaleString()}
                        </td>
                        <td
                          className="border px-2 py-1.5 text-right"
                          style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}
                        >
                          {bucket?.share_of_traffic != null ? `${(bucket.share_of_traffic * 100).toFixed(1)}%` : "-"}
                        </td>
                      </Fragment>
                    );
                  })}
                </tr>
                <tr>
                  <td
                    className="border px-2 py-1.5 font-semibold"
                    style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
                  >
                    합계
                  </td>
                  {MEAL_TYPE_OPTIONS.map((mt) => {
                    const bucket = cornerMealTypeHeadcountQuery.data!.total[mt];
                    return (
                      <Fragment key={mt}>
                        <td
                          className="border px-2 py-1.5"
                          style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
                        />
                        <td
                          className="border px-2 py-1.5 text-right font-semibold"
                          style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
                        >
                          {(bucket?.headcount ?? 0).toLocaleString()}
                        </td>
                        <td
                          className="border px-2 py-1.5 text-right"
                          style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink-muted)" }}
                        >
                          {bucket?.share_of_traffic != null ? `${(bucket.share_of_traffic * 100).toFixed(1)}%` : "-"}
                        </td>
                      </Fragment>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        )}
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
