"""合规层 — 适用于中国法规的 AI 生成内容标识 + 风险提示。

References:
- 《人工智能生成合成内容标识办法》(2025-09-01 施行)
- 《证券法》《广告法》《关于防范和处置非法集资的意见》
"""
from __future__ import annotations

import re

# === AI 生成内容强制标识（显式 + 隐式） ===

AI_LABEL_PREFIX = (
    "⚠️ **AI 辅助生成提示** ｜ 本文由 DiscernBrief 系统（人工智能模型）辅助生成，"
    "内容基于近 24 小时公开信息源采集与判读，**不代表任何投资建议**，"
    "仅供信息分享与研究参考。\n\n"
)

FRONTMATTER_AI_TAG = (
    "ai_generated: true\n"
    "ai_generator: DiscernBrief-1.0\n"
    "ai_law: 《人工智能生成合成内容标识办法》\n"
)

RISK_DISCLAIMER = (
    "\n\n---\n\n"
    "⚠️ **风险提示**\n\n"
    "- 本文由 AI 辅助生成，仅供信息分享与研究参考，**不构成任何投资建议**\n"
    "- 文中观点、推测、结论均为 AI 基于公开信息的研判，存在偏差甚至错误的可能性\n"
    "- 任何投资决策应基于您自身的独立判断与风险承受能力\n"
    "- 过往业绩不代表未来表现，**市场有风险，决策需谨慎**\n"
)

PAID_CONTENT_DISCLAIMER = (
    "\n\n> 📌 **付费内容声明**\n"
    "> 本篇为知识星球付费订阅内容，由 AI 辅助生成。\n"
    "> 严禁未经授权转载、售卖或用于商业培训。\n"
    "> 转载请联系作者保留署名权与完整免责声明。\n"
)

# 排除前位 . / - / : / _ / 字母（避免时间戳 04:07:05.667556 误报）
STOCK_CODE_RE = re.compile(
    r"(?<![\w.\-:/_])(?:[60]\d{5}|[39]\d{5})(?![\d.\-:/])"
)
HK_STOCK_RE = re.compile(
    r"(?<![\w])HK[\s-]?\d{4,5}(?![\d])",
    re.IGNORECASE,
)
BUY_SELL_RE = re.compile(
    r"(买入|卖出|建仓|加仓|减仓|清仓|目标价|止损位|建议.{0,4}(买|卖|持有)|"
    r"now\s+is\s+the\s+time\s+to\s+(buy|sell)|recommend\s+(buy|sell))",
    re.IGNORECASE,
)
GUARANTEE_RE = re.compile(r"(稳赚|保本|无风险|翻倍|稳赚不赔|guaranteed|risk[- ]free)", re.IGNORECASE)
SINGLE_STOCK_NAME_RE = re.compile(
    r"(贵州茅台|宁德时代|比亚迪|腾讯|阿里巴巴|美团|拼多多|京东|百度|网易|小米|"
    r"苹果|特斯拉|英伟达|微软|谷歌|亚马逊|Meta|Netflix|Nvidia)",
)

# 行业术语白名单
INDUSTRY_TERM_WHITELIST = [
    "Nvidia", "AMD", "Qualcomm", "Apple", "Samsung", "Intel", "Broadcom",
    "Microsoft", "Google", "Amazon", "AWS", "Meta", "Oracle", "TSMC",
    "OpenAI", "Anthropic", "Mistral", "Cerebras", "Marvell", "Groq",
    "联发科", "中芯国际", "海光信息", "寒武纪",
]

# 行业术语白名单：合规扫描里这些公司名是 industry context，不算个股点名违规
INDUSTRY_TERM_WHITELIST = [
    "Nvidia", "AMD", "Qualcomm", "Apple", "Samsung", "Intel", "Broadcom",
    "Microsoft", "Google", "Amazon", "AWS", "Meta", "Oracle", "TSMC",
    "OpenAI", "Anthropic", "Mistral", "Cerebras", "Marvell", "Groq",
    "联发科", "中芯国际", "海光信息", "寒武纪",
]


# 行业白名单 — 这些公司名在合规扫描里是 industry context, 不是 stock advice
INDUSTRY_TERM_WHITELIST = {
    "Nvidia", "AMD", "Qualcomm", "Apple", "Samsung", "Intel", "Broadcom",
    "Microsoft", "Google", "Amazon", "AWS", "Meta", "Oracle", "TSMC",
    "OpenAI", "Anthropic", "Mistral", "Cerebras", "Marvell", "联发科", "中芯国际",
}


def scan_violations(text: str) -> list[dict]:
    hits: list[dict] = []
    for rule_name, pattern, severity in [
        ("A 股代码", STOCK_CODE_RE, "high"),
        ("港股代码", HK_STOCK_RE, "high"),
        ("买卖建议", BUY_SELL_RE, "high"),
        ("收益承诺", GUARANTEE_RE, "high"),
        ("个股点名", SINGLE_STOCK_NAME_RE, "medium"),
    ]:
        is_industry_rule = (rule_name == "个股点名")
        for m in pattern.finditer(text):
            if is_industry_rule and m.group(0) in INDUSTRY_TERM_WHITELIST:
                continue
            hits.append({"rule": rule_name, "match": m.group(0), "severity": severity, "span": (m.start(), m.end())})
    return hits


def add_ai_label(text: str, position: str = "prefix") -> str:
    if position == "prefix":
        return AI_LABEL_PREFIX + text
    if position == "suffix":
        return text + AI_LABEL_PREFIX
    raise ValueError(f"position must be prefix|suffix, got {position}")


def add_risk_disclaimer(text: str, is_paid: bool = False) -> str:
    out = text + RISK_DISCLAIMER
    if is_paid:
        out += PAID_CONTENT_DISCLAIMER
    return out


def build_frontmatter(meta: dict) -> str:
    lines = ["---"]
    lines.append(FRONTMATTER_AI_TAG.rstrip())
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def wrap_markdown(body: str, meta: dict, is_paid: bool = False) -> str:
    parts = [build_frontmatter(meta), "", AI_LABEL_PREFIX.rstrip(), body]
    out = "\n\n".join(parts)
    out += RISK_DISCLAIMER
    if is_paid:
        out += PAID_CONTENT_DISCLAIMER
    return out
