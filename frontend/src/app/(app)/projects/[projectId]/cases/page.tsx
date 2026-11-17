"use client";

import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  FolderPlus,
  MoreHorizontal,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { CaseSheet, type SheetState } from "@/components/cases/case-sheet";
import { CaseTable, type CaseGroup } from "@/components/cases/case-table";
import { emptyFilters, FilterBar, isFiltered, type Filters } from "@/components/cases/filter-bar";
import { ImportDialog } from "@/components/cases/import-dialog";
import { MoveDialog } from "@/components/cases/move-dialog";
import { SectionTree } from "@/components/cases/section-tree";
import { ConfirmDialog, NameDialog } from "@/components/dialogs";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { buildTree, flatten, type SectionNode } from "@/lib/tree";
import type { Suite, TestCase } from "@/lib/types";

type Dialog =
  | { kind: "newSuite" }
  | { kind: "renameSuite"; suite: Suite }
  | { kind: "deleteSuite"; suite: Suite }
  | { kind: "newSection"; parentId: number | null }
  | { kind: "renameSection"; section: SectionNode }
  | { kind: "deleteSection"; section: SectionNode }
  | { kind: "import" }
  | { kind: "move" }
  | { kind: "bulkDelete" }
  | null;

export default function CasesPage() {
  return (
    <Suspense>
      <CasesWorkspace />
    </Suspense>
  );
}

