"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AutomationIcon, PriorityBadge, StateBadge, Tag } from "@/components/badges";
import { ConfirmDialog } from "@/components/dialogs";
import { Markdown, MarkdownField } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Combobox, MultiCombobox } from "@/components/combobox";
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
import {
  automationLabel,
  complexityLabel,
  priorityLabel,
  progressLabel,
  stateLabel,
  typeLabel,
} from "@/lib/labels";
import type { SectionNode } from "@/lib/tree";
import { cn } from "@/lib/utils";
import {
  AUTOMATION_COMPLEXITIES,
  AUTOMATION_PROGRESSES,
  AUTOMATION_STATUSES,
  CASE_STATES,
  CASE_TYPES,
  PRIORITIES,
  type CaseInput,
  type CaseState,
  type TestCase,
} from "@/lib/types";

import { CustomFieldsEditor, CustomFieldsView } from "./custom-fields";
import { RolePicker } from "./role-picker";
import { StepsEditor } from "./steps-editor";

export type SheetState = { mode: "view"; caseId: number } | { mode: "create"; sectionId: number } | null;

const emptyCase = (sectionId: number): CaseInput => ({
  section_id: sectionId,
  title: "",
  description: "",
  preconditions: "",
  steps: [],
  expected_result: "",
  priority: "medium",
  type: "functional",
  tags: [],
  automation_status: "manual",
  automation_key: null,
  state: "active",
  owner: null,
  automation_complexity: null,
  automation_progress: null,
  sprint: null,
  roles: [],
  custom_fields: [],
});

const toInput = (c: TestCase): CaseInput => ({
  section_id: c.section_id,
  title: c.title,
  description: c.description,
  preconditions: c.preconditions,
  steps: c.steps,
  expected_result: c.expected_result,
  priority: c.priority,
  type: c.type,
  tags: c.tags,
  automation_status: c.automation_status,
  automation_key: c.automation_key,
  state: c.state,
  owner: c.owner,
  automation_complexity: c.automation_complexity,
  automation_progress: c.automation_progress,
  sprint: c.sprint,
  roles: c.roles,
  custom_fields: c.custom_fields,
});

const NONE = "__none__"; // Radix Select can't use "" as an item value

const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

