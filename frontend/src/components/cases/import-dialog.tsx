"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { SectionNode } from "@/lib/tree";
import type { ImportResult } from "@/lib/types";

const NEW = "__new__";

const baseName = (name: string) => name.replace(/\.(csv|json)$/i, "").trim();

export function ImportDialog({
  open,
  onOpenChange,
  suiteId,
  sections,
  paths,
  defaultSectionId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  suiteId: number;
  sections: SectionNode[];
  paths: Map<number, string>;
  /** Pre-select this section (e.g. the one selected in the tree). */
  defaultSectionId?: number | null;
  onImported: (result: ImportResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<string>(defaultSectionId ? String(defaultSectionId) : NEW);
  const [newName, setNewName] = useState("");
  const [keepPaths, setKeepPaths] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const reset = (o: boolean) => {
    if (!o) {
      setFile(null);
      setResult(null);
      setNewName("");
      setKeepPaths(true);
    } else {
      setTarget(defaultSectionId ? String(defaultSectionId) : NEW);
    }
    onOpenChange(o);
  };

  const submit = async () => {
    if (!file) return;
    const name = (newName || baseName(file.name)).trim();
    if (target === NEW && !name) return toast.error("Enter a section name");
    setBusy(true);
    try {
      const r = await api.importCases(
        suiteId,
        file,
        target === NEW ? { new_section: name, keep_paths: keepPaths } : { section_id: Number(target), keep_paths: keepPaths },
      );
      setResult(r);
      onImported(r);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import cases</DialogTitle>
          <DialogDescription>
            CSV or JSON: TestHarbor exports, BrowserStack Test Management and TestRail CSV exports. Re-importing the
            same file updates the cases instead of duplicating them.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="grid gap-3 text-sm" data-testid="import-result">
            <p>
              <b>{result.created}</b> created, <b>{result.updated}</b> updated, <b>{result.sections_created}</b>{" "}
              sections created.
            </p>
            {result.errors.length > 0 && (
              <Notes tone="error" title={`${result.errors.length} rows skipped`} items={result.errors} />
            )}
            {result.warnings.length > 0 && (
              <Notes tone="warn" title="Imported with defaults" items={result.warnings} />
            )}
            {result.ignored_columns.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Not imported (no matching field): {result.ignored_columns.join(", ")}
              </p>
            )}
          </div>
        ) : (
          <div className="grid gap-4">
            <Input
              type="file"
              accept=".csv,.json,text/csv,application/json"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              aria-label="File to import"
            />
            <div className="grid gap-2">
              <Label>Import into</Label>
              <Select value={target} onValueChange={setTarget}>
                <SelectTrigger className="w-full" aria-label="Target section">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NEW}>New section…</SelectItem>
                  {sections.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {paths.get(s.id)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {target === NEW && (
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={file ? baseName(file.name) : "Section name"}
                  aria-label="New section name"
                />
              )}
              {target === NEW && (
                <p className="text-xs text-muted-foreground">
                  A top-level section; an existing one with the same name is reused.
                </p>
              )}
            </div>
            <label className="flex items-start gap-2 text-sm">
              <Checkbox checked={keepPaths} onCheckedChange={(v) => setKeepPaths(v === true)} className="mt-0.5" />
              <span>
                Keep folders from the file
                <span className="block text-xs text-muted-foreground">
                  Recreates <code>Folder Path</code> / <code>section_path</code> inside the chosen section. Off: all
                  cases go directly into it.
                </span>
              </span>
            </label>
          </div>
        )}
        <DialogFooter>
          {result ? (
            <Button onClick={() => reset(false)}>Done</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => reset(false)}>
                Cancel
              </Button>
              <Button disabled={!file || busy} onClick={submit}>
                {busy ? "Importing…" : "Import"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Notes({ tone, title, items }: { tone: "error" | "warn"; title: string; items: string[] }) {
  const cls =
    tone === "error"
      ? "border-destructive/30 bg-destructive/5 [&_p]:text-destructive"
      : "border-amber-300/60 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40";
  return (
    <div className={`max-h-40 overflow-y-auto rounded-md border p-2 text-xs ${cls}`}>
      <p className="mb-1 font-medium">{title}:</p>
      <ul className="grid gap-0.5">
        {items.map((e, i) => (
          <li key={i}>{e}</li>
        ))}
      </ul>
    </div>
  );
}
