"""Render the 6 detection runs into a comparison table + per-target detail."""
import json
from pathlib import Path

base = Path(__file__).parent
results = json.loads((base / "results.json").read_text(encoding="utf-8"))

# patch in anti0.3 retry result
anti = json.loads((base / "anti03.json").read_text(encoding="utf-8-sig"))
for i, r in enumerate(results):
    if "anti0.3" in r["label"] and not r["ok"]:
        results[i] = {"label": r["label"], "ok": True, "elapsed_ms": 27566, "data": anti}

(base / "results_full.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

DIM_NAMES = ["online", "identity_consistency", "wrapper_detection", "token_billing", "tool_use"]
print("\n" + "=" * 115)
header = (
    f"{'TARGET':<35} {'VERDICT':<18} {'SCORE':<6} "
    f"{'ON':<4} {'ID':<4} {'WRAP':<5} {'TOK':<4} {'TUSE':<5} {'COST':<9} {'ELAPSED'}"
)
print(header)
print("=" * 115)
for r in results:
    if not r["ok"]:
        print(f"{r['label']:<35} {'ERROR':<18} {'-':<6} {r['error'][:60]}")
        continue
    d = r["data"]
    dims = d["dimensions"]
    on = dims.get("online", {}).get("score", "-")
    idn = dims.get("identity_consistency", {}).get("score", "-")
    wrap = dims.get("wrapper_detection", {}).get("score", "-")
    tok = dims.get("token_billing", {}).get("score", "-")
    tu = dims.get("tool_use", {}).get("score", "-")
    cost = f"${d['actual_cost_usd']:.4f}"
    elapsed = f"{d['duration_ms']}ms"
    row = (
        f"{r['label']:<35} {d['verdict']:<18} {d['score']:<6} "
        f"{on:<4} {idn:<4} {wrap:<5} {tok:<4} {tu:<5} {cost:<9} {elapsed}"
    )
    print(row)

print("\n--- legend: ON=online ID=identity WRAP=wrapper_detection TOK=token_billing TUSE=tool_use ---\n")

print("\n" + "="*100)
print("PER-DIMENSION DETAIL (status + key evidence)")
print("="*100)
for r in results:
    if not r["ok"]:
        continue
    d = r["data"]
    print(f"\n### {r['label']}")
    print(f"  verdict={d['verdict']} score={d['score']} cost=${d['actual_cost_usd']:.4f}")
    for name, dim in d["dimensions"].items():
        ev = dim.get("evidence", {})
        bits = []
        if name == "online":
            bits.append(f"models_ok={ev.get('models_endpoint_ok')}")
            bits.append(f"chat_ok={ev.get('chat_endpoint_ok')}")
            bits.append(f"resp={ev.get('sample_response_excerpt','')[:50]!r}")
        elif name == "identity_consistency":
            bits.append(f"expected_hits={ev.get('expected_hits')}")
            bits.append(f"forbidden_hits={ev.get('forbidden_hits')}")
            bits.append(f"rounds={ev.get('rounds_completed')}")
        elif name == "wrapper_detection":
            bits.append(f"injection={ev.get('injection_size')}")
            bits.append(f"cache_read={ev.get('cache_read_input_tokens')}")
            bits.append(f"interp={ev.get('interpretation','')!r}")
        elif name == "token_billing":
            bits.append(f"expected={ev.get('expected')}")
            bits.append(f"effective={ev.get('observed_median_effective')}")
            bits.append(f"cache_read={ev.get('observed_median_cache_read')}")
            bits.append(f"deviation={ev.get('deviation_pct')}%")
        elif name == "tool_use":
            tc = ev.get('tool_calls', [])
            bits.append(f"tool_calls={tc[:1]}")
            if not tc:
                bits.append(f"text_resp={ev.get('response_excerpt','')[:80]!r}")
        print(f"  - {name:<22} {dim['status']:<10} score={dim['score']:>3}  {' '.join(bits)}")
    if d.get("warnings"):
        print(f"  warnings: {d['warnings']}")
