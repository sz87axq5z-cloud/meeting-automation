"""
Claude の要約 Markdown を、共有用の縦スクロール単一ページ HTML に変換する。
PNG レンダラと同じ ## 区切りを解釈（本文は軽量 Markdown 部分対応）。
"""

from __future__ import annotations

import html
import re
from collections import OrderedDict
from typing import Any, Dict, List, Tuple

from app.formatting import format_happened_at_display


def _parse_summary_sections_preserve(raw: str) -> List[Tuple[str | None, str]]:
    """
    `## 見出し` で区切る。本文は ** 等を残す（HTML 変換側で処理）。
    先頭の ## 前は「概要」。
    """
    text = (raw or "").strip()
    if not text:
        return [(None, "（要約なし）")]

    pattern = re.compile(r"(?m)^##\s+(.+?)\s*$")
    if not pattern.search(text):
        return [(None, text)]

    segments = pattern.split(text)
    out: List[Tuple[str | None, str]] = []
    preamble = segments[0].strip()
    if preamble:
        out.append(("概要", preamble))

    rest = segments[1:]
    for i in range(0, len(rest), 2):
        h = rest[i].strip()
        body = rest[i + 1].strip() if i + 1 < len(rest) else ""
        out.append((h or "（無題）", body))

    return out if out else [(None, text)]


def _inline_bold(s: str) -> str:
    """`**太字**` を <strong> に。それ以外はエスケープ。"""
    parts: list[str] = []
    i = 0
    while True:
        j = s.find("**", i)
        if j == -1:
            parts.append(html.escape(s[i:]))
            break
        parts.append(html.escape(s[i:j]))
        k = s.find("**", j + 2)
        if k == -1:
            parts.append(html.escape(s[j:]))
            break
        parts.append("<strong>" + html.escape(s[j + 2 : k]) + "</strong>")
        i = k + 2
    return "".join(parts)


def _body_to_html(body: str, *, ol_extra_class: str = "") -> str:
    """箇条書き `- `・番号付き `1. ` をリスト化。空行で段落区切り。"""
    ol_cls = "body-ol " + ol_extra_class if ol_extra_class else "body-ol"
    ol_cls = " ".join(ol_cls.split())

    lines = body.splitlines()
    chunks: list[str] = []
    ul: list[str] = []
    ol: list[str] = []
    para_buf: list[str] = []

    def flush_para() -> None:
        nonlocal para_buf
        if para_buf:
            t = "\n".join(para_buf).strip()
            if t:
                chunks.append(f'<p class="body-p">{_inline_bold(t)}</p>')
            para_buf = []

    def flush_ul() -> None:
        nonlocal ul
        if ul:
            lis = "".join(f"<li>{_inline_bold(x)}</li>" for x in ul)
            chunks.append(f'<ul class="body-ul">{lis}</ul>')
            ul = []

    def flush_ol() -> None:
        nonlocal ol
        if ol:
            lis = "".join(f"<li>{_inline_bold(x)}</li>" for x in ol)
            chunks.append(f'<ol class="{ol_cls}">{lis}</ol>')
            ol = []

    for line in lines:
        raw = line.rstrip()
        if not raw.strip():
            flush_ul()
            flush_ol()
            flush_para()
            continue
        stripped = raw.strip()
        if stripped.startswith("- "):
            flush_ol()
            flush_para()
            ul.append(stripped[2:].strip())
            continue
        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            flush_ul()
            flush_para()
            ol.append(m.group(1).strip())
            continue
        flush_ul()
        flush_ol()
        para_buf.append(raw)

    flush_ul()
    flush_ol()
    flush_para()
    return "\n".join(chunks)


