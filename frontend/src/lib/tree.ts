import type { Section } from "./types";

export interface SectionNode extends Section {
  children: SectionNode[];
  depth: number;
  /** Cases in this section and all descendants. */
  totalCases: number;
}

export function buildTree(sections: Section[]): SectionNode[] {
  const nodes = new Map<number, SectionNode>();
  for (const s of sections) nodes.set(s.id, { ...s, children: [], depth: 0, totalCases: 0 });
  const roots: SectionNode[] = [];
  for (const n of nodes.values()) {
    const parent = n.parent_id != null ? nodes.get(n.parent_id) : undefined;
    (parent ? parent.children : roots).push(n);
  }
  const sortRec = (list: SectionNode[], depth: number): number => {
    list.sort((a, b) => a.position - b.position || a.id - b.id);
    let sum = 0;
    for (const n of list) {
      n.depth = depth;
      n.totalCases = n.case_count + sortRec(n.children, depth + 1);
      sum += n.totalCases;
    }
    return sum;
  };
  sortRec(roots, 0);
  return roots;
}

/** Depth-first flattening (display order). */
export function flatten(tree: SectionNode[]): SectionNode[] {
  const out: SectionNode[] = [];
  const walk = (list: SectionNode[]) => {
    for (const n of list) {
      out.push(n);
      walk(n.children);
    }
  };
  walk(tree);
  return out;
}

export function sectionPath(sections: Section[], id: number): string {
  const byId = new Map(sections.map((s) => [s.id, s]));
  const parts: string[] = [];
  let cur = byId.get(id);
  while (cur) {
    parts.unshift(cur.name);
    cur = cur.parent_id != null ? byId.get(cur.parent_id) : undefined;
  }
  return parts.join(" › ");
}
