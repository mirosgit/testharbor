"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AgentOption, AutomationAgent, RunParams, RunParamValue } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The agent whose run options the dialog offers: an online one first, else the last one seen. */
export function optionsAgent(agents: AutomationAgent[] | undefined): AutomationAgent | undefined {
  const withOptions = (agents ?? []).filter((a) => a.options.length);
  return withOptions.find((a) => a.online) ?? withOptions[0];
}

function fallback(o: AgentOption): RunParamValue {
  if (o.default != null) return o.default;
  return o.type === "bool" ? false : o.type === "multi" ? [] : (o.choices[0]?.value ?? "");
}

/** Values to start with: the agent's defaults, overridden by the last run's choices that are still offered. */
export function initialParams(options: AgentOption[], remembered: RunParams | null): RunParams {
  const out: RunParams = {};
  for (const o of options) {
    const allowed = new Set(o.choices.map((c) => c.value));
    const last = remembered?.[o.name];
    let value = fallback(o);
    if (o.type === "bool" && typeof last === "boolean") value = last;
    if (o.type === "choice" && typeof last === "string" && allowed.has(last)) value = last;
    if (o.type === "multi" && Array.isArray(last)) value = last.filter((v) => allowed.has(v));
    out[o.name] = value;
  }
  return out;
}

const storageKey = (projectId: number) => `testharbor.run-options.${projectId}`;

export function rememberedParams(projectId: number): RunParams | null {
  try {
    const raw = window.localStorage.getItem(storageKey(projectId));
    return raw ? (JSON.parse(raw) as RunParams) : null;
  } catch {
    return null;
  }
}

export function rememberParams(projectId: number, params: RunParams) {
  try {
    window.localStorage.setItem(storageKey(projectId), JSON.stringify(params));
  } catch {
    // Private mode or blocked storage: the defaults are used next time.
  }
}

/** "Environment: staging · Roles: Admin, Editor · Show the browser" — what a job was started with. */
export function describeParams(params: RunParams, options?: AgentOption[]): string {
  const byName = new Map((options ?? []).map((o) => [o.name, o]));
  const parts: string[] = [];
  // In the agent's order (JSONB does not keep the order of keys); unknown names last.
  const order = (options ?? []).map((o) => o.name);
  const rank = (name: string) => (order.includes(name) ? order.indexOf(name) : order.length);
  const entries = Object.entries(params).sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
  for (const [name, value] of entries) {
    const o = byName.get(name);
    const label = o?.label || name;
    const show = (v: string) => o?.choices.find((c) => c.value === v)?.label || v;
    if (typeof value === "boolean") {
      if (value) parts.push(label);
    } else if (Array.isArray(value)) {
      if (value.length) parts.push(`${label}: ${value.map(show).join(", ")}`);
    } else if (value) {
      parts.push(`${label}: ${show(value)}`);
    }
  }
  return parts.join(" · ");
}

export function RunOptionsForm({
  options,
  value,
  onChange,
}: {
  options: AgentOption[];
  value: RunParams;
  onChange: (v: RunParams) => void;
}) {
  const set = (name: string, v: RunParamValue) => onChange({ ...value, [name]: v });
  const choices = options.filter((o) => o.type !== "bool");
  const flags = options.filter((o) => o.type === "bool");
  return (
    <fieldset className="grid min-w-0 gap-3" data-testid="run-options">
      <legend className="mb-2 text-sm font-medium">Options</legend>
      {choices.map((o) => {
        const id = `run-option-${o.name}`;
        if (o.type === "choice") {
          return (
            <div key={o.name} className="grid gap-1.5 sm:grid-cols-[9rem_1fr] sm:items-center sm:gap-3">
              <Label htmlFor={id}>{o.label || o.name}</Label>
              <div className="grid min-w-0 gap-1">
                <Select value={String(value[o.name] ?? "")} onValueChange={(v) => set(o.name, v)}>
                  <SelectTrigger id={id} className="w-full" size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {o.choices.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label || c.value}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {o.hint && <span className="text-xs text-muted-foreground">{o.hint}</span>}
              </div>
            </div>
          );
        }
        const picked = Array.isArray(value[o.name]) ? (value[o.name] as string[]) : [];
        return (
          <div key={o.name} className="grid min-w-0 gap-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-medium">{o.label || o.name}</span>
              {picked.length > 0 ? (
                <button type="button" className="text-xs text-primary hover:underline" onClick={() => set(o.name, [])}>
                  Clear ({picked.length})
                </button>
              ) : (
                o.hint && <span className="text-xs text-muted-foreground">{o.hint}</span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={o.label || o.name}>
              {o.choices.map((c) => {
                const on = picked.includes(c.value);
                return (
                  <button
                    key={c.value}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      set(
                        o.name,
                        on
                          ? picked.filter((v) => v !== c.value)
                          : o.choices.map((x) => x.value).filter((v) => v === c.value || picked.includes(v)),
                      )
                    }
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                      on ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90" : "hover:bg-muted",
                    )}
                  >
                    {c.label || c.value}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
      {flags.length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {flags.map((o) => (
            <label key={o.name} className="flex cursor-pointer items-center gap-2 text-sm" title={o.hint ?? undefined}>
              <Checkbox checked={value[o.name] === true} onCheckedChange={(v) => set(o.name, v === true)} />
              {o.label || o.name}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
