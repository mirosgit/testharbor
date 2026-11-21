"""A test's case text (description, preconditions, steps, expected result) from what its code says.

Nothing is invented: every field comes from something a person wrote in the tests.

* A docstring or the comment above a test. Plain text is the description; these sections fill the
  other fields (headers are case-insensitive, the colon is required):

      Applies a discount code at checkout.

      Preconditions:
      - A cart with one product
      Steps:
      1. Open the cart -> The total is shown
      2. Enter SAVE10 and apply it
         Expected: the total drops by 10%
      Expected result:
      The order total includes the discount.

  Given / When / Then lines in a docstring work too (see Gherkin below).
* Gherkin (pytest-bdd scenarios, or Given/When/Then lines): Given lines are the preconditions,
  every When starts a step, Then lines are the expected result of the step before them.
* Playwright: `test.step('…')` titles are the steps ("Apply the code -> The total drops" splits into
  action and expected; a `// Expected: …` comment in a step is its expected result), and annotations
  `{ type: 'description' | 'precondition' | 'expected' | 'issue', description: '…' }` fill fields.

A test that says nothing about itself gets a description pointing to its source, so a reviewer
knows where to look.
"""

from __future__ import annotations

import re
from typing import Any

# --- Docstrings and comments ----------------------------------------------------------------

_SECTION = re.compile(
    r"^(?P<name>pre-?conditions?|setup|steps?|expected(?:[ _]results?)?|expected outcome)\s*:\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(?P<text>.*)$")
_EXPECTED_LINE = re.compile(r"^\s*(?:expected(?:[ _]result)?|->|=>|→)\s*:?\s*(?P<text>.+)$", re.IGNORECASE)
_ARROW = re.compile(r"\s+(?:->|=>|→)\s+")
GHERKIN_KINDS = ("Given", "When", "Then")
_GHERKIN = re.compile(r"^\s*(?P<word>Given|When|Then|And|But|\*)\s+(?P<text>.+)$")


def _section_of(name: str) -> str:
    name = name.lower()
    if name.startswith(("pre", "setup")):
        return "preconditions"
    if name.startswith("step"):
        return "steps"
    return "expected_result"


def split_step(text: str) -> dict[str, str]:
    """"Do this -> See that" as a step; text without an arrow is all action."""
    parts = _ARROW.split(text.strip(), maxsplit=1)
    return {"action": parts[0].strip(), "expected": parts[1].strip() if len(parts) > 1 else ""}


def _parse_steps(lines: list[str]) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for line in lines:
        if not line.strip():
            continue
        item = _ITEM.match(line)
        expected = _EXPECTED_LINE.match(line)
        if item:
            steps.append(split_step(item.group("text")))
        elif expected and steps:
            text = expected.group("text").strip()
            steps[-1]["expected"] = f"{steps[-1]['expected']}\n{text}".strip()
        elif steps:  # a continuation of the step
            key = "expected" if steps[-1]["expected"] else "action"
            steps[-1][key] = f"{steps[-1][key]}\n{line.strip()}"
        else:
            steps.append(split_step(line))
    return steps


