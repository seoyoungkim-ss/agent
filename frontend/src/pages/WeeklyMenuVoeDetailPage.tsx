import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Button, Card, ErrorState, LoadingState } from "../components/ui";
import { addDays, currentMonday } from "../lib/week";

// PRD "금주 메뉴 VOE 상세" — 홈 화면 "금주 메뉴 과거 VOE" 카드 클릭 시 진입.
// 이번 주 메인메뉴별로 과거 평가 이력(만족도 추이)을 아코디언으로 펼쳐본다.
export function WeeklyMenuVoeDetailPage({
  onBack,
  monday,
}: {
  onBack: () => void;
  /** 홈에서 보고 있던 주의 월요일. 없이 진입하면 이번 주로 폴백한다.
   *
   * ⚠️ 예전엔 이 화면이 `useState(mondayOf(new Date()))`로 **현재 주에 고정**돼
   * 있었다. 홈에서 주차를 옮겨 놓고 들어와도 최신 주를 조회해 "타일 숫자는 있는데
   * 0건"으로 보였다(2026-08 실사용 신고). 홈이 보던 주를 그대로 받아 쓴다. */
  monday?: string;
}) {
  const selectedMonday = monday ?? currentMonday();
  const saturdayOfSelected = addDays(selectedMonday, 5);
  const [expandedMenu, setExpandedMenu] = useState<string | null>(null);

  const weeklyMenuQuery = useQuery({
    queryKey: ["weekly-voe-detail-menu", selectedMonday, saturdayOfSelected],
    queryFn: () => api.weeklyMenu({ period_start: selectedMonday, period_end: saturdayOfSelected }),
  });

  const mainMenus = [
    ...new Map(
      (weeklyMenuQuery.data ?? [])
        .filter((s) => s.main)
        .map((s) => [
          s.main!.menu_name,
          { menuName: s.main!.menu_name as string, cornerName: s.corner_name },
        ]),
    ).values(),
  ];

  const historyQuery = useQuery({
    queryKey: ["weekly-voe-detail-history", expandedMenu],
    queryFn: () => api.menuHistory(expandedMenu as string),
    enabled: !!expandedMenu,
  });
  const commentsQuery = useQuery({
    queryKey: ["weekly-voe-detail-comments", expandedMenu],
    queryFn: () => api.menuComments(expandedMenu as string),
    enabled: !!expandedMenu,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">금주 메뉴 VOE 상세</h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            {selectedMonday} ~ {saturdayOfSelected}
          </p>
        </div>
        <Button variant="secondary" onClick={onBack}>
          ← 홈으로
        </Button>
      </div>

      <Card title="이번 주 메인메뉴별 과거 평가 이력">
        {weeklyMenuQuery.isLoading && <LoadingState />}
        {weeklyMenuQuery.isError && <ErrorState error={weeklyMenuQuery.error} />}
        {mainMenus.length === 0 && !weeklyMenuQuery.isLoading && (
          <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
            이번 주 등록된 메인메뉴가 없습니다.
          </p>
        )}
        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {mainMenus.map((m) => {
            const isOpen = expandedMenu === m.menuName;
            return (
              <div key={m.menuName} className="py-2">
                <button
                  className="flex w-full items-center justify-between text-left"
                  onClick={() => setExpandedMenu((cur) => (cur === m.menuName ? null : m.menuName))}
                >
                  <span className="text-[13px] font-medium">
                    {m.menuName} <span style={{ color: "var(--ink-muted)" }}>({m.cornerName})</span>
                  </span>
                  <span style={{ color: "var(--ink-muted)" }}>{isOpen ? "▲" : "▼"}</span>
                </button>
                {isOpen && (
                  <div className="mt-2 grid grid-cols-1 gap-4 pl-2 sm:grid-cols-2">
                    <div>
                      <p className="mb-1 text-xs font-medium" style={{ color: "var(--ink-secondary)" }}>
                        과거 만족도 추이
                      </p>
                      {historyQuery.isLoading && <LoadingState />}
                      {historyQuery.isError && <ErrorState error={historyQuery.error} />}
                      {historyQuery.data && historyQuery.data.length === 0 && (
                        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                          과거 평가 이력이 없습니다.
                        </p>
                      )}
                      {historyQuery.data && historyQuery.data.length > 0 && (
                        <table className="w-full text-[13px]">
                          <thead>
                            <tr style={{ color: "var(--ink-muted)" }}>
                              <th className="py-1 text-left font-medium">기간</th>
                              <th className="py-1 text-right font-medium">만족도</th>
                              <th className="py-1 text-right font-medium">평가건수</th>
                            </tr>
                          </thead>
                          <tbody>
                            {historyQuery.data.map((h, i) => (
                              <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                                <td className="py-1">
                                  {h.period_start} ~ {h.period_end}
                                </td>
                                <td className="py-1 text-right">{h.adjusted_score?.toFixed(2) ?? "-"}</td>
                                <td className="py-1 text-right">{h.evaluation_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-medium" style={{ color: "var(--ink-secondary)" }}>
                        과거 VOE 코멘트(최근 {commentsQuery.data?.length ?? 0}건)
                      </p>
                      {commentsQuery.isLoading && <LoadingState />}
                      {commentsQuery.isError && <ErrorState error={commentsQuery.error} />}
                      {commentsQuery.data && commentsQuery.data.length === 0 && (
                        <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
                          등록된 코멘트가 없습니다.
                        </p>
                      )}
                      {commentsQuery.data && commentsQuery.data.length > 0 && (
                        <ul className="max-h-56 space-y-1.5 overflow-y-auto text-[13px]">
                          {commentsQuery.data.map((c, i) => (
                            <li key={i} className="border-b pb-1.5" style={{ borderColor: "var(--border)" }}>
                              <span style={{ color: "var(--ink-muted)" }}>
                                {c.eaten_at.slice(0, 10)}
                                {c.taste_score ? ` · ${c.taste_score}` : ""}
                              </span>
                              <div>{c.comment}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
