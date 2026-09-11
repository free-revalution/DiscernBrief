"""每日内容生成 — 从昨日 Excel 提取 top 信号，构造发布模板。

输出：
  cache/daily-content/<date>/
    ├── brief.md                 总览简报
    └── <slug>/
        ├── zsxq-1.md, zsxq-2.md, zsxq-3.md   知识星球 3 个角度
        ├── xhs.md               小红书引流帖
        └── jike.md              即刻引流帖
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import openpyxl

from .compliance import wrap_markdown


@dataclass
class Signal:
    id: int
    title: str
    summary: str
    why_it_matters: str
    business_angle: str
    category: str
    importance: str
    confidence: float
    source_urls: list[str]
    published_at: str | None
    created_at: str | None

    @property
    def slug(self) -> str:
        s = re.sub(r"[^\w\s-]", "", self.title.lower()).strip()
        s = re.sub(r"[-\s]+", "-", s)[:60]
        return s or f"signal-{self.id}"

    @property
    def priority(self) -> int:
        return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(self.importance, 3)


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    s = str(v).strip()
    if s.startswith("["):
        try:
            return ", ".join(str(x) for x in json.loads(s))
        except Exception:
            return s
    return s


def load_signals_from_xlsx(xlsx_path: Path) -> list[Signal]:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Excel not found: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    if "signals" not in wb.sheetnames:
        raise ValueError(f"No 'signals' sheet in {xlsx_path.name}")
    ws = wb["signals"]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = list(rows[0])  # row 0 = header
    data_rows = rows[1:]
    out: list[Signal] = []
    for r in data_rows:
        rec = dict(zip(header, r))
        if not rec.get("title"):
            continue
        out.append(Signal(
            id=int(rec.get("id") or 0),
            title=str(rec.get("title") or ""),
            summary=str(rec.get("summary") or ""),
            why_it_matters=str(rec.get("why_it_matters") or ""),
            business_angle=str(rec.get("business_angle") or ""),
            category=str(rec.get("category") or "其他"),
            importance=str(rec.get("importance") or "MEDIUM"),
            confidence=float(rec.get("confidence") or 0.5),
            source_urls=_norm(rec.get("url") or rec.get("source_urls")),
            published_at=rec.get("published_at"),
            created_at=rec.get("created_at"),
        ))
    return out


def rank_signals(signals: Iterable[Signal], top_n: int = 3) -> list[Signal]:
    return sorted(signals, key=lambda s: (s.priority, -s.confidence))[:top_n]


ZSXQ_ANGLE_TEMPLATES = [
    {"title": "深度产业链拆解", "outline": [
        "## 这件事的本质是什么？",
        "## 产业链上下游分别意味着什么机会？",
        "## 谁受益、谁受损、谁观望？",
        "## 短期 vs 中期 vs 长期，分别会怎样演化？",
    ], "hook": "为什么这次{topic}值得花 10 分钟深读？"},
    {"title": "商业模式与竞争格局重估", "outline": [
        "## 发生了什么（简述）",
        "## 这改变了什么商业假设？",
        "## 头部 / 中部 / 长尾玩家分别怎么应对？",
        "## 投资人/创业者可以从这个变化中学到什么？",
    ], "hook": "如果只看标题，你会错过什么？"},
    {"title": "对个体的影响：技能 / 职业 / 决策", "outline": [
        "## 这件事跟普通读者有什么关系？",
        "## 哪类人群最受影响？",
        "## 哪些技能 / 行为会升值，哪些会贬值？",
        "## 接下来 90 天，你可以做的一件具体的事",
    ], "hook": "读完这篇，你应该能回答这三个问题。"},
]


XHS_TEMPLATE = """# {topic}

> 一句话钩子：{hook}

**为什么这件事值得刷到**：
{summary}

**对普通人意味着什么**：
{angle}

👇 想看完整产业链拆解 + 头部玩家反应？戳主页置顶帖。

#相关话题 #{tag1} #{tag2} #{tag3}
"""


JIKE_TEMPLATE = """{topic} — {hook}

刚看到一个值得聊的事：

{summary}

我的判断：{angle}

