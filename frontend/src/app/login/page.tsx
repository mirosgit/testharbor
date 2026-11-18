"use client";

import { useQuery } from "@tanstack/react-query";
import { Anchor, Terminal } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: setup } = useQuery({ queryKey: ["setup-status"], queryFn: api.setupStatus });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email, password);
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  return (
    <div className="grid w-full max-w-sm gap-4">
      <form onSubmit={submit} className="grid gap-4 rounded-xl border bg-card p-8 shadow-sm">
        <div className="mb-2 flex items-center gap-2">
          <Anchor className="size-6 text-primary" />
          <span className="text-xl font-semibold">TestHarbor</span>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          No account? Ask your TestHarbor admin for an invite link.
        </p>
      </form>
      {setup && !setup.has_users && (
        <div className="grid gap-2 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <p className="flex items-center gap-2 font-medium">
            <Terminal className="size-4" /> No users yet
          </p>
          <p>Create the first admin on the server:</p>
          <code className="rounded bg-background/70 px-2 py-1 font-mono text-xs break-all">
            docker compose exec backend python -m app.manage create-admin
          </code>
        </div>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <ThemeToggle className="fixed top-3 right-3" />
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
