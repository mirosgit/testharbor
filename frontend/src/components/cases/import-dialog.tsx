"use client";

import { useState } from "react";
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
import { api, ApiError } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

export function ImportDialog({
  open,
  onOpenChange,
  suiteId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  suiteId: number;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const reset = (o: boolean) => {
    if (!o) {
      setFile(null);
      setResult(null);
    }
    onOpenChange(o);
  };

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import cases</DialogTitle>
          <DialogDescription>
            Upload a CSV or JSON file (same format as Export). Rows with an existing case id update
            that case; others create new cases. Sections are created from <code>section_path</code>.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="grid gap-2 text-sm">
            <p>
              <b>{result.created}</b> created, <b>{result.updated}</b> updated,{" "}
              <b>{result.sections_created}</b> sections created.
            </p>
            {result.errors.length > 0 && (
              <div className="max-h-48 overflow-y-auto rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs">
                <p className="mb-1 font-medium text-destructive">{result.errors.length} rows skipped:</p>
                <ul className="grid gap-0.5">
                  {result.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <Input
            type="file"
            accept=".csv,.json,text/csv,application/json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            aria-label="File to import"
          />
        )}
        <DialogFooter>
          {result ? (
            <Button onClick={() => reset(false)}>Done</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => reset(false)}>
                Cancel
              </Button>
              <Button
                disabled={!file || busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    setResult(await api.importCases(suiteId, file!));
                    onImported();
                  } catch (e) {
                    toast.error(e instanceof ApiError ? e.message : "Import failed");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Importing…" : "Import"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
