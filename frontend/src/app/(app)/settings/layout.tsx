"use client";

import { Bot, KeyRound, User, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useIsAdmin } from "@/lib/me";
import { cn } from "@/lib/utils";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAdmin = useIsAdmin();
  const items = [
    { href: "/settings", label: "Profile", icon: User },
    { href: "/settings/tokens", label: "API tokens", icon: KeyRound },
    { href: "/settings/claude", label: "Claude", icon: Bot },
    ...(isAdmin ? [{ href: "/settings/users", label: "Users", icon: Users }] : []),
  ];
  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-5xl gap-8 p-8 md:grid-cols-[180px_1fr]">
        <nav className="grid content-start gap-1" aria-label="Settings">
          <h1 className="mb-3 text-2xl font-semibold">Settings</h1>
          {items.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                pathname === href && "bg-muted font-medium text-foreground",
              )}
            >
              <Icon className="size-4" /> {label}
            </Link>
          ))}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </main>
  );
}