const Empty = () => <span className="text-muted-foreground">—</span>;

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
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-3xl lg:max-w-4xl" data-testid="case-sheet">
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

      <div className="grid min-w-0 gap-6 p-4 sm:p-6 [&>*]:min-w-0">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4" data-testid="case-meta">
          <Meta label="State">
            <StateBadge state={c.state} />
          </Meta>
          <Meta label="Priority">
            <PriorityBadge priority={c.priority} />
          </Meta>
          <Meta label="Type">{typeLabel[c.type]}</Meta>
          <Meta label="Owner">{c.owner ?? <Empty />}</Meta>
          <Meta label="Automation">
            <span className="inline-flex items-center gap-1.5">
              <AutomationIcon status={c.automation_status} />
              {automationLabel[c.automation_status]}
            </span>
          </Meta>
          <Meta label="Automation progress">
            {c.automation_progress ? progressLabel[c.automation_progress] : <Empty />}
          </Meta>
          <Meta label="Automation complexity">
            {c.automation_complexity ? complexityLabel[c.automation_complexity] : <Empty />}
          </Meta>
          <Meta label="Sprint">{c.sprint ?? <Empty />}</Meta>
          <Meta label="Applicable Roles" className="col-span-2">
            {c.roles.length ? (
              <div className="flex flex-wrap gap-1">
                {c.roles.map((r) => (
                  <Tag key={r}>{r}</Tag>
                ))}
              </div>
            ) : (
              <Empty />
            )}
          </Meta>
          <Meta label="Created">{dateTime(c.created_at)}</Meta>
          <Meta label="Last updated">
            {dateTime(c.updated_at)}
            {c.updated_by && <div className="text-xs text-muted-foreground">by {c.updated_by}</div>}
          </Meta>
          {c.external_id && (
            <Meta label="External ID">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{c.external_id}</code>
            </Meta>
          )}
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

        {/* The case's results across runs, before its text, so they are in view when the sheet opens. */}
        {extra?.(c)}

        {c.custom_fields.length > 0 && (
          <Block title="Fields">
            <CustomFieldsView fields={c.custom_fields} />
          </Block>
        )}

        {c.description.trim() && (
          <Block title="Description">
            <Markdown>{c.description}</Markdown>
          </Block>
        )}

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
                <li
                  key={i}
                  className="grid grid-cols-[2rem_minmax(0,1fr)_minmax(0,1fr)] gap-3 px-3 py-2.5 [overflow-wrap:anywhere]"
                >
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
    <section className="min-w-0">
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
  const { data: knownFields = [] } = useQuery({
    queryKey: ["custom-fields", projectId],
    queryFn: () => api.customFields(projectId),
  });
  const { data: known } = useQuery({
    queryKey: ["case-values", projectId],
    queryFn: () => api.caseValues(projectId),
  });
  const set = <K extends keyof CaseInput>(k: K, val: CaseInput[K]) => setV((p) => ({ ...p, [k]: val }));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...v,
        steps: v.steps.filter((s) => s.action.trim() || s.expected.trim()),
        owner: v.owner?.trim() || null,
        sprint: v.sprint?.trim() || null,
        custom_fields: v.custom_fields.filter((f) => f.name.trim() && f.value.trim()),
      };
      return caseId ? api.updateCase(caseId, body) : api.createCase(body);
    },
    onSuccess: (saved) => {
      toast.success(caseId ? `${saved.key} saved` : `${saved.key} created`);
      qc.setQueryData(["case", saved.id], saved);
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["sections"] });
      qc.invalidateQueries({ queryKey: ["tags", projectId] });
      qc.invalidateQueries({ queryKey: ["custom-fields", projectId] });
      qc.invalidateQueries({ queryKey: ["case-values", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
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
      {/* Field order and grouping follow BrowserStack Test Management's case form. */}
      <div className="grid flex-1 content-start gap-5 p-6">
        <Field label="Title" htmlFor="case-title" required>
          <Input
            id="case-title"
            value={v.title}
            onChange={(e) => set("title", e.target.value)}
            autoFocus
            placeholder="e.g. Login with valid credentials"
          />
        </Field>

        <Field label="Description" htmlFor="case-description">
          <MarkdownField id="case-description" value={v.description} onChange={(x) => set("description", x)} />
        </Field>

        <Field label="Preconditions" htmlFor="case-preconditions">
          <MarkdownField id="case-preconditions" value={v.preconditions} onChange={(x) => set("preconditions", x)} />
        </Field>

        <Field label="Steps">
          <StepsEditor steps={v.steps} onChange={(s) => set("steps", s)} />
        </Field>

        <Field label="Expected Result" htmlFor="case-expected">
          <MarkdownField id="case-expected" value={v.expected_result} onChange={(x) => set("expected_result", x)} />
        </Field>

        <FormSection title="Details">
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
          <Field label="Owner" htmlFor="case-owner">
            <Combobox
              id="case-owner"
              aria-label="Owner"
              value={v.owner}
              onChange={(x) => set("owner", x)}
              options={known?.owners ?? []}
              placeholder="Select owner"
              searchPlaceholder="Find a person"
              creatable
            />
          </Field>
          <Field label="State">
            <EnumSelect label="State" value={v.state} onChange={(x) => x && set("state", x)} options={CASE_STATES} labels={stateLabel} />
          </Field>
          <Field label="Priority">
            <EnumSelect label="Priority" value={v.priority} onChange={(x) => x && set("priority", x)} options={PRIORITIES} labels={priorityLabel} />
          </Field>
          <Field label="Type of Test Case">
            <EnumSelect label="Type" value={v.type} onChange={(x) => x && set("type", x)} options={CASE_TYPES} labels={typeLabel} />
          </Field>
          <Field label="Automation Status">
            <EnumSelect
              label="Automation status"
              value={v.automation_status}
              onChange={(x) => x && set("automation_status", x)}
              options={AUTOMATION_STATUSES}
              labels={automationLabel}
            />
          </Field>
          <Field label="Tags" htmlFor="case-tags" wide>
            <MultiCombobox
              id="case-tags"
              aria-label="Tags"
              value={v.tags}
              onChange={(t) => set("tags", t)}
              options={tagSuggestions}
              placeholder="Add tags"
              searchPlaceholder="Find a tag"
              normalize={(t) => t.trim().toLowerCase()}
              noun="tag"
            />
          </Field>
        </FormSection>

        <FormSection title="Custom Fields">
          <Field label="Automation Complexity">
            <EnumSelect
              label="Automation complexity"
              value={v.automation_complexity}
              onChange={(x) => set("automation_complexity", x)}
              options={AUTOMATION_COMPLEXITIES}
              labels={complexityLabel}
              nullable
            />
          </Field>
          <Field label="Automation Progress">
            <EnumSelect
              label="Automation progress"
              value={v.automation_progress}
              onChange={(x) => set("automation_progress", x)}
              options={AUTOMATION_PROGRESSES}
              labels={progressLabel}
              nullable
            />
          </Field>
          <Field label="Applicable Roles" htmlFor="case-roles">
            <RolePicker
              id="case-roles"
              value={v.roles}
              onChange={(r) => set("roles", r)}
              options={known?.roles ?? []}
              projectId={projectId}
              placeholder="Select roles"
            />
          </Field>
          <Field label="Sprint No." htmlFor="case-sprint">
            <Combobox
              id="case-sprint"
              aria-label="Sprint"
              value={v.sprint}
              onChange={(x) => set("sprint", x)}
              options={known?.sprints ?? []}
              placeholder="Select sprint"
              searchPlaceholder="Find a sprint"
              creatable
            />
          </Field>
          <Field label="Automation Key" htmlFor="case-automation-key" wide>
            <Input
              id="case-automation-key"
              value={v.automation_key ?? ""}
              onChange={(e) => set("automation_key", e.target.value || null)}
              placeholder="tests/test_auth.py::test_login — links JUnit results to this case"
              className="font-mono text-xs"
            />
          </Field>
          <Field label="Other fields" wide>
            <CustomFieldsEditor value={v.custom_fields} onChange={(f) => set("custom_fields", f)} known={knownFields} />
          </Field>
        </FormSection>
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

function Field({
  label,
  htmlFor,
  required,
  wide,
  children,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  /** Spans both columns inside a FormSection. */
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid content-start gap-2", wide && "sm:col-span-2")}>
      <Label htmlFor={htmlFor}>
        {label}
        {required && <span className="text-destructive">*</span>}
      </Label>
      {children}
    </div>
  );
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t pt-5">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function EnumSelect<T extends string>({
  label,
  value,
  onChange,
  options,
  labels,
  nullable = false,
}: {
  label: string;
  value: T | null;
  onChange: (v: T | null) => void;
  options: readonly T[];
  labels: Record<T, string>;
  nullable?: boolean;
}) {
  return (
    <Select value={value ?? NONE} onValueChange={(x) => onChange(x === NONE ? null : (x as T))}>
      <SelectTrigger className="w-full" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {nullable && <SelectItem value={NONE}>Not set</SelectItem>}
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {labels[o]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
