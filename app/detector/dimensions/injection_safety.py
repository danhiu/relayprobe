"""Detect prompt-injection / response-poisoning by a relay.

A compromised or malicious relay can splice payloads into the model's
response that the model itself never generated. Real-world incidents
seen in 2026 include:

  - Shell commands hidden in markdown code blocks ("just run this to
    install the helper") so an agent like Claude Code or Codex executes
    them.
  - Markdown image references with attacker-controlled URLs that
    exfiltrate the conversation as query parameters when an agent
    renders the response.
  - Zero-width unicode characters embedded in plain prose, used to
    smuggle further instructions to downstream agents.
  - "Forget your previous instructions" / "to continue, do X" kinds of
    rogue post-script appended after the model's real reply.
  - Unsolicited HTTP requests planted in code suggestions when the user
    asked for nothing of the kind.

We probe with deliberately innocuous prompts ("What is 12 x 7?", "Name
a Renaissance painter") so any of these signatures showing up in the
reply is, by construction, the relay's contribution rather than the
model's. The dimension is conservative — it only fires on patterns
seen in actual poisoning campaigns; benign code samples that the model
might genuinely produce (a `print()` call, an arithmetic example) do
not trigger it."""
from __future__ import annotations

import re

from app.detector.budget import BudgetExceeded
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.probes import draw
from app.detector.types import ChatMessage, DimensionResult, RoundLog

DEFAULT_PROBE_ROUNDS = 4

# Zero-width / direction / format characters used to smuggle hidden
# instructions through plain text. We don't include these in our own
# probes (see data/probes.yaml) so any occurrence in a response is
# anomalous.
HIDDEN_UNICODE = {
    "​": "ZERO WIDTH SPACE",
    "‌": "ZERO WIDTH NON-JOINER",
    "‍": "ZERO WIDTH JOINER",
    "⁠": "WORD JOINER",
    "﻿": "ZERO WIDTH NO-BREAK SPACE / BOM",
    "‮": "RIGHT-TO-LEFT OVERRIDE",
    "‭": "LEFT-TO-RIGHT OVERRIDE",
}

# Shell-execution patterns that Claude Code, Codex, Aider etc. might
# obediently run if surfaced as a "fix it by running this" suggestion.
# We require pipe-to-shell or sudo-curl combos rather than bare "curl"
# alone — bare curl is a legitimate teaching example and would false-
# positive constantly.
SHELL_EXEC_PATTERNS = [
    re.compile(r"\bcurl\b[^\n`]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b", re.IGNORECASE),
    re.compile(r"\bwget\b[^\n`]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b", re.IGNORECASE),
    re.compile(r"\bbash\s*<\(\s*curl\b", re.IGNORECASE),
    re.compile(r"\bsh\s*<\(\s*curl\b", re.IGNORECASE),
    re.compile(r"\beval\s*[\"']?\$\(\s*curl\b", re.IGNORECASE),
    re.compile(r"\bpowershell\b[^\n`]*-(?:e|enc|EncodedCommand)\b", re.IGNORECASE),
    re.compile(r"\biwr\b[^\n`]*\|\s*iex\b", re.IGNORECASE),  # PS Invoke-WebRequest | Invoke-Expression
]

# Rogue instruction phrases that try to hijack a downstream agent.
# Wrapped in word boundaries so a normal sentence ("ignore the noise
# in the second sentence") doesn't trip.
ROGUE_INSTRUCTION_PATTERNS = [
    re.compile(r"\b(?:please\s+)?ignore\s+(?:all\s+)?(?:your\s+)?previous\s+(?:instructions|prompts?)\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(?:all\s+)?(?:prior|previous)\s+(?:instructions|context)\b", re.IGNORECASE),
    re.compile(r"\bnew\s+system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"\b(?:you\s+(?:must|should)\s+now|the\s+user\s+wants\s+you\s+to)\s+(?:run|execute|download)\b", re.IGNORECASE),
    re.compile(r"\bto\s+(?:continue|proceed)\b[^.\n]{0,40}\b(?:run|execute|paste|copy)\b", re.IGNORECASE),
]

# Markdown image / link patterns that exfiltrate via URL parameters.
# A normal answer to "name a Renaissance painter" doesn't include image
# tags at all, so any image is suspicious; we still focus on the
# query-parameter-with-payload signature.
EXFIL_IMG_PATTERN = re.compile(
    r"!\[[^\]]*\]\((https?://[^\s)]+\?[^\s)]*=[^\s)]+)\)",
    re.IGNORECASE,
)

# "Read this base64 / hex blob" style payloads inside fenced code blocks.
# Filters out short numeric strings (e.g. an answer of "42") by
# requiring 80+ chars of base64-ish content.
LONG_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/=]{80,}")
LONG_HEX_BLOB = re.compile(r"\b[0-9a-fA-F]{120,}\b")


