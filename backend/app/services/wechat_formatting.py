from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WechatTheme:
    key: str
    name: str
    description: str
    accent_color: str
    heading_style: str
    quote_background: str


WECHAT_THEMES: dict[str, WechatTheme] = {
    "clean": WechatTheme(
        key="clean",
        name="清爽简约",
        description="留白充足，适合通知、知识分享和日常运营。",
        accent_color="#1677ff",
        heading_style="bar",
        quote_background="#f5f7fa",
    ),
    "brand": WechatTheme(
        key="brand",
        name="品牌强调",
        description="标题和重点色更醒目，适合品牌活动与产品介绍。",
        accent_color="#07c160",
        heading_style="block",
        quote_background="#f0faf5",
    ),
    "editorial": WechatTheme(
        key="editorial",
        name="杂志阅读",
        description="克制的标题线和较宽行距，适合长文与人物故事。",
        accent_color="#9a6b3f",
        heading_style="underline",
        quote_background="#faf7f2",
    ),
}

DEFAULT_WECHAT_FORMAT = {
    "theme": "clean",
    "accent_color": "#1677ff",
    "font_size": 16,
    "line_height": 1.8,
    "paragraph_spacing": 16,
    "first_line_indent": False,
    "link_footnotes": True,
}


def wechat_theme_profiles() -> list[dict[str, str]]:
    return [asdict(theme) for theme in WECHAT_THEMES.values()]


def normalize_wechat_profile(profile: dict | None = None) -> dict:
    raw = {**DEFAULT_WECHAT_FORMAT, **(profile or {})}
    theme_key = str(raw.get("theme", "clean"))
    if theme_key not in WECHAT_THEMES:
        theme_key = "clean"
    theme = WECHAT_THEMES[theme_key]
    color = str(raw.get("accent_color") or theme.accent_color).lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", color):
        color = theme.accent_color
    return {
        "theme": theme_key,
        "accent_color": color,
        "font_size": min(20, max(14, int(raw.get("font_size", 16)))),
        "line_height": min(2.2, max(1.4, float(raw.get("line_height", 1.8)))),
        "paragraph_spacing": min(32, max(8, int(raw.get("paragraph_spacing", 16)))),
        "first_line_indent": bool(raw.get("first_line_indent", False)),
        "link_footnotes": bool(raw.get("link_footnotes", True)),
    }


def _safe_url(value: str) -> str | None:
    url = value.strip()
    return url if re.match(r"^https?://", url, re.IGNORECASE) else None


def _inline_markdown(value: str, *, link_footnotes: bool, references: list[str]) -> str:
    placeholders: dict[str, str] = {}

    def replace_code(match: re.Match[str]) -> str:
        key = f"CPPLACEHOLDER{len(placeholders)}TOKEN"
        placeholders[key] = (
            '<code style="padding:2px 5px;border-radius:4px;background:#f2f3f5;'
            'color:#d14;font-family:Menlo,Consolas,monospace;font-size:0.88em;">'
            f"{html.escape(match.group(1), quote=True)}</code>"
        )
        return key

    def replace_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=True)
        url = _safe_url(match.group(2))
        if not url:
            return label
        escaped_url = html.escape(url, quote=True)
        key = f"CPPLACEHOLDER{len(placeholders)}TOKEN"
        if link_footnotes:
            if url not in references:
                references.append(url)
            number = references.index(url) + 1
            placeholders[key] = f'{label}<sup style="color:#888;">[{number}]</sup>'
        else:
            placeholders[key] = (
                f'<a href="{escaped_url}" style="color:#1677ff;text-decoration:none;">{label}</a>'
            )
        return key

    value = re.sub(r"`([^`]+)`", replace_code, value)
    value = re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)", replace_link, value)
    rendered = html.escape(value, quote=True)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", rendered)
    for key, replacement in placeholders.items():
        rendered = rendered.replace(key, replacement)
    return rendered


