#!/bin/bash
# run_tables.sh - Benchmark the 4 local models on TABLE-AWARE input (pdfplumber/HTML tables).
# Runs throttled (background QoS) so it doesn't gum up interactive use. Test set = the 15
# vision-subset districts + the 2 mangled-table showcases (FL Orange 1201440, WY 5605302).
set -u
cd "$(dirname "$0")/../../.." || exit 1
RUNNER="infrastructure/scripts/benchmark/run_manifest_benchmark.py"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="data/benchmark_results/tables_run_${TS}.log"
mkdir -p data/benchmark_results

MODELS="mistral:7b qwen2.5:7b qwen2.5vl:7b llama3.1:8b"
TEST_SET="2507110,2307320,3200480,3904378,5000395,5400180,5400600,0200510,0200600,0100270,0102370,0102430,0408800,1100031,1000200,1201440,5605302"

# throttle watcher: keep ollama/llama-server in background QoS for the whole run
( while true; do
    for pid in $(pgrep -f "ollama serve") $(pgrep -f "llama-server"); do taskpolicy -b -p "$pid" 2>/dev/null; done
    sleep 20
  done ) &
WATCHER=$!
trap 'kill $WATCHER 2>/dev/null' EXIT

echo "===== TABLES SWEEP $TS =====" | tee -a "$LOG"
for m in $MODELS; do
  if ! ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$m"; then
    echo ">>> SKIP $m (not installed)" | tee -a "$LOG"; continue
  fi
  echo ">>> RUN $m (tables) @ $(date +%H:%M:%S)" | tee -a "$LOG"
  python3 "$RUNNER" --model "ollama:$m" --mode tables --districts "$TEST_SET" --delay 1 >> "$LOG" 2>&1 \
    && echo ">>> OK $m" | tee -a "$LOG" || echo ">>> FAIL $m -- continuing" | tee -a "$LOG"
done

echo "===== TABLES SWEEP DONE $(date -u +%Y%m%dT%H%M%SZ) =====" | tee -a "$LOG"
touch "data/benchmark_results/TABLES_DONE_${TS}"
