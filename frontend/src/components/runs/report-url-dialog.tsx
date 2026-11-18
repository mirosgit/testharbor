"use client";

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
import { ApiError } from "@/lib/api";

/** Set where the run's HTML report lives; per-test links are built from it. */
export function ReportUrlDialog({
  open,
  onOpenChange,
  initial,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  initial: string;
  onSubmit: (url: string) => Promise<void>;
}) {
  const [url, setUrl] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setUrl(initial);
  }, [open, initial]);
  const valid = !url.trim() || /^https?:\/\/\S+$/i.test(url.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await onSubmit(url.trim());
              toast.success(url.trim() ? "Report link saved" : "Report link removed");
              onOpenChange(false);
            } catch (err) {
              toast.error(err instanceof ApiError ? err.message : "Could not save");
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Report link</DialogTitle>
            <DialogDescription>
              Where this run&apos;s HTML report is published, e.g. Playwright&apos;s <code>index.html</code>. Tests
              uploaded from a Playwright JSON report link straight to their page in it.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="report-url">Report URL</Label>
            <Input
              id="report-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://ci.example.com/artifacts/playwright-report/index.html"
              autoFocus
            />
            {!valid && <p className="text-xs text-destructive">Must start with http:// or https://</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !valid}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
