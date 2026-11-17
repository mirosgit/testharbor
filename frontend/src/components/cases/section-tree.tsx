"use client";

import { useDroppable } from "@dnd-kit/core";
import { ChevronRight, Folder, FolderOpen, Layers, MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SectionNode } from "@/lib/tree";
import { cn } from "@/lib/utils";

export interface SectionActions {
  onAddSection: (parentId: number | null) => void;
  onAddCase: (sectionId: number) => void;
  onRename: (s: SectionNode) => void;
  onDelete: (s: SectionNode) => void;
}

export function SectionTree({
  tree,
  totalCases,
  selectedId,
  onSelect,
  actions,
}: {
  tree: SectionNode[];
  totalCases: number;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  actions: SectionActions;
}) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div role="tree" aria-label="Sections" className="grid gap-px text-sm">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted",
          selectedId === null && "bg-muted font-medium",
        )}
      >
        <Layers className="size-4 text-muted-foreground" />
        <span className="flex-1">All cases</span>
        <span className="text-xs text-muted-foreground tabular-nums">{totalCases}</span>
      </button>
      {tree.map((n) => (
        <TreeNode
          key={n.id}
          node={n}
          collapsed={collapsed}
          toggle={toggle}
          selectedId={selectedId}
          onSelect={onSelect}
          actions={actions}
        />
      ))}
    </div>
  );
}

function TreeNode({
  node,
  collapsed,
  toggle,
  selectedId,
  onSelect,
  actions,
}: {
  node: SectionNode;
  collapsed: Set<number>;
  toggle: (id: number) => void;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  actions: SectionActions;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `section:${node.id}`, data: { sectionId: node.id } });
  const isCollapsed = collapsed.has(node.id);
  const hasChildren = node.children.length > 0;
  const selected = selectedId === node.id;
  const Icon = selected ? FolderOpen : Folder;

  return (
    <div role="treeitem" aria-selected={selected} aria-expanded={hasChildren ? !isCollapsed : undefined}>
      <div
        ref={setNodeRef}
        className={cn(
          "group flex items-center gap-1 rounded-md pr-1 hover:bg-muted",
          selected && "bg-muted font-medium",
          isOver && "bg-primary/10 ring-2 ring-primary/50",
        )}
        style={{ paddingLeft: node.depth * 14 + 2 }}
      >
        <button
          type="button"
          className={cn("rounded p-0.5 text-muted-foreground hover:text-foreground", !hasChildren && "invisible")}
          onClick={() => toggle(node.id)}
          aria-label={isCollapsed ? "Expand" : "Collapse"}
        >
          <ChevronRight className={cn("size-3.5 transition-transform", !isCollapsed && "rotate-90")} />
        </button>
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
          onClick={() => onSelect(node.id)}
        >
          <Icon className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>
        <span className="text-xs text-muted-foreground tabular-nums group-hover:hidden">{node.totalCases}</span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-xs"
              className="hidden group-hover:inline-flex data-[state=open]:inline-flex"
              aria-label={`Actions for ${node.name}`}
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onSelect={() => actions.onAddCase(node.id)}>Add case</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => actions.onAddSection(node.id)}>Add subsection</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => actions.onRename(node)}>Rename</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => actions.onDelete(node)}>
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {hasChildren && !isCollapsed && (
        <div role="group">
          {node.children.map((c) => (
            <TreeNode
              key={c.id}
              node={c}
              collapsed={collapsed}
              toggle={toggle}
              selectedId={selectedId}
              onSelect={onSelect}
              actions={actions}
            />
          ))}
        </div>
      )}
    </div>
  );
}
