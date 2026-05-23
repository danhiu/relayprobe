"""CLI entry: `python -m app.cli --base ... --key ... --model ...`."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.detector import run_detection
from app.detector.log_redact import install_global_filter
from app.detector.types import DetectRequest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="detector", description="AI relay station detector")
    p.add_argument("--base", required=True, help="upstream base URL, e.g. https://api.example.com")
    p.add_argument("--key", required=True, help="API key")
    p.add_argument("--model", required=True, help="target model id")
    p.add_argument("--provider", default=None, help="optional provider override")
    p.add_argument("--rounds", type=int, default=11)
    p.add_argument("--budget", type=float, default=0.5, help="USD budget cap")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true", help="emit raw JSON only")
    return p.parse_args(argv)


def _format_pretty(report: dict) -> str:
    lines = [
        f"Verdict: {report['verdict']}",
        f"Score:   {report['score']}/100",
        f"Model:   {report.get('summary_en', '')}",
        "",
        "Dimensions:",
    ]
    for name, dim in report["dimensions"].items():
        lines.append(f"  - {name:<22} {dim['score']:>3}  [{dim['status']}]")
    lines.append("")
    lines.append(f"Cost:     ${report['actual_cost_usd']:.4f}")
    lines.append(f"Duration: {report['duration_ms']} ms")
    if report.get("over_budget"):
        lines.append("[!] over_budget=true")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    install_global_filter()

    req = DetectRequest(
        base_url=args.base,
        api_key=args.key,
        model=args.model,
        expected_provider=args.provider,
        rounds=args.rounds,
        budget_usd=args.budget,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        resp = asyncio.run(run_detection(req))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    body = resp.model_dump()
    if args.json:
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(_format_pretty(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
