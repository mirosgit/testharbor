import { Bot, Hand, Hourglass } from "lucide-react";

import { automationLabel, priorityClass, priorityLabel, statusLabel, statusPill } from "@/lib/labels";
import type { AutomationStatus, Priority, ResultStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export function PriorityBadge({ priority, className }: { priority: Priority; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium",
        priorityClass[priority],
        className,
      )}
    >
      {priorityLabel[priority]}
    </span>
  );
}

const automationIcon = { automated: Bot, manual: Hand, to_be_automated: Hourglass };

export function AutomationIcon({ status }: { status: AutomationStatus }) {
  const Icon = automationIcon[status];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex",
            status === "automated" ? "text-primary" : "text-muted-foreground",
          )}
          aria-label={automationLabel[status]}
        >
          <Icon className="size-4" />
        </span>
      </TooltipTrigger>
      <TooltipContent>{automationLabel[status]}</TooltipContent>
    </Tooltip>
  );
}

export function StatusBadge({ status, className }: { status: ResultStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        statusPill[status],
        className,
      )}
    >
      {statusLabel[status]}
    </span>
  );
}

export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded border bg-background px-1.5 py-px text-[11px] text-muted-foreground">
      {children}
    </span>
  );
}
