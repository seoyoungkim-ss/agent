import { useState } from "react";
import { HomePage } from "./pages/HomePage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { SimulationPage } from "./pages/SimulationPage";
import { ChatPage } from "./pages/ChatPage";

type Tab = "home" | "analysis" | "simulation" | "chat";

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
        {tab === "home" && <HomePage />}
        {tab === "analysis" && <AnalysisPage />}
        {tab === "simulation" && <SimulationPage />}
        {tab === "chat" && <ChatPage />}
      </main>
    </div>
  );
}

export default App;
