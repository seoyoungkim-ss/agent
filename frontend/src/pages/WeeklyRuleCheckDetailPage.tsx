import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Button, Card, ErrorState, LoadingState } from "../components/ui";
import { buildDailyRuleCard, buildLowHeadcountRuleCard, RuleCard, type RuleCardConfig } from "../components/RuleCard";
import { addDays, currentMonday } from "../lib/week";

// §104 — 홈 화면 "금주 메뉴 편성 규칙 이상 여부" 타일 클릭 시 진입.
// WeeklyMenuVoeDetailPage와 같은 자기완결형 패턴(자체 쿼리, monday/onBack
// props). 메뉴 편성·운영 탭의 WeeklyMenuReviewTab과 달리 이 화면엔 연동할
// 격자가 없으므로, RuleCard의 onToggle은 그리드 하이라이트 없이 단순
// 펼침/접힘만 한다.
export function WeeklyRuleCheckDetailPage({
  onBack,
  monday,
}: {
  onBack: () => void;
  monday?: string;
}) {
  const selectedMonday = monday ?? currentMonday();
  const saturdayOfSelected = addDays(selectedMonday, 5);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const ruleCheckQuery = useQuery({
    queryKey: ["weekly-rule-check-detail", selectedMonday, saturdayOfSelected],
    queryFn: () => api.weeklyMenuPlanRuleCheck({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });
  // 해장 규칙(highlightFullDayOnViolation)이 위반일 전체 슬롯을 짚으려면
  // 필요 — 이 화면엔 그리드가 없어 실제로 하이라이트되진 않지만, 빌더
  // 시그니처를 WeeklyMenuReviewTab과 동일하게 맞추기 위해 그대로 넘긴다.
  const slotsQuery = useQuery({
    queryKey: ["weekly-rule-check-detail-slots", selectedMonday, saturdayOfSelected],
    queryFn: () => api.weeklyMenu({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });

  const weekdayDates = Array.from({ length: 6 }, (_, i) => addDays(selectedMonday, i)); // 월~토

  const ruleCards: RuleCardConfig[] = ruleCheckQuery.data
    ? [
        buildDailyRuleCard(
          "hangover",
          "해장 메뉴 (하루 최소 1개)",
          ruleCheckQuery.data.hangover,
          { isCountType: false, highlightFullDayOnViolation: true },
          slotsQuery.data ?? [],
        ),
        buildDailyRuleCard(
          "noodle",
          "면류 (하루 최대 4개)",
          ruleCheckQuery.data.noodle,
          { isCountType: true },
          slotsQuery.data ?? [],
        ),
        buildDailyRuleCard(
          "spicy_red_broth",
          "매운(빨간국물) (하루 최대 4개)",
          ruleCheckQuery.data.spicy_red_broth,
          { isCountType: true },
          slotsQuery.data ?? [],
        ),
        buildLowHeadcountRuleCard(ruleCheckQuery.data.low_headcount_reuse, weekdayDates),
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">금주 메뉴 편성 규칙 검증 상세</h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {selectedMonday} ~ {saturdayOfSelected}
          </p>
        </div>
        <Button variant="secondary" onClick={onBack}>
          ← 홈으로
        </Button>
      </div>

      <Card title="주간 편성 규칙 검증 (주중, 요일별)">
        {ruleCheckQuery.isLoading && <LoadingState />}
        {ruleCheckQuery.isError && <ErrorState error={ruleCheckQuery.error} />}
        {ruleCards.map((cfg) => (
          <RuleCard
            key={cfg.key}
            cfg={cfg}
            isActive={activeKey === cfg.key}
            onToggle={() => setActiveKey((cur) => (cur === cfg.key ? null : cfg.key))}
            renderMatchChip={(_m, label, key) => (
              <span
                key={key}
                className="rounded-full border px-2 py-0.5 text-[11px]"
                style={{ borderColor: "var(--border)", color: "var(--ink)" }}
              >
                {label}
              </span>
            )}
            weekdayDates={weekdayDates}
          />
        ))}
      </Card>
    </div>
  );
}
