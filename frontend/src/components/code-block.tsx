"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/** A block of code or a command, with a copy button. */
export function CodeBlock({ code, testId }: { code: string; testId?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre
        data-testid={testId}
        className="overflow-x-auto rounded-lg border bg-muted/50 p-4 pr-12 font-mono text-[13px] leading-relaxed break-all whitespace-pre-wrap"
      >
        {code}
      </pre>
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute top-2 right-2"
        aria-label="Copy"
        onClick={async () => {
          await navigator.clipboard?.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}
