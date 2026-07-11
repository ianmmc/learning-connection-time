"""#213 / epic #209 Phase 2 — the immutable, fingerprinted Stage-5 config artifact.

The executable spec of the promotable unit: a self-contained artifact that captures the WHOLE tunable
surface (detector params INLINE + a knob snapshot) + the GT it was validated against, content-addressed by
a `version` fingerprint. These tests pin the gap this closes (detector params, invisible to
`harness.fingerprints`, ARE in the artifact identity), the semver classification that drives validation
burden, and the refuse-to-run load guard. Pure functions + a CONFIG_DIR read; no DB."""
import pytest

from infrastructure.acquisition.stage5_filter import config_artifact as CA  # noqa: E402

_DP = {"table_min_times": 4, "table_min_periods": 2, "neg_dom_min": 2}
_KNOBS = {"stage5_neg_board": {"entries": [{"value": "agenda"}]}}


def _artifact(dp=None, knobs=None, gt="gtV1", semver="1.0.0", created_at="2026-07-10T00:00:00Z"):
    return CA.build_artifact(dp or _DP, knobs or _KNOBS, gt, semver=semver, created_at=created_at)


# ----------------------------- identity: content-addressed, detector-params-inclusive -----------------------------
def test_version_is_independent_of_created_at_and_provenance():
    # Two artifacts with the same tunable surface + GT are the SAME version, whenever/however built.
    a = CA.build_artifact(_DP, _KNOBS, "gtV1", semver="1.0.0", created_at="2026-07-10T00:00:00Z")
    b = CA.build_artifact(_DP, _KNOBS, "gtV1", semver="9.9.9", created_at="2099-01-01T00:00:00Z",
                          provenance={"by": "someone"})
    assert a["version"] == b["version"]                   # content-addressed, not time/metadata-addressed


def test_a_detector_param_change_moves_the_version_the_gap_this_closes():
    # The whole point of #213: DEFAULT_DETECTOR_PARAMS is a Python constant harness.fingerprints never sees,
    # so a change to it does NOT move the config fingerprint. In an artifact it MUST.
    a = _artifact()
    b = _artifact(dp={**_DP, "table_min_times": 5})
    assert a["version"] != b["version"]


def test_a_knob_change_and_a_gt_change_both_move_the_version():
    a = _artifact()
    assert _artifact(knobs={"stage5_neg_board": {"entries": [{"value": "minutes"}]}})["version"] != a["version"]
    assert _artifact(gt="gtV2")["version"] != a["version"]


def test_recompute_version_matches_a_freshly_built_artifact():
    a = _artifact()
    assert CA.recompute_version(a) == a["version"]


# ----------------------------- semver classification -> validation burden -----------------------------
def test_classify_none_for_an_identical_surface():
    assert CA.classify_change(_artifact(), _artifact(semver="1.0.1")) == "none"


def test_classify_gt_only_change_is_none_not_patch():
    # PR #220 review: gt_version moves the content fingerprint, so the old version-inequality shortcut
    # sent a gt-only diff down the 'patch' branch — routing two artifacts validated against DIFFERENT
    # ground truths into the cheap in-memory gate. GT drift is verify_on_load's / the flow's concern;
    # an identical tunable surface is 'none' regardless of gt.
    old, new = _artifact(gt="gtA"), _artifact(gt="gtB")
    assert old["version"] != new["version"]              # the fingerprint DOES move (identity is gt-aware)
    assert CA.classify_change(old, new) == "none"        # ...but the config surface did not change


def test_classify_patch_for_a_detector_param_value_change():
    old, new = _artifact(), _artifact(dp={**_DP, "neg_dom_min": 3})
    assert CA.classify_change(old, new) == "patch"
    assert CA.requires_full_gate("patch") is False        # cheap gates only


def test_classify_minor_for_a_knob_doc_change():
    old = _artifact()
    new = _artifact(knobs={"stage5_neg_board": {"entries": [{"value": "budget"}]}})
    assert CA.classify_change(old, new) == "minor"
    assert CA.requires_full_gate("minor") is True         # full #212 statistical gate


