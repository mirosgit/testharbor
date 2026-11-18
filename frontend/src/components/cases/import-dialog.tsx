"use client";

import { useEffect, useState } from "react";
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
const ROOT = "__root__"; // folders from the file become top-level sections

const baseName = (name: string) => name.replace(/\.(csv|json)$/i, "").trim();

export function ImportDialog({
  open,
  onOpenChange,
  suiteId,
  sections,
  paths,
  onImported,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  suiteId: number;
  sections: SectionNode[];
  paths: Map<number, string>;
  onImported: (result: ImportResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<string>(ROOT);
  const [newName, setNewName] = useState("");
  const [keepPaths, setKeepPaths] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [columns, setColumns] = useState<Set<string> | null>(null); // null = server default

  const targetFor = (dry: boolean) => {
    const name = (newName || (file ? baseName(file.name) : "")).trim();
    const base =
      target === ROOT ? {} : target === NEW ? { new_section: name } : { section_id: Number(target) };
    return {
      ...base,
      keep_paths: target === ROOT || keepPaths,
      dry_run: dry,
      columns: columns ? [...columns] : undefined,
    };
  };

  // Dry run whenever the file or target changes: shows counts and the extra columns.
  useEffect(() => {
    if (!file || result) return;
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const p = await api.importCases(suiteId, file, { ...targetFor(true), columns: undefined });
        if (cancelled) return;
        setPreview(p);
        setPreviewError(null);
        setColumns((prev) => prev ?? new Set(p.extra_columns.filter((c) => c.selected).map((c) => c.name)));
      } catch (e) {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(e instanceof ApiError ? e.message : "Can't read the file");
        }
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, target, newName, keepPaths]);

  const reset = (o: boolean) => {
    if (!o) {
      setFile(null);
      setResult(null);
      setPreview(null);
      setPreviewError(null);
      setColumns(null);
      setNewName("");
      setKeepPaths(true);
    } else {
      setTarget(ROOT);
    }
    onOpenChange(o);
  };

  const submit = async () => {
    if (!file) return;
    const name = (newName || baseName(file.name)).trim();
    if (target === NEW && !name) return toast.error("Enter a section name");
    setBusy(true);
    try {
      const r = await api.importCases(suiteId, file, targetFor(false));
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
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setPreview(null);
                setColumns(null);
              }}
              aria-label="File to import"
            />
            {previewError && <p className="text-sm text-destructive">{previewError}</p>}
            <div className="grid gap-2">
              <Label>Import into</Label>
              <Select value={target} onValueChange={setTarget}>
                <SelectTrigger className="w-full" aria-label="Target section">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ROOT}>Top level (folders from the file)</SelectItem>
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
                  A top-level section; an existing one with the same name is reused. Folders from the file go inside
                  it.
                </p>
              )}
              {target === ROOT && (
                <p className="text-xs text-muted-foreground">
                  <code>Billing&gt;Invoices</code> in the file becomes <code>Billing › Invoices</code> at the top of
                  the suite; existing sections with the same path are reused. Cases without a folder go to
                  “Imported”.
                </p>
              )}
            </div>
            {target !== ROOT && (
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
            )}
            {preview && (
              <div className="grid gap-2 rounded-md border bg-muted/30 p-3 text-sm" data-testid="import-preview">
                <p>
                  Will create <b>{preview.created}</b>, update <b>{preview.updated}</b>
                  {preview.sections_created > 0 && <>, add <b>{preview.sections_created}</b> sections</>}
                  {preview.errors.length > 0 && <>, skip <b className="text-destructive">{preview.errors.length}</b> rows</>}.
                </p>
                {preview.extra_columns.length > 0 && columns && (
                  <div className="grid gap-1.5">
                    <p className="text-xs text-muted-foreground">
                      Extra columns, kept as custom fields on each case:
                    </p>
                    <div className="grid max-h-44 grid-cols-2 gap-x-3 gap-y-1 overflow-y-auto">
                      {preview.extra_columns.map((c) => (
                        <label key={c.name} className="flex min-w-0 items-center gap-2 text-xs">
                          <Checkbox
                            checked={columns.has(c.name)}
                            onCheckedChange={(v) =>
                              setColumns((prev) => {
                                const n = new Set(prev);
                                if (v === true) n.add(c.name);
                                else n.delete(c.name);
                                return n;
                              })
                            }
                            aria-label={`Import column ${c.name}`}
                          />
                          <span className="truncate">{c.name}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
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
