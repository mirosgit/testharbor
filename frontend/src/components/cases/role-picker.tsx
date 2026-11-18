"use client";

import { Settings2 } from "lucide-react";
import Link from "next/link";

import { MultiCombobox } from "@/components/combobox";

/** Pick roles from the project's list. A new role typed in the search box can be added
 * too; it joins the project list when the case is saved. */
export function RolePicker({
  id,
  value,
  onChange,
  options,
  projectId,
  placeholder = "No roles",
}: {
  id?: string;
  value: string[];
  onChange: (roles: string[]) => void;
  options: string[];
  projectId: number;
  placeholder?: string;
}) {
  return (
    <MultiCombobox
      id={id}
      aria-label="Roles"
      value={value}
      onChange={onChange}
      options={options}
      placeholder={placeholder}
      searchPlaceholder="Find a role"
      noun="role"
      footer={
        <Link
          href={`/projects/${projectId}/settings`}
          className="flex items-center gap-1.5 rounded-sm px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Settings2 className="size-3.5" /> Manage project roles
        </Link>
      }
    />
  );
}
