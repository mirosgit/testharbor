"use client";

import { ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { CatalogSyncDialog, useCatalog } from "@/components/cases/catalog-sync";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import type { CatalogItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Folder {
  name: string;
  path: string;
  folders: Folder[];
  tests: CatalogItem[];
}

/** Tests of the catalog that have a case (only those can run: their results need somewhere to go). */
export const runnable = (i: CatalogItem) => i.case_id != null && i.action !== "outdated";

function tree(items: CatalogItem[]): Folder {
  const root: Folder = { name: "", path: "", folders: [], tests: [] };
  for (const i of items) {
    let node = root;
    for (const name of i.path) {
      let next = node.folders.find((f) => f.name === name);
      if (!next) {
        next = { name, path: node.path ? `${node.path} › ${name}` : name, folders: [], tests: [] };
        node.folders.push(next);
      }
      node = next;
    }
    node.tests.push(i);
  }
  return root;
}

function allTests(f: Folder): CatalogItem[] {
  return [...f.tests, ...f.folders.flatMap(allTests)];
}

/** Pick automated tests from the agent's catalog; the value is the ids of their cases. */
export function TestPicker({
  projectId,
  value,
  onChange,
  listClassName = "max-h-72",
  onSynced,
}: {
  projectId: number;
  value: Set<number>;
  onChange: (v: Set<number>) => void;
  /** Height of the scrolling list. */
  listClassName?: string;
  onSynced?: () => void;
}) {
  const { data: catalog, isLoading } = useCatalog(projectId);
  const [q, setQ] = useState("");
  const [syncOpen, setSyncOpen] = useState(false);
  const [closed, setClosed] = useState<Set<string>>(new Set());

  const items = useMemo(() => (catalog?.items ?? []).filter((i) => i.action !== "outdated"), [catalog]);
  const notSynced = items.filter((i) => !runnable(i)).length;
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return items;
    return items.filter((i) => {
      const text = `${i.title} ${i.path.join(" ")} ${i.case_key ?? ""}`.toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [items, q]);
  const root = useMemo(() => tree(shown), [shown]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading the tests…</p>;
  if (!catalog)
    return (
      <p className="rounded-md border p-3 text-sm text-muted-foreground">
        No list of tests yet. Start the agent with <code>--catalog</code>.
      </p>
    );

  const set = (tests: CatalogItem[], on: boolean) => {
    const next = new Set(value);
    for (const t of tests) if (runnable(t)) (on ? next.add(t.case_id!) : next.delete(t.case_id!));
    onChange(next);
  };

  const renderFolder = (f: Folder, depth: number) => {
    const tests = allTests(f).filter(runnable);
    const picked = tests.filter((t) => value.has(t.case_id!)).length;
    const open = q !== "" || !closed.has(f.path);
    return (
      <li key={f.path}>
        <div className="flex items-center gap-1.5 py-1" style={{ paddingLeft: depth * 16 }}>
          <button
            type="button"
            aria-label={open ? `Collapse ${f.name}` : `Expand ${f.name}`}
            className="text-muted-foreground"
            onClick={() =>
              setClosed((s) => {
                const n = new Set(s);
                if (n.has(f.path)) n.delete(f.path);
                else n.add(f.path);
                return n;
              })
            }
          >
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          </button>
          <Checkbox
            aria-label={`All tests in ${f.name}`}
            disabled={!tests.length}
            checked={picked && picked === tests.length ? true : picked ? "indeterminate" : false}
            onCheckedChange={(v) => set(tests, v === true)}
          />
          <span className="min-w-0 truncate text-sm font-medium">{f.name}</span>
          <span className="text-xs text-muted-foreground">
            {picked ? `${picked}/` : ""}
            {allTests(f).length}
          </span>
        </div>
        {open && (
          <ul>
            {f.folders.map((sub) => renderFolder(sub, depth + 1))}
            {f.tests.map((t) => (
              <li key={t.key}>
                <label
                  className={cn(
                    "flex items-start gap-2 py-1 text-sm",
                    runnable(t) ? "cursor-pointer" : "cursor-not-allowed text-muted-foreground",
                  )}
                  style={{ paddingLeft: (depth + 1) * 16 + 20 }}
                  title={runnable(t) ? undefined : "Not synced yet: it has no case, so its results would have nowhere to go"}
                >
                  <Checkbox
                    className="mt-0.5"
                    disabled={!runnable(t)}
                    checked={runnable(t) && value.has(t.case_id!)}
                    onCheckedChange={(v) => set([t], v === true)}
                  />
                  <span className="min-w-0 flex-1 break-words">{t.title}</span>
                  {t.case_key && <span className="shrink-0 font-mono text-xs text-muted-foreground">{t.case_key}</span>}
                </label>
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className="grid min-w-0 gap-2" data-testid="test-picker">
      {notSynced > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-xs dark:border-amber-800 dark:bg-amber-950/40">
          <span className="min-w-0 flex-1">
            {notSynced} of {items.length} tests have no case yet. Sync them to run them one by one.
          </span>
          <Button type="button" size="xs" variant="outline" onClick={() => setSyncOpen(true)}>
            Sync autotests
          </Button>
        </div>
      )}
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input className="h-8 pl-8" placeholder="Search tests" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className={cn("overflow-y-auto rounded-md border px-2 py-1", listClassName)}>
        {shown.length ? (
          <ul>
            {root.tests.length > 0 && renderFolder({ ...root, name: "Other", path: "(other)", folders: [] }, 0)}
            {root.folders.map((f) => renderFolder(f, 0))}
          </ul>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">No tests match.</p>
        )}
      </div>
      <CatalogSyncDialog open={syncOpen} onOpenChange={setSyncOpen} projectId={projectId} onApplied={() => onSynced?.()} />
    </div>
  );
}
