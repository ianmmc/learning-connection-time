#!/usr/bin/env python3
"""Stage 2 headless CLI smoke test (REQ-104) — run this in a PLAIN terminal, not inside a Claude
Code session (nested `claude` is blocked). It exercises the real `claude -p` path the governance
server will use, and DUMPS THE RAW ENVELOPE so we can confirm two unknowns before trusting the
runner:

  1. Does headless `--allowedTools WebSearch` actually fire WebSearch and return real URLs?
  2. Where does `--json-schema` output land in the `--output-format json` envelope?
     (headless._extract_result_payload currently guesses with fallbacks — this pins it.)

Usage (from repo root):
    python3 scripts/stage2_cli_smoke.py            # step 1 (trivial, no web) + step 2 (1 district, web)
    python3 scripts/stage2_cli_smoke.py --schema-only   # just the fast no-web envelope probe

It does NOT write anything to data/raw or the registry — pure observation.
"""
import argparse
import json
import subprocess
import sys

from infrastructure.acquisition.stage2_discover import headless as H
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import paths


def _raw_cli(prompt: str, *, allow_websearch: bool, model="haiku", effort="low", timeout=420):
    cmd = ["claude", "-p", "--model", model, "--effort", effort,
           "--output-format", "json", "--json-schema", json.dumps(H.WAVE1_SCHEMA),
           "--strict-mcp-config", "--disable-slash-commands"]
    if allow_websearch:
        cmd += ["--allowedTools", "WebSearch"]
    print(f"\n$ {' '.join(cmd[:6])} … (prompt on stdin, websearch={allow_websearch})", file=sys.stderr)
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          timeout=timeout, cwd=str(paths.REPO_ROOT))
    print(f"--- exit {proc.returncode} ---", file=sys.stderr)
    if proc.stderr.strip():
        print("STDERR:\n" + proc.stderr[:2000], file=sys.stderr)
    print("RAW STDOUT:\n" + proc.stdout[:6000])
    try:
        env = json.loads(proc.stdout)
        print("\nENVELOPE KEYS:", sorted(env.keys()))
        print("PARSED BY headless._extract_result_payload:")
        print(json.dumps(H._extract_result_payload(env), indent=2)[:3000])
    except Exception as e:
        print(f"\n[!] could not parse/extract: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema-only", action="store_true", help="only the fast no-web envelope probe")
    a = ap.parse_args()

    print("=" * 70 + "\nSTEP 1 — trivial json-schema probe (no WebSearch, fast)\n" + "=" * 70)
    _raw_cli('Return a JSON object: district_id "TEST123", domain "example.org", schools [].',
             allow_websearch=False, timeout=120)
    if a.schema_only:
        return

    print("\n" + "=" * 70 + "\nSTEP 2 — one real district, headless WebSearch\n" + "=" * 70)
    # A tiny real district from batch_00002's receipt (first one), 1 school only to keep it quick.
    batch = H.load_batch_any("batch_00002")
    d = batch["districts"][0]
    roster = D2.build_roster(d)[:1]   # just the first school for the smoke test
    print(f"District: {d['name']} ({d['district_id']}) domain={d.get('domain')!r}  "
          f"school={roster[0]['school'] if roster else '—'}", file=sys.stderr)
    _raw_cli(H.build_wave1_prompt(d, roster), allow_websearch=True)


if __name__ == "__main__":
    main()
