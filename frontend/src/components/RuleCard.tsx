import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { type DailyMenuPlanRuleResult, type LowHeadcountViolation } from "../api/client";

// §103/§104: 주간 편성 규칙 검증 카드 — 처음엔 메뉴 편성·운영 탭의
// WeeklyMenuReviewTab 안에 로컬 클로저로 있었는데(§103), 홈의 "금주 메뉴
// 편성 규칙 이상 여부" 타일에서 진입하는 새 단독 상세 화면
// (WeeklyRuleCheckDetailPage)도 같은 카드를 그려야 해서(§104) 여기로
// 뽑았다. 그리드 하이라이트·스크롤처럼 화면마다 다른 동작은 `onToggle`/
// `renderMatchChip` 프롭으로 받아, 이 컴포넌트 자체는 그리드 유무와
// 무관하게 재사용 가능하다.

export const WEEKDAY_LABELS_MON_FRI = ["월", "화", "수", "목", "금"];

export type RuleDayStatus = { ok: boolean; count?: number; limit?: number | null };

export type RuleCardConfig = {
  key: string;
  label: string;
  ok: boolean;
  isCountType: boolean;
  dayResults: Map<string, RuleDayStatus>;
  highlightMatches: { plan_date: string; corner_id: number }[];
  chips: { match: { plan_date: string; corner_id: number }; label: string; renderKey: string | number }[];
  unclickableNotes?: { key: string | number; label: string }[];
};

// isCountType(면류/매운맛처럼 "하루 최대 N개")만 격자 요일 헤더에 "N/M개
// 초과" 배지를 얹는다 — 부재형 규칙(해장 최소 1개)이나 개별 매치 기반
// 규칙(저조 식수 재사용)은 특정 초과분을 셀 수 없어 배지가 의미가 없다.
export function buildDailyRuleCard(
  key: string,
  label: string,
  results: DailyMenuPlanRuleResult[],
  opts: { isCountType: boolean; highlightFullDayOnViolation?: boolean },
  slots: { plan_date: string; corner_id: number }[],
): RuleCardConfig {
  const dayResults = new Map<string, RuleDayStatus>(
    results.map((r) => [r.plan_date, { ok: r.ok, count: r.count, limit: r.limit }]),
  );
  const violatingDays = results.filter((r) => !r.ok);
  const realMatches = violatingDays.flatMap((r) => r.matches);
  // "해장 최소 1개"처럼 위반이 특정 메뉴의 존재가 아니라 부재라서 matches가
  // 항상 비어있는 규칙은(그날 해장 메뉴가 0개라 predicate에 걸리는 슬롯
  // 자체가 없음), 실제 matches 대신 그날 전체 슬롯을 격자 하이라이트
  // 대상으로 써야 클릭했을 때 뭔가 강조된다. 다만 이 경우 카드를 펼쳐도
  // "이 메뉴가 위반"이라고 짚을 수 있는 게 없어 칩 목록(chips)은 비워둔다.
  const highlightMatches = opts.highlightFullDayOnViolation
    ? violatingDays.flatMap((r) =>
        slots
          .filter((s) => s.plan_date === r.plan_date)
          .map((s) => ({ plan_date: s.plan_date, corner_id: s.corner_id })),
      )
    : realMatches;
  return {
    key,
    label,
    ok: violatingDays.length === 0,
    isCountType: opts.isCountType,
    dayResults,
    highlightMatches,
    chips: realMatches.map((m, i) => ({
      match: m,
      label: `${m.menu_name}(${m.corner_name}, ${m.plan_date.slice(5)})`,
      renderKey: i,
    })),
  };
}

