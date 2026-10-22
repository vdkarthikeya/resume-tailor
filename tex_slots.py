"""Parse one of the resume .tex files into editable slots and render edits back.

Design rule: the .tex file is never regenerated. We find exact character spans
(bullet text, skill items, coursework list, the project list) and replace only
those spans. Everything else (preamble, macros, headings, dates, spacing) is
copied through byte for byte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PROJECT_SPACER = "\n        \\vspace{2pt}\n\n"


class MarkupError(ValueError):
    pass


# ---------------------------------------------------------------- brace helpers
def match_brace(s: str, i: int) -> int:
    """s[i] must be '{'. Return the index of its matching '}'."""
    if s[i] != "{":
        raise ValueError("match_brace called on non-brace")
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("unbalanced braces")


def read_args(s: str, i: int, n: int) -> tuple[list[str], int]:
    """Read n brace groups starting at/after index i. Returns (args, end_index)."""
    args = []
    for _ in range(n):
        while s[i] in " \t\r\n":
            i += 1
        j = match_brace(s, i)
        args.append(s[i + 1 : j])
        i = j + 1
    return args, i


def plain(s: str) -> str:
    s = re.sub(r"\\href\{[^}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- markup <-> latex
def latex_to_markup(s: str) -> str:
    """LaTeX bullet text -> light markup (**bold**, unicode superscript 2, x)."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s.startswith("\\textbf{", i):
            j = match_brace(s, i + len("\\textbf"))
            out.append("**" + latex_to_markup(s[i + len("\\textbf{") : j]) + "**")
            i = j + 1
        elif s.startswith("\\textsuperscript{2}", i):
            out.append("\u00b2")
            i += len("\\textsuperscript{2}")
        elif s.startswith("$\\times$", i):
            out.append("\u00d7")
            i += len("$\\times$")
        elif s[i] == "\\" and i + 1 < len(s) and s[i + 1] in "%&#$_":
            out.append(s[i + 1])
            i += 2
        elif s[i] in "\\{}$^~":
            raise MarkupError(f"unsupported LaTeX near {s[i:i+24]!r}")
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


_BAD_CHARS = set("\\{}~^`\n\r\t")


def _esc(seg: str) -> str:
    seg = seg.replace("%", "\\%").replace("&", "\\&").replace("#", "\\#")
    seg = seg.replace("_", "\\_").replace("$", "\\$")
    seg = seg.replace("\u00b2", "\\textsuperscript{2}").replace("\u00d7", "$\\times$")
    return seg


def markup_to_latex(m: str) -> str:
    """Light markup -> LaTeX. Rejects anything that is not plain text + **bold**."""
    m = m.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    m = m.strip()
    if not m:
        raise MarkupError("empty text")
    if any(c in _BAD_CHARS for c in m):
        raise MarkupError("contains a character that is not allowed (backslash, braces, ~, ^, backtick, newline)")
    if "\u2014" in m or "\u2013" in m or "--" in m:
        raise MarkupError("contains a dash that reads as AI-written (em dash, en dash, or --)")
    parts = m.split("**")
    if len(parts) % 2 == 0:
        raise MarkupError("unbalanced ** bold markers")
    out = []
    for k, seg in enumerate(parts):
        if k % 2 == 1:
            if not seg.strip():
                raise MarkupError("empty bold span")
            out.append("\\textbf{" + _esc(seg) + "}")
        else:
            out.append(_esc(seg))
    return "".join(out)


def latex_list_to_names(items: list[str]) -> list[str]:
    return [i.replace("\\&", "&") for i in items]


def names_to_latex_list(items: list[str]) -> list[str]:
    return [i.replace("&", "\\&") for i in items]


# ---------------------------------------------------------------- parsed structures
@dataclass
class Bullet:
    start: int
    end: int  # inner span of \resumeItem{ ... }
    latex: str
    markup: str


@dataclass
class Entry:
    id: str
    kind: str  # "exp" | "lead"
    section: str
    company: str
    role: str
    bullets: list[Bullet] = field(default_factory=list)


@dataclass
class SkillLine:
    id: str
    label: str
    start: int
    end: int
    items: list[str]


@dataclass
class Coursework:
    start: int
    end: int
    completed: list[str]  # plain names (& not escaped)
    in_progress: list[str]


@dataclass
class ProjectBlock:
    title: str  # latex form
    url: str
    tech: str  # latex form
    bullets: list[Bullet]
    style: str = "link"  # "link": title is the hyperlink + arrow; "right": plain bold title, GitHub link at the right edge


@dataclass
class ProjectsRegion:
    start: int
    end: int
    projects: list[ProjectBlock]


@dataclass
class Parsed:
    text: str
    entries: list[Entry]
    skills: list[SkillLine]
    coursework: Coursework | None
    projects: ProjectsRegion | None


def _sections(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in re.finditer(r"\\section\{([^}]*)\}", text)]


def _section_at(secs: list[tuple[int, str]], pos: int) -> str:
    name = ""
    for p, n in secs:
        if p <= pos:
            name = n
    return name


def _bullets_in(text: str, lo: int, hi: int) -> list[Bullet]:
    out = []
    for m in re.finditer(r"\\resumeItem\{", text[lo:hi]):
        brace = lo + m.end() - 1
        close = match_brace(text, brace)
        latex = text[brace + 1 : close]
        try:
            markup = latex_to_markup(latex)
        except MarkupError:
            markup = None  # not editable
        out.append(Bullet(brace + 1, close, latex, markup))
    return out


def parse(text: str) -> Parsed:
    doc = text.index("\\begin{document}")
    secs = _sections(text)
    entries: list[Entry] = []

    # experience / leadership headings
    heads = []
    for m in re.finditer(r"\\(resumeCompactHeading|resumeLeadHeading)\b", text[doc:]):
        pos = doc + m.start()
        args, end = read_args(text, doc + m.end(), 4)
        heads.append((pos, end, m.group(1), args))
    for idx, (pos, end, kind, args) in enumerate(heads):
        nxt = heads[idx + 1][0] if idx + 1 < len(heads) else None
        # entry bullets end at the end of its itemize block
        lst_end = text.index("\\resumeItemListEnd", end)
        hi = lst_end
        e = Entry(
            id=f"e{idx}",
            kind="exp" if kind == "resumeCompactHeading" else "lead",
            section=_section_at(secs, pos),
            company=plain(args[0]),
            role=plain(args[1]),
        )
        e.bullets = _bullets_in(text, end, hi)
        entries.append(e)

    # technical skills lines
    skills: list[SkillLine] = []
    sk_start = next((p for p, n in secs if n == "Technical Skills"), None)
    if sk_start is not None:
        sk_end = next((p for p, n in secs if p > sk_start), len(text))
        for m in re.finditer(r"^(?P<ind>\s*)(?:\\small\{\\item\{\s*)?\\textbf\{(?P<label>[^}]+)\}\{: (?P<items>[^\n]*?)\}(?P<tail>[ \t]*(?:\\\\\[2pt\])?)[ \t]*$", text[sk_start:sk_end], re.M):
            start = sk_start + m.start("items")
            end = sk_start + m.end("items")
            items = [i.strip() for i in m.group("items").split(",")]
            skills.append(SkillLine(f"skills:{m.group('label')}", m.group("label"), start, end, items))

    # coursework
    coursework = None
    for b in _bullets_in(text, doc, len(text)):
        if b.latex.startswith("\\textbf{Relevant Coursework:}"):
            rest = b.latex[len("\\textbf{Relevant Coursework:}") :].strip()
            if "\\textit{In progress:}" in rest:
                done_part, prog_part = re.split(r"[;\s]*\\textit\{In progress:\}\s*", rest, maxsplit=1)
                done_part = re.sub(r"[;,\s]*(?:\$\\cdot\$)?\s*$", "", done_part)
            else:
                done_part, prog_part = rest, ""
            split = lambda t: [x.strip().replace("\\&", "&") for x in re.split(r"\s*(?:\$\\cdot\$|,)\s*", t) if x.strip()]
            comp, prog = split(done_part), split(prog_part)
            coursework = Coursework(b.start, b.end, comp, prog)

    # projects region
    projects = None
    ps = next((p for p, n in secs if n == "Projects"), None)
    if ps is not None:
        m = re.search(r"\\resumeSubHeadingListStart", text[ps:])
        lo = ps + m.end()
        hi = text.index("\\resumeSubHeadingListEnd", lo)
        blocks = []
        for hm in re.finditer(r"\\resumeProjectHeading\s*\{", text[lo:hi]):
            brace = lo + hm.end() - 1
            close = match_brace(text, brace)
            head = text[brace + 1 : close]
            m_link = re.search(r"\\uline\{(.*?)\}\}\\lk", head)
            url_m = re.search(r"\\href\{([^}]*)\}", head)
            url = url_m.group(1) if url_m else ""
            if m_link:
                style, title = "link", m_link.group(1)
            else:
                style, title = "right", re.search(r"\\textbf\{([^{}]*)\}", head).group(1)
            tech = re.search(r"\\emph\{([^{}]*)\}", head).group(1)
            lst_end = text.index("\\resumeItemListEnd", close)
            blocks.append(ProjectBlock(title, url, tech, _bullets_in(text, close, lst_end), style))
        projects = ProjectsRegion(lo, hi, blocks)

    return Parsed(text, entries, skills, coursework, projects)


# ---------------------------------------------------------------- rendering
def render_coursework(completed: list[str], in_progress: list[str]) -> str:
    out = "\\textbf{Relevant Coursework:} " + ", ".join(names_to_latex_list(completed))
    if in_progress:
        out += ("; " if completed else "") + "\\textit{In progress:} " + ", ".join(names_to_latex_list(in_progress))
    return out


def render_projects(projs: list[dict]) -> str:
    """projs: [{title, url, tech, bullets_latex:[...]}] -> text for the region."""
    blocks = []
    for p in projs:
        if p.get("style", "link") == "right":
            link = f" \\hfill \\href{{{p['url']}}}{{\\uline{{GitHub}}}}" if p["url"] else ""
            head = f"{{\\textbf{{{p['title']}}} $|$ \\emph{{{p['tech']}}}{link}}}"
        else:
            head = f"{{\\textbf{{\\href{{{p['url']}}}{{\\uline{{{p['title']}}}}}\\lk}} $|$ \\emph{{{p['tech']}}}}}"
        b = (
            "        \\resumeProjectHeading\n"
            f"            {head}\n"
            "        \\resumeItemListStart\n"
        )
        for bl in p["bullets_latex"]:
            b += f"            \\resumeItem{{{bl}}}\n"
        b += "        \\resumeItemListEnd"
        blocks.append(b)
    return "\n\n" + PROJECT_SPACER.join(blocks) + "\n\n    "


def apply_replacements(text: str, reps: list[tuple[int, int, str]]) -> str:
    reps = sorted(reps, key=lambda r: r[0], reverse=True)
    last = len(text) + 1
    for s, e, new in reps:
        if e > last:
            raise ValueError("overlapping replacements")
        text = text[:s] + new + text[e:]
        last = s
    return text
