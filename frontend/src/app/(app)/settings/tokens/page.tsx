"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog, NameDialog } from "@/components/dialogs";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { timeAgo } from "@/components/runs/run-meta";
import { api } from "@/lib/api";
import { useIsAdmin } from "@/lib/me";
import type { ApiToken } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function TokensPage() {
  const qc = useQueryClient();
  const { data: tokens, isLoading } = useQuery({ queryKey: ["tokens"], queryFn: api.tokens });
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<ApiToken | null>(null);
  const isAdmin = useIsAdmin();
  const [origin, setOrigin] = useState("https://testharbor.example.com");
  useEffect(() => setOrigin(window.location.origin), []);

  const revoke = useMutation({
    mutationFn: (id: number) => api.revokeToken(id),
    onSuccess: () => {
      toast.success("Token revoked");
      qc.invalidateQueries({ queryKey: ["tokens"] });
    },
  });

  const projectId = projects?.[0]?.id ?? 1;
  const snippet = `pip install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"

export TESTHARBOR_URL=${origin}
export TESTHARBOR_TOKEN=<your token>

pytest --junitxml=report.xml
testcli upload report.xml --project ${projectId} --run-name "Nightly" --auto-create`;

  return (
    <>
      <div className="grid gap-10">
        <section className="grid gap-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">API tokens</h2>
              <p className="text-sm text-muted-foreground">
                Use tokens in CI and scripts: <code className="rounded bg-muted px-1">Authorization: Bearer &lt;token&gt;</code>.
                A token acts as you and is shown only once, when it is created.
                {isAdmin && " As an admin you see and can revoke everyone's tokens."}
              </p>
            </div>
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus /> New token
            </Button>
          </div>
          {isLoading ? (
            <Skeleton className="h-24" />
          ) : !tokens?.length ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
              <KeyRound className="size-8" />
              No tokens yet. Create one to upload results from CI.
            </div>
          ) : (
            <div className="divide-y rounded-lg border" data-testid="tokens">
              {tokens.map((t) => (
                <div key={t.id} className={cn("flex items-center gap-4 px-4 py-3 text-sm", t.revoked_at && "opacity-50")}>
                  <KeyRound className="size-4 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{t.name}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {t.prefix}…{isAdmin && t.owner && <span className="font-sans"> · {t.owner}</span>}
                    </div>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <div>Created {timeAgo(t.created_at)}</div>
                    <div>{t.last_used_at ? `Last used ${timeAgo(t.last_used_at)}` : "Never used"}</div>
                  </div>
                  {t.revoked_at ? (
                    <span className="w-20 text-center text-xs text-muted-foreground">Revoked</span>
                  ) : (
                    <Button variant="outline" size="sm" className="w-20" onClick={() => setRevoking(t)}>
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="grid gap-3">
          <h2 className="text-lg font-semibold">Connect your automated tests</h2>
          <p className="text-sm text-muted-foreground">
            Any framework that writes JUnit XML works (pytest, Playwright, Jest, JUnit/TestNG, Cypress…).
            Tests are linked to cases by a <code className="rounded bg-muted px-1">C123</code> id in the test name or a{" "}
            <code className="rounded bg-muted px-1">case_id</code> property, then by the case&apos;s automation key.
            See <code className="rounded bg-muted px-1">docs/integration.md</code> in the repository for CI examples.
          </p>
          <CodeBlock code={snippet} />
          <p className="text-sm text-muted-foreground">
            API reference:{" "}
            <a className="text-primary underline" href="/docs" target="_blank" rel="noreferrer">
              {origin}/docs
            </a>
          </p>
        </section>
      </div>

      <NameDialog
        open={creating}
        onOpenChange={setCreating}
        title="New API token"
        description="Give it a name that says where it is used, e.g. “GitHub Actions”."
        submitLabel="Create token"
        onSubmit={async ({ name }) => {
          const t = await api.createToken(name);
          qc.invalidateQueries({ queryKey: ["tokens"] });
          setCreated(t.token);
        }}
      />
      <Dialog open={!!created} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Copy your token now</DialogTitle>
            <DialogDescription>You won&apos;t be able to see it again. Store it as a CI secret.</DialogDescription>
          </DialogHeader>
          {created && <CodeBlock code={created} testId="new-token" />}
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!revoking}
        onOpenChange={(o) => !o && setRevoking(null)}
        title={`Revoke “${revoking?.name}”?`}
        description="Anything using this token will stop working immediately."
        confirmLabel="Revoke"
        onConfirm={() => revoke.mutate(revoking!.id)}
      />
    </>
  );
}

function CodeBlock({ code, testId }: { code: string; testId?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre
        data-testid={testId}
        className="overflow-x-auto rounded-lg border bg-muted/50 p-4 pr-12 font-mono text-[13px] leading-relaxed break-all whitespace-pre-wrap"
      >
        {code}
      </pre>
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute top-2 right-2"
        aria-label="Copy"
        onClick={async () => {
          await navigator.clipboard?.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}