export function buildLowHeadcountRuleCard(
  data: { ok: boolean; violations: LowHeadcountViolation[] },
  weekdayDates: string[],
): RuleCardConfig {
  const violationDates = new Set<string>();
  const highlightMatches: { plan_date: string; corner_id: number }[] = [];
  const chips: RuleCardConfig["chips"] = [];
  const unclickableNotes: { key: string | number; label: string }[] = [];
  data.violations.forEach((v, vi) => {
    if (v.matches.length === 0) {
      unclickableNotes.push({
        key: vi,
        label: `${v.menu_name}(${v.corner_name}, 최근 평균 ${v.recent_avg_headcount}식)`,
      });
      return;
    }
    v.matches.forEach((m, mi) => {
      violationDates.add(m.plan_date);
      highlightMatches.push({ plan_date: m.plan_date, corner_id: m.corner_id });
      chips.push({
        match: m,
        label: `${v.menu_name}(${v.corner_name}, 최근 평균 ${v.recent_avg_headcount}식, ${m.plan_date.slice(5)})`,
        renderKey: `${vi}_${mi}`,
      });
    });
  });
  const dayResults = new Map<string, RuleDayStatus>(
    weekdayDates.slice(0, 5).map((d) => [d, { ok: !violationDates.has(d) }]),
  );
  return {
    key: "low_headcount",
    label: "최근 저조 식수(200식 이하) 재편성",
    ok: data.ok,
    isCountType: false,
    dayResults,
    highlightMatches,
    chips,
    unclickableNotes,
  };
}

// PASS/FAIL 아이콘 + 요일 5개 dot + (펼쳤을 때만) 위반 칩을 보여주는 카드.
// 카드 클릭 = onToggle 호출 — 그리드가 있는 화면(WeeklyMenuReviewTab)에서는
// 격자 하이라이트+스크롤+카드 펼침이 함께 일어나고, 그리드가 없는 단독
// 상세 화면(WeeklyRuleCheckDetailPage)에서는 카드 펼침만 일어난다.
export function RuleCard({
  cfg,
  isActive,
  onToggle,
  renderMatchChip,
  weekdayDates,
}: {
  cfg: RuleCardConfig;
  isActive: boolean;
  onToggle: () => void;
  renderMatchChip: (m: { plan_date: string; corner_id: number }, label: string, key: string | number) => ReactNode;
  /** 월~토(또는 그 이상) 날짜 배열 — 앞 5개(월~금)를 요일 dot에 순서대로 맞춘다. */
  weekdayDates: string[];
}) {
  const hasViolations = !cfg.ok;
  const hasExpandedContent = cfg.chips.length > 0 || (cfg.unclickableNotes?.length ?? 0) > 0;
  return (
    <div
      className="mb-2 rounded-xl border p-3 transition-colors"
      style={{
        borderColor: "var(--border)",
        borderLeftColor: isActive ? "var(--rule-primary)" : "var(--border)",
        borderLeftWidth: isActive ? 3 : 1,
        background: "var(--surface)",
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <button
          className="flex flex-1 flex-wrap items-center gap-3 text-left disabled:cursor-default"
          onClick={() => hasViolations && onToggle()}
          disabled={!hasViolations}
          title={hasViolations ? "클릭하면 이번 주 위반을 격자에서 하이라이트합니다" : "이번 주 위반 없음"}
        >
          <span className="text-[13px] font-medium">{cfg.label}</span>
          <span className="flex items-center gap-1">
            {weekdayDates.slice(0, 5).map((d, i) => {
              const day = cfg.dayResults.get(d);
              const violated = day ? !day.ok : false;
              return (
                <span
                  key={d}
                  title={`${WEEKDAY_LABELS_MON_FRI[i]}요일 ${violated ? "위반" : "통과"}`}
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{
                    background: violated ? "var(--rule-decrease)" : "transparent",
                    border: violated ? "none" : "1.5px solid var(--border-strong)",
                  }}
                />
              );
            })}
          </span>
        </button>
        <span className="flex shrink-0 items-center gap-2">
          {cfg.ok ? (
            <CheckCircle2 size={20} style={{ color: "var(--good)" }} />
          ) : (
            <AlertTriangle size={20} style={{ color: "var(--rule-decrease)" }} />
          )}
          {isActive && (
            <button onClick={onToggle} style={{ color: "var(--ink-muted)" }} title="선택 해제">
              <X size={16} />
            </button>
          )}
        </span>
      </div>
      {isActive && hasExpandedContent && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {cfg.chips.map((c) => renderMatchChip(c.match, c.label, c.renderKey))}
          {cfg.unclickableNotes?.map((n) => (
            <span key={n.key} className="text-xs" style={{ color: "var(--ink-muted)" }}>
              {n.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
