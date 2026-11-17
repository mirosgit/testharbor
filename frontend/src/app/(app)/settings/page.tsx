"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/me";

const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

export default function ProfilePage() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [name, setName] = useState("");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setName(me?.name ?? ""), [me?.name]);

  if (!me) return <Skeleton className="h-64" />;

  return (
    <div className="grid gap-10">
      <section className="grid max-w-md gap-4">
        <div>
          <h2 className="text-lg font-semibold">Profile</h2>
          <p className="text-sm text-muted-foreground">
            {me.email} · <span className="capitalize">{me.role}</span>
          </p>
        </div>
        <form
          className="flex items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              qc.setQueryData(["me"], await api.updateProfile(name));
              toast.success("Name saved");
            } catch (err) {
              fail(err);
            }
          }}
        >
          <div className="grid flex-1 gap-2">
            <Label htmlFor="profile-name">Name</Label>
            <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" variant="outline" disabled={!name.trim() || name === me.name}>
            Save
          </Button>
        </form>
      </section>

      <section className="grid max-w-md gap-4">
        <div>
          <h2 className="text-lg font-semibold">Change password</h2>
          <p className="text-sm text-muted-foreground">You stay signed in here; other sessions are signed out.</p>
        </div>
        <form
          className="grid gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (next !== repeat) return toast.error("New passwords don't match");
            setBusy(true);
            try {
              qc.setQueryData(["me"], await api.changePassword(current, next));
              toast.success("Password changed");
              setCurrent("");
              setNext("");
              setRepeat("");
            } catch (err) {
              fail(err);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="grid gap-2">
            <Label htmlFor="pw-current">Current password</Label>
            <Input id="pw-current" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pw-new">New password</Label>
            <Input id="pw-new" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
            <p className="text-xs text-muted-foreground">At least 10 characters.</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pw-repeat">Repeat new password</Label>
            <Input id="pw-repeat" type="password" value={repeat} onChange={(e) => setRepeat(e.target.value)} autoComplete="new-password" />
          </div>
          <Button type="submit" className="justify-self-start" disabled={busy || !current || !next}>
            Change password
          </Button>
        </form>
      </section>

      <section className="grid max-w-md gap-3">
        <h2 className="text-lg font-semibold">Sessions</h2>
        <p className="text-sm text-muted-foreground">
          Signed in on a shared or lost device? Sign out everywhere except this browser.
        </p>
        <Button
          variant="outline"
          className="justify-self-start"
          onClick={async () => {
            try {
              await api.logoutOthers();
              toast.success("Other sessions signed out");
            } catch (err) {
              fail(err);
            }
          }}
        >
          Sign out other sessions
        </Button>
      </section>
    </div>
  );
}
