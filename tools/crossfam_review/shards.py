"""Enumerate the review surface and bin it into coherent, context-sized shards.

"Everyone reviews everything" (Ian, 2026-07-13) can't be one 800k-token blob — several finders have
~200k context windows, and a focused shard produces better review than a haystack anyway. So each
finder reviews every SHARD: a coherent slice of the codebase (one module, or a numbered split of a
big one), files kept WHOLE, under a token budget every finder's window can hold.

Discovery is by walking the tree, NOT a hardcoded file list — "leave no gaps" (Ian) means a newly
added source file is picked up automatically on the next run rather than silently skipped. The walk
is deterministic (sorted) so shard membership and the council's per-candidate rotation are stable and
re-runnable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Repo root = two parents up from this file (tools/crossfam_review/shards.py).
REPO_ROOT = Path(__file__).resolve().parents[2]

# Roots of the review surface. Everything code is on the table (Ian); docs are context, not targets.
SURFACE_ROOTS = ["infrastructure", "tests"]
SOURCE_SUFFIXES = {".py", ".js", ".mjs"}

# Directories never worth a model's tokens — generated, vendored, archived, or binary caches.
EXCLUDE_DIR_PARTS = {
    "__pycache__", "node_modules", ".git", "archive", "data", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "migrations_backup", "dist", "build",
}

# ~4 chars/token is the usual rough English/code ratio; good enough for binning + estimate (actual
# spend is billed on real tokens). Deliberately a slight over-estimate so shards stay UNDER a window.
CHARS_PER_TOKEN = 4
# Target shard size. Comfortably inside the smallest finder window (~200k) with room for the review
# prompt and the model's own output; small enough to keep the review focused. A single file larger
# than this becomes its own (oversized) shard — we never split a file, since a half-function is
# un-reviewable; only the ≥200k-window finders will read such a shard fully.
SHARD_TOKEN_BUDGET = 60_000


@dataclass
class Shard:
    shard_id: str
    title: str            # human/label — the module this slice covers
    area_label: str       # the GitHub area:* label for findings rooted here (best-effort; triage refines)
    files: list[Path] = field(default_factory=list)   # absolute paths, whole files
    est_tokens: int = 0

    def rel_files(self) -> list[str]:
        return [str(p.relative_to(REPO_ROOT)) for p in self.files]

    def render(self) -> str:
        """The shard as one review payload: each file under a `===== path =====` banner, **every line
        prefixed with its own 1-based line number** (`   123\\tcode`). The line numbers are essential —
        without them a finder guesses line numbers by counting across a multi-file blob and is wildly
        off (server.py:766 reported as :425 in the 2026-07-13 smoke), which then misaligns dedup and
        the judge's code context and gets every finding refuted. Numbering is per-file (restarts at 1),
        matching `council.code_context` so the number a finder cites indexes the same line the judge
        later reads from the real file."""
        blocks = []
        for p in self.files:
            rel = p.relative_to(REPO_ROOT)
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                body = "\n".join(f"{i + 1:>6}\t{ln}" for i, ln in enumerate(lines))
            except Exception as e:  # unreadable file — record it, don't abort the shard
                body = f"<<could not read: {e}>>"
            blocks.append(f"===== {rel} =====\n{body}")
        return "\n\n".join(blocks)


def _est_tokens(path: Path) -> int:
    try:
        return max(1, path.stat().st_size // CHARS_PER_TOKEN)
    except OSError:
        return 1


def _area_label(rel: str) -> str:
    """Best-effort map from a repo-relative path to an existing GitHub area:* label. Triage (Opus)
    refines mislabels; this only seeds the auto-file so findings land roughly-sorted, not unlabeled."""
    r = rel.replace("\\", "/")
    # Order matters: most specific stage buckets before the coarse fallbacks.
    if any(s in r for s in ("stage7_extract", "stage8_aggregate", "stage9")):
        return "area:stage7-9"
    if any(s in r for s in ("stage5_filter", "stage6_handoff", "process_governance")):
        return "area:stage5-6"
    if any(s in r for s in ("stage1_queue", "stage2_discover", "stage3", "stage4", "scraper")):
        return "area:stage1-4"
    if any(s in r for s in ("scripts/analyze", "database", "state_requirements", "crosswalk")):
        return "area:lct-core"
    if r.startswith("tests/"):
        return "area:hygiene"
    return "area:stage5-6"  # common/, misc infrastructure — cross-cutting; default, triage refines


def _module_key(rel: str) -> tuple:
    """Group files by their module directory so a shard is one coherent unit. Uses the path up to
    (but not including) the filename, capped at 3 segments deep so we don't over-fragment."""
    parts = Path(rel).parts[:-1]
    return parts[:3] or ("<root>",)


def build_shards(root: Path | None = None, budget: int = SHARD_TOKEN_BUDGET) -> list[Shard]:
    """Discover all source files under the surface roots and bin them into shards, grouped by module
    and kept under `budget` tokens. Deterministic (sorted) for stable, re-runnable shard identity."""
    base = root or REPO_ROOT
    files: list[Path] = []
    for r in SURFACE_ROOTS:
        rd = base / r
        if not rd.exists():
            continue
        for p in rd.rglob("*"):
            if p.suffix not in SOURCE_SUFFIXES or not p.is_file():
                continue
            if any(part in EXCLUDE_DIR_PARTS for part in p.relative_to(base).parts):
                continue
            files.append(p)
    files.sort()

    # Bin per module directory; split a module across numbered shards when it overflows the budget.
    groups: dict[tuple, list[Path]] = {}
    for p in files:
        groups.setdefault(_module_key(str(p.relative_to(base))), []).append(p)

    shards: list[Shard] = []
    for key in sorted(groups):
        title = "/".join(key)
        cur: list[Path] = []
        cur_tok = 0
        part = 1

        def flush():
            nonlocal cur, cur_tok, part
            if not cur:
                return
            sid = title.replace("/", ".") + (f"~{part}" if part > 1 or cur_tok > budget else "")
            area = _area_label(str(cur[0].relative_to(base)))
            shards.append(Shard(shard_id=sid, title=title, area_label=area,
                                files=list(cur), est_tokens=cur_tok))
            part += 1
            cur, cur_tok = [], 0

        for p in groups[key]:
            tok = _est_tokens(p)
            # A single file over budget gets its own shard (files are never split).
            if tok >= budget:
                flush()
                cur, cur_tok = [p], tok
                flush()
                continue
            if cur_tok + tok > budget:
                flush()
            cur.append(p)
            cur_tok += tok
        flush()

    return shards


def surface_summary(shards: list[Shard]) -> dict:
    return {
        "shards": len(shards),
        "files": sum(len(s.files) for s in shards),
        "est_tokens": sum(s.est_tokens for s in shards),
    }
