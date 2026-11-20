"use client";

import { ArrowLeft, Check, Copy } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AgentStatus } from "@/components/runs/autotests";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Framework = "playwright" | "pytest" | "custom";

const INSTALL = 'uv tool install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"';
const INSTALL_PIPX = 'pipx install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"';

const FRAMEWORKS: { key: Framework; label: string; detail: string }[] = [
  { key: "playwright", label: "Playwright", detail: "@playwright/test (JS / TS)" },
  { key: "pytest", label: "pytest", detail: "Python, incl. pytest-playwright" },
  { key: "custom", label: "Anything else", detail: "Your own runner or script" },
];

function config(fw: Framework, url: string, projectId: number): string {
  const head = [`url = "${url}"`, `project = ${projectId}`, `framework = "${fw}"`];
  if (fw === "playwright")
    return [
      ...head,
      "# Defaults for Playwright (uncomment to change):",
      '# command = "npx playwright test --reporter=list,json,html"',
      '# report = "reports/results.json"',
    ].join("\n");
  if (fw === "pytest")
    return [
      ...head,
      'command = "uv run pytest --junitxml=reports/junit.xml"   # or "python -m pytest …"',
      '# report = "reports/junit.xml"',
    ].join("\n");
  return [
    ...head,
    'command = "./run-tests.sh"                 # how your tests run',
    'report = "reports/*.xml"                   # the JUnit XML (or Playwright JSON) it writes; may use {job_id}',
    'select = "env"                             # selected tests: read the JSON file in $TESTHARBOR_SELECTION',
    'catalog = "testharbor-catalog.json"        # the list of your tests (format below)',
    '# options = "testharbor-options.json"      # choices people get in TestHarbor (environment, roles, browser…)',
    '# prepare = "./make-testharbor-files.sh"   # runs first, e.g. to write the two files above',
  ].join("\n");
}

const SETUP_EXAMPLE: Record<Framework, string> = {
  playwright: 'setup = ["npm ci", "npx playwright install chromium"]',
  pytest: 'setup = ["uv sync --locked", "uv run playwright install chromium"]   # or pip install -r requirements.txt',
  custom: 'setup = ["uv sync --locked"]   # whatever a fresh clone needs before the tests run',
};

const CATALOG_EXAMPLE = `{"tests": [{
  "key": "tests/checkout.py::test_pay_by_card",
  "title": "Pay by card",
  "path": ["Checkout", "Payments"],
  "description": "", "preconditions": "- Given a cart with one item",
  "steps": [{"action": "When I pay by card", "expected": "Then the order is paid"}],
  "roles": ["Customer"], "tags": ["smoke"], "case_ids": []
}]}`;

const OPTIONS_EXAMPLE = `{"options": [
  {"name": "ENV", "label": "Environment", "type": "choice", "choices": ["dev", "qa"], "default": "dev"},
  {"name": "BROWSER", "label": "Browser", "type": "choice", "choices": ["chromium", "firefox"]},
  {"name": "HEADED", "label": "Show the browser", "type": "bool"}
]}`;

