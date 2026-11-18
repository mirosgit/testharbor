"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";

const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

export default function ProjectSettingsPage() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const { data: project } = useQuery({ queryKey: ["project", projectId], queryFn: () => api.project(projectId) });

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-3xl gap-10 p-6">
        <h1 className="text-xl font-semibold">Project settings</h1>
        {!project ? (
          <Skeleton className="h-64" />
        ) : (
          <>
            <General project={project} />
            <Roles project={project} />
          </>
        )}
      </div>
    </main>
  );
}

function useSaveProject() {
  const qc = useQueryClient();
  return (p: Project) => {
    qc.setQueryData(["project", p.id], p);
    qc.invalidateQueries({ queryKey: ["projects"] });
    qc.invalidateQueries({ queryKey: ["case-values", p.id] });
  };
}

function General({ project }: { project: Project }) {
  const saved = useSaveProject();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  useEffect(() => {
    setName(project.name);
    setDescription(project.description);
  }, [project.name, project.description]);
  const dirty = name !== project.name || description !== project.description;

  return (
    <form
      className="grid gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          saved(await api.updateProject(project.id, { name: name.trim(), description }));
          toast.success("Project saved");
        } catch (err) {
          fail(err);
        }
      }}
    >
      <h2 className="text-lg font-semibold">General</h2>
      <div className="grid gap-2">
        <Label htmlFor="project-name">Name</Label>
        <Input id="project-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="project-description">Description</Label>
        <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </div>
      <Button type="submit" variant="outline" className="justify-self-start" disabled={!dirty || !name.trim()}>
        Save
      </Button>
    </form>
  );
}

function Roles({ project }: { project: Project }) {
  const saved = useSaveProject();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const setRoles = async (roles: string[], message: string) => {
    try {
      saved(await api.updateProject(project.id, { roles }));
      toast.success(message);
    } catch (err) {
      fail(err);
    }
  };

  const add = async () => {
    // Several at once: "Editor, Reviewer" or one per line.
    const has = new Set(project.roles.map((r) => r.toLowerCase()));
    const fresh: string[] = [];
    for (const part of draft.split(/[,;\n]/)) {
      const r = part.trim().replace(/\s+/g, " ");
      if (r && !has.has(r.toLowerCase())) {
        has.add(r.toLowerCase());
        fresh.push(r);
      }
    }
    setDraft("");
    if (fresh.length) await setRoles([...project.roles, ...fresh], `Added ${fresh.join(", ")}`);
  };

  const rename = async (old: string) => {
    const name = newName.trim();
    setEditing(null);
    if (!name || name === old) return;
    try {
      saved(await api.renameRole(project.id, old, name));
      toast.success(`Renamed “${old}” to “${name}” in the list and in all cases`);
    } catch (err) {
      fail(err);
    }
  };

  return (
    <section className="grid gap-4" data-testid="project-roles">
      <div>
        <h2 className="text-lg font-semibold">Roles</h2>
        <p className="text-sm text-muted-foreground">
          User roles of the product under test. Cases pick from this list. Renaming a role also renames it in all
          cases; removing it from the list keeps it on cases that already have it.
        </p>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="New role, or several separated by commas"
          aria-label="New role"
          maxLength={2000}
        />
        <Button type="submit" variant="outline" disabled={!draft.trim()}>
          <Plus /> Add
        </Button>
      </form>
      {project.roles.length === 0 ? (
        <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          No roles yet. Roles used in cases or imported from a file are added here automatically.
        </p>
      ) : (
        <ul className="divide-y rounded-md border">
          {project.roles.map((role) => (
            <li key={role} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              {editing === role ? (
                <form
                  className="flex flex-1 items-center gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void rename(role);
                  }}
                >
                  <Input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                    autoFocus
                    className="h-8"
                    aria-label={`New name for ${role}`}
                    maxLength={100}
                  />
                  <Button type="submit" size="icon-sm" variant="ghost" aria-label="Save name">
                    <Check />
                  </Button>
                  <Button type="button" size="icon-sm" variant="ghost" aria-label="Cancel" onClick={() => setEditing(null)}>
                    <X />
                  </Button>
                </form>
              ) : (
                <>
                  <span className="flex-1">{role}</span>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Rename ${role}`}
                    onClick={() => {
                      setEditing(role);
                      setNewName(role);
                    }}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Remove ${role}`}
                    onClick={() => setRoles(project.roles.filter((r) => r !== role), `Removed ${role}`)}
                  >
                    <X />
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
