"use client";

import { X } from "lucide-react";
import { useId, useState } from "react";

export function TagInput({
  value,
  onChange,
  suggestions = [],
  id,
  lowercase = true,
  placeholder = "Add tags…",
  noun = "tag",
}: {
  value: string[];
  onChange: (tags: string[]) => void;
  suggestions?: string[];
  id?: string;
  /** Tags are lowercased; other lists (e.g. roles) keep their spelling. */
  lowercase?: boolean;
  placeholder?: string;
  noun?: string;
}) {
  const [draft, setDraft] = useState("");
  const listId = useId();
  const has = (list: string[], t: string) => list.some((x) => x.toLowerCase() === t.toLowerCase());
  const add = (raw: string) => {
    const tags: string[] = [];
    for (const part of raw.split(",")) {
      const t = lowercase ? part.trim().toLowerCase() : part.trim().replace(/\s+/g, " ");
      if (t && !has(value, t) && !has(tags, t)) tags.push(t);
    }
    if (tags.length) onChange([...value, ...tags]);
    setDraft("");
  };

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-md border px-2 py-1 focus-within:ring-[3px] focus-within:ring-ring/50">
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-xs">
          {t}
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => onChange(value.filter((x) => x !== t))}
            aria-label={`Remove ${noun} ${t}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        list={listId}
        value={draft}
        placeholder={value.length ? "" : placeholder}
        className="min-w-24 flex-1 bg-transparent text-sm outline-none"
        onChange={(e) => {
          const v = e.target.value;
          if (v.endsWith(",")) add(v);
          else setDraft(v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add(draft);
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => draft && add(draft)}
      />
      <datalist id={listId}>
        {suggestions
          .filter((s) => !has(value, s))
          .map((s) => (
            <option key={s} value={s} />
          ))}
      </datalist>
    </div>
  );
}
