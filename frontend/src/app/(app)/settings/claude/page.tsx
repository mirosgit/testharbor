"use client";

import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/code-block";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";

const READS = [
  "Projects, suites and the section tree",
  "Search cases by title, section, state, priority, automation or tags",
  "A case with all its steps and fields, and its results across runs",
  "Runs, with failed cases and their error messages",
  "The project dashboard: coverage, pass rate, failing and flaky cases",
];
const WRITES = [
  "Create test cases and sections",
  "Change a case's fields and steps",
];
const PROMPTS = [
  "Which cases failed in the last nightly run of “My project”, and what do the errors have in common?",
  "Write test cases for password reset into the Auth section, using the project's roles.",
  "Find cases about exporting orders that have no steps yet, and fill in their steps.",
];

export default function ClaudePage() {
  const qc = useQueryClient();
  const [origin, setOrigin] = useState("https://testharbor.example.com");
  useEffect(() => setOrigin(window.location.origin), []);
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const createToken = async () => {
    setBusy(true);
    try {
      setToken((await api.createToken("Claude")).token);
      qc.invalidateQueries({ queryKey: ["tokens"] });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const url = `${origin}/api/mcp`;
  const command = `claude mcp add --transport http --scope user testharbor ${url} \\
  --header "Authorization: Bearer ${token ?? "<your token>"}"`;
  const mcpJson = `{
  "mcpServers": {
    "testharbor": {
      "type": "http",
      "url": "${url}",
      "headers": { "Authorization": "Bearer \${TESTHARBOR_TOKEN}" }
    }
  }
}`;

  return (
    <div className="grid gap-8" data-testid="claude-settings">
      <section className="grid gap-2">
        <h2 className="text-lg font-semibold">Claude</h2>
        <p className="text-sm text-muted-foreground">
          Work with TestHarbor from Claude Code, on your own Claude account, personal or your company&apos;s plan.
          Claude runs on your side. TestHarbor gives it tools to look things up and to write test cases, and it acts
          as you. Cases it creates arrive as <span className="font-medium text-foreground">Pending review</span>, and
          it has no tools that delete anything.
        </p>
      </section>

      <section className="grid gap-3">
        <h3 className="font-medium">1. A token for Claude</h3>
        {token ? (
          <p className="text-sm text-muted-foreground">
            Created a token named “Claude”. It is in the command below and is shown only now. You can revoke it under{" "}
            <Link href="/settings/tokens" className="text-primary hover:underline">
              API tokens
            </Link>
            .
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" onClick={createToken} disabled={busy} data-testid="claude-token">
              {busy ? <Loader2 className="animate-spin" /> : <KeyRound />}
              Create a token for Claude
            </Button>
            <span className="text-sm text-muted-foreground">or use one you already have.</span>
          </div>
        )}
      </section>

      <section className="grid gap-3">
        <h3 className="font-medium">2. Add TestHarbor to Claude Code</h3>
        <CodeBlock code={command} testId="claude-command" />
        <p className="text-sm text-muted-foreground">
          Then run <code className="rounded bg-muted px-1">claude</code> and check that{" "}
          <code className="rounded bg-muted px-1">/mcp</code> lists <span className="font-medium">testharbor</span>.
        </p>
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            For the whole team, in a repository
          </summary>
          <div className="mt-3 grid gap-2">
            <p className="text-muted-foreground">
              Put this in <code className="rounded bg-muted px-1">.mcp.json</code> at the root of the repository. Each
              person sets <code className="rounded bg-muted px-1">TESTHARBOR_TOKEN</code> to a token of their own, so
              the token never goes into git.
            </p>
            <CodeBlock code={mcpJson} />
          </div>
        </details>
      </section>

      <section className="grid gap-3">
        <h3 className="font-medium">3. Ask</h3>
        <ul className="grid gap-1.5 text-sm">
          {PROMPTS.map((p) => (
            <li key={p} className="rounded-md border bg-muted/30 px-3 py-2">
              {p}
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="grid content-start gap-2">
          <h3 className="font-medium">What Claude can read</h3>
          <ul className="grid list-disc gap-1 pl-5 text-sm text-muted-foreground">
            {READS.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
        <div className="grid content-start gap-2">
          <h3 className="font-medium">What Claude can change</h3>
          <ul className="grid list-disc gap-1 pl-5 text-sm text-muted-foreground">
            {WRITES.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