export default function ConnectAutotestsPage() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const [fw, setFw] = useState<Framework>("playwright");
  const [mode, setMode] = useState<"local" | "server">("local");
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const url = origin || "https://testharbor.example.com";

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-3xl gap-6 p-4 sm:p-6">
        <div className="grid gap-1">
          <Link
            href={`/projects/${projectId}/autotests`}
            className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-4" /> Autotests
          </Link>
          <h1 className="text-xl font-semibold">Connect autotests</h1>
          <p className="text-sm text-muted-foreground">
            A small agent, <code>testcli</code>, runs on a machine with your tests: your laptop or a server. It
            picks up the runs people start here, runs the tests and sends the results back. TestHarbor never sends it
            commands, only which tests to run.
          </p>
        </div>

        <AgentStatus projectId={projectId} />

        <div className="grid gap-2">
          <h2 className="text-sm font-medium">Run the tests</h2>
          <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Where the tests run">
            {(
              [
                ["local", "On my computer", "From a folder you choose, as it is: uncommitted changes too"],
                ["server", "On a server", "A git branch you pick when starting a run, freshly pulled"],
              ] as const
            ).map(([key, label, detail]) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={mode === key}
                onClick={() => setMode(key)}
                className={cn(
                  "grid rounded-md border px-3 py-2 text-left text-sm",
                  mode === key ? "border-primary bg-primary/5" : "hover:bg-muted",
                )}
              >
                <span className="font-medium">{label}</span>
                <span className="text-xs text-muted-foreground">{detail}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-2">
          <h2 className="text-sm font-medium">Your tests use</h2>
          <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Test framework">
            {FRAMEWORKS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="radio"
                aria-checked={fw === f.key}
                onClick={() => setFw(f.key)}
                className={cn(
                  "grid rounded-md border px-3 py-2 text-left text-sm",
                  fw === f.key ? "border-primary bg-primary/5" : "hover:bg-muted",
                )}
              >
                <span className="font-medium">{f.label}</span>
                <span className="text-xs text-muted-foreground">{f.detail}</span>
              </button>
            ))}
          </div>
        </div>

        {mode === "local" ? (
          <>
        <Step n={1} title="Install testcli (once per machine)">
          <Code text={INSTALL} />
          <p className="text-xs text-muted-foreground">
            Or <code>{INSTALL_PIPX}</code>. It needs Python 3.11+ and nothing else.
          </p>
        </Step>

        <Step n={2} title="Create an API token">
          <p className="text-sm">
            In{" "}
            <Link href="/settings/tokens" className="text-primary underline">
              API tokens
            </Link>
            . It acts as the user who creates it: for a shared machine, create a separate user (e.g. “QA agent”, role
            Tester) and its token, so it can be revoked on its own.
          </p>
        </Step>

        <Step n={3} title="Set it up in the folder with the tests">
          <Code
            text={[
              `testcli init --project ${projectId} --url ${url}${fw === "custom" ? " --framework custom" : ""}`,
              'echo "TESTHARBOR_TOKEN=th_your_token" >> .env',
            ].join("\n")}
          />
          <p className="text-xs text-muted-foreground">
            <code>init</code> writes <code>testharbor.toml</code> (commit it; no secrets in it):
          </p>
          <Code text={config(fw, url, projectId)} />
          <p className="text-xs text-muted-foreground">
            The token goes into <code>.env</code> (or the environment) only. Make sure <code>.env</code> is in{" "}
            <code>.gitignore</code>: <code>testcli init</code> warns if it isn&apos;t.
          </p>
        </Step>

        <Step n={4} title="Start the agent in that folder">
          <Code text={"testcli agent\n# or from anywhere:  testcli agent --cwd ~/path/to/your/tests"} />
          <p className="text-xs text-muted-foreground">
            It runs the tests from this folder as they are, uncommitted changes included, and shows the folder and
            branch here. Keep it running; after every run it re-reads the list of tests.
          </p>
          <p className="text-xs text-muted-foreground">
            <b>Secrets.</b> If your tests need secrets you get with a script (an MFA code, a vault login, a session
            that expires), put that command into <code>testharbor.toml</code>:{" "}
            <code>secrets = &quot;./get-secrets.sh&quot;</code>. The agent runs it in your terminal when it starts, so
            you can type the code; skip it with <code>testcli agent --no-secrets</code> while they are still valid.
            Runs on a server don&apos;t use it: there the secrets live on the server.
          </p>
        </Step>

          </>
        ) : (
          <>
        <Step n={1} title="Commit testharbor.toml to the test repository">
          <p className="text-sm">
            Run <code>testcli init</code> in the repository (see “On my computer”) and add how to install the tests on
            a clean checkout:
          </p>
          <Code text={SETUP_EXAMPLE[fw]} />
        </Step>

        <Step n={2} title="Give the server access to the repository">
          <p className="text-sm">
            Bitbucket: Repository settings › <b>Access tokens</b> › create one with <i>Repositories: Read</i>. GitHub: a
            fine-grained token with <i>Contents: read</i>. GitLab: a project access token with <i>read_repository</i>.
          </p>
        </Step>

        <Step n={3} title="Settings, in the TestHarbor folder on the server">
          <Code
            text={[
              "make runner-token          # prints a TestHarbor token for the runner (prod: make prod-runner-token)",
              "",
              "# then add to .env:",
              "RUNNER_TOKEN=th_...",
              `RUNNER_PROJECT=${projectId}`,
              "RUNNER_REPO=https://bitbucket.org/your-team/your-tests.git",
              "RUNNER_GIT_TOKEN=<the access token>",
            ].join("\n")}
          />
        </Step>

        <Step n={4} title="The tests' secrets (if they have any)">
          <Code
            text={[
              "mkdir -p runner-secrets",
              "cp ~/your-tests/.env runner-secrets/tests.env          # becomes .env of every checkout",
              "# other secret files go to runner-secrets/files/ at their paths, e.g.",
              "#   runner-secrets/files/config/credentials.ini",
            ].join("\n")}
          />
          <p className="text-xs text-muted-foreground">
            <code>runner-secrets/</code> is git-ignored and mounted read-only into the runner.
          </p>
        </Step>

        <Step n={5} title="Start the runner">
          <Code text={"make runner            # production stack: make prod-runner\ndocker compose logs -f runner"} />
          <p className="text-xs text-muted-foreground">
            It shows up above as <b>Server</b>. Every run fetches the repository, checks the chosen branch out at its
            latest commit, runs <code>setup</code> and the tests, sends the results and removes the checkout.
            Dependencies and browsers are cached between runs.
          </p>
        </Step>

          </>
        )}

        <Step n={6} title="Run tests from TestHarbor">
          <p className="text-sm">
            Open{" "}
            <Link href={`/projects/${projectId}/autotests`} className="text-primary underline">
              Autotests
            </Link>
            , press <b>Sync autotests</b> once to create cases for the tests (or link them to existing cases), tick the
            tests, choose where to run (and the branch, on a server) and press <b>Run selected</b>.
          </p>
          {fw === "playwright" && (
            <p className="text-xs text-muted-foreground">
              Selected tests run with <code>--grep</code> of their titles. A tag like <code>@C142</code> on a test
              links it to an existing case.
            </p>
          )}
          {fw === "pytest" && (
            <p className="text-xs text-muted-foreground">
              Selected tests run as node ids (<code>tests/test_shop.py::test_pay</code>); parametrized variants are
              results of one case. <code>C142</code> in a test name links it to an existing case.
            </p>
          )}
        </Step>

        {fw === "custom" && (
          <Step n={7} title="What your runner gets and gives">
            <ul className="grid list-disc gap-1 pl-5 text-sm">
              <li>
                <code>$TESTHARBOR_SELECTION</code>: a JSON file{" "}
                <code>{'{"case_ids": [142], "automation_keys": ["…"]}'}</code>; both empty for “run all”.
              </li>
              <li>
                The run options people chose, as environment variables (from <code>options</code>), and{" "}
                <code>TESTHARBOR_JOB_ID</code>, <code>TESTHARBOR_RUN_ID</code>.
              </li>
              <li>
                It writes JUnit XML where <code>report</code> points. A test&apos;s <code>automation_key</code>{" "}
                property (or <code>classname::name</code>) must equal its <code>key</code> in the catalog; a{" "}
                <code>config</code> property (e.g. a role or browser) labels the result.
              </li>
            </ul>
            <p className="text-xs text-muted-foreground">The catalog file:</p>
            <Code text={CATALOG_EXAMPLE} />
            <p className="text-xs text-muted-foreground">The options file (optional):</p>
            <Code text={OPTIONS_EXAMPLE} />
          </Step>
        )}

      </div>
    </main>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="grid min-w-0 gap-2">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">
          {n}
        </span>
        {title}
      </h2>
      <div className="grid min-w-0 gap-2 pl-7">{children}</div>
    </section>
  );
}

function Code({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative min-w-0">
      <pre className="overflow-x-auto rounded-md border bg-muted/50 p-3 pr-10 font-mono text-xs leading-relaxed">{text}</pre>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute top-1.5 right-1.5"
        aria-label="Copy"
        onClick={() => {
          void navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}
