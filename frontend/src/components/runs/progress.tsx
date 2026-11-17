import { statusBg, statusLabel } from "@/lib/labels";
import { RESULT_STATUSES, type RunStats } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export function RunProgress({ stats, className }: { stats: RunStats; className?: string }) {
  const total = stats.total || 1;
  return (
    <div
      className={cn("flex h-2 w-full overflow-hidden rounded-full bg-status-untested", className)}
      role="img"
      aria-label={RESULT_STATUSES.map((s) => `${stats[s]} ${s}`).join(", ")}
    >
      {RESULT_STATUSES.filter((s) => s !== "untested" && stats[s] > 0).map((s) => (
        <Tooltip key={s}>
          <TooltipTrigger asChild>
            <div className={cn("h-full", statusBg[s])} style={{ width: `${(stats[s] / total) * 100}%` }} />
          </TooltipTrigger>
          <TooltipContent>
            {stats[s]} {statusLabel[s].toLowerCase()}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

export function percentDone(stats: RunStats) {
  return stats.total ? Math.round(((stats.total - stats.untested) / stats.total) * 100) : 0;
}

export function passRate(stats: RunStats) {
  const done = stats.total - stats.untested;
  return done ? Math.round((stats.passed / done) * 100) : 0;
}

export function StatusCounts({
  stats,
  active,
  onToggle,
}: {
  stats: RunStats;
  active?: Set<string>;
  onToggle?: (s: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {RESULT_STATUSES.map((s) => {
        const on = active?.has(s);
        const Comp = onToggle ? "button" : "span";
        return (
          <Comp
            key={s}
            type={onToggle ? "button" : undefined}
            onClick={onToggle ? () => onToggle(s) : undefined}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
              onToggle && "hover:bg-muted",
              on && "border-primary bg-primary/5",
            )}
          >
            <span className={cn("size-2 rounded-full", statusBg[s])} />
            {statusLabel[s]}
            <span className="font-semibold tabular-nums">{stats[s]}</span>
          </Comp>
        );
      })}
    </div>
  );
}
