"use client";

import { useEffect, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Delete",
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription>{description}</AlertDialogDescription>}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            onClick={() => void onConfirm()}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Small form dialog for "name (+ description)" entities. */
export function NameDialog({
  open,
  onOpenChange,
  title,
  description,
  initialName = "",
  initialDescription,
  submitLabel = "Save",
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  initialName?: string;
  /** Pass a string to show the description field. */
  initialDescription?: string;
  submitLabel?: string;
  onSubmit: (values: { name: string; description: string }) => Promise<unknown>;
}) {
  const [name, setName] = useState(initialName);
  const [desc, setDesc] = useState(initialDescription ?? "");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setName(initialName);
      setDesc(initialDescription ?? "");
    }
  }, [open, initialName, initialDescription]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!name.trim()) return;
            setBusy(true);
            try {
              await onSubmit({ name: name.trim(), description: desc });
              onOpenChange(false);
            } finally {
              setBusy(false);
            }
          }}
          className="grid gap-4"
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="name-dialog-name">Name</Label>
            <Input
              id="name-dialog-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          {initialDescription !== undefined && (
            <div className="grid gap-2">
              <Label htmlFor="name-dialog-desc">Description</Label>
              <Textarea
                id="name-dialog-desc"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                rows={3}
              />
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
