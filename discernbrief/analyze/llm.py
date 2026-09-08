"""LLM layer.

Per SPEC.md, AI analysis runs *inside* OpenClaw — the assistant IS the
filter. There is no external LLM server.

Workflow:

    $ radar filter-prompt --limit 20 --out prompts/batch.json
    # → sends prompt to wherever the assistant can read it
    # (e.g. file in workspace, or a Feishu chat message)

    # assistant reads, judges, writes judgments JSON to disk
    $ radar ingest-signals prompts/batch.judgments.json
    # → writes signals to the SQLite signals table

`ManualLlm` is the only implementation. `OpenAILlm` / `AnthropicLlm`
were removed; if external models are ever wanted, re-add them in a
sealed opt-in module so they can never become the default path.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from .filter import build_judgment_prompt


class Llm:
    """Protocol-ish marker. ManualLlm is the only impl."""
    name: str = "manual"

    def complete(self, prompt: str) -> str: ...


class ManualLlm:
    """Prints the prompt to stdout (or a file), expects JSON on stdin.

    In the OpenClaw-native flow the assistant reads the prompt from
    a file the CLI generated, judges the items, and writes judgments
    JSON which `ingest-signals` then ingests. This class exists so
    the same `FilterPipeline` code path can be driven end-to-end by
    a human too.
    """

    name = "manual"

    def __init__(self, out_stream=None, in_stream=None, write_to_file: str | None = None):
        self.out = out_stream or sys.stdout
        self.inp = in_stream or sys.stdin
        self.write_to_file = write_to_file

    def complete(self, prompt: str) -> str:
        if self.write_to_file:
            with open(self.write_to_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            self.out.write(f"[prompt written to {self.write_to_file}]\n")
            self.out.flush()
        else:
            self.out.write(prompt)
            self.out.flush()
        self.out.write("\n--- paste JSON response, then EOF (Ctrl-D) ---\n")
        self.out.flush()
        return self.inp.read()


def make_llm(name: str | None = None, **kwargs) -> Llm:
    """Factory. Only `manual` is supported in the OpenClaw-native build."""
    name = (name or "manual").lower()
    if name == "manual":
        return ManualLlm(**kwargs)
    raise ValueError(
        f"unknown llm: {name!r}. Per SPEC.md, AI analysis runs inside OpenClaw — "
        "use 'manual' and let the assistant judge the prompt."
    )


def build_prompt(items: list[dict]) -> str:
    """Helper used by CLI for the standalone `filter-prompt` command."""
    return build_judgment_prompt(items)