def format_wechat_html(markdown: str, profile: dict | None = None) -> tuple[str, dict]:
    """Convert a safe Markdown subset to WeChat-friendly inline-styled HTML."""
    settings = normalize_wechat_profile(profile)
    theme = WECHAT_THEMES[settings["theme"]]
    accent = settings["accent_color"]
    font_size = settings["font_size"]
    spacing = settings["paragraph_spacing"]
    line_height = settings["line_height"]
    indent = "text-indent:2em;" if settings["first_line_indent"] else ""
    references: list[str] = []
    blocks: list[str] = []
    code_lines: list[str] = []
    in_code = False

    paragraph_style = (
        f"margin:0 0 {spacing}px;color:#2b2b2b;font-size:{font_size}px;"
        f"line-height:{line_height};letter-spacing:0.02em;word-break:break-word;{indent}"
    )

    def inline(value: str) -> str:
        return _inline_markdown(
            value,
            link_footnotes=settings["link_footnotes"],
            references=references,
        )

    def heading_style(level: int) -> str:
        base = f"margin:{30 if level <= 2 else 24}px 0 14px;font-weight:700;line-height:1.45;"
        size = 22 if level <= 2 else 18
        if theme.heading_style == "block":
            return (
                f"{base}padding:7px 12px;border-radius:4px;background:{accent};"
                f"color:#fff;font-size:{size}px;"
            )
        if theme.heading_style == "underline":
            return (
                f"{base}padding-bottom:7px;border-bottom:2px solid {accent};"
                f"color:#262626;font-size:{size}px;"
            )
        return (
            f"{base}padding-left:10px;border-left:4px solid {accent};"
            f"color:#262626;font-size:{size}px;"
        )

    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if in_code:
                code = html.escape("\n".join(code_lines), quote=True)
                blocks.append(
                    '<pre style="margin:0 0 18px;padding:14px 16px;overflow-wrap:anywhere;'
                    "border-radius:6px;background:#f5f7fa;color:#333;font-size:13px;"
                    f'line-height:1.65;white-space:pre-wrap;"><code>{code}</code></pre>'
                )
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw_line)
            continue
        if not stripped:
            continue

        image = re.fullmatch(r"!\[([^\]]*)\]\(([^\s)]+)\)", stripped)
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        ordered = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        if image:
            url = _safe_url(image.group(2))
            if url:
                alt = html.escape(image.group(1), quote=True)
                escaped_url = html.escape(url, quote=True)
                blocks.append(
                    f'<figure style="margin:22px 0;text-align:center;">'
                    f'<img src="{escaped_url}" alt="{alt}" '
                    'style="display:block;width:100%;height:auto;border-radius:6px;" />'
                    '<figcaption style="margin-top:7px;color:#999;font-size:12px;">'
                    f"{alt}</figcaption></figure>"
                )
        elif heading:
            level = len(heading.group(1))
            heading_content = inline(heading.group(2))
            blocks.append(
                f'<h{level + 1} style="{heading_style(level)}">{heading_content}</h{level + 1}>'
            )
        elif ordered or bullet:
            marker = f"{ordered.group(1)}." if ordered else "•"
            content = ordered.group(2) if ordered else bullet.group(1)
            blocks.append(
                f'<section style="display:flex;margin:0 0 {max(8, spacing - 4)}px;'
                f'color:#2b2b2b;font-size:{font_size}px;line-height:{line_height};">'
                f'<span style="flex:none;width:1.8em;color:{accent};'
                f'font-weight:700;">{marker}</span>'
                f'<span style="min-width:0;flex:1;">{inline(content)}</span></section>'
            )
        elif stripped.startswith("> "):
            blocks.append(
                '<blockquote style="margin:20px 0;padding:12px 15px;'
                f"border-left:3px solid {accent};"
                f"background:{theme.quote_background};color:#666;font-size:{font_size - 1}px;"
                f'line-height:{line_height};">{inline(stripped[2:])}</blockquote>'
            )
        elif re.fullmatch(r"-{3,}|\*{3,}", stripped):
            blocks.append(
                '<hr style="margin:28px auto;border:0;'
                f'border-top:1px solid {accent};opacity:.35;" />'
            )
        else:
            blocks.append(f'<p style="{paragraph_style}">{inline(stripped)}</p>')

    if in_code:
        code = html.escape("\n".join(code_lines), quote=True)
        blocks.append(
            '<pre style="margin:0 0 18px;padding:14px 16px;border-radius:6px;background:#f5f7fa;'
            f'white-space:pre-wrap;"><code>{code}</code></pre>'
        )
    if references:
        items = "".join(
            '<p style="margin:5px 0;color:#888;font-size:12px;'
            'line-height:1.6;word-break:break-all;">'
            f"[{index}] {html.escape(url, quote=True)}</p>"
            for index, url in enumerate(references, 1)
        )
        blocks.append(
            '<section style="margin-top:30px;padding-top:12px;'
            f'border-top:1px solid #eee;">{items}</section>'
        )

    body = "".join(blocks)
    root = (
        f'<section data-contentpilot-format="wechat-{settings["theme"]}" '
        f'style="box-sizing:border-box;max-width:100%;color:#2b2b2b;font-family:'
        "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB',"
        f"'Microsoft YaHei',sans-serif;\">{body}</section>"
    )
    return root, settings
