"""Stage 7 — Extract: the paid OpenRouter council (REQ-117).

Independent stage package (common-only imports, enforced by import-linter). Holds the
Stage-7-specific pure pieces: the paid OpenRouter client (`openrouter.py`) and the model-output
parser (`parse.py`). The cross-stage orchestration that wires Stage 6's request assembly and
Stage 8's consensus into a run lives in the APP layer (`process_governance/stage7_run.py`),
mirroring `stage6_dispatch.py` — because stages may not import each other, only the app may.
"""
