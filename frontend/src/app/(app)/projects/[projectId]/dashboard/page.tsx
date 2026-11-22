"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Minus,
  Play,
  RefreshCw,
  Shuffle,
  Table2,
  BarChart3,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, type ReactNode } from "react";

import { CatalogSyncDialog, useCatalog } from "@/components/cases/catalog-sync";
import {
  fmt,
  Legend,
  Meter,
  Panel,
  pct,
  SegmentBar,
  Sparkline,
  StackedColumns,
  type Part,
  type Series,
} from "@/components/dashboard/charts";
import { timeAgo } from "@/components/runs/run-meta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { priorityLabel } from "@/lib/labels";
import type { Dashboard, DashboardCaseRow, DashboardDay, DashboardRun } from "@/lib/types";
import { cn } from "@/lib/utils";

const PERIODS = [7, 30, 90] as const;

const DAY_SERIES: Series<DashboardDay>[] = [
  { key: "passed", label: "Passed", color: "bg-status-passed" },
  { key: "failed", label: "Failed", color: "bg-status-failed" },
  { key: "blocked", label: "Blocked", color: "bg-status-blocked" },
  { key: "retest", label: "Retest", color: "bg-status-retest" },
  { key: "skipped", label: "Skipped", color: "bg-status-skipped" },
];
const RUN_SERIES: Series<DashboardRun>[] = [...(DAY_SERIES as unknown as Series<DashboardRun>[]),
  { key: "untested", label: "Untested", color: "bg-status-untested" }];

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardView />
    </Suspense>
  );
}

