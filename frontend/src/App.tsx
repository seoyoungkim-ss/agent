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
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
          <span className="text-lg font-bold">🍽️ 사내 카페테리아 운영 관리</span>
          <nav className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => setTab(t.value)}
                className={
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors " +
                  (tab === t.value
                    ? "bg-indigo-600 text-white"
                    : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800")
                }
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
