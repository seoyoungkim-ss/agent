import type { ReactNode } from "react";
import clsx from "clsx";

export function Card({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div
      className={clsx("rounded-md border p-5", className)}
      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
    >
      {title && (
        <h3 className="mb-3 text-[13px] font-medium" style={{ color: "var(--ink-secondary)" }}>
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-md border p-4" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
      <div className="text-[13px]" style={{ color: "var(--ink-secondary)" }}>
        {label}
      </div>
      <div className="mt-1 text-[28px] font-semibold leading-none" style={{ color: "var(--ink)" }}>
        {value}
      </div>
      {sub && (
        <div className="mt-1.5 text-xs" style={{ color: "var(--ink-muted)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

// PRD 6.3.4: 메뉴 4분면은 사실상 "건강도" 신호(좋음/주의/심각/위험)에 가까워
// 데이터비즈 status 팔레트를 그대로 매핑한다. 텍스트는 항상 ink를 쓰고, 색은
// 점(dot)에만 실어 "텍스트에 데이터 색을 입히지 않는다" 규칙을 지킨다.
const QUADRANT_COLOR: Record<string, string> = {
  인기메뉴: "var(--good)",
  숨은강자: "var(--series-1)",
  개선시급: "var(--warning)",
  퇴출후보: "var(--critical)",
  표본부족: "var(--ink-muted)",
};

export function QuadrantBadge({ label }: { label: string | null }) {
  if (!label) return <span style={{ color: "var(--ink-muted)" }}>-</span>;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs"
      style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
    >
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: QUADRANT_COLOR[label] ?? "var(--ink-muted)" }}
      />
      {label}
    </span>
  );
}

export function quadrantColor(label: string | null): string {
  return QUADRANT_COLOR[label ?? ""] ?? "var(--ink-muted)";
}

// ECharts는 Canvas에 그리기 때문에 CSS var()를 해석하지 못한다(값을 대입해도
// 조용히 무시되고 내부 기본값으로 대체됨) — 그래서 차트 옵션에 넣을 색은 항상
// 이 함수로 실제 계산된 값을 읽어와야 라이트/다크 모드에 맞게 반영된다.
export function resolveColor(cssVarExpr: string): string {
  if (typeof window === "undefined" || !cssVarExpr.startsWith("var(")) return cssVarExpr;
  const varName = cssVarExpr.slice(4, -1).trim();
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || "#898781";
}

export function useChartTheme() {
  return {
    text: resolveColor("var(--ink-muted)"),
    axis: resolveColor("var(--chart-axis)"),
    grid: resolveColor("var(--chart-gridline)"),
    accent: resolveColor("var(--accent)"),
  };
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
    <div
      className="inline-flex rounded-md border p-0.5"
      style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="rounded px-3 py-1.5 text-[13px] font-medium transition-colors"
          style={
            value === opt.value
              ? { background: "var(--surface)", color: "var(--ink)" }
              : { color: "var(--ink-secondary)" }
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function LoadingState({ label = "불러오는 중" }: { label?: string }) {
  return (
    <div className="p-6 text-[13px]" style={{ color: "var(--ink-muted)" }}>
      {label}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      className="rounded-md border px-4 py-3 text-[13px]"
      style={{ borderColor: "var(--critical)", color: "var(--critical)", background: "var(--surface-2)" }}
    >
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
      className="rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
      style={
        variant === "primary"
          ? { background: "var(--accent)", color: "var(--accent-ink)" }
          : { border: "1px solid var(--border)", color: "var(--ink-secondary)", background: "var(--surface)" }
      }
    >
      {children}
    </button>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs" style={{ color: "var(--ink-secondary)" }}>
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function Table({
  columns,
  rows,
  rowKey,
}: {
  columns: { key: string; label: string; align?: "left" | "right" }[];
  rows: Record<string, ReactNode>[];
  rowKey: (row: Record<string, ReactNode>, i: number) => string;
}) {
  return (
    <table className="w-full text-[13px]" style={{ color: "var(--ink)" }}>
      <thead>
        <tr>
          {columns.map((col) => (
            <th
              key={col.key}
              className={clsx("border-b py-2 pr-4 font-medium", col.align === "right" && "text-right")}
              style={{ borderColor: "var(--border-strong)", color: "var(--ink-muted)" }}
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={rowKey(row, i)} className="border-b" style={{ borderColor: "var(--border)" }}>
            {columns.map((col) => (
              <td key={col.key} className={clsx("py-2 pr-4", col.align === "right" && "text-right")}>
                {row[col.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
