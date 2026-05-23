"""Run detection against a list of targets and dump a markdown summary."""
import json
import sys
import time
from pathlib import Path

import httpx

TARGETS = json.loads(Path(__file__).with_name("targets.json").read_text(encoding="utf-8"))
DETECTOR_URL = "http://127.0.0.1:8800/detect"
MODEL = "claude-sonnet-4-6"
ROUNDS = 6
BUDGET_USD = 0.15


def run_one(target):
    body = {
        "base_url": target["base"],
        "api_key": target["key"],
        "model": MODEL,
        "rounds": ROUNDS,
        "budget_usd": BUDGET_USD,
    }
    t0 = time.monotonic()
    try:
        r = httpx.post(DETECTOR_URL, json=body, timeout=120.0)
        r.raise_for_status()
        elapsed = int((time.monotonic() - t0) * 1000)
        return {"label": target["label"], "ok": True, "elapsed_ms": elapsed, "data": r.json()}
    except httpx.HTTPStatusError as e:
        return {
            "label": target["label"], "ok": False,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}",
        }
    except Exception as e:
        return {"label": target["label"], "ok": False, "error": str(e)}


def main():
    results = []
    for t in TARGETS:
        print(f"[run] {t['label']} ...", flush=True)
        res = run_one(t)
        if res["ok"]:
            d = res["data"]
            print(f"  -> verdict={d['verdict']} score={d['score']} cost=${d['actual_cost_usd']:.4f}")
        else:
            print(f"  -> ERROR: {res['error']}")
        results.append(res)
    Path(__file__).with_name("results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {len(results)} results to results.json")


if __name__ == "__main__":
    sys.exit(main() or 0)
