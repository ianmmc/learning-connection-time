#!/usr/bin/env python3
"""Immutable, fingerprinted Stage-5 config artifact — the promotable unit (#213, epic #209 Phase 2).

**The gap this closes.** Today "the Stage-5 config" is split across two homes with different visibility:
the knob JSON files under `CONFIG_DIR` (hashed by `harness.fingerprints`'s `config` field) AND
`detectors.DEFAULT_DETECTOR_PARAMS` — a **Python constant the fingerprint never sees**. So the frontier
grid tunes `table_min_times`/`table_min_periods`/`neg_dom_min`, but a change to them does NOT move the
config fingerprint: two materially different configs can carry the *same* fingerprint. That is fine while
a human eyeballs every change; it is unsafe the moment promotion is even semi-automated (you cannot roll
back to, or refuse to load, a version you cannot name).

**What an artifact is.** A single self-contained, immutable JSON object capturing the WHOLE tunable
surface — the detector params inline **and** a snapshot of every `CONFIG_DIR` knob doc — plus the GT
version it was validated against. Its `version` is a **content fingerprint** over that surface, so it is
content-addressed and finally includes the detector params. Two artifacts with the same surface + GT have
the same `version` regardless of when built; `created_at`/provenance are metadata, never part of identity.

**Why embed the knob snapshot (not just fingerprint it).** The user's decision (2026-07-10) is artifacts
in git, pointers in the DB. A self-contained artifact makes rollback EXACT — restoring `@fallback` doesn't
depend on git archaeology or on a live knob file not having drifted. Knob docs are small (keyword lists);
the honesty is worth the bytes.

**Semver drives the validation burden** (#213 / FINDINGS §2): `classify_change` labels a champion→challenger
diff patch / minor / major — patch (a detector-param threshold tweak) needs only the cheap gates; minor
(a knob-list/weight change) and major (a structural key change) need the full #212 group-aware statistical
gate. `verify_on_load` is the refuse-to-run guard (GT/fingerprint mismatch → raise), the COUNCIL_LAB §5a
twin for Stage-5 configs.

PURE CORE + a thin I/O shell (reads `CONFIG_DIR` + `detectors`), mirroring `tuning_ledger.py`. No DB, no
network. Design authority: STAGE5_FILTER_DESIGN §5c (to be written); issue #213; FINDINGS-AND-DECISIONS §2.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import paths  # noqa: E402

SCHEMA = "stage5-config-artifact/v1"
_CHANGE_ORDER = ("none", "patch", "minor", "major")   # increasing validation burden


class ArtifactVerificationError(RuntimeError):
    """Raised by `verify_on_load` when an artifact does not match the live environment (a changed GT, or a
    fingerprint that no longer matches its content). The refuse-to-run guard — a config validated against a
    different ground truth, or a tampered/corrupted artifact, must never silently drive the live pipeline."""


def _h(s):
    """md5[:12] over a string — the codebase's fingerprint convention (harness._h), reused so config
    fingerprints read the same everywhere."""
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()[:12]


def canonical_json(obj):
    """Deterministic serialization for fingerprinting: sorted keys, compact separators. The SAME surface
    always serializes identically, so its content fingerprint is stable across processes/machines/time."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ----------------------------- pure core (testable, no I/O) -----------------------------
def surface_fingerprint(detector_params, knobs, gt_version):
    """The content fingerprint that IS the artifact `version` — over the full tunable surface (detector
    params + knob snapshot) AND the GT it was validated against. Includes detector_params, the thing the
    live `harness.fingerprints` config hash omits — the whole point of #213."""
    return _h(canonical_json({"detector_params": detector_params, "knobs": knobs, "gt_version": gt_version}))


def build_artifact(detector_params, knobs, gt_version, *, semver, created_at=None,
                   provenance=None, parent=None):
    """Assemble an immutable artifact from an explicit tunable surface. `detector_params` is any params dict
    (NOT necessarily the live constant — a challenger holds its own), `knobs` is {knob_name: full_doc},
    `gt_version` is the label-set fingerprint the config was validated against. `version` is the content
    fingerprint — deliberately independent of `created_at`/`provenance` so identical surfaces share a
    version (content-addressed). `semver` is the human version string; `parent` is the prior version this
    descends from (lineage). Pure: `created_at` is passed in (the shell stamps it), never read from a clock
    here, so the same inputs build byte-identical artifacts in a test."""
    version = surface_fingerprint(detector_params, knobs, gt_version)
    return {
        "schema": SCHEMA,
        "version": version,
        "semver": semver,
        "created_at": created_at,
        "gt_version": gt_version,
        "detector_params": detector_params,
        "knobs": knobs,
        "parent": parent,
        "provenance": provenance or {},
    }


def recompute_version(artifact):
    """The `version` an artifact's stored content SHOULD have — recompute from its own surface. If this
    differs from the stored `version`, the artifact was hand-edited/corrupted after freezing (immutability
    broken). Used by `verify_on_load`."""
    return surface_fingerprint(artifact["detector_params"], artifact["knobs"], artifact["gt_version"])