def gherkin_case(steps: list[tuple[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Gherkin (keyword, text) steps as preconditions and steps. And / But / * take the kind of the
    step before them; a Then without a When before it is a step with an empty action."""
    preconditions: list[str] = []
    result: list[dict[str, list[str]]] = []
    kind = "Given"
    for keyword, text in steps:
        word = keyword.strip()
        if word in GHERKIN_KINDS:
            kind = word
        line = f"{word} {text.strip()}".strip()
        if kind == "Given":
            preconditions.append(f"- {line}")
        elif kind == "When":
            if word == "When" or not result or result[-1]["expected"]:
                result.append({"action": [], "expected": []})
            result[-1]["action"].append(line)
        else:
            if not result:
                result.append({"action": [], "expected": []})
            result[-1]["expected"].append(line)
    return "\n".join(preconditions), [
        {"action": "\n".join(s["action"]), "expected": "\n".join(s["expected"])} for s in result
    ]


def _gherkin_lines(lines: list[str]) -> list[tuple[str, str]] | None:
    """Given / When / Then lines of a text, if it has a When or a Then (else it's just prose)."""
    found = [(m.group("word"), m.group("text")) for line in lines if (m := _GHERKIN.match(line))]
    return found if any(w in ("When", "Then") for w, _ in found) else None


def _clean_block(lines: list[str]) -> str:
    text = "\n".join(lines).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_doc(text: str) -> dict[str, Any]:
    """The case fields a docstring or comment states; only the fields it has."""
    lines = [line.rstrip() for line in (text or "").strip().splitlines()]
    if not lines:
        return {}
    blocks: dict[str, list[str]] = {"description": []}
    current = "description"
    for line in lines:
        m = _SECTION.match(line)
        # "Expected: …" right under a step is that step's expected result, not a section.
        if m and current == "steps" and m.group("name").lower() == "expected" and m.group("rest").strip():
            m = None
        if m:
            current = _section_of(m.group("name"))
            blocks.setdefault(current, [])
            if m.group("rest").strip():
                blocks[current].append(m.group("rest"))
        else:
            blocks.setdefault(current, []).append(line)

    out: dict[str, Any] = {}
    prose = blocks["description"]
    if "steps" not in blocks and (gherkin := _gherkin_lines(prose)):
        preconditions, steps = gherkin_case(gherkin)
        prose = [line for line in prose if not _GHERKIN.match(line)]
        if preconditions and "preconditions" not in blocks:
            out["preconditions"] = preconditions
        out["steps"] = steps
    if description := _clean_block([line.strip() for line in prose]):
        out["description"] = description
    if "preconditions" in blocks and (pre := _clean_block([line.strip() for line in blocks["preconditions"]])):
        out["preconditions"] = pre
    if "steps" in blocks and (steps := _parse_steps(blocks["steps"])):
        out["steps"] = steps
    if "expected_result" in blocks and (exp := _clean_block([line.strip() for line in blocks["expected_result"]])):
        out["expected_result"] = exp
    return out


def title_and_doc(doc: str, max_title: int = 150) -> tuple[str | None, str]:
    """A docstring's summary line as a title (when it is one short line before a blank line or the end),
    and the rest of the docstring."""
    lines = (doc or "").strip().splitlines()
    if not lines:
        return None, ""
    first = lines[0].strip()
    rest_starts_blank = len(lines) == 1 or not lines[1].strip()
    if not first or len(first) > max_title or _SECTION.match(first) or _GHERKIN.match(first) or not rest_starts_blank:
        return None, doc
    return first.rstrip("."), "\n".join(lines[1:]).strip()


def examples_table(rows: list[dict[str, Any]]) -> str:
    """Rows of a Scenario Outline's Examples as a Markdown table."""
    columns: list[str] = []
    for row in rows:
        columns.extend(c for c in row if c not in columns)
    if not columns:
        return ""

    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(row.get(c, "")) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def source_note(file: str, line: int | None) -> str:
    where = f"{file}:{line}" if line else file
    return f"Automated test in `{where}`. Its code has no description yet."


def finish(entry: dict[str, Any], found: dict[str, Any], file: str, line: int | None) -> dict[str, Any]:
    """`entry` with the fields `found` in the code; a test that says nothing points to its source."""
    for name in ("description", "preconditions", "steps", "expected_result"):
        if found.get(name):
            entry[name] = found[name]
    if not entry.get("description") and file:
        entry["description"] = source_note(file, line)
    return entry


# --- Playwright source ----------------------------------------------------------------------


def _skip_string(src: str, i: int) -> int:
    """The index after the string literal starting at src[i]."""
    quote = src[i]
    i += 1
    while i < len(src):
        ch = src[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        if quote == "`" and src.startswith("${", i):
            i = _match(src, i + 1, "{", "}")
            continue
        if ch == "\n" and quote != "`":
            return i
        i += 1
    return i


def _match(src: str, i: int, open_: str = "(", close: str = ")") -> int:
    """The index after the bracket that closes the one at src[i] (strings and comments skipped)."""
    depth = 0
    while i < len(src):
        ch = src[i]
        if ch in "'\"`":
            i = _skip_string(src, i)
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = len(src) if end == -1 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = len(src) if end == -1 else end + 2
            continue
        if ch == open_:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _offset(src: str, line: int, column: int) -> int:
    lines = src.splitlines(keepends=True)
    return sum(len(x) for x in lines[: max(line - 1, 0)]) + max(column - 1, 0)


def comment_above(src: str, line: int) -> str:
    """The comment right above a line: a /* … */ block or // lines (JSDoc @tags dropped)."""
    lines = src.splitlines()
    i = line - 2  # the line before, 0-based
    while i >= 0 and lines[i].strip().startswith("@"):  # decorators
        i -= 1
    if i < 0:
        return ""
    if lines[i].strip().endswith("*/"):
        end = i
        while i >= 0 and "/*" not in lines[i]:
            i -= 1
        if i < 0:
            return ""
        block = lines[i : end + 1]
        block[0] = block[0].split("/*", 1)[1].lstrip("*")
        block[-1] = block[-1].rsplit("*/", 1)[0]
        text = [re.sub(r"^\s*\*\s?", "", x) for x in block]
    else:
        text = []
        while i >= 0 and lines[i].strip().startswith("//"):
            text.insert(0, re.sub(r"^\s*//+\s?", "", lines[i]))
            i -= 1
    text = [x for x in text if not re.match(r"^\s*@\w", x)]
    return "\n".join(text).strip()


_STEP = re.compile(r"\.step\s*\(\s*(['\"`])")
_COMMENT_EXPECTED = re.compile(r"//\s*expect(?:ed)?(?:[ _]result)?\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def playwright_steps(src: str, line: int, column: int) -> list[dict[str, str]]:
    """The test.step titles of the test called at line:column, in order. Steps nested in a step are
    sub-items of its action."""
    start = _offset(src, line, column)
    paren = src.find("(", start)
    if paren == -1:
        return []
    end = _match(src, paren)
    body = src[paren:end]
    found: list[tuple[int, int, str]] = []  # (start, end, title)
    for m in _STEP.finditer(body):
        title_end = _skip_string(body, m.start(1))
        title = body[m.start(1) + 1 : title_end - 1]
        call_end = _match(body, body.index("(", m.start()))
        found.append((m.start(), call_end, " ".join(re.sub(r"\\(.)", r"\1", title).split())))
    steps: list[dict[str, str]] = []
    outer: tuple[int, int] | None = None
    for s, e, title in found:
        if outer and s < outer[1]:  # inside the step before
            steps[-1]["action"] += f"\n- {title}"
            continue
        outer = (s, e)
        step = split_step(title)
        inner = body[s:e]
        if not step["expected"] and (m := _COMMENT_EXPECTED.search(inner)):
            step["expected"] = m.group(1).strip()
        steps.append(step)
    return steps


_ANNOTATION_FIELDS = {
    "description": "description", "summary": "description",
    "precondition": "preconditions", "preconditions": "preconditions", "setup": "preconditions",
    "expected": "expected_result", "expected result": "expected_result", "expected_result": "expected_result",
}
_ANNOTATION_LINKS = {"issue", "bug", "story", "requirement", "ticket", "link"}


def from_annotations(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, list[str]] = {}
    links: list[str] = []
    seen: set[tuple[str, str]] = set()  # the same test in several projects repeats its annotations
    for a in annotations or []:
        kind = str(a.get("type") or "").strip().lower()
        text = str(a.get("description") or "").strip()
        if not text or (kind, text) in seen:
            continue
        seen.add((kind, text))
        if kind in _ANNOTATION_FIELDS:
            out.setdefault(_ANNOTATION_FIELDS[kind], []).append(text)
        elif kind in _ANNOTATION_LINKS:
            links.append(f"{kind.capitalize()}: {text}")
    fields: dict[str, Any] = {k: "\n\n".join(v) for k, v in out.items()}
    if links:
        fields["links"] = "\n".join(f"- {x}" for x in links)
    return fields


def playwright_found(src: str | None, spec: dict[str, Any], annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything a Playwright test's code says about it: its comment, test.step titles, annotations."""
    found: dict[str, Any] = {}
    line, column = int(spec.get("line") or 0), int(spec.get("column") or 1)
    if src and line:
        found.update(parse_doc(comment_above(src, line)))
        if not found.get("steps") and (steps := playwright_steps(src, line, column)):
            found["steps"] = steps
    notes = from_annotations(annotations)
    for name in ("description", "preconditions", "expected_result"):
        if notes.get(name):
            found[name] = notes[name]
    if notes.get("links"):
        found["description"] = "\n\n".join(x for x in (found.get("description"), notes["links"]) if x)
    return found
