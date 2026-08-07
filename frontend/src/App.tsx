import { useState } from "react";
import { HomePage } from "./pages/HomePage";
import { AdminPage, MenuPlanningPage, SatisfactionVoePage } from "./pages/AnalysisPage";
import { ChatPage } from "./pages/ChatPage";
import { WeeklyMenuVoeDetailPage } from "./pages/WeeklyMenuVoeDetailPage";

// 담당자 협의에서 정한 5개 축으로 재편(2026-08). 기존 "분석" 탭(서브탭 5개)과
// "시뮬레이션" 탭은 없어졌다 — 시뮬레이션의 실질 입력이던 "사내 행사" 토글은
// 현황의 금주 예상 식수 카드가 흡수했다.
// "weekly-voe"는 상단 내비게이션엔 안 보이는 화면 — 홈의 "금주 메뉴 과거 VOE"
// 카드를 클릭했을 때만 진입한다(뒤로가기 버튼으로 홈에 복귀).
type Tab = "home" | "menu-planning" | "satisfaction" | "chat" | "admin" | "weekly-voe";

const TABS: { value: Tab; label: string }[] = [
  { value: "home", label: "현황" },
  { value: "menu-planning", label: "메뉴 편성·운영" },
  { value: "satisfaction", label: "만족도·VoE" },
  { value: "chat", label: "Agent 채팅" },
  { value: "admin", label: "관리" },
];

function App() {
  const [tab, setTab] = useState<Tab>("home");
  // 홈에서 "금주 메뉴 과거 VOE"를 누른 시점의 주. 탭 전환은 상태 하나로만
  // 이뤄지고 라우터/URL이 없어서, 주차가 흐를 통로를 여기 둔다.
  const [weeklyVoeMonday, setWeeklyVoeMonday] = useState<string | undefined>(undefined);

  return (
    <div className="min-h-screen" style={{ background: "var(--page)", color: "var(--ink)" }}>
      <header className="border-b" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-6">
          <span className="py-4 text-[15px] font-semibold tracking-tight">카페테리아 운영 관리</span>
          <nav className="flex gap-6">
            {TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => setTab(t.value)}
                className="border-b-2 py-4 text-[13px] font-medium transition-colors"
                style={{
                  borderColor: tab === t.value ? "var(--accent)" : "transparent",
                  color: tab === t.value ? "var(--ink)" : "var(--ink-secondary)",
                }}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        {tab === "home" && (
          <HomePage
            onOpenWeeklyVoe={(monday) => {
              // 홈에서 보고 있던 주를 그대로 넘긴다 — 안 넘기면 상세 화면이
              // 오늘 기준으로 다시 계산해 다른 주를 연다(2026-08 신고).
              setWeeklyVoeMonday(monday);
              setTab("weekly-voe");
            }}
          />
        )}
        {tab === "menu-planning" && <MenuPlanningPage />}
        {tab === "satisfaction" && <SatisfactionVoePage />}
        {tab === "chat" && <ChatPage />}
        {tab === "admin" && <AdminPage />}
        {tab === "weekly-voe" && (
          <WeeklyMenuVoeDetailPage monday={weeklyVoeMonday} onBack={() => setTab("home")} />
        )}
      </main>
    </div>
  );
}

export default App;
