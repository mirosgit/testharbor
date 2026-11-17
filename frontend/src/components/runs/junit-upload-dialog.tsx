"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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
import { api, ApiError } from "@/lib/api";
import type { JUnitImportResult } from "@/lib/types";

export function JUnitUploadDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [runName, setRunName] = useState("");
  const [branch, setBranch] = useState("");
  const [commit, setCommit] = useState("");
  const [autoCreate, setAutoCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<JUnitImportResult | null>(null);

  const close = (o: boolean) => {
    if (!o) {
      setFiles([]);
      setResult(null);
      setRunName("");
      setBranch("");
      setCommit("");
      setAutoCreate(false);
    }
    onOpenChange(o);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.importJunit(projectId, files, {
        run_name: runName.trim() || undefined,
        branch: branch.trim() || undefined,
        commit: commit.trim() || undefined,
        auto_create: autoCreate,
      });
      setResult(r);
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["suites", projectId] });
      qc.invalidateQueries({ queryKey: ["cases"] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload JUnit XML</DialogTitle>
          <DialogDescription>
            Creates a CI run from one or more JUnit reports. In CI, use <code>testcli upload</code> instead.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="grid gap-3 text-sm" data-testid="junit-result">
            <p>
              <b>{result.total}</b> tests: <b>{result.matched}</b> matched, <b>{result.created}</b> cases created,{" "}
              <b>{result.unmatched.length}</b> unmatched.
            </p>
            {result.unmatched.length > 0 && (
              <div className="max-h-48 overflow-y-auto rounded-md border bg-muted/40 p-2 text-xs">
                <ul className="grid gap-1">
                  {result.unmatched.map((u, i) => (
                    <li key={i}>
                      <span className="font-mono">{u.classname ? `${u.classname}::${u.name}` : u.name}</span>
                      <span className="text-muted-foreground"> — {u.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <DialogFooter>
              <Button variant="ghost" onClick={() => close(false)}>
                Close
              </Button>
              <Button
                onClick={() => {
                  close(false);
                  router.push(`/projects/${projectId}/runs/${result.run_id}`);
                }}
              >
                Open run
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-4">
            <Input
              type="file"
              multiple
              accept=".xml,application/xml,text/xml"
              onChange={(e) => setFiles([...(e.target.files ?? [])])}
              aria-label="JUnit XML files"
            />
            <div className="grid gap-2">
              <Label htmlFor="junit-run-name">Run name</Label>
              <Input
                id="junit-run-name"
                value={runName}
                onChange={(e) => setRunName(e.target.value)}
                placeholder="Defaults to “Automated run <date>”"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="junit-branch">Branch</Label>
                <Input id="junit-branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="junit-commit">Commit</Label>
                <Input id="junit-commit" value={commit} onChange={(e) => setCommit(e.target.value)} />
              </div>
            </div>
            <label className="flex items-start gap-2 text-sm">
              <Checkbox checked={autoCreate} onCheckedChange={(v) => setAutoCreate(v === true)} className="mt-0.5" />
              <span>
                Create cases for unmatched tests
                <span className="block text-xs text-muted-foreground">In the “Unsorted › Automated” section.</span>
              </span>
            </label>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy || files.length === 0}>
                {busy ? "Uploading…" : "Upload"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
