"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Textarea } from "./ui/textarea";

export function Markdown({ children, className }: { children: string; className?: string }) {
  if (!children?.trim()) return null;
  return (
    <div className={cn("markdown text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

export function MarkdownField({
  id,
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <Tabs defaultValue="write" className="gap-1">
      <TabsList className="h-7 self-end">
        <TabsTrigger value="write" className="h-5 px-2 text-xs">
          Write
        </TabsTrigger>
        <TabsTrigger value="preview" className="h-5 px-2 text-xs">
          Preview
        </TabsTrigger>
      </TabsList>
      <TabsContent value="write">
        <Textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="font-mono text-[13px]"
        />
      </TabsContent>
      <TabsContent value="preview">
        <div className="min-h-[72px] rounded-md border px-3 py-2">
          {value.trim() ? (
            <Markdown>{value}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing to preview</p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
