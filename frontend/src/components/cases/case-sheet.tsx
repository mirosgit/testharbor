"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AutomationIcon, PriorityBadge, Tag } from "@/components/badges";
import { ConfirmDialog } from "@/components/dialogs";
import { Markdown, MarkdownField } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { automationLabel, priorityLabel, typeLabel } from "@/lib/labels";
import type { SectionNode } from "@/lib/tree";
import {
  AUTOMATION_STATUSES,
  CASE_TYPES,
  PRIORITIES,
  type CaseInput,
  type TestCase,
} from "@/lib/types";

import { StepsEditor } from "./steps-editor";
import { TagInput } from "./tag-input";

export type SheetState = { mode: "view"; caseId: number } | { mode: "create"; sectionId: number } | null;

const emptyCase = (sectionId: number): CaseInput => ({
  section_id: sectionId,
  title: "",
  preconditions: "",
  steps: [],
  expected_result: "",
  priority: "medium",
  type: "functional",
  tags: [],
  automation_status: "manual",
  automation_key: null,
});

const toInput = (c: TestCase): CaseInput => ({
  section_id: c.section_id,
  title: c.title,
  preconditions: c.preconditions,
  steps: c.steps,
  expected_result: c.expected_result,
  priority: c.priority,
  type: c.type,
  tags: c.tags,
  automation_status: c.automation_status,
  automation_key: c.automation_key,
});

