"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, MoreHorizontal, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog, NameDialog } from "@/components/dialogs";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useIsAdmin } from "@/lib/me";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const { data: projects, isLoading } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const isAdmin = useIsAdmin();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["projects"] });
  const del = useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: () => {
      toast.success("Project deleted");
      refresh();
    },
  });

  return (
    <main className="mx-auto max-w-5xl overflow-y-auto p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Button onClick={() => setCreating(true)}>
          <Plus /> New project
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : projects?.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-16 text-center">
          <FolderOpen className="size-10 text-muted-foreground" />
          <p className="text-muted-foreground">No projects yet.</p>
          <Button onClick={() => setCreating(true)}>
            <Plus /> Create your first project
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects?.map((p) => (
            <div
              key={p.id}
              className="group relative rounded-xl border bg-card p-5 transition-shadow hover:shadow-md"
            >
              <Link href={`/projects/${p.id}/cases`} className="absolute inset-0" aria-label={p.name} />
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold">{p.name}</h2>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon-xs" className="relative z-10" aria-label="Project actions">
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => setEditing(p)}>Edit</DropdownMenuItem>
                    {isAdmin && (
                      <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(p)}>
                        Delete
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">
                {p.description || "No description"}
              </p>
              <div className="mt-4 flex gap-4 text-xs text-muted-foreground">
                <span>{p.suite_count} suites</span>
                <span>{p.case_count} cases</span>
                <span>{p.run_count} runs</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <NameDialog
        open={creating}
        onOpenChange={setCreating}
        title="New project"
        initialDescription=""
        submitLabel="Create"
        onSubmit={async (v) => {
          await api.createProject(v);
          refresh();
        }}
      />
      <NameDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        title="Edit project"
        initialName={editing?.name}
        initialDescription={editing?.description ?? ""}
        onSubmit={async (v) => {
          await api.updateProject(editing!.id, v);
          refresh();
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete project “${deleting?.name}”?`}
        description={`This permanently deletes ${deleting?.suite_count} suites, ${deleting?.case_count} cases and ${deleting?.run_count} runs.`}
        onConfirm={() => del.mutate(deleting!.id)}
      />
    </main>
  );
}