_MERMAID_BLOCK_RE = re.compile(
    r"```\s*mermaid\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)


def _sanitize_mermaid_code(code: str) -> str | None:
    c = code.strip()
    if not c:
        return None
    low = c.lower()
    if "<script" in low or "</script" in low or "javascript:" in low:
        return None
    return c


def _body_to_html_with_diagrams(body: str) -> str:
    """本文内の ```mermaid ... ``` を HTML 図として差し込み、それ以外は従来どおり。"""
    if not _MERMAID_BLOCK_RE.search(body):
        return _body_to_html(body)
    parts: list[str] = []
    pos = 0
    for m in _MERMAID_BLOCK_RE.finditer(body):
        before = body[pos : m.start()]
        if before.strip():
            parts.append(_body_to_html(before))
        safe = _sanitize_mermaid_code(m.group(1))
        if safe:
            parts.append(
                '<figure class="mermaid-wrap" aria-label="フロー図">'
                f'<div class="mermaid">{safe}</div>'
                "</figure>"
            )
        pos = m.end()
    tail = body[pos:]
    if tail.strip():
        parts.append(_body_to_html(tail))
    return "\n".join(p for p in parts if p)


def _section_icon_svg(heading: str) -> str:
    """見出し語に応じた線画アイコン（28x28）。"""
    h = heading or ""
    if "タスク" in h:
        return (
            '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
            '<path d="M4 6h16M4 12h10M4 18h14" stroke-linecap="round" /></svg>'
        )
    if "課題" in h or "リスク" in h or "懸念" in h:
        return (
            '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
            '<path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" '
            'stroke-linecap="round" stroke-linejoin="round" /></svg>'
        )
    if "決定" in h or "合意" in h:
        return (
            '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
            '<path d="M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z" '
            'stroke-linecap="round" stroke-linejoin="round" /></svg>'
        )
    if "次" in h or "フォロー" in h or "アクション" in h:
        return (
            '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
            '<path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z" stroke-linecap="round" stroke-linejoin="round" /></svg>'
        )
    if "背景" in h or "目的" in h or "なぜ" in h:
        return (
            '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
            '<circle cx="12" cy="12" r="9" /><path d="M12 8v4l3 2" stroke-linecap="round" /></svg>'
        )
    return (
        '<svg class="sec-icon" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />'
        '<path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke-linecap="round" /></svg>'
    )


_TASK_LINE_RE = re.compile(
    r"^\d+\.\s+\*\*(?P<name>[^*]+)\*\*\s*-\s*(?P<rest>.+)$"
)


def _task_section_body_to_html(body: str) -> str:
    """
    `## タスク一覧` 相当の本文。
    `1. **担当** - 内容 - 期限` 形式を担当者ごとにまとめ、1人1ブロックで複数タスクを列挙する。
    パースできた行が1件も無ければ従来の _body_to_html にフォールバック。
    """
    groups: OrderedDict[str, list[str]] = OrderedDict()
    non_matching: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _TASK_LINE_RE.match(stripped)
        if m:
            name = m.group("name").strip()
            rest = m.group("rest").strip()
            groups.setdefault(name, []).append(rest)
        else:
            non_matching.append(line)

    if not groups:
        return _body_to_html_with_diagrams(body)

    chunks: list[str] = []
    if non_matching:
        chunks.append(_body_to_html_with_diagrams("\n".join(non_matching)))

    for assignee, items in groups.items():
        lis = "".join(f"<li>{_inline_bold(t)}</li>" for t in items)
        chunks.append(
            '<div class="task-group">'
            f'<div class="task-assignee">{html.escape(assignee)}</div>'
            f'<ul class="task-group-ul">{lis}</ul>'
            "</div>"
        )
    return "\n".join(chunks)


def extract_task_list_body(raw_markdown: str) -> str:
    """`## タスク一覧` セクションの本文のみ（Markdown）を返す。無ければ空文字。"""
    sections = _parse_summary_sections_preserve(raw_markdown or "")
    for heading, body in sections:
        if heading and "タスク一覧" in heading:
            return (body or "").strip()
    return ""


def build_embedded_task_list_block_html(raw_markdown: str) -> str:
    """
    インフォグラフィック等に埋め込むタスク一覧 HTML（要約 HTML と同型の見た目）。
    スクロール末尾に置く想定。スタイルは .ma-embed-tasklist 配下にスコープする。
    """
    body_md = extract_task_list_body(raw_markdown)
    if not body_md:
        return ""

    body_html = _task_section_body_to_html(body_md)
    icon = _section_icon_svg("タスク一覧").replace('class="sec-icon"', 'class="ma-et-icon"', 1)

    style = """
<style>
.ma-embed-tasklist.section {
  background: #f8f9fa;
  border-top: 1px solid #e2e8f0;
}
.ma-embed-tasklist .ma-et-title {
  font-family: system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-size: 1.38rem;
  font-weight: 700;
  margin: 0 0 1.25rem;
  color: #0d6e7a;
  display: flex;
  align-items: center;
  gap: 0.55rem;
}
.ma-embed-tasklist .ma-et-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  color: #0d6e7a;
}
.ma-embed-tasklist .ma-et-body {
  color: #1a2332;
  line-height: 1.75;
  font-size: 17px;
}
.ma-embed-tasklist .task-group { margin-bottom: 1.35rem; }
.ma-embed-tasklist .task-group:last-child { margin-bottom: 0; }
.ma-embed-tasklist .task-assignee {
  font-weight: 700;
  font-size: 1.08rem;
  color: #0d6e7a;
  margin: 0 0 0.45rem;
  padding-bottom: 0.25rem;
  border-bottom: 2px solid #e6f4f5;
}
.ma-embed-tasklist .task-group-ul {
  margin: 0;
  padding-left: 1.35rem;
  list-style: disc;
}
.ma-embed-tasklist .task-group-ul li { margin-bottom: 0.4rem; }
.ma-embed-tasklist .body-p { margin: 0 0 1rem; }
</style>""".strip()

    return (
        f"{style}\n"
        '<section class="section ma-embed-tasklist visible" data-animate '
        'aria-labelledby="ma-et-h">'
        f'<h2 class="ma-et-title" id="ma-et-h">{icon}タスク一覧</h2>'
        f'<div class="ma-et-body">{body_html}</div>'
        "</section>"
    )


def _pop_overview_sections(
    sections: List[Tuple[str | None, str]],
) -> tuple[str | None, List[Tuple[str | None, str]]]:
    if not sections:
        return None, sections
    h0, b0 = sections[0]
    if h0 == "概要" and (b0 or "").strip():
        return b0, sections[1:]
    return None, sections


def build_summary_html_document(meeting_info: Dict[str, Any], raw_markdown: str) -> str:
    """
    共有用 HTML 全文（UTF-8 でエンコードしてアップロード想定）。
    """
    name = str(meeting_info.get("name") or "会議")
    happened = format_happened_at_display(meeting_info.get("happened_at"))
    participants = meeting_info.get("participants")
    if isinstance(participants, list):
        parts_line = ", ".join(str(p) for p in participants if p)
    else:
        parts_line = ""

    sections = _parse_summary_sections_preserve(raw_markdown)
    overview_body, rest_sections = _pop_overview_sections(sections)

    meta_bits: list[str] = []
    if happened:
        meta_bits.append(html.escape(happened))
    if parts_line:
        meta_bits.append(html.escape(parts_line))
    meta_line = " · ".join(meta_bits)

    if overview_body:
        hero_lead_inner = _body_to_html_with_diagrams(overview_body)
    else:
        hero_lead_inner = (
            '<p class="hero-lead">このページは会議の<strong>要約</strong>です。'
            "各見出しの下に内容を整理しています。</p>"
        )

    section_html: list[str] = []
    for heading, body in rest_sections:
        h = heading or "内容"
        hid = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff-]+", "-", h)[:48].strip("-") or "section"
        icon = _section_icon_svg(h)
        is_task = "タスク" in h
        body_html = (
            _task_section_body_to_html(body)
            if is_task
            else _body_to_html_with_diagrams(body)
        )

        section_html.append(
            f'<section class="content-section" data-animate aria-labelledby="h-{html.escape(hid, quote=True)}">'
            f'<h2 class="section-title" id="h-{html.escape(hid, quote=True)}">{icon}{html.escape(h)}</h2>'
            f'<div class="section-body">{body_html}</div></section>'
        )

    blocks = "\n".join(section_html)

    title = f"{name} — 要約（HTML）"
    meta_para = f'<p class="hero-meta">{meta_line}</p>' if meta_line else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Outfit:wght@500;700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: #f7f9fc;
      --surface: #ffffff;
      --ink: #1a2332;
      --muted: #5a6578;
      --line: #d8dee8;
      --accent: #0d6e7a;
      --accent-soft: #e6f4f5;
      --radius: 14px;
      --shadow: 0 12px 40px rgba(26, 35, 50, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: "Noto Sans JP", system-ui, sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.75;
      font-size: 17px;
    }}
    .progress {{
      position: fixed;
      top: 0;
      left: 0;
      height: 4px;
      background: linear-gradient(90deg, var(--accent), #2a9d8f);
      width: 0%;
      z-index: 100;
      transition: width 0.15s ease-out;
    }}
    header.hero {{
      min-height: 62vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      padding: 3rem 1.5rem 2.5rem;
      background: linear-gradient(165deg, #0f3d45 0%, #0d6e7a 45%, #1a5c66 100%);
      color: #f0fafb;
    }}
    .hero-inner {{ max-width: 720px; margin: 0 auto; width: 100%; }}
    .hero-kicker {{
      font-family: "Outfit", sans-serif;
      font-size: 0.85rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      opacity: 0.85;
      margin-bottom: 1rem;
    }}
    .hero h1 {{
      font-family: "Outfit", sans-serif;
      font-weight: 700;
      font-size: clamp(1.5rem, 4vw, 2.2rem);
      line-height: 1.25;
      margin: 0 0 1rem;
    }}
    .hero-meta {{ font-size: 0.92rem; opacity: 0.88; margin: 0 0 1.25rem; }}
    .hero-lead-wrap .body-p,
    .hero-lead-wrap .body-ul,
    .hero-lead-wrap .body-ol {{
      font-size: 1.05rem;
      opacity: 0.95;
      color: #f0fafb;
    }}
    .hero-lead-wrap .body-p a {{ color: #a5f3fc; }}
    .hero-lead {{ font-size: 1.05rem; opacity: 0.95; margin: 0; }}
    .hero-lead strong {{ color: #fff; font-weight: 700; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 0 1.5rem 4rem; }}
    .content-section {{
      padding: 2.75rem 0;
      border-bottom: 1px solid var(--line);
      opacity: 0;
      transform: translateY(26px);
      transition: opacity 0.65s ease, transform 0.65s ease;
    }}
    .content-section.is-visible {{ opacity: 1; transform: translateY(0); }}
    .content-section:last-of-type {{ border-bottom: none; }}
    .section-title {{
      font-family: "Outfit", sans-serif;
      font-size: 1.38rem;
      margin: 0 0 1rem;
      color: var(--accent);
      display: flex;
      align-items: center;
      gap: 0.55rem;
    }}
    .sec-icon {{ width: 28px; height: 28px; flex-shrink: 0; color: var(--accent); }}
    .section-body .body-p {{ margin: 0 0 1rem; color: var(--ink); }}
    .section-body .body-ul,
    .section-body .body-ol {{ margin: 0 0 1rem; padding-left: 1.35rem; }}
    .section-body li {{ margin-bottom: 0.4rem; }}
    .body-ol-tasks {{ counter-reset: taskstep; list-style: none; padding-left: 0; }}
    .body-ol-tasks li {{
      counter-increment: taskstep;
      position: relative;
      padding-left: 2.35rem;
      margin-bottom: 0.65rem;
      border-left: 3px solid var(--accent-soft);
      padding-top: 0.15rem;
      padding-bottom: 0.15rem;
      padding-right: 0.5rem;
      background: linear-gradient(90deg, var(--accent-soft), transparent);
      border-radius: 0 8px 8px 0;
    }}
    .body-ol-tasks li::before {{
      content: counter(taskstep);
      position: absolute;
      left: 0.35rem;
      top: 0.2rem;
      font-family: "Outfit", sans-serif;
      font-weight: 700;
      font-size: 0.8rem;
      color: var(--accent);
    }}
    .task-group {{ margin-bottom: 1.35rem; }}
    .task-group:last-child {{ margin-bottom: 0; }}
    .task-assignee {{
      font-family: "Outfit", sans-serif;
      font-weight: 700;
      font-size: 1.08rem;
      color: var(--accent);
      margin: 0 0 0.45rem;
      padding-bottom: 0.25rem;
      border-bottom: 2px solid var(--accent-soft);
    }}
    .task-group-ul {{
      margin: 0;
      padding-left: 1.35rem;
      list-style: disc;
    }}
    .task-group-ul li {{ margin-bottom: 0.4rem; }}
    .muted {{ color: var(--muted); font-size: 0.95rem; }}
    .mermaid-wrap {{
      margin: 1.35rem 0;
      padding: 1rem 1rem 0.5rem;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow-x: auto;
    }}
    .hero-lead-wrap .mermaid-wrap {{
      background: rgba(255, 255, 255, 0.97);
      color: var(--ink);
      margin-top: 1rem;
    }}
    .hero-lead-wrap .mermaid-wrap .mermaid {{ min-height: 2rem; }}
  </style>
</head>
<body>
  <div class="progress" id="read-progress" aria-hidden="true"></div>
  <header class="hero">
    <div class="hero-inner">
      <p class="hero-kicker">Meeting summary · 縦スクロール図解</p>
      <h1>{html.escape(name)}</h1>
      {meta_para}
      <div class="hero-lead-wrap">{hero_lead_inner}</div>
    </div>
  </header>
  <main>
{blocks}
  </main>
  <script>
    (function () {{
      var bar = document.getElementById("read-progress");
      function onScroll() {{
        var doc = document.documentElement;
        var scrollTop = doc.scrollTop || document.body.scrollTop;
        var height = doc.scrollHeight - doc.clientHeight;
        var pct = height > 0 ? (scrollTop / height) * 100 : 0;
        bar.style.width = Math.min(100, pct) + "%";
      }}
      window.addEventListener("scroll", onScroll, {{ passive: true }});
      onScroll();
      var sections = document.querySelectorAll("[data-animate]");
      if ("IntersectionObserver" in window) {{
        var obs = new IntersectionObserver(
          function (entries) {{
            entries.forEach(function (e) {{
              if (e.isIntersecting) e.target.classList.add("is-visible");
            }});
          }},
          {{ root: null, rootMargin: "0px 0px -8% 0px", threshold: 0.08 }}
        );
        sections.forEach(function (s) {{ obs.observe(s); }});
      }} else {{
        sections.forEach(function (s) {{ s.classList.add("is-visible"); }});
      }}
    }})();
  </script>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.0/+esm";
    mermaid.initialize({{ startOnLoad: false, theme: "neutral", securityLevel: "strict" }});
    var nodes = document.querySelectorAll(".mermaid-wrap .mermaid");
    if (nodes.length) {{
      await mermaid.run({{ nodes: Array.from(nodes) }});
    }}
  </script>
</body>
</html>
"""