function DashboardView() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const days = PERIODS.find((p) => p === Number(search.get("days"))) ?? 30;
  const q = useQuery({
    queryKey: ["dashboard", projectId, days],
    queryFn: () => api.dashboard(projectId, days),
    placeholderData: (prev) => prev,
    refetchInterval: 60_000,
  });
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const project = projects?.find((p) => p.id === projectId);
  const d = q.data;

  const setDays = (n: number) => router.replace(n === 30 ? pathname : `${pathname}?days=${n}`, { scroll: false });

  return (
    <main className="h-full overflow-y-auto bg-muted/30">
      <div className="mx-auto grid max-w-7xl gap-4 p-4 sm:gap-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">Dashboard</h1>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              {project?.name ?? "…"}
              {d && <> · updated {timeAgo(d.generated_at)}</>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div role="radiogroup" aria-label="Period" className="inline-flex rounded-lg border bg-card p-0.5 shadow-xs">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={p === days}
                  onClick={() => setDays(p)}
                  className={cn(
                    "rounded-md px-3 py-1 text-sm transition-colors",
                    p === days ? "bg-primary text-primary-foreground shadow-xs" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {p} days
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Refresh"
              onClick={() => qc.invalidateQueries({ queryKey: ["dashboard", projectId] })}
            >
              <RefreshCw className={cn(q.isFetching && "animate-spin")} />
            </Button>
          </div>
        </div>

        {q.isError && !d ? (
          <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
            Couldn&apos;t load the dashboard. <Button variant="link" onClick={() => q.refetch()}>Try again</Button>
          </div>
        ) : !d ? (
          <Loading />
        ) : (
          <Content d={d} projectId={projectId} />
        )}
      </div>
    </main>
  );
}

function Loading() {
  return (
    <div className="grid gap-4 sm:gap-5" aria-busy>
      <div className="grid gap-4 sm:grid-cols-2 sm:gap-5 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-40 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-3">
        <Skeleton className="h-80 rounded-xl lg:col-span-2" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  );
}

function Content({ d, projectId }: { d: Dashboard; projectId: number }) {
  const base = `/projects/${projectId}`;
  const mainSuite = d.suites[0]?.id;
  const casesLink = (params: Record<string, string>, suite = mainSuite) =>
    `${base}/cases?${new URLSearchParams({ ...(suite ? { suite: String(suite) } : {}), ...params })}`;
  const caseLink = (c: { id: number; suite_id: number }) => `${base}/cases?suite=${c.suite_id}&case=${c.id}`;

  const cov = d.coverage;
  const automation: Part[] = [
    { key: "automated", label: "Automated", value: cov.automated, color: "bg-chart-automated",
      href: casesLink({ automation_status: "automated" }) },
    { key: "planned", label: "To be automated", value: cov.to_be_automated, color: "bg-chart-planned",
      href: casesLink({ automation_status: "to_be_automated" }) },
    { key: "manual", label: "Manual", value: cov.manual, color: "bg-chart-manual",
      note: cov.cannot_be_automated ? `${fmt(cov.cannot_be_automated)} can't be automated` : undefined,
      href: casesLink({ automation_status: "manual" }) },
  ];
  const states: Part[] = [
    { key: "active", label: "Active", value: d.states.active, color: "bg-chart-active", href: casesLink({ state: "active" }) },
    { key: "pending_review", label: "Pending review", value: d.states.pending_review, color: "bg-chart-review",
      href: casesLink({ state: "pending_review" }, d.review.suite_id ?? mainSuite) },
    { key: "draft", label: "Draft", value: d.states.draft, color: "bg-chart-draft", href: casesLink({ state: "draft" }) },
    { key: "outdated", label: "Outdated", value: d.states.outdated, color: "bg-chart-outdated",
      href: casesLink({ state: "outdated" }) },
    { key: "rejected", label: "Rejected", value: d.states.rejected, color: "bg-chart-rejected",
      href: casesLink({ state: "rejected" }) },
  ];

  return (
    <div className="grid gap-4 sm:gap-5">
      {/* --- Headline numbers --- */}
      <div className="grid gap-4 sm:grid-cols-2 sm:gap-5 xl:grid-cols-4">
        <CoverageTile d={d} parts={automation} />
        <ReviewTile d={d} link={(suite) => casesLink({ state: "pending_review" }, suite)} />
        <PassRateTile d={d} />
        <AutotestsTile d={d} projectId={projectId} />
      </div>

      {/* --- Results and the case mix --- */}
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-3">
        <ResultsPanel d={d} projectId={projectId} className="lg:col-span-2" />
        <Panel title="Cases" hint={`${fmt(d.cases_total)} in the project · ${fmt(cov.live)} live`}>
          <div className="grid gap-5">
            <div className="grid gap-2">
              <div className="flex items-baseline justify-between text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Automation</span>
                <span>live cases</span>
              </div>
              <SegmentBar parts={automation} label="Live cases by automation status" />
              <Legend parts={automation} />
            </div>
            <div className="grid gap-2">
              <div className="flex items-baseline justify-between text-xs text-muted-foreground">
                <span className="font-medium text-foreground">State</span>
                <span>all cases</span>
              </div>
              <SegmentBar parts={states} label="Cases by state" />
              <Legend parts={states} />
            </div>
          </div>
        </Panel>
      </div>

      {/* --- Where coverage is --- */}
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-3">
        <AreasPanel d={d} base={base} className="lg:col-span-2" />
        <PriorityPanel d={d} casesLink={casesLink} />
      </div>

      {/* --- What needs attention --- */}
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-3">
        <CaseList
          title="Failing most"
          hint={`Most failed results in ${d.days} days`}
          icon={<AlertTriangle className="size-4 text-status-failed" />}
          rows={d.failing}
          link={caseLink}
          empty="No failures in this period."
          value={(r) => `${r.count} of ${r.results} failed`}
          meter={(r) => [r.count, r.results]}
          meterColor="bg-status-failed"
          testId="dash-failing"
        />
        <CaseList
          title="Flaky"
          hint="Passed and failed in turns"
          icon={<Shuffle className="size-4 text-status-skipped" />}
          rows={d.flaky}
          link={caseLink}
          empty="Nothing flips between passed and failed."
          value={(r) => `${r.count} flips in ${r.results}`}
          meter={(r) => [r.count, Math.max(1, r.results - 1)]}
          meterColor="bg-status-skipped"
          testId="dash-flaky"
        />
        <RunsPanel d={d} base={base} />
      </div>
    </div>
  );
}

// --- Tiles ---------------------------------------------------------------------------------

function Tile({
  icon,
  label,
  children,
  footer,
  testId,
  tone,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
  footer?: ReactNode;
  testId: string;
  tone?: string;
}) {
  return (
    <section
      className="relative flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card p-4 shadow-xs sm:p-5"
      data-testid={testId}
      aria-label={label}
    >
      <div className={cn("absolute inset-x-0 top-0 h-0.5", tone)} />
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="flex size-7 items-center justify-center rounded-md bg-muted text-foreground">{icon}</span>
        {label}
      </div>
      <div className="mt-3 flex-1">{children}</div>
      {footer && <div className="mt-3 border-t pt-3 text-xs text-muted-foreground">{footer}</div>}
    </section>
  );
}

function Big({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-3xl font-semibold tracking-tight">{children}</span>
      {sub && <span className="text-sm text-muted-foreground">{sub}</span>}
    </div>
  );
}

function CoverageTile({ d, parts }: { d: Dashboard; parts: Part[] }) {
  const c = d.coverage;
  return (
    <Tile
      icon={<Gauge className="size-4" />}
      label="Automation coverage"
      testId="dash-coverage"
      tone="bg-chart-automated"
      footer={
        c.live ? (
          <>
            {pct(c.automatable_percent, 1)} of what can be automated
            {c.to_be_automated > 0 && <> · {fmt(c.to_be_automated)} planned</>}
          </>
        ) : (
          "No live cases yet"
        )
      }
    >
      <Big sub={c.live ? `${fmt(c.automated)} of ${fmt(c.live)} cases` : undefined}>{pct(c.percent, 1)}</Big>
      <SegmentBar parts={parts} className="mt-3 h-2" label="Automation coverage" />
    </Tile>
  );
}

function ReviewTile({ d, link }: { d: Dashboard; link: (suite: number) => string }) {
  const r = d.review;
  const where = d.suites.filter((s) => s.pending_review > 0).sort((a, b) => b.pending_review - a.pending_review);
  return (
    <Tile
      icon={<ClipboardCheck className="size-4" />}
      label="Pending review"
      testId="dash-review"
      tone={r.count ? "bg-chart-review" : "bg-status-passed"}
      footer={
        r.count ? (
          where.length > 1 ? (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>Review in</span>
              {where.map((s) => (
                <Link key={s.id} href={link(s.id)} className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                  {s.name} <span className="tabular-nums text-muted-foreground">{fmt(s.pending_review)}</span>
                </Link>
              ))}
            </span>
          ) : (
            <Link href={link(where[0]?.id ?? r.suite_id ?? 0)} className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
              Review cases <ArrowRight className="size-3.5" />
            </Link>
          )
        ) : (
          "Every case has been reviewed"
        )
      }
    >
      {r.count ? (
        <Big sub={r.oldest_at ? `oldest ${timeAgo(r.oldest_at)}` : undefined}>{fmt(r.count)}</Big>
      ) : (
        <div className="flex items-center gap-2 text-status-passed">
          <CheckCircle2 className="size-7" />
          <span className="text-lg font-semibold text-foreground">All clear</span>
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        {r.count
          ? "New and changed autotest cases wait for a person to check their text."
          : "New and changed autotest cases will show up here."}
      </p>
    </Tile>
  );
}

function PassRateTile({ d }: { d: Dashboard }) {
  const r = d.results;
  const delta = r.pass_rate != null && r.previous_pass_rate != null ? r.pass_rate - r.previous_pass_rate : null;
  const daily = r.days.map((x) => {
    const ex = x.passed + x.failed + x.blocked + x.retest;
    return ex ? (100 * x.passed) / ex : null;
  });
  return (
    <Tile
      icon={<CheckCircle2 className="size-4" />}
      label="Pass rate"
      testId="dash-pass-rate"
      tone="bg-status-passed"
      footer={
        r.executed ? (
          <>
            {fmt(r.executed)} results · {fmt(r.tested_cases)} cases · {fmt(d.runs_in_period)} runs
          </>
        ) : (
          `No results in ${d.days} days`
        )
      }
    >
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <Big>{pct(r.pass_rate, 1)}</Big>
          <Delta value={delta} days={d.days} />
        </div>
        <Sparkline values={daily} className="h-10 w-24 shrink-0" />
      </div>
    </Tile>
  );
}

function Delta({ value, days }: { value: number | null; days: number }) {
  if (value == null) return <p className="mt-1 text-xs text-muted-foreground">No earlier {days} days to compare</p>;
  const flat = Math.abs(value) < 0.05;
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <p className="mt-1 flex items-center gap-1 text-xs">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium",
          flat
            ? "bg-muted text-muted-foreground"
            : value > 0
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
              : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
        )}
      >
        <Icon className="size-3" />
        {flat ? "no change" : `${value > 0 ? "+" : ""}${value.toFixed(1)} pts`}
      </span>
      <span className="text-muted-foreground">vs previous {days} days</span>
    </p>
  );
}

function AutotestsTile({ d, projectId }: { d: Dashboard; projectId: number }) {
  const { data: catalog } = useCatalog(projectId);
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const a = d.automation;
  const toSync = catalog ? catalog.counts.create + catalog.counts.update + catalog.counts.link + catalog.counts.outdated : 0;
  const online = a.agents_online > 0;
  return (
    <Tile
      icon={<Bot className="size-4" />}
      label="Autotests"
      testId="dash-autotests"
      tone={online ? "bg-status-passed" : "bg-chart-manual"}
      footer={
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", online ? "bg-status-passed" : "bg-status-untested")} />
            {a.agents ? `${a.agents_online} of ${a.agents} agents online` : "No agent connected yet"}
          </span>
          <Link href={`/projects/${projectId}/autotests`} className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
            <Play className="size-3" /> Run
          </Link>
        </span>
      }
    >
      <Big sub={catalog ? `of ${fmt(catalog.items.length)} tests in the catalog` : "cases follow a test"}>
        {fmt(a.catalog_managed)}
      </Big>
      <div className="mt-2 text-xs">
        {!catalog ? (
          <span className="text-muted-foreground">No catalog yet: start the agent with --catalog.</span>
        ) : toSync ? (
          <button type="button" onClick={() => setOpen(true)}
                  className="inline-flex items-center gap-1 rounded-full bg-chart-review/15 px-2 py-0.5 font-medium text-foreground hover:bg-chart-review/25">
            <span className="size-1.5 rounded-full bg-chart-review" />
            {fmt(toSync)} to sync · Review
          </button>
        ) : (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <CheckCircle2 className="size-3.5 text-status-passed" /> Catalog in sync
            {catalog.uploaded_at && <> · {timeAgo(catalog.uploaded_at)}</>}
          </span>
        )}
      </div>
      <CatalogSyncDialog
        open={open}
        onOpenChange={setOpen}
        projectId={projectId}
        onApplied={() => qc.invalidateQueries({ queryKey: ["dashboard", projectId] })}
      />
    </Tile>
  );
}

// --- Panels --------------------------------------------------------------------------------

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function ResultsPanel({ d, projectId, className }: { d: Dashboard; projectId: number; className?: string }) {
  const [table, setTable] = useState(false);
  const days = d.results.days;
  const every = days.length > 60 ? 15 : days.length > 20 ? 7 : 1;
  return (
    <Panel
      title="Results per day"
      hint={`Every result recorded in the last ${d.days} days, manual and automated`}
      className={className}
      data-testid="dash-results"
      action={
        <Button variant="ghost" size="xs" onClick={() => setTable((t) => !t)} aria-pressed={table}>
          {table ? <BarChart3 /> : <Table2 />}
          {table ? "Chart" : "Table"}
        </Button>
      }
    >
      {table ? (
        <div className="max-h-72 overflow-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Day</th>
                {DAY_SERIES.map((s) => (
                  <th key={s.key} className="px-3 py-1.5 text-right font-medium">{s.label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {[...days].reverse().map((x) => (
                <tr key={x.date} className="border-t">
                  <td className="px-3 py-1.5 whitespace-nowrap">{shortDate(x.date)}</td>
                  {DAY_SERIES.map((s) => (
                    <td key={s.key} className={cn("px-3 py-1.5 text-right", !x[s.key] && "text-muted-foreground")}>
                      {fmt(Number(x[s.key]))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <StackedColumns
          items={days}
          series={DAY_SERIES}
          label={`Results per day over the last ${d.days} days`}
          title={(x) => new Date(`${x.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
          tickLabel={(x, i) => ((days.length - 1 - i) % every === 0 ? shortDate(x.date) : null)}
          height={300}
          empty={
            <span>
              No results yet.{" "}
              <Link href={`/projects/${projectId}/autotests`} className="text-primary hover:underline">Run autotests</Link>{" "}
              or <Link href={`/projects/${projectId}/runs`} className="text-primary hover:underline">start a run</Link>.
            </span>
          }
        />
      )}
    </Panel>
  );
}

function AreasPanel({ d, base, className }: { d: Dashboard; base: string; className?: string }) {
  const [order, setOrder] = useState<"size" | "lowest">("size");
  const [all, setAll] = useState(false);
  const rows = useMemo(() => {
    const r = [...d.areas];
    if (order === "lowest") {
      r.sort((a, b) => a.automated / a.total - b.automated / b.total || b.total - a.total);
    }
    return r;
  }, [d.areas, order]);
  const shown = all ? rows : rows.slice(0, 8);
  const multiSuite = new Set(d.areas.map((a) => a.suite_id)).size > 1;
  return (
    <Panel
      title="Coverage by area"
      hint="Top-level sections with everything under them"
      className={className}
      data-testid="dash-areas"
      action={
        d.areas.length > 1 && (
          <div role="radiogroup" aria-label="Order" className="inline-flex rounded-md bg-muted p-0.5 text-xs">
            {([["size", "Largest"], ["lowest", "Least covered"]] as const).map(([k, l]) => (
              <button key={k} type="button" role="radio" aria-checked={order === k} onClick={() => setOrder(k)}
                      className={cn("rounded px-2 py-0.5 transition-colors",
                        order === k ? "bg-card font-medium shadow-xs" : "text-muted-foreground hover:text-foreground")}>
                {l}
              </button>
            ))}
          </div>
        )
      }
    >
      {d.areas.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">No cases yet.</p>
      ) : (
        <>
          <ul className="grid gap-1">
            {shown.map((a) => {
              const p = a.total ? (100 * a.automated) / a.total : 0;
              return (
                <li key={a.section_id}>
                  <Link
                    href={`${base}/cases?suite=${a.suite_id}&section=${a.section_id}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 rounded-md px-2 py-1.5 transition-colors hover:bg-muted sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_7rem]"
                  >
                    <span className="min-w-0 truncate text-sm">
                      {a.name}
                      {multiSuite && <span className="ml-1.5 text-xs text-muted-foreground">{a.suite}</span>}
                    </span>
                    <Meter value={a.automated} max={a.total} label={`${a.name}: ${pct(p)} automated`}
                           className="col-span-2 row-start-2 sm:col-span-1 sm:row-start-auto" />
                    <span className="text-right text-xs tabular-nums text-muted-foreground">
                      <span className="font-medium text-foreground">{pct(p)}</span> · {fmt(a.automated)}/{fmt(a.total)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          {rows.length > 8 && (
            <Button variant="ghost" size="sm" className="mt-2 self-start" onClick={() => setAll((x) => !x)}>
              {all ? "Show fewer" : `Show all ${rows.length}`}
            </Button>
          )}
        </>
      )}
    </Panel>
  );
}

function PriorityPanel({ d, casesLink }: { d: Dashboard; casesLink: (p: Record<string, string>) => string }) {
  const risky = d.priorities
    .filter((p) => p.priority === "critical" || p.priority === "high")
    .reduce((n, p) => n + p.total - p.automated, 0);
  return (
    <Panel title="Coverage by priority" hint="Automated share of live cases" data-testid="dash-priority">
      <ul className="grid gap-3">
        {d.priorities.map((p) => {
          const share = p.total ? (100 * p.automated) / p.total : 0;
          return (
            <li key={p.priority}>
              <Link href={casesLink({ priority: p.priority })} className="-mx-2 grid gap-1.5 rounded-md px-2 py-1 hover:bg-muted">
                <span className="flex items-baseline justify-between text-sm">
                  <span>{priorityLabel[p.priority]}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    <span className="font-medium text-foreground">{p.total ? pct(share) : "—"}</span> · {fmt(p.automated)}/{fmt(p.total)}
                  </span>
                </span>
                <Meter value={p.automated} max={p.total} label={`${priorityLabel[p.priority]}: ${pct(share)} automated`} />
              </Link>
            </li>
          );
        })}
      </ul>
      {risky > 0 && (
        <Link
          href={casesLink({ priority: "critical,high", automation_status: "manual,to_be_automated" })}
          className="mt-4 flex items-start gap-2 rounded-lg border border-chart-review/40 bg-chart-review/10 p-3 text-sm hover:bg-chart-review/15"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-chart-review" />
          <span>
            <b className="tabular-nums">{fmt(risky)}</b> critical and high cases aren&apos;t automated yet.
            <span className="ml-1 text-primary">Show them</span>
          </span>
        </Link>
      )}
    </Panel>
  );
}

function CaseList({
  title,
  hint,
  icon,
  rows,
  link,
  empty,
  value,
  meter,
  meterColor,
  testId,
}: {
  title: string;
  hint: string;
  icon: ReactNode;
  rows: DashboardCaseRow[];
  link: (r: DashboardCaseRow) => string;
  empty: string;
  value: (r: DashboardCaseRow) => string;
  meter: (r: DashboardCaseRow) => [number, number];
  meterColor: string;
  testId: string;
}) {
  return (
    <Panel title={title} hint={hint} action={icon} data-testid={testId}>
      {rows.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-center text-sm text-muted-foreground">
          <CheckCircle2 className="size-6 text-status-passed" />
          {empty}
        </div>
      ) : (
        <ol className="-mx-2 grid gap-0.5">
          {rows.map((r) => {
            const [v, max] = meter(r);
            return (
              <li key={r.id}>
                <Link href={link(r)} className="grid gap-1 rounded-md px-2 py-1.5 transition-colors hover:bg-muted">
                  <span className="flex min-w-0 items-baseline gap-2 text-sm">
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">C{r.id}</span>
                    <span className="min-w-0 flex-1 truncate">{r.title}</span>
                    {r.automated && <Bot className="size-3.5 shrink-0 self-center text-muted-foreground" aria-label="Automated" />}
                  </span>
                  <span className="flex items-center gap-2">
                    <Meter value={v} max={max} color={meterColor} className="h-1.5 flex-1" />
                    <span className="w-24 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{value(r)}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

function RunsPanel({ d, base }: { d: Dashboard; base: string }) {
  const latest = [...d.runs].reverse().slice(0, 4);
  return (
    <Panel
      title="Recent runs"
      hint={d.runs.length ? `Last ${d.runs.length}, share of each status` : "No runs yet"}
      data-testid="dash-runs"
      action={
        <Link href={`${base}/runs`} className="text-xs font-medium text-primary hover:underline">
          All runs
        </Link>
      }
    >
      {d.runs.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Runs will show up here.</p>
      ) : (
        <>
          <StackedColumns
            items={d.runs}
            series={RUN_SERIES}
            normalize
            label="Recent runs by status"
            title={(r) => `${r.name} · ${new Date(r.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}
            href={(r) => `${base}/runs/${r.id}`}
            height={120}
          />
          <ul className="-mx-2 mt-3 grid gap-0.5 border-t pt-2">
            {latest.map((r) => {
              const done = r.total - r.untested;
              return (
                <li key={r.id}>
                  <Link href={`${base}/runs/${r.id}`} className="grid gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-muted">
                    <span className="flex min-w-0 items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate">{r.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{timeAgo(r.created_at)}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <SegmentBar
                        className="h-1.5 flex-1"
                        label={`${r.name}: ${r.passed} passed of ${r.total}`}
                        parts={RUN_SERIES.map((s) => ({ key: s.key, label: s.label, value: Number(r[s.key]) || 0, color: s.color }))}
                      />
                      <span className="w-20 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                        {r.total ? `${pct((100 * r.passed) / r.total)} passed` : "empty"}
                        {done < r.total && r.total > 0 && <span className="sr-only">, {r.untested} untested</span>}
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Panel>
  );
}
