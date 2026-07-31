import { useState } from "react";
import { HomePage } from "./pages/HomePage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { SimulationPage } from "./pages/SimulationPage";
import { ChatPage } from "./pages/ChatPage";
import { WeeklyMenuVoeDetailPage } from "./pages/WeeklyMenuVoeDetailPage";

// "weekly-voe"는 상단 내비게이션엔 안 보이는 화면 — 홈의 "금주 메뉴 과거 VOE"
// 카드를 클릭했을 때만 진입한다(뒤로가기 버튼으로 홈에 복귀).
type Tab = "home" | "analysis" | "simulation" | "chat" | "weekly-voe";

const TABS: { value: Tab; label: string }[] = [
  { value: "home", label: "홈" },
  { value: "analysis", label: "분석" },
  { value: "simulation", label: "시뮬레이션" },
  { value: "chat", label: "Agent 채팅" },
];

function App() {
  const [tab, setTab] = useState<Tab>("home");

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
        {tab === "home" && <HomePage onOpenWeeklyVoe={() => setTab("weekly-voe")} />}
        {tab === "analysis" && <AnalysisPage />}
        {tab === "simulation" && <SimulationPage />}
        {tab === "chat" && <ChatPage />}
        {tab === "weekly-voe" && <WeeklyMenuVoeDetailPage onBack={() => setTab("home")} />}
      </main>
    </div>
  );
}

export default App;
