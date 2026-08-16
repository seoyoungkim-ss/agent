import type { ReactNode } from "react";
import clsx from "clsx";

export function Card({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div
      className={clsx("rounded-2xl border p-6 shadow-sm", className)}
      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
    >
      {title && (
        <h3 className="mb-2 text-[12px] font-semibold tracking-wide" style={{ color: "var(--ink-muted)" }}>
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

const STAT_TILE_TONE_COLOR: Record<string, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
};

// §98(3단계): 카드 배경에 옅게 깔리는 최근 추이 — 값이 2개 미만이면 그리지
// 않는다. ECharts 인스턴스 없이 순수 SVG로 그려 타일 하나당 비용을 최소화한다.
function StatTileSparkline({ values, color }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = range === 0 ? 20 : 36 - ((v - min) / range) * 32;
      return `${x},${y}`;
    })
    .join(" ");
  // §101: 다크 강조 카드(고정 어두운 배경) 위에서는 기본 opacity(0.15)가
  // 너무 옅어 보여, 지정된 색상일 때만 조금 더 진하게 그린다.
  return (
    <svg
      className="pointer-events-none absolute inset-x-0 bottom-0 h-10 w-full"
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color ?? "var(--accent)"}
        strokeWidth="2"
        opacity={color ? "0.25" : "0.15"}
      />
    </svg>
  );
}

const STAT_TILE_TREND_COLOR: Record<string, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
  neutral: "var(--ink-muted)",
};

const TREND_ARROW: Record<"up" | "down" | "flat", string> = { up: "▲", down: "▼", flat: "―" };

export function StatTile({
  label,
  value,
  sub,
  onClick,
  tone,
  trend,
  sparkline,
  variant,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  onClick?: () => void;
  // 핵심 수치가 상태(주의/위험 등)를 나타낼 때만 지정 — 값 텍스트에는 색을 넣지
  // 않고 라벨 옆 점(dot)에만 싣는다(QuadrantBadge와 동일한 "색은 점에만" 규칙).
  tone?: "good" | "warning" | "critical";
  // §98(3단계): 전일/전주 대비 방향 배지. direction(화살표 모양)과
  // tone(색상)을 분리했다 — "증가가 항상 좋은 신호"는 아니라서(예: 규칙
  // 위반 건수는 증가=critical) 호출부가 의미를 직접 판단해 넘긴다.
  trend?: { direction: "up" | "down" | "flat"; text: string; tone: "good" | "warning" | "critical" | "neutral" };
  sparkline?: number[];
  // §101: 탭당 대표 지표 하나를 OS 다크모드 여부와 무관하게 항상 어두운
  // 고정색(--hero-*)으로 강조. 기본값 없음 = 기존 호출부는 전부 무변경.
  variant?: "default" | "dark";
}) {
  const Tag = onClick ? "button" : "div";
  const toneColor = tone ? STAT_TILE_TONE_COLOR[tone] : undefined;
  const isDark = variant === "dark";
  return (
    <Tag
      className={clsx(
        "relative w-full overflow-hidden rounded-2xl border p-6 text-left shadow-sm transition-colors",
        onClick && "hover:border-current",
      )}
      style={{
        borderColor: isDark ? "rgba(255,255,255,0.08)" : "var(--border)",
        background: isDark ? "var(--hero-bg)" : "var(--surface)",
        cursor: onClick ? "pointer" : undefined,
        // borderLeftColor/Width를 매 렌더 항상 같은 키로 넣는다 — tone 유무에 따라
        // 키 자체를 넣었다 뺐다 하면(§92 규칙 이상여부 타일처럼 tone이 로딩 중
        // undefined였다가 나중에 생기는 경우) React가 shorthand(borderColor)와
        // longhand(borderLeftColor)를 섞어 쓴다고 콘솔 경고를 낸다.
        borderLeftColor: toneColor ?? (isDark ? "rgba(255,255,255,0.08)" : "var(--border)"),
        borderLeftWidth: toneColor ? 3 : 1,
      }}
      onClick={onClick}
    >
      {sparkline && (
        <StatTileSparkline values={sparkline} color={isDark ? "var(--hero-accent)" : undefined} />
      )}
      <div className="relative">
        <div
          className="flex items-center gap-1.5 text-[13px]"
          style={{ color: isDark ? "var(--hero-ink-muted)" : "var(--ink-secondary)" }}
        >
          {toneColor && <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: toneColor }} />}
          {label}
        </div>
        <div className="mt-1 flex items-baseline gap-2">
          <span
            className="text-[28px] font-bold leading-none"
            style={{ color: isDark ? "var(--hero-accent)" : "var(--ink)" }}
          >
            {value}
          </span>
          {trend && (
            <span
              className="text-[12px] font-medium"
              style={{
                color:
                  isDark && trend.tone === "neutral" ? "var(--hero-ink-muted)" : STAT_TILE_TREND_COLOR[trend.tone],
              }}
            >
              {TREND_ARROW[trend.direction]} {trend.text}
            </span>
          )}
        </div>
        {sub && (
          <div className="mt-1.5 text-xs" style={{ color: isDark ? "var(--hero-ink-muted)" : "var(--ink-muted)" }}>
            {sub}
          </div>
        )}
      </div>
    </Tag>
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
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs"
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

const BADGE_TONE_COLOR: Record<string, string> = {
  critical: "var(--critical)",
  warning: "var(--warning)",
  good: "var(--good)",
  accent: "var(--accent)",
  muted: "var(--ink-muted)",
};

// 경고/위험 상태를 표시하는 작은 공용 컴포넌트 — QuadrantBadge와 같은 "색은
// 점(dot)에만 싣고 글자는 항상 ink" 규칙(§39.12)을 따른다. 옅은 색 텍스트가
// 주변 회색 설명글에 묻혀 "눈에 안 들어온다"는 신고(2026-08, 중복점검 화면)에
// 대응 — 색 텍스트를 쓰던 자리를 이걸로 교체하면 자동으로 규칙을 지키게 된다.
export function Badge({
  label,
  tone,
}: {
  label: ReactNode;
  tone: "critical" | "warning" | "good" | "accent" | "muted";
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: BADGE_TONE_COLOR[tone] }} />
      <span style={{ color: "var(--ink)" }}>{label}</span>
    </span>
  );
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
  options: { label: ReactNode; value: T }[];
  onChange: (v: T) => void;
}) {
  return (
    <div
      className="inline-flex rounded-full border p-0.5"
      style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors"
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
      className="rounded-xl border px-4 py-3 text-[13px]"
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
      className="rounded-xl px-4 py-2 text-[13px] font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
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
    // 열 내용(특히 긴 코너명 등)이 좁은 칸에서 세로로 늘어지는 문제
    // (2026-08 신고) — 셀은 줄바꿈하지 않고 넘치면 컨테이너가 가로 스크롤로
    // 받는다. 이 컴포넌트를 쓰는 모든 표에 한 번에 적용된다.
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]" style={{ color: "var(--ink)" }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  "whitespace-nowrap border-b py-2.5 pr-4 font-medium",
                  col.align === "right" && "text-right",
                )}
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
                <td
                  key={col.key}
                  className={clsx("whitespace-nowrap py-2.5 pr-4", col.align === "right" && "text-right")}
                >
                  {row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
