"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Link2, Lock, MoreHorizontal, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/dialogs";
import { timeAgo } from "@/components/runs/run-meta";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { useIsAdmin, useMe } from "@/lib/me";
import type { AdminUser, InviteLink, Role } from "@/lib/types";
import { cn } from "@/lib/utils";

const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

export default function UsersPage() {
  const qc = useQueryClient();
  const isAdmin = useIsAdmin();
  const { data: me } = useMe();
  const usersQ = useQuery({ queryKey: ["users"], queryFn: api.users, enabled: isAdmin });
  const invitesQ = useQuery({ queryKey: ["invites"], queryFn: api.invites, enabled: isAdmin });
  const [inviting, setInviting] = useState(false);
  const [link, setLink] = useState<InviteLink | null>(null);
  const [deactivating, setDeactivating] = useState<AdminUser | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["invites"] });
  };
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateUser>[1] }) => api.updateUser(id, body),
    onSuccess: () => refresh(),
    onError: fail,
  });

  if (me && !isAdmin) return <p className="text-muted-foreground">Only admins can manage users.</p>;

  return (
    <div className="grid gap-10">
      <section className="grid gap-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Users</h2>
            <p className="text-sm text-muted-foreground">
              Testers work with cases, runs and their own API tokens. Admins can also manage users and delete projects.
            </p>
          </div>
          <Button size="sm" onClick={() => setInviting(true)}>
            <UserPlus /> Invite user
          </Button>
        </div>
        {usersQ.isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <div className="divide-y rounded-lg border" data-testid="users">
            {usersQ.data?.map((u) => (
              <div key={u.id} className={cn("flex items-center gap-4 px-4 py-3 text-sm", !u.is_active && "opacity-50")}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 font-medium">
                    {u.name}
                    {u.id === me?.id && <span className="text-xs font-normal text-muted-foreground">(you)</span>}
                    {u.locked && (
                      <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 text-[11px] text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                        <Lock className="size-3" /> locked
                      </span>
                    )}
                    {!u.is_active && <span className="text-xs font-normal">deactivated</span>}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">{u.email}</div>
                </div>
                <div className="hidden text-right text-xs text-muted-foreground sm:block">
                  {u.last_login_at ? `Last sign-in ${timeAgo(u.last_login_at)}` : "Never signed in"}
                </div>
                <Select
                  value={u.role}
                  disabled={u.id === me?.id || !u.is_active}
                  onValueChange={(role) => update.mutate({ id: u.id, body: { role: role as Role } })}
                >
                  <SelectTrigger size="sm" className="w-28" aria-label={`Role of ${u.name}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tester">Tester</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${u.name}`}>
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {u.is_active && (
                      <DropdownMenuItem
                        onSelect={async () => {
                          try {
                            setLink(await api.resetLink(u.id));
                            refresh();
                          } catch (e) {
                            fail(e);
                          }
                        }}
                      >
                        <Link2 /> Password reset link
                      </DropdownMenuItem>
                    )}
                    {u.locked && (
                      <DropdownMenuItem onSelect={() => update.mutate({ id: u.id, body: { unlock: true } })}>
                        Unlock sign-in
                      </DropdownMenuItem>
                    )}
                    {u.id !== me?.id && (
                      <>
                        <DropdownMenuSeparator />
                        {u.is_active ? (
                          <DropdownMenuItem variant="destructive" onSelect={() => setDeactivating(u)}>
                            Deactivate
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onSelect={() => update.mutate({ id: u.id, body: { is_active: true } })}>
                            Reactivate
                          </DropdownMenuItem>
                        )}
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">Pending links</h2>
        {!invitesQ.data?.length ? (
          <p className="text-sm text-muted-foreground">No pending invites or reset links.</p>
        ) : (
          <div className="divide-y rounded-lg border" data-testid="invites">
            {invitesQ.data.map((i) => (
              <div key={i.id} className="flex items-center gap-4 px-4 py-2.5 text-sm">
                <span className="w-16 text-xs text-muted-foreground">{i.purpose === "reset" ? "Reset" : "Invite"}</span>
                <span className="min-w-0 flex-1 truncate">{i.email}</span>
                <span className="text-xs text-muted-foreground capitalize">{i.role}</span>
                <span className="text-xs text-muted-foreground">
                  expires {new Date(i.expires_at).toLocaleString()}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => api.revokeInvite(i.id).then(refresh, fail)}
                >
                  Revoke
                </Button>
              </div>
            ))}
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          The link itself is shown only once, when it is created. If it got lost, revoke it and create a new one.
        </p>
      </section>

      <InviteDialog open={inviting} onOpenChange={setInviting} onCreated={(l) => { setLink(l); refresh(); }} />
      <LinkDialog link={link} onClose={() => setLink(null)} />
      <ConfirmDialog
        open={!!deactivating}
        onOpenChange={(o) => !o && setDeactivating(null)}
        title={`Deactivate ${deactivating?.name}?`}
        description="They are signed out immediately and their API tokens stop working. You can reactivate them later; their history is kept."
        confirmLabel="Deactivate"
        onConfirm={() => update.mutate({ id: deactivating!.id, body: { is_active: false } })}
      />
    </div>
  );
}

function InviteDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCreated: (link: InviteLink) => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("tester");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form
          className="grid gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              const l = await api.createInvite(email, role);
              onOpenChange(false);
              setEmail("");
              setRole("tester");
              onCreated(l);
            } catch (err) {
              fail(err);
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Invite a user</DialogTitle>
            <DialogDescription>You&apos;ll get a one-time link (valid 72 hours) to send them.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="invite-email-input">Email</Label>
            <Input id="invite-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </div>
          <div className="grid gap-2">
            <Label>Role</Label>
            <Select value={role} onValueChange={(r) => setRole(r as Role)}>
              <SelectTrigger className="w-full" aria-label="Role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tester">Tester</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !email}>
              Create link
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LinkDialog({ link, onClose }: { link: InviteLink | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const url = link && typeof window !== "undefined" ? `${window.location.origin}${link.path}` : "";
  return (
    <Dialog open={!!link} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{link?.purpose === "reset" ? "Password reset link" : "Invite link"}</DialogTitle>
          <DialogDescription>
            Send this to {link?.email} over a channel you trust. It works once and expires in 72 hours. It won&apos;t be
            shown again.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <Input readOnly value={url} className="font-mono text-xs" data-testid="invite-url" onFocus={(e) => e.target.select()} />
          <Button
            variant="outline"
            size="icon"
            aria-label="Copy link"
            onClick={async () => {
              await navigator.clipboard?.writeText(url);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? <Check /> : <Copy />}
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
