"use client";

import { useDraggable, useDroppable } from "@dnd-kit/core";
import { GripVertical, Plus } from "lucide-react";

import { AutomationIcon, PriorityBadge, Tag } from "@/components/badges";
import { Checkbox } from "@/components/ui/checkbox";
import { typeLabel } from "@/lib/labels";
import type { SectionNode } from "@/lib/tree";
import type { TestCase } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface CaseGroup {
  section: SectionNode;
  path: string;
  cases: TestCase[];
}

export function CaseTable({
  groups,
  selected,
  onToggle,
  onToggleMany,
  onOpen,
  onAddCase,
  activeCaseId,
  draggingIds,
}: {
  groups: CaseGroup[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleMany: (ids: number[], on: boolean) => void;
  onOpen: (c: TestCase) => void;
  onAddCase: (sectionId: number) => void;
  activeCaseId?: number;
  draggingIds: Set<number>;
}) {
  return (
    <div className="grid gap-5" data-testid="case-table">
      {groups.map((g) => {
        const ids = g.cases.map((c) => c.id);
        const all = ids.length > 0 && ids.every((id) => selected.has(id));
        const some = ids.some((id) => selected.has(id));
        return (
          <section key={g.section.id} aria-label={g.path}>
            <GroupHeader
              group={g}
              checked={all ? true : some ? "indeterminate" : false}
              onCheck={(on) => onToggleMany(ids, on)}
              onAddCase={() => onAddCase(g.section.id)}
            />
            {g.cases.length === 0 ? (
              <EmptyDrop sectionId={g.section.id} />
            ) : (
              <div className="divide-y rounded-md border">
                {g.cases.map((c) => (
                  <CaseRow
                    key={c.id}
                    c={c}
                    selected={selected.has(c.id)}
                    active={activeCaseId === c.id}
                    dragging={draggingIds.has(c.id)}
                    onToggle={() => onToggle(c.id)}
                    onOpen={() => onOpen(c)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function GroupHeader({
  group,
  checked,
  onCheck,
  onAddCase,
}: {
  group: CaseGroup;
  checked: boolean | "indeterminate";
  onCheck: (on: boolean) => void;
  onAddCase: () => void;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `group:${group.section.id}`,
    data: { sectionId: group.section.id },
  });
  return (
    <div
      ref={setNodeRef}
      className={cn("mb-1.5 flex items-center gap-2 rounded px-2 py-0.5", isOver && "bg-primary/10")}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={(v) => onCheck(v === true)}
        disabled={group.cases.length === 0}
        aria-label={`Select all in ${group.path}`}
      />
      <h3 className="text-sm font-semibold">{group.path}</h3>
      <span className="text-xs text-muted-foreground">{group.cases.length}</span>
      <button
        type="button"
        onClick={onAddCase}
        className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <Plus className="size-3.5" /> Add case
      </button>
    </div>
  );
}

function EmptyDrop({ sectionId }: { sectionId: number }) {
  const { setNodeRef, isOver } = useDroppable({ id: `empty:${sectionId}`, data: { sectionId } });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "rounded-md border border-dashed px-3 py-3 text-center text-xs text-muted-foreground",
        isOver && "border-primary bg-primary/5",
      )}
    >
      No cases in this section.
    </div>
  );
}

function CaseRow({
  c,
  selected,
  active,
  dragging,
  onToggle,
  onOpen,
}: {
  c: TestCase;
  selected: boolean;
  active: boolean;
  dragging: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const drag = useDraggable({ id: `case:${c.id}`, data: { caseId: c.id } });
  const drop = useDroppable({ id: `case:${c.id}`, data: { caseId: c.id, sectionId: c.section_id } });

  return (
    <div
      ref={drop.setNodeRef}
      data-testid="case-row"
      data-case-id={c.id}
      className={cn(
        "group relative flex items-center gap-2 bg-card px-2 py-1.5 text-sm hover:bg-muted/50",
        selected && "bg-primary/5",
        active && "bg-primary/10",
        dragging && "opacity-40",
        drop.isOver && !dragging && "before:absolute before:inset-x-0 before:-top-px before:h-0.5 before:bg-primary",
      )}
    >
      <button
        ref={drag.setNodeRef}
        {...drag.listeners}
        {...drag.attributes}
        type="button"
        className="cursor-grab text-muted-foreground/50 hover:text-muted-foreground active:cursor-grabbing"
        aria-label={`Drag ${c.key}`}
      >
        <GripVertical className="size-4" />
      </button>
      <Checkbox checked={selected} onCheckedChange={onToggle} aria-label={`Select ${c.key}`} />
      <button type="button" onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <span className="w-14 shrink-0 font-mono text-xs text-muted-foreground">{c.key}</span>
        <span className="min-w-0 flex-1 truncate">{c.title}</span>
        <span className="hidden shrink-0 gap-1 lg:flex">
          {c.tags.slice(0, 3).map((t) => (
            <Tag key={t}>{t}</Tag>
          ))}
        </span>
        <span className="hidden w-24 shrink-0 text-xs text-muted-foreground md:block">{typeLabel[c.type]}</span>
        <PriorityBadge priority={c.priority} className="w-16 shrink-0 justify-center" />
        <AutomationIcon status={c.automation_status} />
      </button>
    </div>
  );
}