function CasesWorkspace() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const qc = useQueryClient();

  const setParams = useCallback(
    (patch: Record<string, string | number | null>) => {
      const next = new URLSearchParams(search.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null) next.delete(k);
        else next.set(k, String(v));
      }
      router.replace(`${pathname}?${next}`, { scroll: false });
    },
    [search, router, pathname],
  );

  // --- Data ---------------------------------------------------------------------------
  const suitesQ = useQuery({ queryKey: ["suites", projectId], queryFn: () => api.suites(projectId) });
  const suites = suitesQ.data ?? [];
  const suiteId = Number(search.get("suite")) || suites[0]?.id;
  const suite = suites.find((s) => s.id === suiteId);
  const sectionId = search.get("section") ? Number(search.get("section")) : null;
  const openCaseId = search.get("case") ? Number(search.get("case")) : null;

  const sectionsQ = useQuery({
    queryKey: ["sections", suiteId],
    queryFn: () => api.sections(suiteId!),
    enabled: !!suiteId,
  });
  const tree = useMemo(() => buildTree(sectionsQ.data ?? []), [sectionsQ.data]);
  const flat = useMemo(() => flatten(tree), [tree]);
  const paths = useMemo(() => {
    const m = new Map<number, string>();
    const byId = new Map(flat.map((s) => [s.id, s]));
    for (const s of flat) {
      const parts = [s.name];
      let p = s.parent_id != null ? byId.get(s.parent_id) : undefined;
      while (p) {
        parts.unshift(p.name);
        p = p.parent_id != null ? byId.get(p.parent_id) : undefined;
      }
      m.set(s.id, parts.join(" › "));
    }
    return m;
  }, [flat]);

  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const filtered = isFiltered(filters);
  const casesQ = useQuery({
    queryKey: ["cases", projectId, suiteId, sectionId, filters],
    queryFn: () =>
      api.cases(projectId, {
        suite_id: suiteId,
        section_id: sectionId ?? undefined,
        q: filters.q || undefined,
        tags: filters.tags,
        priority: filters.priority,
        type: filters.type,
        automation_status: filters.automation_status,
      }),
    enabled: !!suiteId,
    placeholderData: (prev) => prev,
  });
  const { data: tags = [] } = useQuery({ queryKey: ["tags", projectId], queryFn: () => api.tags(projectId) });

  // Group cases by section in tree order. Without filters show every section in scope
  // (so empty sections are visible drop targets); with filters only sections with hits.
  const groups: CaseGroup[] = useMemo(() => {
    const cases = casesQ.data?.items ?? [];
    const bySection = new Map<number, TestCase[]>();
    for (const c of cases) {
      if (!bySection.has(c.section_id)) bySection.set(c.section_id, []);
      bySection.get(c.section_id)!.push(c);
    }
    let scope = flat;
    if (sectionId !== null) {
      const root = flat.find((s) => s.id === sectionId);
      scope = root ? flatten([root]) : [];
    }
    return scope
      // Parent sections with no direct cases only add noise; their children are listed.
      .filter((s) => (filtered ? bySection.has(s.id) : bySection.has(s.id) || s.children.length === 0))
      .map((s) => ({
        section: s,
        path: paths.get(s.id) ?? s.name,
        cases: (bySection.get(s.id) ?? []).sort((a, b) => a.position - b.position || a.id - b.id),
      }));
  }, [casesQ.data, flat, sectionId, filtered, paths]);
  const visibleCases = useMemo(() => groups.flatMap((g) => g.cases), [groups]);

  // --- Selection ----------------------------------------------------------------------
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const toggleMany = (ids: number[], on: boolean) =>
    setSelected((prev) => {
      const n = new Set(prev);
      ids.forEach((id) => (on ? n.add(id) : n.delete(id)));
      return n;
    });

  // --- Mutations ----------------------------------------------------------------------
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cases"] });
    qc.invalidateQueries({ queryKey: ["sections"] });
    qc.invalidateQueries({ queryKey: ["suites", projectId] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };
  const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

  const moveCases = async (ids: number[], targetSection: number, position?: number) => {
    try {
      await api.moveCases(ids, targetSection, position);
      const label = ids.length === 1 ? visibleCases.find((c) => c.id === ids[0])?.key ?? "1 case" : `${ids.length} cases`;
      toast.success(`Moved ${label} to ${paths.get(targetSection)}`);
      refresh();
    } catch (e) {
      fail(e);
    }
  };

  // --- Drag and drop ------------------------------------------------------------------
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [dragIds, setDragIds] = useState<number[]>([]);
  const onDragStart = (e: DragStartEvent) => {
    const id = e.active.data.current?.caseId as number;
    setDragIds(selected.has(id) ? visibleCases.filter((c) => selected.has(c.id)).map((c) => c.id) : [id]);
  };
  const onDragEnd = (e: DragEndEvent) => {
    const ids = dragIds;
    setDragIds([]);
    const over = e.over?.data.current as { sectionId: number; caseId?: number } | undefined;
    if (!over || ids.length === 0) return;
    if (over.caseId !== undefined) {
      if (ids.includes(over.caseId)) return;
      // Insert before the target case: its index among the section's remaining cases.
      const remaining = visibleCases.filter((c) => c.section_id === over.sectionId && !ids.includes(c.id));
      const index = remaining.findIndex((c) => c.id === over.caseId);
      void moveCases(ids, over.sectionId, index);
    } else {
      const alreadyThere = ids.every((id) => visibleCases.find((c) => c.id === id)?.section_id === over.sectionId);
      if (!alreadyThere) void moveCases(ids, over.sectionId);
    }
  };

  // --- Dialogs / sheet ------------------------------------------------------------------
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);
  const [createIn, setCreateIn] = useState<number | null>(null);
  const sheet: SheetState =
    createIn !== null
      ? { mode: "create", sectionId: createIn }
      : openCaseId !== null
        ? { mode: "view", caseId: openCaseId }
        : null;
  const addCase = (sid?: number) => {
    const target = sid ?? sectionId ?? flat[0]?.id;
    if (target === undefined) {
      setDialog({ kind: "newSection", parentId: null });
      toast.info("Create a section first");
      return;
    }
    setCreateIn(target);
  };

  const sectionTitle = sectionId !== null ? paths.get(sectionId) : "All cases";
  const selectedIds = visibleCases.filter((c) => selected.has(c.id)).map((c) => c.id);

  // --- Render -------------------------------------------------------------------------
  if (suitesQ.isLoading) {
    return (
      <div className="grid h-full grid-cols-[280px_1fr]">
        <div className="border-r p-3">
          <Skeleton className="h-8" />
        </div>
        <div className="p-6">
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (suites.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <FolderPlus className="size-10 text-muted-foreground" />
        <p className="text-muted-foreground">This project has no test suites yet.</p>
        <Button onClick={() => setDialog({ kind: "newSuite" })}>
          <Plus /> Create a suite
        </Button>
        <SuiteDialogs dialog={dialog} close={close} projectId={projectId} onDone={refresh} setParams={setParams} />
      </div>
    );
  }

  return (
    <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragIds([])}>
      <div className="grid h-full grid-cols-[280px_1fr]">
        {/* Left: suite picker + section tree */}
        <aside className="flex min-h-0 flex-col border-r bg-muted/20">
          <div className="flex items-center gap-1 border-b p-2">
            <Select
              value={suiteId ? String(suiteId) : undefined}
              onValueChange={(v) => {
                setSelected(new Set());
                setParams({ suite: v, section: null, case: null });
              }}
            >
              <SelectTrigger size="sm" className="min-w-0 flex-1 bg-background" aria-label="Suite">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {suites.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name} <span className="text-muted-foreground">({s.case_count})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Suite actions">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onSelect={() => setDialog({ kind: "newSuite" })}>
                  <Plus /> New suite
                </DropdownMenuItem>
                {suite && (
                  <>
                    <DropdownMenuItem onSelect={() => setDialog({ kind: "renameSuite", suite })}>
                      Edit suite
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setDialog({ kind: "import" })}>
                      <Upload /> Import cases…
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <a href={api.exportUrl(suite.id, "csv")} download>
                        <Download /> Export CSV
                      </a>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <a href={api.exportUrl(suite.id, "json")} download>
                        <Download /> Export JSON
                      </a>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" onSelect={() => setDialog({ kind: "deleteSuite", suite })}>
                      <Trash2 /> Delete suite
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {sectionsQ.isLoading ? (
              <div className="grid gap-2">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-6" />
                ))}
              </div>
            ) : (
              <SectionTree
                tree={tree}
                totalCases={suite?.case_count ?? 0}
                selectedId={sectionId}
                onSelect={(id) => setParams({ section: id })}
                actions={{
                  onAddSection: (parentId) => setDialog({ kind: "newSection", parentId }),
                  onAddCase: (id) => addCase(id),
                  onRename: (section) => setDialog({ kind: "renameSection", section }),
                  onDelete: (section) => setDialog({ kind: "deleteSection", section }),
                }}
              />
            )}
          </div>
          <div className="border-t p-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start"
              onClick={() => setDialog({ kind: "newSection", parentId: null })}
            >
              <FolderPlus /> New section
            </Button>
          </div>
        </aside>

        {/* Right: toolbar + case list */}
        <main className="flex min-h-0 flex-col">
          <div className="grid gap-3 border-b px-6 py-3">
            <div className="flex items-center gap-3">
              <h1 className="truncate text-lg font-semibold">{sectionTitle}</h1>
              <span className="text-sm text-muted-foreground">
                {casesQ.data ? `${casesQ.data.total} cases` : ""}
              </span>
              <div className="ml-auto flex items-center gap-2">
                <Button size="sm" onClick={() => addCase()}>
                  <Plus /> Add case
                </Button>
              </div>
            </div>
            <FilterBar value={filters} onChange={setFilters} tags={tags} />
            {selectedIds.length > 0 && (
              <div className="flex items-center gap-2 rounded-md bg-primary/5 px-3 py-1.5 text-sm">
                <span className="font-medium">{selectedIds.length} selected</span>
                <Button variant="outline" size="xs" onClick={() => setDialog({ kind: "move" })}>
                  Move to…
                </Button>
                <Button variant="outline" size="xs" onClick={() => setDialog({ kind: "bulkDelete" })}>
                  <Trash2 className="text-destructive" /> Delete
                </Button>
                <Button variant="ghost" size="xs" className="ml-auto" onClick={() => setSelected(new Set())}>
                  Clear selection
                </Button>
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {casesQ.isLoading || sectionsQ.isLoading ? (
              <div className="grid gap-2">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : flat.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-16 text-center">
                <FolderPlus className="size-10 text-muted-foreground" />
                <p className="text-muted-foreground">This suite has no sections yet.</p>
                <Button onClick={() => setDialog({ kind: "newSection", parentId: null })}>
                  <Plus /> Create a section
                </Button>
              </div>
            ) : groups.length === 0 ? (
              <p className="py-16 text-center text-muted-foreground">No cases match the filters.</p>
            ) : (
              <CaseTable
                groups={groups}
                selected={selected}
                onToggle={toggle}
                onToggleMany={toggleMany}
                onOpen={(c) => {
                  setCreateIn(null);
                  setParams({ case: c.id });
                }}
                onAddCase={addCase}
                activeCaseId={openCaseId ?? undefined}
                draggingIds={new Set(dragIds)}
              />
            )}
          </div>
        </main>
      </div>

      <DragOverlay dropAnimation={null}>
        {dragIds.length > 0 && (
          <div className="w-max max-w-md truncate rounded-md border bg-background px-3 py-1.5 text-sm whitespace-nowrap shadow-lg">
            {dragIds.length === 1
              ? `${visibleCases.find((c) => c.id === dragIds[0])?.key} ${visibleCases.find((c) => c.id === dragIds[0])?.title}`
              : `${dragIds.length} cases`}
          </div>
        )}
      </DragOverlay>

      <CaseSheet
        state={sheet}
        onClose={() => {
          setCreateIn(null);
          if (openCaseId !== null) setParams({ case: null });
        }}
        onCreated={(c) => {
          setCreateIn(null);
          setParams({ case: c.id });
        }}
        projectId={projectId}
        sections={flat}
        paths={paths}
      />

      <SuiteDialogs dialog={dialog} close={close} projectId={projectId} onDone={refresh} setParams={setParams} />
      {suiteId && (
        <>
          <NameDialog
            open={dialog?.kind === "newSection"}
            onOpenChange={(o) => !o && close()}
            title={
              dialog?.kind === "newSection" && dialog.parentId !== null
                ? `New subsection in “${paths.get(dialog.parentId)}”`
                : "New section"
            }
            submitLabel="Create"
            onSubmit={async ({ name }) => {
              const parentId = dialog?.kind === "newSection" ? dialog.parentId : null;
              try {
                const s = await api.createSection(suiteId, { name, parent_id: parentId });
                refresh();
                setParams({ section: s.id });
              } catch (e) {
                fail(e);
                throw e;
              }
            }}
          />
          <NameDialog
            open={dialog?.kind === "renameSection"}
            onOpenChange={(o) => !o && close()}
            title="Rename section"
            initialName={dialog?.kind === "renameSection" ? dialog.section.name : ""}
            onSubmit={async ({ name }) => {
              if (dialog?.kind !== "renameSection") return;
              await api.updateSection(dialog.section.id, { name });
              refresh();
            }}
          />
          <ConfirmDialog
            open={dialog?.kind === "deleteSection"}
            onOpenChange={(o) => !o && close()}
            title={dialog?.kind === "deleteSection" ? `Delete section “${dialog.section.name}”?` : ""}
            description={
              dialog?.kind === "deleteSection"
                ? `This deletes ${flatten([dialog.section]).length - 1} subsections and ${dialog.section.totalCases} cases, including their results in test runs. This cannot be undone.`
                : ""
            }
            onConfirm={async () => {
              if (dialog?.kind !== "deleteSection") return;
              const deletingSelected =
                sectionId !== null && flatten([dialog.section]).some((s) => s.id === sectionId);
              await api.deleteSection(dialog.section.id).catch(fail);
              if (deletingSelected) setParams({ section: null });
              refresh();
            }}
          />
          <ImportDialog
            open={dialog?.kind === "import"}
            onOpenChange={(o) => !o && close()}
            suiteId={suiteId}
            onImported={refresh}
          />
          <MoveDialog
            open={dialog?.kind === "move"}
            onOpenChange={(o) => !o && close()}
            sections={flat}
            paths={paths}
            count={selectedIds.length}
            onMove={async (target) => {
              await moveCases(selectedIds, target);
              setSelected(new Set());
            }}
          />
          <ConfirmDialog
            open={dialog?.kind === "bulkDelete"}
            onOpenChange={(o) => !o && close()}
            title={`Delete ${selectedIds.length} cases?`}
            description="The cases and all of their results in test runs will be deleted."
            onConfirm={async () => {
              await Promise.all(selectedIds.map((id) => api.deleteCase(id))).catch(fail);
              toast.success(`Deleted ${selectedIds.length} cases`);
              setSelected(new Set());
              refresh();
            }}
          />
        </>
      )}
    </DndContext>
  );
}

