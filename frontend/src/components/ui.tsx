import type { ReactNode } from "react";
import clsx from "clsx";

export function Card({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900",
        className,
      )}
    >
      {title && <h3 className="mb-3 text-sm font-semibold text-slate-500 dark:text-slate-400">{title}</h3>}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

const QUADRANT_COLORS: Record<string, string> = {
  인기메뉴: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  숨은강자: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  개선시급: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  퇴출후보: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  표본부족: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

export function QuadrantBadge({ label }: { label: string | null }) {
  if (!label) return <span className="text-slate-400">-</span>;
  return (
    <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", QUADRANT_COLORS[label])}>{label}</span>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { label: string; value: T }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-700 dark:bg-slate-800">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={clsx(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            value === opt.value
              ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function LoadingState({ label = "불러오는 중..." }: { label?: string }) {
  return <div className="p-6 text-sm text-slate-400">{label}</div>;
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
      {message}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary";
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary"
          ? "bg-indigo-600 text-white hover:bg-indigo-500"
          : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
      )}
    >
      {children}
    </button>
  );
}
