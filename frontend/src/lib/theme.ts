// §104: 다크모드 수동 토글 — 저장된 선택이 없으면 시스템 설정을 따르고,
// 한 번 토글하면 그 선택이 localStorage에 저장돼 이후 방문·시스템 설정
// 변경과 무관하게 유지된다.

export type Theme = "light" | "dark";

const STORAGE_KEY = "cafeteria-theme";

export function getInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
}