function SuiteDialogs({
  dialog,
  close,
  projectId,
  onDone,
  setParams,
}: {
  dialog: Dialog;
  close: () => void;
  projectId: number;
  onDone: () => void;
  setParams: (p: Record<string, string | number | null>) => void;
}) {
  return (
    <>
      <NameDialog
        open={dialog?.kind === "newSuite"}
        onOpenChange={(o) => !o && close()}
        title="New suite"
        description="A suite groups related test cases, e.g. “Web app” or “Public API”."
        initialDescription=""
        submitLabel="Create"
        onSubmit={async (v) => {
          const s = await api.createSuite(projectId, v);
          onDone();
          setParams({ suite: s.id, section: null, case: null });
        }}
      />
      <NameDialog
        open={dialog?.kind === "renameSuite"}
        onOpenChange={(o) => !o && close()}
        title="Edit suite"
        initialName={dialog?.kind === "renameSuite" ? dialog.suite.name : ""}
        initialDescription={dialog?.kind === "renameSuite" ? dialog.suite.description : ""}
        onSubmit={async (v) => {
          if (dialog?.kind !== "renameSuite") return;
          await api.updateSuite(dialog.suite.id, v);
          onDone();
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === "deleteSuite"}
        onOpenChange={(o) => !o && close()}
        title={dialog?.kind === "deleteSuite" ? `Delete suite “${dialog.suite.name}”?` : ""}
        description={
          dialog?.kind === "deleteSuite"
            ? `All ${dialog.suite.case_count} cases in this suite and their results will be deleted.`
            : ""
        }
        onConfirm={async () => {
          if (dialog?.kind !== "deleteSuite") return;
          await api.deleteSuite(dialog.suite.id);
          setParams({ suite: null, section: null, case: null });
          onDone();
        }}
      />
    </>
  );
}
