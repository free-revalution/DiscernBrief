"""Schema for signals (AI judgment output). Spec §25 / §26."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Spec §26 unified business-value categories
CATEGORIES = [
    "AI", "科技", "创业", "软件", "开发者", "电商", "跨境电商",
    "消费", "内容", "营销", "广告", "招聘", "B2B", "供应链",
    "政策", "金融市场", "网络安全", "科研", "产品", "基础设施", "其他",
]
IMPORTANCE_LEVELS = ["HIGH", "MEDIUM", "LOW"]


@dataclass
class Signal:
    raw_item_ids: list[int]
    title: str
    summary: str
    why_it_matters: str
    business_angle: str
    category: str = "其他"
    importance: str = "MEDIUM"
    source_urls: list[str] = field(default_factory=list)
    published_at: str | None = None
    confidence: float = 0.5  # 0.0 - 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errs = []
        if self.category not in CATEGORIES:
            errs.append(f"category {self.category!r} not in {CATEGORIES}")
        if self.importance not in IMPORTANCE_LEVELS:
            errs.append(f"importance {self.importance!r} not in {IMPORTANCE_LEVELS}")
        if not (0.0 <= self.confidence <= 1.0):
            errs.append(f"confidence {self.confidence} not in [0,1]")
        if not self.title:
            errs.append("title is empty")
        if not self.summary:
            errs.append("summary is empty")
        return errs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)