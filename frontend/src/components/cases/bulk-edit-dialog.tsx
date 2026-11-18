"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import {
  automationLabel,
  complexityLabel,
  priorityLabel,
  progressLabel,
  stateLabel,
  typeLabel,
} from "@/lib/labels";
import {
  AUTOMATION_COMPLEXITIES,
  AUTOMATION_PROGRESSES,
  AUTOMATION_STATUSES,
  CASE_STATES,
  CASE_TYPES,
  PRIORITIES,
  type CaseBulkUpdate,
} from "@/lib/types";

import { RolePicker } from "./role-picker";
import { TagInput } from "./tag-input";

const KEEP = "__keep__";
const CLEAR = "__clear__";
const SET = "__set__";

type Choice = Record<string, string>; // field -> KEEP | CLEAR | value
const CHOICE_FIELDS = [
  "state",
  "priority",
  "type",
  "automation_status",
  "automation_progress",
  "automation_complexity",
] as const;

export function BulkEditDialog({
  open,
  onOpenChange,
  projectId,
  caseIds,
  onDone,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
  caseIds: number[];
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [choice, setChoice] = useState<Choice>({});
  const [text, setText] = useState<Record<"owner" | "sprint", { mode: string; value: string }>>({
    owner: { mode: KEEP, value: "" },
    sprint: { mode: KEEP, value: "" },
  });
  const [addTags, setAddTags] = useState<string[]>([]);
  const [removeTags, setRemoveTags] = useState<string[]>([]);
  const [addRoles, setAddRoles] = useState<string[]>([]);
  const [removeRoles, setRemoveRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChoice({});
    setText({ owner: { mode: KEEP, value: "" }, sprint: { mode: KEEP, value: "" } });
    setAddTags([]);
    setRemoveTags([]);
    setAddRoles([]);
    setRemoveRoles([]);
  }, [open]);

  const { data: known } = useQuery({
    queryKey: ["case-values", projectId],
    queryFn: () => api.caseValues(projectId),
    enabled: open,
  });
  const { data: tags = [] } = useQuery({ queryKey: ["tags", projectId], queryFn: () => api.tags(projectId), enabled: open });

  const body = (): CaseBulkUpdate => {
    const set: Record<string, string | null> = {};
    for (const k of CHOICE_FIELDS) {
      const c = choice[k];
      if (c && c !== KEEP) set[k] = c === CLEAR ? null : c;
    }
    for (const k of ["owner", "sprint"] as const) {
      const { mode, value } = text[k];
      if (mode === CLEAR) set[k] = null;
      else if (mode === SET && value.trim()) set[k] = value.trim();
    }
    return {
      case_ids: caseIds,
      set: set as CaseBulkUpdate["set"],
      add_tags: addTags,
      remove_tags: removeTags,
      add_roles: addRoles,
      remove_roles: removeRoles,
    };
  };
  const b = body();
  const changes =
    Object.keys(b.set ?? {}).length + addTags.length + removeTags.length + addRoles.length + removeRoles.length;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.bulkUpdateCases(b);
      toast.success(`Updated ${r.updated} cases`);
      for (const key of ["cases", "case", "tags", "case-values", "project"]) qc.invalidateQueries({ queryKey: [key] });
      onDone();
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update cases");
    } finally {
      setBusy(false);
    }
  };

  const pick = (field: (typeof CHOICE_FIELDS)[number], label: string, options: [string, string][], clearable = false) => (
    <Row label={label}>
      <Select value={choice[field] ?? KEEP} onValueChange={(v) => setChoice((c) => ({ ...c, [field]: v }))}>
        <SelectTrigger className="w-full" aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={KEEP}>Keep as is</SelectItem>
          {clearable && <SelectItem value={CLEAR}>Not set</SelectItem>}
          <SelectSeparator />
          {options.map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Row>
  );

  const freeText = (field: "owner" | "sprint", label: string, suggestions: string[]) => (
    <Row label={label}>
      <div className="grid grid-cols-[8.5rem_1fr] gap-2">
        <Select
          value={text[field].mode}
          onValueChange={(mode) => setText((t) => ({ ...t, [field]: { ...t[field], mode } }))}
        >
          <SelectTrigger className="w-full" aria-label={`${label} change`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={KEEP}>Keep as is</SelectItem>
            <SelectItem value={SET}>Set to…</SelectItem>
            <SelectItem value={CLEAR}>Clear</SelectItem>
          </SelectContent>
        </Select>
        {text[field].mode === SET && (
          <>
            <Input
              value={text[field].value}
              onChange={(e) => setText((t) => ({ ...t, [field]: { ...t[field], value: e.target.value } }))}
              list={`bulk-${field}-options`}
              aria-label={label}
              autoFocus
            />
            <datalist id={`bulk-${field}-options`}>
              {suggestions.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </>
        )}
      </div>
    </Row>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Edit {caseIds.length} cases</DialogTitle>
            <DialogDescription>Only the fields you change are applied; everything else stays as it is.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            {pick("state", "State", CASE_STATES.map((s) => [s, stateLabel[s]]))}
            {pick("priority", "Priority", PRIORITIES.map((p) => [p, priorityLabel[p]]))}
            {pick("type", "Type", CASE_TYPES.map((t) => [t, typeLabel[t]]))}
            {pick("automation_status", "Automation", AUTOMATION_STATUSES.map((a) => [a, automationLabel[a]]))}
            {pick("automation_progress", "Automation progress", AUTOMATION_PROGRESSES.map((a) => [a, progressLabel[a]]), true)}
            {pick(
              "automation_complexity",
              "Automation complexity",
              AUTOMATION_COMPLEXITIES.map((a) => [a, complexityLabel[a]]),
              true,
            )}
            {freeText("owner", "Owner", known?.owners ?? [])}
            {freeText("sprint", "Sprint", known?.sprints ?? [])}
            <Row label="Add roles" htmlFor="bulk-add-roles">
              <RolePicker id="bulk-add-roles" value={addRoles} onChange={setAddRoles} options={known?.roles ?? []} projectId={projectId} />
            </Row>
            <Row label="Remove roles" htmlFor="bulk-remove-roles">
              <RolePicker
                id="bulk-remove-roles"
                value={removeRoles}
                onChange={setRemoveRoles}
                options={known?.roles ?? []}
                projectId={projectId}
              />
            </Row>
            <Row label="Add tags" htmlFor="bulk-add-tags">
              <TagInput id="bulk-add-tags" value={addTags} onChange={setAddTags} suggestions={tags} />
            </Row>
            <Row label="Remove tags" htmlFor="bulk-remove-tags">
              <TagInput id="bulk-remove-tags" value={removeTags} onChange={setRemoveTags} suggestions={tags} placeholder="Tags to remove…" />
            </Row>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || changes === 0}>
              {busy ? "Saving…" : `Apply to ${caseIds.length} cases`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="grid items-center gap-1.5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-3">
      <Label htmlFor={htmlFor} className="text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}