def classify_change(old, new):
    """Classify a champion→challenger diff → 'none' | 'patch' | 'minor' | 'major', the level that sets the
    validation burden (#213):
      - none  : identical surface (same version).
      - patch : ONLY detector-param VALUES changed (same knob docs, same param key set) — cheap gates only.
      - minor : a knob DOC changed (a keyword list/weight edited), key sets unchanged — full statistical gate.
      - major : a structural key change — a knob added/removed, or a detector-param key added/removed — full
                gate + human (a new dimension is not a like-for-like comparison).
    A GT-version change is orthogonal (handled by `verify_on_load`), not a config semver level."""
    if old["version"] == new["version"]:
        return "none"
    old_knob_keys, new_knob_keys = set(old["knobs"]), set(new["knobs"])
    old_param_keys, new_param_keys = set(old["detector_params"]), set(new["detector_params"])
    if old_knob_keys != new_knob_keys or old_param_keys != new_param_keys:
        return "major"
    if old["knobs"] != new["knobs"]:
        return "minor"
    # same knob docs, same key sets, different version -> only detector-param values moved
    return "patch"


def bump_semver(old_semver, change_type):
    """Bump a MAJOR.MINOR.PATCH string by the classified change level. 'none' returns it unchanged. Raises
    on a malformed input or an unknown change_type — a version string must stay well-formed to be a pointer
    target."""
    if change_type not in _CHANGE_ORDER:
        raise ValueError(f"change_type must be one of {_CHANGE_ORDER} (got {change_type!r})")
    parts = str(old_semver).split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"semver must be MAJOR.MINOR.PATCH of integers (got {old_semver!r})")
    major, minor, patch = (int(p) for p in parts)
    if change_type == "none":
        return f"{major}.{minor}.{patch}"
    if change_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if change_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major + 1}.0.0"                       # major


def requires_full_gate(change_type):
    """Does this change level need the full #212 group-aware statistical gate (minor/major), or only the
    cheap gates (patch)? The cost governor on the promotion machinery — a param tweak isn't worth a bootstrap
    battery, a structural change always is. 'none' needs nothing (there is no change to gate)."""
    return change_type in ("minor", "major")


def verify_on_load(artifact, *, live_gt_version, strict_gt=True):
    """Refuse-to-run guard (COUNCIL_LAB §5a twin). Raises `ArtifactVerificationError` when the artifact does
    not match the live environment:
      - its recomputed `version` != the stored `version` (the artifact was mutated after freezing), OR
      - `strict_gt` and its `gt_version` != `live_gt_version` (validated against a DIFFERENT ground truth —
        the labels moved under it, so its non-inferiority proof no longer applies to the live GT).
    Returns the artifact unchanged when it verifies, so callers can `cfg = verify_on_load(...)` inline."""
    recomputed = recompute_version(artifact)
    if recomputed != artifact.get("version"):
        raise ArtifactVerificationError(
            f"artifact fingerprint mismatch: stored version={artifact.get('version')} but its content "
            f"hashes to {recomputed} — the artifact was modified after freezing (immutability violated).")
    if strict_gt and artifact.get("gt_version") != live_gt_version:
        raise ArtifactVerificationError(
            f"GT-version mismatch: artifact validated against gt_version={artifact.get('gt_version')} but "
            f"the live GT is {live_gt_version} — its non-inferiority proof does not apply to the current "
            f"ground truth. Re-validate under the live GT before loading.")
    return artifact


# ----------------------------- I/O shell (reads CONFIG_DIR + detectors) -----------------------------
def read_knobs(config_dir=None):
    """Snapshot every knob doc under CONFIG_DIR as {knob_name: full_doc} — the embedded, self-contained
    config surface. Sorted by name for a deterministic snapshot."""
    cdir = Path(config_dir or paths.CONFIG_DIR)
    return {p.stem: json.loads(p.read_text()) for p in sorted(cdir.glob("*.json"))}


def live_detector_params():
    """The live detector-param constant — imported lazily so the pure core has no hard dep on detectors."""
    from infrastructure.acquisition.stage5_filter import detectors as DET
    return dict(DET.DEFAULT_DETECTOR_PARAMS)


def current_artifact(gt_version, *, semver, detector_params=None, config_dir=None, created_at=None,
                     provenance=None, parent=None):
    """Build an artifact from the LIVE tunable surface (the live detector-param constant unless overridden +
    the current CONFIG_DIR knob snapshot). `created_at` defaults to now (the I/O shell may read a clock —
    the pure `build_artifact` never does)."""
    stamp = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_artifact(detector_params if detector_params is not None else live_detector_params(),
                          read_knobs(config_dir), gt_version, semver=semver, created_at=stamp,
                          provenance=provenance, parent=parent)