class InjectionSafety(Dimension):
    name = "injection_safety"
    weight = 0.15

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        n_rounds = min(DEFAULT_PROBE_ROUNDS, max(2, ctx.rounds // 4))

        per_round: list[dict] = []
        # Findings keyed by category — we count each *category* of injection
        # at most once per round so a single payload with both a curl|sh
        # and a hidden unicode doesn't double-count.
        any_shell = 0
        any_rogue = 0
        any_hidden_unicode = 0
        any_exfil_img = 0
        any_long_blob = 0
        rounds_completed = 0

        for i in range(n_rounds):
            try:
                prompt, _nonce = draw("injection_safety", rng=ctx.rng)
            except KeyError:
                # Older deployments without the probe pool — degrade
                # gracefully instead of erroring out the whole scan.
                return DimensionResult(
                    name=self.name, score=0, status="skipped",
                    evidence={"reason": "injection_safety probe pool missing"},
                )

            try:
                result = await ctx.adapter.chat(
                    model=ctx.target_model,
                    messages=[ChatMessage(role="user", content=prompt)],
                    max_tokens=200,
                )
                ctx.budget.charge(
                    model=ctx.baseline.name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
            except BudgetExceeded:
                raise
            except Exception as e:
                per_round.append({"round": i, "error": str(e)})
                continue

            text = result.text
            findings = _scan(text)
            rounds_completed += 1
            if findings["shell_exec"]:
                any_shell += 1
            if findings["rogue_instructions"]:
                any_rogue += 1
            if findings["hidden_unicode"]:
                any_hidden_unicode += 1
            if findings["exfil_images"]:
                any_exfil_img += 1
            if findings["long_blobs"]:
                any_long_blob += 1

            verdict = "clean" if not findings["any"] else "tainted"
            ctx.rounds_log.append(
                RoundLog(
                    round=len(ctx.rounds_log) + 1,
                    dimension=self.name,
                    prompt=prompt,
                    response_excerpt=text[:200],
                    verdict=verdict,
                    duration_ms=result.total_latency_ms,
                )
            )
            per_round.append(
                {
                    "round": i,
                    "prompt": prompt,
                    "response_excerpt": text[:200],
                    "verdict": verdict,
                    "findings": findings,
                }
            )

        evidence = {
            "rounds_completed": rounds_completed,
            "shell_exec_rounds": any_shell,
            "rogue_instruction_rounds": any_rogue,
            "hidden_unicode_rounds": any_hidden_unicode,
            "exfil_image_rounds": any_exfil_img,
            "long_blob_rounds": any_long_blob,
            "per_round": per_round,
        }

        if rounds_completed == 0:
            return DimensionResult(
                name=self.name, score=0, status="error", evidence=evidence,
                error="no successful injection_safety probe rounds",
            )

        # Severity ladder. The signatures aren't equally bad: a single
        # `curl|sh` instruction routed at an agent is catastrophic,
        # while hidden unicode is a strong but lower-blast-radius
        # signal. Score reflects that.
        if any_shell > 0 or any_rogue > 0:
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence,
            )
        if any_exfil_img > 0:
            return DimensionResult(
                name=self.name, score=20, status="missing", evidence=evidence,
            )
        if any_hidden_unicode > 0:
            return DimensionResult(
                name=self.name, score=40, status="degraded", evidence=evidence,
            )
        if any_long_blob > 0:
            return DimensionResult(
                name=self.name, score=70, status="degraded", evidence=evidence,
            )
        return DimensionResult(
            name=self.name, score=100, status="ok", evidence=evidence,
        )


def _scan(text: str) -> dict:
    """Return a dict of category-keyed findings for a single response.

    Each list entry is a dict the UI / admin can render: pattern type +
    a short excerpt of what matched, never the full text (response can
    be long and is shown separately as response_excerpt)."""
    shell_exec = []
    for pat in SHELL_EXEC_PATTERNS:
        m = pat.search(text)
        if m:
            shell_exec.append({"pattern": pat.pattern, "match": m.group(0)[:140]})

    rogue = []
    for pat in ROGUE_INSTRUCTION_PATTERNS:
        m = pat.search(text)
        if m:
            rogue.append({"pattern": pat.pattern, "match": m.group(0)[:140]})

    hidden_unicode = []
    for ch, name in HIDDEN_UNICODE.items():
        if ch in text:
            hidden_unicode.append({"char": repr(ch), "name": name})

    exfil_imgs = []
    for m in EXFIL_IMG_PATTERN.finditer(text):
        exfil_imgs.append({"url": m.group(1)[:200]})

    long_blobs = []
    for pat in (LONG_BASE64_BLOB, LONG_HEX_BLOB):
        m = pat.search(text)
        if m:
            long_blobs.append({"kind": "base64" if pat is LONG_BASE64_BLOB else "hex",
                               "excerpt": m.group(0)[:80] + "…"})
            break  # one is enough — they overlap

    findings = {
        "shell_exec": shell_exec,
        "rogue_instructions": rogue,
        "hidden_unicode": hidden_unicode,
        "exfil_images": exfil_imgs,
        "long_blobs": long_blobs,
    }
    findings["any"] = any(findings[k] for k in
                          ("shell_exec", "rogue_instructions", "hidden_unicode",
                           "exfil_images", "long_blobs"))
    return findings