如果你也在关注这个领域，欢迎转发聊聊。
"""


def generate_daily_content(xlsx_path: Path, out_dir: Path, top_n: int = 3) -> dict:
    signals = load_signals_from_xlsx(xlsx_path)
    if not signals:
        raise ValueError(f"No signals found in {xlsx_path}")
    top = rank_signals(signals, top_n)
    date_str = xlsx_path.stem.replace("DiscernBrief-", "")

    out_dir.mkdir(parents=True, exist_ok=True)

    brief_md = _render_brief(top, date_str, total_signals=len(signals))
    (out_dir / "brief.md").write_text(brief_md, encoding="utf-8")

    files_written: list[str] = []
    for idx, sig in enumerate(top, start=1):
        slug = f"{idx:02d}-{sig.slug}"
        topic_dir = out_dir / slug
        topic_dir.mkdir(exist_ok=True)
        for n, tpl in enumerate(ZSXQ_ANGLE_TEMPLATES, start=1):
            md = _render_zsxq_template(sig, tpl, n)
            (topic_dir / f"zsxq-{n}.md").write_text(md, encoding="utf-8")
            files_written.append(str(topic_dir / f"zsxq-{n}.md"))
        xhs = _render_xhs(sig)
        (topic_dir / "xhs.md").write_text(xhs, encoding="utf-8")
        files_written.append(str(topic_dir / "xhs.md"))
        jike = _render_jike(sig)
        (topic_dir / "jike.md").write_text(jike, encoding="utf-8")
        files_written.append(str(topic_dir / "jike.md"))

    return {
        "date": date_str,
        "total_signals": len(signals),
        "selected_count": len(top),
        "topics": [
            {"id": s.id, "title": s.title, "importance": s.importance, "slug": f"{i+1:02d}-{s.slug}"}
            for i, s in enumerate(top)
        ],
        "out_dir": str(out_dir),
        "files": files_written,
    }


def _render_brief(top: list[Signal], date_str: str, total_signals: int) -> str:
    lines = [
        f"# DiscernBrief 每日内容简报 — {date_str}",
        "",
        f"本周期共判读 **{total_signals}** 条信号，按重要性 + 置信度排序取 top {len(top)}，",
        "分别生成 3 篇知识星球深度文章（不同角度） + 1 篇小红书 + 1 篇即刻。",
        "",
        "---",
        "",
    ]
    for idx, sig in enumerate(top, start=1):
        lines.append(f"## #{idx} — {sig.title}")
        lines.append("")
        lines.append(f"- **重要性**：{sig.importance}  ·  **置信度**：{sig.confidence:.2f}")
        lines.append(f"- **类目**：{sig.category}")
        lines.append(f"- **摘要**：{sig.summary}")
        if sig.why_it_matters:
            lines.append(f"- **为什么重要**：{sig.why_it_matters}")
        if sig.business_angle:
            lines.append(f"- **商业角度**：{sig.business_angle}")
        if sig.source_urls:
            urls = sig.source_urls.split(", ")[:3]
            lines.append(f"- **来源**：{', '.join(urls)}")
        lines.append("")
    return "\n".join(lines)


def _render_zsxq_template(sig: Signal, tpl: dict, n: int) -> str:
    meta = {
        "title": f"{sig.title}（{tpl['title']}）",
        "date": sig.created_at or "",
        "category": sig.category,
        "importance": sig.importance,
        "confidence": f"{sig.confidence:.2f}",
        "signal_id": sig.id,
        "source_urls": [u for u in sig.source_urls.split(", ") if u][:3],
        "angle_variant": n,
        "ai_purpose": "knowledge_planet_subscription",
        "language": "zh",
    }
    body_lines = [
        f"# {sig.title}（{tpl['title']}）",
        "",
        f"**核心钩子**：{tpl['hook'].format(topic=sig.title)}",
        "",
        "## TL;DR",
        "",
        sig.summary or "（待补充）",
        "",
        "## 为什么这件事值得花 10 分钟深读",
        "",
        sig.why_it_matters or "（待补充 — 思考这个变化对行业格局、对个人决策的深层含义）",
        "",
    ]
    for h in tpl["outline"]:
        body_lines += [h, "", "（待补充 — 用具体案例 / 数据 / 反直觉观察填满这一节，每节 200-400 字）", ""]
    body_lines += [
        "## 给读者的一个具体行动建议", "",
        sig.business_angle or "（待补充）", "",
        "## 来源", "",
    ]
    for u in [x for x in sig.source_urls.split(", ") if x][:3]:
        body_lines.append(f"- {u}")
    body = "\n".join(body_lines)
    return wrap_markdown(body, meta, is_paid=True)


def _render_xhs(sig: Signal) -> str:
    meta = {
        "title": f"【{sig.category}】{sig.title}",
        "platform": "xiaohongshu",
        "signal_id": sig.id,
        "importance": sig.importance,
        "language": "zh",
        "ai_purpose": "social_traffic_to_knowledge_planet",
    }
    tags = _xhs_tags(sig)
    body = XHS_TEMPLATE.format(
        topic=sig.title,
        hook=_xhs_hook(sig),
        summary=sig.summary,
        angle=sig.business_angle or sig.why_it_matters or "（待补充）",
        tag1=tags[0], tag2=tags[1], tag3=tags[2],
    )
    return wrap_markdown(body, meta, is_paid=False)


def _render_jike(sig: Signal) -> str:
    meta = {
        "title": sig.title,
        "platform": "jike",
        "signal_id": sig.id,
        "importance": sig.importance,
        "language": "zh",
        "ai_purpose": "social_traffic_to_knowledge_planet",
    }
    body = JIKE_TEMPLATE.format(
        topic=sig.title,
        hook=_jike_hook(sig),
        summary=sig.summary,
        angle=sig.business_angle or sig.why_it_matters or "（待补充）",
    )
    return wrap_markdown(body, meta, is_paid=False)


def _xhs_hook(sig: Signal) -> str:
    if sig.why_it_matters:
        return sig.why_it_matters[:60].rstrip("。.,. ") + "。"
    return f"这件事只看到标题会错过 {sig.importance} 级别的信号"


def _jike_hook(sig: Signal) -> str:
    if sig.business_angle:
        return sig.business_angle[:50].rstrip("。.,. ") + "。"
    return f"{sig.importance} 信号 · {sig.category}"


def _xhs_tags(sig: Signal) -> list[str]:
    cat = sig.category.replace("/", "·")
    return [f"{cat}观察", "AI情报局", "知识星球订阅"]
