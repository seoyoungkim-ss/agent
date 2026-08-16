import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Bot, CloudSun, LayoutDashboard, MessageSquareHeart, Settings, UtensilsCrossed } from "lucide-react";
import { HomePage } from "./pages/HomePage";
import { AdminPage, MenuPlanningPage, SatisfactionVoePage, SimulationPage } from "./pages/AnalysisPage";
import { ChatPage } from "./pages/ChatPage";
import { WeeklyMenuVoeDetailPage } from "./pages/WeeklyMenuVoeDetailPage";

// 담당자 협의에서 정한 5개 축으로 재편(2026-08). 기존 "분석" 탭(서브탭 5개)과
// "시뮬레이션" 탭은 없어졌다 — 시뮬레이션의 실질 입력이던 "사내 행사" 토글은
// 현황의 금주 예상 식수 카드가 흡수했다.
// §81: 날씨 관련 화면은 "시뮬레이션" 탭으로 다시 분리했다 — 위 흡수 결정은
// 그대로 두고(사내 행사 토글은 복원하지 않음), 날씨 콘텐츠만 별도 탭으로
// 옮겨달라는 명시적 요청이라 이 부분만 되돌린다.
// "weekly-voe"는 사이드바 내비게이션엔 안 보이는 화면 — 홈의 "금주 메뉴 과거
// VOE" 카드를 클릭했을 때만 진입한다(뒤로가기 버튼으로 홈에 복귀).
type Tab = "home" | "menu-planning" | "simulation" | "satisfaction" | "chat" | "admin" | "weekly-voe";

const TABS: { value: Tab; label: string; icon: LucideIcon }[] = [
  { value: "home", label: "현황", icon: LayoutDashboard },
  { value: "menu-planning", label: "메뉴 편성·운영", icon: UtensilsCrossed },
  { value: "simulation", label: "시뮬레이션", icon: CloudSun },
  { value: "satisfaction", label: "만족도·VoE", icon: MessageSquareHeart },
  { value: "chat", label: "Agent 채팅", icon: Bot },
  { value: "admin", label: "관리", icon: Settings },
];

function App() {
  const [tab, setTab] = useState<Tab>("home");
  // 홈에서 "금주 메뉴 과거 VOE"를 누른 시점의 주. 탭 전환은 상태 하나로만
  // 이뤄지고 라우터/URL이 없어서, 주차가 흐를 통로를 여기 둔다.
  const [weeklyVoeMonday, setWeeklyVoeMonday] = useState<string | undefined>(undefined);

  return (
    <div className="flex min-h-screen" style={{ background: "var(--page)", color: "var(--ink)" }}>
      <aside
        className="flex w-60 shrink-0 flex-col border-r px-3 py-5"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <span className="mb-6 px-3 text-[15px] font-semibold tracking-tight">카페테리아 운영 관리</span>
        <nav className="flex flex-col gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.value;
            return (
              <button
                key={t.value}
                onClick={() => setTab(t.value)}
                className="flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[13px] font-medium transition-colors"
                style={{
                  background: active ? "var(--surface-2)" : "transparent",
                  color: active ? "var(--ink)" : "var(--ink-secondary)",
                  boxShadow: active ? "inset 3px 0 0 var(--accent)" : undefined,
                }}
              >
                <Icon size={17} strokeWidth={2} />
                {t.label}
              </button>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1 px-8 py-8">
        <div className="max-w-6xl">
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
          {tab === "simulation" && <SimulationPage />}
          {tab === "satisfaction" && <SatisfactionVoePage />}
          {tab === "chat" && <ChatPage />}
          {tab === "admin" && <AdminPage />}
          {tab === "weekly-voe" && (
            <WeeklyMenuVoeDetailPage monday={weeklyVoeMonday} onBack={() => setTab("home")} />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