export function CaseSheet({
  state,
  onClose,
  onCreated,
  projectId,
  sections,
  paths,
  extra,
}: {
  state: SheetState;
  onClose: () => void;
  onCreated: (c: TestCase) => void;
  projectId: number;
  sections: SectionNode[];
  paths: Map<number, string>;
  /** Extra content under the case details in view mode (e.g. run history). */
  extra?: (c: TestCase) => React.ReactNode;
}) {
  const caseId = state?.mode === "view" ? state.caseId : undefined;
  const { data: testCase, isLoading } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.case(caseId!),
    enabled: caseId !== undefined,
  });
  const [editing, setEditing] = useState(false);
  useEffect(() => setEditing(false), [caseId]);

  const open = state !== null;
  const isCreate = state?.mode === "create";

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-3xl" data-testid="case-sheet">
        {isCreate ? (
          <CaseForm
            key={`new-${state.sectionId}`}
            title="New test case"
            initial={emptyCase(state.sectionId)}
            projectId={projectId}
            sections={sections}
            paths={paths}
            onCancel={onClose}
            onSaved={onCreated}
          />
        ) : isLoading || !testCase ? (
          <div className="grid gap-3 p-6">
            <SheetHeader className="p-0">
              <SheetTitle>Loading…</SheetTitle>
            </SheetHeader>
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-40" />
          </div>
        ) : editing ? (
          <CaseForm
            key={`edit-${testCase.id}`}
            title={`Edit ${testCase.key}`}
            caseId={testCase.id}
            initial={toInput(testCase)}
            projectId={projectId}
            sections={sections}
            paths={paths}
            onCancel={() => setEditing(false)}
            onSaved={() => setEditing(false)}
          />
        ) : (
          <CaseView
            testCase={testCase}
            path={paths.get(testCase.section_id) ?? ""}
            onEdit={() => setEditing(true)}
            onDeleted={onClose}
            extra={extra}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

function CaseView({
  testCase: c,
  path,
  onEdit,
  onDeleted,
  extra,
}: {
  testCase: TestCase;
  path: string;
  onEdit: () => void;
  onDeleted: () => void;
  extra?: (c: TestCase) => React.ReactNode;
}) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const del = useMutation({
    mutationFn: () => api.deleteCase(c.id),
    onSuccess: () => {
      toast.success(`${c.key} deleted`);
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["sections"] });
      onDeleted();
    },
  });

  return (
    <>
      <SheetHeader className="border-b pr-12">
        <SheetDescription className="flex items-center gap-2 font-mono text-xs">
          {c.key}
          <span className="font-sans">· {path}</span>
        </SheetDescription>
        <SheetTitle className="text-lg leading-snug">{c.title}</SheetTitle>
        <div className="flex items-center gap-2 pt-1">
          <Button size="sm" onClick={onEdit}>
            <Pencil /> Edit
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon-sm" variant="outline" aria-label="More actions">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem
                onSelect={() => {
                  void navigator.clipboard?.writeText(c.key);
                  toast.success(`Copied ${c.key}`);
                }}
              >
                <Copy /> Copy case ID
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirm(true)}>
                <Trash2 /> Delete case
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </SheetHeader>

      <div className="grid gap-6 p-6">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
          <Meta label="Priority">
            <PriorityBadge priority={c.priority} />
          </Meta>
          <Meta label="Type">{typeLabel[c.type]}</Meta>
          <Meta label="Automation">
            <span className="inline-flex items-center gap-1.5">
              <AutomationIcon status={c.automation_status} />
              {automationLabel[c.automation_status]}
            </span>
          </Meta>
          <Meta label="Updated">{new Date(c.updated_at).toLocaleDateString()}</Meta>
          {c.automation_key && (
            <Meta label="Automation key" className="col-span-full">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
                {c.automation_key}
              </code>
            </Meta>
          )}
          {c.tags.length > 0 && (
            <Meta label="Tags" className="col-span-full">
              <div className="flex flex-wrap gap-1">
                {c.tags.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
              </div>
            </Meta>
          )}
        </dl>

        {c.preconditions.trim() && (
          <Block title="Preconditions">
            <Markdown>{c.preconditions}</Markdown>
          </Block>
        )}

        <Block title="Steps">
          {c.steps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No steps.</p>
          ) : (
            <ol className="divide-y rounded-md border">
              {c.steps.map((s, i) => (
                <li key={i} className="grid grid-cols-[2rem_1fr_1fr] gap-3 px-3 py-2.5">
                  <span className="text-sm text-muted-foreground tabular-nums">{i + 1}</span>
                  <Markdown>{s.action}</Markdown>
                  <div className="text-muted-foreground">
                    <Markdown>{s.expected}</Markdown>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Block>

        {c.expected_result.trim() && (
          <Block title="Expected result">
            <Markdown>{c.expected_result}</Markdown>
          </Block>
        )}

        {extra?.(c)}
      </div>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete ${c.key}?`}
        description="The case and all of its results in test runs will be deleted."
        onConfirm={() => del.mutate()}
      />
    </>
  );
}

function Meta({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <dt className="mb-1 text-xs text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  );
}

function CaseForm({
  title,
  caseId,
  initial,
  projectId,
  sections,
  paths,
  onCancel,
  onSaved,
}: {
  title: string;
  caseId?: number;
  initial: CaseInput;
  projectId: number;
  sections: SectionNode[];
  paths: Map<number, string>;
  onCancel: () => void;
  onSaved: (c: TestCase) => void;
}) {
  const qc = useQueryClient();
  const [v, setV] = useState<CaseInput>(initial);
  const [error, setError] = useState<string | null>(null);
  const { data: tagSuggestions = [] } = useQuery({
    queryKey: ["tags", projectId],
    queryFn: () => api.tags(projectId),
  });
  const set = <K extends keyof CaseInput>(k: K, val: CaseInput[K]) => setV((p) => ({ ...p, [k]: val }));

  const save = useMutation({
    mutationFn: () => {
      const body = { ...v, steps: v.steps.filter((s) => s.action.trim() || s.expected.trim()) };
      return caseId ? api.updateCase(caseId, body) : api.createCase(body);
    },
    onSuccess: (saved) => {
      toast.success(caseId ? `${saved.key} saved` : `${saved.key} created`);
      qc.setQueryData(["case", saved.id], saved);
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["sections"] });
      qc.invalidateQueries({ queryKey: ["tags", projectId] });
      onSaved(saved);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Save failed"),
  });

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!v.title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    save.mutate();
  };

  return (
    <form
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
      }}
      className="flex min-h-full flex-col"
    >
      <SheetHeader className="border-b">
        <SheetTitle>{title}</SheetTitle>
        <SheetDescription>Markdown is supported in text fields. Ctrl+Enter saves.</SheetDescription>
      </SheetHeader>
      <div className="grid flex-1 gap-5 p-6">
        <div className="grid gap-2">
          <Label htmlFor="case-title">Title</Label>
          <Input
            id="case-title"
            value={v.title}
            onChange={(e) => set("title", e.target.value)}
            autoFocus
            placeholder="e.g. Login with valid credentials"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Section">
            <Select value={String(v.section_id)} onValueChange={(x) => set("section_id", Number(x))}>
              <SelectTrigger className="w-full" aria-label="Section">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {sections.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {paths.get(s.id)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Priority">
            <Select value={v.priority} onValueChange={(x) => set("priority", x as CaseInput["priority"])}>
              <SelectTrigger className="w-full" aria-label="Priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITIES.map((p) => (
                  <SelectItem key={p} value={p}>
                    {priorityLabel[p]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Type">
            <Select value={v.type} onValueChange={(x) => set("type", x as CaseInput["type"])}>
              <SelectTrigger className="w-full" aria-label="Type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CASE_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {typeLabel[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Automation">
            <Select
              value={v.automation_status}
              onValueChange={(x) => set("automation_status", x as CaseInput["automation_status"])}
            >
              <SelectTrigger className="w-full" aria-label="Automation status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUTOMATION_STATUSES.map((a) => (
                  <SelectItem key={a} value={a}>
                    {automationLabel[a]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tags" htmlFor="case-tags">
            <TagInput
              id="case-tags"
              value={v.tags}
              onChange={(t) => set("tags", t)}
              suggestions={tagSuggestions}
            />
          </Field>
          <Field label="Automation key" htmlFor="case-automation-key">
            <Input
              id="case-automation-key"
              value={v.automation_key ?? ""}
              onChange={(e) => set("automation_key", e.target.value || null)}
              placeholder="tests/test_auth.py::test_login"
              className="font-mono text-xs"
            />
          </Field>
        </div>

        <Field label="Preconditions" htmlFor="case-preconditions">
          <MarkdownField id="case-preconditions" value={v.preconditions} onChange={(x) => set("preconditions", x)} />
        </Field>

        <Field label="Steps">
          <StepsEditor steps={v.steps} onChange={(s) => set("steps", s)} />
        </Field>

        <Field label="Expected result" htmlFor="case-expected">
          <MarkdownField id="case-expected" value={v.expected_result} onChange={(x) => set("expected_result", x)} />
        </Field>
      </div>

      <div className="sticky bottom-0 flex items-center gap-2 border-t bg-background px-6 py-3">
        {error && <p className="mr-auto text-sm text-destructive">{error}</p>}
        <div className="ml-auto flex gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : caseId ? "Save" : "Create case"}
          </Button>
        </div>
      </div>
    </form>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="grid content-start gap-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}
