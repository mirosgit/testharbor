"use client";

import { useQuery } from "@tanstack/react-query";
import { Anchor, Bot, ChevronsUpDown, KeyRound, LogOut, User, Users } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { api } from "@/lib/api";
import { useMe } from "@/lib/me";
import { cn } from "@/lib/utils";

import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

export function AppHeader() {
  const params = useParams<{ projectId?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const projectId = params.projectId ? Number(params.projectId) : undefined;
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const { data: me } = useMe();
  const project = projects?.find((p) => p.id === projectId);

  const tabs = projectId
    ? [
        { href: `/projects/${projectId}/dashboard`, label: "Dashboard" },
        { href: `/projects/${projectId}/cases`, label: "Test cases" },
        { href: `/projects/${projectId}/runs`, label: "Test runs" },
        { href: `/projects/${projectId}/autotests`, label: "Autotests" },
        { href: `/projects/${projectId}/settings`, label: "Settings" },
      ]
    : [];

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-background px-4">
      <Link href="/" className="mr-2 flex shrink-0 items-center gap-1.5 font-semibold" aria-label="TestHarbor">
        <Anchor className="size-5 text-primary" />
        <span className={cn(projectId && "hidden md:inline")}>TestHarbor</span>
      </Link>
      {projectId && (
        <>
          <span className="hidden text-muted-foreground md:inline">/</span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="min-w-0 shrink gap-1 font-medium">
                <span className="max-w-24 truncate sm:max-w-48">{project?.name ?? "…"}</span>
                <ChevronsUpDown className="size-3.5 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="min-w-56">
              {projects?.map((p) => (
                <DropdownMenuItem key={p.id} onSelect={() => router.push(`/projects/${p.id}/cases`)}>
                  {p.name}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => router.push("/")}>All projects</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <nav className="ml-1 flex min-w-0 items-center gap-1 overflow-x-auto [scrollbar-width:none] md:ml-2">
            {tabs.map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className={cn(
                  "rounded-md px-2 py-1.5 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground sm:px-3",
                  pathname.startsWith(t.href) && "bg-muted font-medium text-foreground",
                )}
              >
                {t.label}
              </Link>
            ))}
          </nav>
        </>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2" aria-label="Account menu">
              <span className="flex size-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                {(me?.name ?? "?").slice(0, 1).toUpperCase()}
              </span>
              <span className="hidden max-w-40 truncate sm:inline">{me?.name}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <div className="truncate font-medium">{me?.name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {me?.email} · <span className="capitalize">{me?.role}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => router.push("/settings")}>
              <User /> Profile
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => router.push("/settings/tokens")}>
              <KeyRound /> API tokens
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => router.push("/settings/claude")}>
              <Bot /> Connect Claude
            </DropdownMenuItem>
            {me?.role === "admin" && (
              <DropdownMenuItem onSelect={() => router.push("/settings/users")}>
                <Users /> Users
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={async () => {
                await api.logout();
                window.location.href = "/login";
              }}
            >
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
