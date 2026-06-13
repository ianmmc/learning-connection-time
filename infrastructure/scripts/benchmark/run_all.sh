#!/bin/bash
# run_all.sh - Autonomous local benchmark sweep.
#
# Order is deliberate: the FAST, complete text lane runs first (so a full comparison is
# guaranteed even if the slow vision lane is interrupted), then vision models run in BOTH
# text and vision mode on a stratified SUBSET (clean per-model text-vs-vision lift).
#
# Resilient: a model that fails (missing pull, crash) is logged and skipped; the sweep
# continues. Writes a leaderboard and a DONE marker at the end.

set -u
cd "$(dirname "$0")/../../.." || exit 1
ROOT="$(pwd)"
RUNNER="infrastructure/scripts/benchmark/run_manifest_benchmark.py"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="data/benchmark_results/run_${TS}.log"
mkdir -p data/benchmark_results

# All candidates run in TEXT mode (image PDFs handled via OCR in reading.py).
TEXT_MODELS="llama3.1:8b qwen2.5:7b mistral:7b deepseek-v2:16b qwen2.5vl:7b llama3.2-vision:11b"
VISION_MODELS="qwen2.5vl:7b llama3.2-vision:11b"
RUN_VISION="${RUN_VISION:-0}"   # vision lane gated off until Ollama VLM context issue is resolved

# Stratified vision subset: all image-modality districts + a few pdf + a few html.
SUBSET="$(python3 - <<'PY'
import json
M=json.load(open("data/benchmark/ground_truth_manifest.json"))
img=[d["district_id"] for d in M["districts"] if "image" in d["modality"]]
pdf=[d["district_id"] for d in M["districts"] if "image" not in d["modality"] and "pdf" in d["modality"]][:5]
html=[d["district_id"] for d in M["districts"] if "html" in d["modality"]][:3]
print(",".join(dict.fromkeys(img+pdf+html)))
PY
)"

have() { ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$1"; }
run() {  # model  mode  [districts]
  local model="$1" mode="$2" dists="${3:-}"
  if ! have "$model"; then echo ">>> SKIP $model ($mode): not installed" | tee -a "$LOG"; return; fi
  echo ">>> RUN $model mode=$mode districts=${dists:-ALL} @ $(date +%H:%M:%S)" | tee -a "$LOG"
  local args=(--model "ollama:$model" --mode "$mode")
  [ -n "$dists" ] && args+=(--districts "$dists")
  python3 "$RUNNER" "${args[@]}" >> "$LOG" 2>&1 \
    && echo ">>> OK   $model ($mode)" | tee -a "$LOG" \
    || echo ">>> FAIL $model ($mode) -- continuing" | tee -a "$LOG"
}

{
  echo "===== BENCHMARK SWEEP START $TS ====="
  echo "subset (vision lane): $SUBSET"
  echo "text models: $TEXT_MODELS"
  echo "vision models: $VISION_MODELS"
} | tee -a "$LOG"

# TEXT LANE - all candidate models, all 41 districts
for m in $TEXT_MODELS; do run "$m" text ""; done

# VISION LANE - only if explicitly enabled (RUN_VISION=1); pending Ollama VLM context fix
if [ "$RUN_VISION" = "1" ]; then
  for m in $VISION_MODELS; do run "$m" vision "$SUBSET"; done
fi

echo "===== AGGREGATING @ $(date +%H:%M:%S) =====" | tee -a "$LOG"
python3 infrastructure/scripts/benchmark/compare_runs.py >> "$LOG" 2>&1

echo "===== SWEEP DONE $(date -u +%Y%m%dT%H%M%SZ) =====" | tee -a "$LOG"
touch "data/benchmark_results/DONE_${TS}"
