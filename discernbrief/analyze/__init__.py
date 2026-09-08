"""AI analysis: filter, business analysis, signal generation.

Phase 5 (Filter): keep / drop + category + importance
Phase 6 (Business Analysis): summary + why_it_matters + business_angle

For Phase 1 we keep the LLM interface pluggable. `ManualLlm` is the
default: it renders the prompt and expects JSON back via stdin or file.
Swap in `OpenAILlm` / `AnthropicLlm` later when API keys exist.
"""
from .schema import CATEGORIES, Signal  # noqa: F401
from .filter import FilterPipeline  # noqa: F401
from .llm import ManualLlm, build_prompt  # noqa: F401