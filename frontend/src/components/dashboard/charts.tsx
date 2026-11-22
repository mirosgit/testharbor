"use client";

import Link from "next/link";
import { useId, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export const fmt = (n: number) => n.toLocaleString("en-US");
export const pct = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : `${n.toFixed(digits).replace(/\.0+$/, "")}%`;

export interface Part {
  key: string;
  label: string;
  value: number;
  /** Tailwind background class of the swatch and the segment. */
  color: string;
  href?: string;
  note?: string;
}

/** A card of the dashboard: a title, an optional hint and action, then the content. */
export function Panel({
  title,
  hint,
  action,
  className,
  children,
  ...rest
}: {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-xl border bg-card p-4 shadow-xs sm:p-5", className)} {...rest}>
      <header className="mb-4 flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/** One bar split into parts, with a 2px gap between them. */
export function SegmentBar({ parts, className, label }: { parts: Part[]; className?: string; label: string }) {
  const total = parts.reduce((n, p) => n + p.value, 0);
  return (
    <div className={cn("flex h-3 w-full gap-0.5 overflow-hidden rounded-full", className)} role="img" aria-label={label}>
      {total === 0 ? (
        <div className="h-full w-full bg-muted" />
      ) : (
        parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <div
              key={p.key}
              className={cn("h-full min-w-1 transition-[flex-grow] duration-500", p.color)}
              style={{ flexGrow: p.value, flexBasis: 0 }}
              title={`${p.label}: ${fmt(p.value)}`}
            />
          ))
      )}
    </div>
  );
}

/** The legend of a SegmentBar: a swatch, the name, the count and the share; rows link to the cases. */
export function Legend({ parts }: { parts: Part[] }) {
  const total = parts.reduce((n, p) => n + p.value, 0);
  return (
    <ul className="grid gap-0.5">
      {parts.map((p) => {
        const body = (
          <>
            <span className={cn("size-2.5 shrink-0 rounded-[3px]", p.color)} aria-hidden />
            <span className="min-w-0 flex-1 truncate">
              {p.label}
              {p.note && <span className="ml-1.5 text-xs text-muted-foreground">{p.note}</span>}
            </span>
            <span className="tabular-nums font-medium">{fmt(p.value)}</span>
            <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
              {total ? pct((100 * p.value) / total) : "—"}
            </span>
          </>
        );
        const cls = "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm";
        return (
          <li key={p.key}>
            {p.href && p.value > 0 ? (
              <Link href={p.href} className={cn(cls, "-mx-0 transition-colors hover:bg-muted")}>
                {body}
              </Link>
            ) : (
              <div className={cls}>{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** A thin progress meter. */
export function Meter({ value, max, className, color = "bg-chart-automated", label }: {
  value: number;
  max: number;
  className?: string;
  color?: string;
  label?: string;
}) {
  const w = max > 0 ? Math.max(0, Math.min(100, (100 * value) / max)) : 0;
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-label={label}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500", color)} style={{ width: `${w}%` }} />
    </div>
  );
}

/** A small line of values (nulls are gaps), for a stat tile. Decorative: the tile states the number. */
export function Sparkline({ values, className }: { values: (number | null)[]; className?: string }) {
  const id = useId();
  const pts = values.map((v, i) => (v == null ? null : ([i, v] as const)));
  const known = pts.filter((p): p is readonly [number, number] => p !== null);
  if (known.length < 3) return <div className={className} />; // two points make a line, not a trend
  const W = 100, H = 28;
  const lo = Math.min(...known.map((p) => p[1]));
  const hi = Math.max(...known.map((p) => p[1]));
  const span = hi - lo || 1;
  const x = (i: number) => (values.length > 1 ? (i / (values.length - 1)) * W : W / 2);
  const y = (v: number) => H - 3 - ((v - lo) / span) * (H - 6);
  const line = known.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join("");
  const area = `${line}L${x(known[known.length - 1][0]).toFixed(2)},${H}L${x(known[0][0]).toFixed(2)},${H}Z`;
  const [li, lv] = known[known.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={cn("overflow-visible", className)} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="var(--chart-automated)" stopOpacity="0.18" />
          <stop offset="1" stopColor="var(--chart-automated)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke="var(--chart-automated)" strokeWidth="2" vectorEffect="non-scaling-stroke"
            strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(li)} cy={y(lv)} r="3.5" fill="var(--chart-automated)" stroke="var(--card)" strokeWidth="2"
              vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export interface Series<T> {
  key: keyof T & string;
  label: string;
  color: string;
}

/**
 * Stacked columns with a hover (and arrow-key) tooltip. Columns grow from one baseline; the top segment
 * has the rounded end. `href` makes a column a link (a run).
 */
export function StackedColumns<T>({
  items,
  series,
  label,
  title,
  tickLabel,
  href,
  normalize = false,
  height = 176,
  empty,
}: {
  items: T[];
  series: Series<T>[];
  label: string;
  title: (item: T) => string;
  tickLabel?: (item: T, i: number) => string | null;
  href?: (item: T) => string;
  normalize?: boolean;
  height?: number;
  empty?: ReactNode;
}) {
  const [active, setActive] = useState<number | null>(null);
  const totals = useMemo(
    () => items.map((it) => series.reduce((n, s) => n + (Number(it[s.key]) || 0), 0)),
    [items, series],
  );
  const max = normalize ? 1 : niceMax(Math.max(0, ...totals));
  const ticks = normalize ? [0, 0.5, 1] : [0, max / 2, max];
  const any = totals.some((t) => t > 0);

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const d = e.key === "ArrowLeft" ? -1 : 1;
    setActive((a) => Math.max(0, Math.min(items.length - 1, (a ?? (d > 0 ? -1 : items.length)) + d)));
  };

  const shown = active !== null ? (items[active] ?? null) : null;
  const leftPct = active !== null ? ((active + 0.5) / items.length) * 100 : 0;

  return (
    <div className="relative">
      <div className="flex gap-2">
        {/* y-axis ticks */}
        <div className="relative w-8 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground" style={{ height }}>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${(1 - t / max) * 100}%` }}>
              {normalize ? `${Math.round(t * 100)}%` : compact(t)}
            </span>
          ))}
        </div>
        <div
          className="relative min-w-0 flex-1 rounded-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          style={{ height }}
          tabIndex={0}
          role="group"
          aria-label={`${label}. Use the left and right arrow keys to read the values.`}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
          onMouseLeave={() => setActive(null)}
        >
          {ticks.map((t) => (
            <div key={t} className="pointer-events-none absolute inset-x-0 border-t border-border/70"
                 style={{ top: `${(1 - t / max) * 100}%` }} />
          ))}
          {!any && empty && (
            <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-muted-foreground">
              {empty}
            </div>
          )}
          <div className={cn("absolute inset-0 flex items-end", items.length > 45 ? "gap-px" : "gap-[3px]")}>
            {items.map((it, i) => {
              const total = totals[i];
              const scale = normalize ? (total ? 1 / total : 0) : 1 / max;
              const col = (
                <div className="flex h-full w-full max-w-6 flex-col-reverse items-stretch">
                  {series.map((s) => {
                    const v = Number(it[s.key]) || 0;
                    if (!v) return null;
                    return (
                      <div
                        key={s.key}
                        className={cn("w-full border-t-2 border-card first:border-t-0 last:rounded-t-[4px]", s.color)}
                        style={{ height: `${v * scale * 100}%` }}
                      />
                    );
                  })}
                </div>
              );
              const cls = cn(
                "flex h-full min-w-0 flex-1 cursor-default items-end justify-center rounded-sm transition-colors",
                active === i && "bg-muted/70",
              );
              return href ? (
                <Link key={i} href={href(it)} className={cn(cls, "cursor-pointer")} tabIndex={-1} aria-hidden
                      onMouseEnter={() => setActive(i)}>
                  {col}
                </Link>
              ) : (
                <div key={i} className={cls} onMouseEnter={() => setActive(i)}>
                  {col}
                </div>
              );
            })}
          </div>
          {shown !== null && active !== null && (
            <div
              className="pointer-events-none absolute top-1 z-10 w-max max-w-56 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md"
              style={{
                left: `${leftPct}%`,
                // beside the column, on the side with more room
                transform: leftPct > 50 ? "translateX(calc(-100% - 14px))" : "translateX(14px)",
              }}
              role="status"
            >
              <div className="mb-1 truncate font-medium">{title(shown)}</div>
              {series.map((s) => {
                const v = Number(shown[s.key]) || 0;
                return (
                  <div key={s.key} className={cn("flex items-center gap-2", !v && "text-muted-foreground")}>
                    <span className={cn("size-2 rounded-[2px]", s.color)} />
                    <span className="flex-1">{s.label}</span>
                    <span className="tabular-nums">{fmt(v)}</span>
                  </div>
                );
              })}
              <div className="mt-1 flex justify-between border-t pt-1 text-muted-foreground">
                <span>Total</span>
                <span className="tabular-nums">{fmt(totals[active])}</span>
              </div>
            </div>
          )}
        </div>
      </div>
      {tickLabel && (
        <div className="mt-1.5 flex gap-2">
          <div className="w-8 shrink-0" />
          <div className="relative h-4 min-w-0 flex-1 text-[10px] text-muted-foreground">
            {items.map((it, i) => {
              const t = tickLabel(it, i);
              if (!t) return null;
              const left = ((i + 0.5) / items.length) * 100;
              return (
                <span key={i} className="absolute -translate-x-1/2 whitespace-nowrap first:translate-x-[-25%]"
                      style={{ left: `${left}%` }}>
                  {t}
                </span>
              );
            })}
          </div>
        </div>
      )}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className={cn("size-2.5 rounded-[3px]", s.color)} aria-hidden />
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const mag = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * mag >= v) return m * mag;
  return 10 * mag;
}

function compact(n: number): string {
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(Math.round(n));
}
