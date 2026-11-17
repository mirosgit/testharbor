import { AppHeader } from "@/components/app-header";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col">
      <AppHeader />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
