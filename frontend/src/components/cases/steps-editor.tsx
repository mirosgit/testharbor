"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Step } from "@/lib/types";

export function StepsEditor({ steps, onChange }: { steps: Step[]; onChange: (s: Step[]) => void }) {
  const update = (i: number, patch: Partial<Step>) =>
    onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const move = (i: number, d: -1 | 1) => {
    const next = [...steps];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  const insert = (i: number) =>
    onChange([...steps.slice(0, i), { action: "", expected: "" }, ...steps.slice(i)]);

  return (
    <div className="rounded-md border" data-testid="steps-editor">
      <div className="grid grid-cols-[2rem_1fr_1fr_5.5rem] gap-2 border-b bg-muted/50 px-2 py-1.5 text-xs font-medium text-muted-foreground">
        <span>#</span>
        <span>Step</span>
        <span>Expected Result</span>
        <span />
      </div>
      {steps.length === 0 && (
        <p className="px-3 py-4 text-center text-sm text-muted-foreground">No steps yet.</p>
      )}
      {steps.map((s, i) => (
        <div
          key={i}
          className="group grid grid-cols-[2rem_1fr_1fr_5.5rem] items-start gap-2 border-b px-2 py-2 last:border-b-0"
        >
          <span className="pt-2 text-sm text-muted-foreground tabular-nums">{i + 1}</span>
          <Textarea
            aria-label={`Step ${i + 1} action`}
            value={s.action}
            onChange={(e) => update(i, { action: e.target.value })}
            rows={2}
            className="min-h-9 text-sm"
          />
          <Textarea
            aria-label={`Step ${i + 1} expected result`}
            value={s.expected}
            onChange={(e) => update(i, { expected: e.target.value })}
            rows={2}
            className="min-h-9 text-sm"
          />
          <div className="flex flex-wrap gap-0.5 opacity-60 group-focus-within:opacity-100 group-hover:opacity-100">
            <Button type="button" variant="ghost" size="icon-xs" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move step up">
              <ArrowUp />
            </Button>
            <Button type="button" variant="ghost" size="icon-xs" disabled={i === steps.length - 1} onClick={() => move(i, 1)} aria-label="Move step down">
              <ArrowDown />
            </Button>
            <Button type="button" variant="ghost" size="icon-xs" onClick={() => insert(i + 1)} aria-label="Insert step below">
              <Plus />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              onClick={() => onChange(steps.filter((_, j) => j !== i))}
              aria-label="Delete step"
            >
              <Trash2 className="text-destructive" />
            </Button>
          </div>
        </div>
      ))}
      <div className="p-2">
        <Button type="button" variant="outline" size="sm" onClick={() => insert(steps.length)}>
          <Plus /> Add step
        </Button>
      </div>
    </div>
  );
}
