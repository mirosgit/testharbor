"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SectionNode } from "@/lib/tree";

export function MoveDialog({
  open,
  onOpenChange,
  sections,
  paths,
  count,
  onMove,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  sections: SectionNode[];
  paths: Map<number, string>;
  count: number;
  onMove: (sectionId: number) => Promise<void>;
}) {
  const [target, setTarget] = useState<string>("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Move {count} cases</DialogTitle>
        </DialogHeader>
        <Select value={target} onValueChange={setTarget}>
          <SelectTrigger className="w-full" aria-label="Target section">
            <SelectValue placeholder="Choose a section" />
          </SelectTrigger>
          <SelectContent>
            {sections.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {paths.get(s.id)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!target}
            onClick={async () => {
              await onMove(Number(target));
              onOpenChange(false);
            }}
          >
            Move
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
