"use client";

import { useQuery } from "@tanstack/react-query";
import { Anchor } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";

const MIN = 10;

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { data: info, isLoading, error } = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api.inviteInfo(token),
    retry: false,
  });
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isReset = info?.purpose === "reset";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN) return setProblem(`Password must be at least ${MIN} characters`);
    if (password !== repeat) return setProblem("Passwords don't match");
    if (!isReset && !name.trim()) return setProblem("Enter your name");
    setBusy(true);
    setProblem(null);
    try {
      await api.acceptInvite(token, { name: isReset ? undefined : name.trim(), password });
      router.replace("/");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <div className="grid w-full max-w-sm gap-4 rounded-xl border bg-card p-8 shadow-sm">
        <div className="flex items-center gap-2">
          <Anchor className="size-6 text-primary" />
          <span className="text-xl font-semibold">TestHarbor</span>
        </div>
        {isLoading ? (
          <Skeleton className="h-40" />
        ) : error || !info ? (
          <div className="grid gap-3 text-sm">
            <p className="font-medium">This link is invalid or has expired.</p>
            <p className="text-muted-foreground">Links work once and expire after 72 hours. Ask your admin for a new one.</p>
            <Link href="/login" className="text-primary underline">
              Go to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-4">
            <div>
              <h1 className="text-lg font-semibold">{isReset ? "Set a new password" : "Create your account"}</h1>
              <p className="text-sm text-muted-foreground">
                {isReset ? `For ${info.name ?? info.email}` : `You were invited as ${info.role}.`}
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="invite-email">Email</Label>
              <Input id="invite-email" value={info.email} disabled />
            </div>
            {!isReset && (
              <div className="grid gap-2">
                <Label htmlFor="invite-name">Your name</Label>
                <Input id="invite-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="name" />
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="invite-password">Password</Label>
              <Input
                id="invite-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                autoFocus={isReset}
              />
              <p className="text-xs text-muted-foreground">At least {MIN} characters. A passphrase works well.</p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="invite-repeat">Repeat password</Label>
              <Input
                id="invite-repeat"
                type="password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            {problem && (
              <p role="alert" className="text-sm text-destructive">
                {problem}
              </p>
            )}
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : isReset ? "Set password and sign in" : "Create account"}
            </Button>
          </form>
        )}
      </div>
    </main>
  );
}