def test_classify_major_for_a_structural_key_change():
    old = _artifact()
    # a knob added
    assert CA.classify_change(old, _artifact(knobs={**_KNOBS, "stage5_neg_new": {}})) == "major"
    # a detector-param dimension added
    assert CA.classify_change(old, _artifact(dp={**_DP, "new_knob": 1})) == "major"
    assert CA.requires_full_gate("major") is True


def test_bump_semver_by_level():
    assert CA.bump_semver("1.2.3", "none") == "1.2.3"
    assert CA.bump_semver("1.2.3", "patch") == "1.2.4"
    assert CA.bump_semver("1.2.3", "minor") == "1.3.0"
    assert CA.bump_semver("1.2.3", "major") == "2.0.0"


def test_bump_semver_rejects_malformed_input_and_unknown_level():
    # #204: match the MESSAGE, not just ValueError — the validation is `len != 3 OR not all-digit`; an
    # `and` mutant would fall through to an unpack/int ValueError with a different (opaque) message.
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        CA.bump_semver("1.2", "patch")                     # not MAJOR.MINOR.PATCH
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        CA.bump_semver("1.2.x", "patch")                   # non-integer
    with pytest.raises(ValueError, match="change_type"):
        CA.bump_semver("1.2.3", "rewrite")                 # unknown change level


def test_build_artifact_defaults_provenance_to_an_empty_dict():
    # #204: `provenance or {}` — omitting provenance yields {}, not None (an `and` mutant would give None).
    a = CA.build_artifact(_DP, _KNOBS, "gt", semver="1.0.0", created_at="x")
    assert a["provenance"] == {}


# ----------------------------- verify_on_load: the refuse-to-run guard -----------------------------
def test_verify_passes_and_returns_the_artifact_on_a_clean_match():
    a = _artifact(gt="gtLIVE")
    assert CA.verify_on_load(a, live_gt_version="gtLIVE") is a


def test_verify_raises_when_the_live_gt_moved_under_the_artifact():
    a = _artifact(gt="gtV1")
    with pytest.raises(CA.ArtifactVerificationError, match="GT-version mismatch"):
        CA.verify_on_load(a, live_gt_version="gtV2")
    # strict_gt=False bypasses the GT check (e.g. a deliberate cross-GT inspection), fingerprint still enforced
    assert CA.verify_on_load(a, live_gt_version="gtV2", strict_gt=False) is a


def test_verify_raises_when_the_artifact_content_was_mutated_after_freezing():
    a = _artifact()
    tampered = {**a, "detector_params": {**_DP, "neg_dom_min": 9}}   # content changed, version now stale
    with pytest.raises(CA.ArtifactVerificationError, match="fingerprint mismatch"):
        CA.verify_on_load(tampered, live_gt_version=a["gt_version"])


# ----------------------------- I/O shell (reads the real CONFIG_DIR knob files) -----------------------------
def test_current_artifact_reads_the_live_surface_and_is_verifiable():
    a = CA.current_artifact("gtLIVE", semver="1.0.0", created_at="2026-07-11T00:00:00Z")
    assert a["schema"] == CA.SCHEMA
    assert a["detector_params"] == CA.live_detector_params()
    assert "stage5_neg_board" in a["knobs"]                # a real knob doc was snapshotted
    assert a["created_at"] == "2026-07-11T00:00:00Z"       # #204: an explicit created_at passes through (not now())
    assert CA.verify_on_load(a, live_gt_version="gtLIVE")["version"] == a["version"]


def test_current_artifact_honors_a_detector_params_override():
    base = CA.current_artifact("gtLIVE", semver="1.0.0", created_at="x")
    chall = CA.current_artifact("gtLIVE", semver="1.0.1", created_at="x",
                                detector_params={**CA.live_detector_params(), "table_min_times": 5})
    assert CA.classify_change(base, chall) == "patch"      # same knobs, one detector-param value moved
