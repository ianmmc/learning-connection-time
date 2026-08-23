"""#717 — gate@6 subtracts reps a prior PRODUCTION run already bought.

gate@6 composition built from the CURRENT sendable set and never subtracted already-extracted
reps, so re-dispatching a district re-bought the full council on reps production had already
read — spend with zero informational gain, since REQ-160's earliest-wins merge guarantees the
duplicate result cannot change anything. Stage 3 has had this delta for capture since REQ-172
(`seedFromPriorCaptures`); this is its dispatch-layer sibling.

THE PREDICATE IS THE FIX, and it was chosen by measurement, not by intuition
(`docs/technical-notes/production-quality-control-research/2026-08-23-already-extracted-delta-measure.py`).
The obvious rule — "subtract reps from runs that recorded no errors" — is WRONG, because
`extraction.n_errors` is per (district, handoff), not per rep: one errored rep re-admits its whole
run, and district 3904378 went 7 reps -> 0. Measured, that rule needlessly re-buys 32 reps across
11 districts that demonstrably succeeded. The rule that ships uses a `school_fact` row as per-rep
PROOF that THAT rep was read, and re-admits only the 8 reps corpus-wide that both errored and
yielded nothing. `test_errored_run_subtracts_only_the_fact_proven_rep` is the falsifier: it fails
under the run-level rule and under no-rule-at-all alike.

DB-free tests follow test_stage6_production_eligibility's convention (session=None, readers
monkeypatched); the predicate's own tests drive a fake session against real receipts on disk, since
what it must get right is the receipt/DB JOIN rather than any SQL dialect.
"""
import json

import pytest

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import extraction_delta as XD
from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage5_filter import release as REL

REASON = BR.ALREADY_EXTRACTED_REASON


# --------------------------------------------------------------------------------------
# the predicate itself — a fake session over real receipts on disk
# --------------------------------------------------------------------------------------
class _FakeSession:
    """Answers the module's two statements by identity. Rows mirror the real column order:
    runs = (handoff_hash, n_errors, path); facts = (rec_key, source_file)."""

    def __init__(self, runs, facts):
        self._runs, self._facts = runs, facts

    def execute(self, stmt, params=None):
        return self._runs if stmt is XD._RUNS_SQL else self._facts


def _write_receipt(root, handoff_hash, district_id, reps, decision="send"):
    """A minimal but structurally REAL receipt — same shape `handoff.py` freezes."""
    path = root / f"handoff_{handoff_hash}_20260101T000000Z.json"
    path.write_text(json.dumps({
        "handoff_hash": handoff_hash, "created_at": "2026-01-01T00:00:00Z",
        "districts": [{"district_id": district_id, "records": [
            {"rec_key": rk, "decision": decision, "reps": [{"file": f}]} for rk, f in reps]}]}))
    return path


def test_clean_run_subtracts_every_rep_it_sent(tmp_path):
    """A run that recorded no errors read everything it was sent, so all of it is already bought —
    including a rep that yielded no fact (a clean read that simply found no times; re-buying it is
    deterministic waste, which is why the predicate is not just "has facts")."""
    _write_receipt(tmp_path, "h1", "D1", [("D1:a", "p.txt"), ("D1:b", "q.txt")])
    sess = _FakeSession([("h1", 0, None)], [("D1:a", "p.txt")])   # only `a` left a fact
    assert XD.already_extracted_reps(sess, "D1", root=tmp_path) == {
        ("D1:a", "p.txt"), ("D1:b", "q.txt")}


def test_errored_run_subtracts_only_the_fact_proven_rep(tmp_path):
    """THE falsifier (see the module docstring). One run, two reps, an error recorded at the run
    grain and a fact for exactly one rep. `a` provably got read -> already extracted. `b` may never
    have been -> stays sendable, a legitimate retry.

    Fails under the rejected run-level rule (which would subtract NEITHER, re-buying `a`) and under
    today's no-delta behaviour (which subtracts neither and re-buys both)."""
    _write_receipt(tmp_path, "h1", "D1", [("D1:a", "p.txt"), ("D1:b", "q.txt")])
    sess = _FakeSession([("h1", 1, None)], [("D1:a", "p.txt")])
    assert XD.already_extracted_reps(sess, "D1", root=tmp_path) == {("D1:a", "p.txt")}


def test_no_prior_production_run_never_narrows_a_first_dispatch(tmp_path):
    """A district nobody has dispatched must compose exactly as it does today."""
    assert XD.already_extracted_reps(_FakeSession([], []), "D1", root=tmp_path) == set()


def test_unreadable_receipt_degrades_to_fact_evidence_rather_than_stranding(tmp_path):
    """The receipt is the sent-set's only home, so an unreadable one could either strand a district
    (subtract everything) or re-buy it (subtract nothing). It does neither: the run still
    contributes its fact-proven reps. Over-spend is observable and reversible; a district that
    silently sends nothing is neither."""
    (tmp_path / "handoff_h1_20260101T000000Z.json").write_text("{ not json")
    sess = _FakeSession([("h1", 0, None)], [("D1:a", "p.txt")])
    assert XD.already_extracted_reps(sess, "D1", root=tmp_path) == {("D1:a", "p.txt")}


def test_a_composed_but_never_run_handoff_bought_nothing(tmp_path):
    """`_RUNS_SQL` selects from `extraction`, so a draft that was frozen but never extracted has no
    row and cannot suppress anything. Guarded here because the receipt EXISTS on disk for such a
    handoff — reading receipts alone would wrongly subtract it."""
    _write_receipt(tmp_path, "never_ran", "D1", [("D1:a", "p.txt")])
    assert XD.already_extracted_reps(_FakeSession([], []), "D1", root=tmp_path) == set()


def test_only_this_districts_reps_are_returned(tmp_path):
    """One receipt carries many districts (batch_00043's carried 7). A neighbour's reps must never
    suppress this district's — they are different documents that happen to share a dispatch."""
    path = tmp_path / "handoff_h1_20260101T000000Z.json"
    path.write_text(json.dumps({"handoff_hash": "h1", "districts": [
        {"district_id": "D1", "records": [
            {"rec_key": "D1:a", "decision": "send", "reps": [{"file": "p.txt"}]}]},
        {"district_id": "D2", "records": [
            {"rec_key": "D2:z", "decision": "send", "reps": [{"file": "z.txt"}]}]}]}))
    sess = _FakeSession([("h1", 0, None)], [])
    assert XD.already_extracted_reps(sess, "D1", root=tmp_path) == {("D1:a", "p.txt")}


def test_a_held_rep_was_never_bought(tmp_path):
    """Only `decision == "send"` reps cost anything. A record the composer HELD rode in the receipt
    for traceability and must stay sendable — the #679/#691 holds are exactly this shape."""
    _write_receipt(tmp_path, "h1", "D1", [("D1:a", "p.txt")], decision="hold")
    assert XD.already_extracted_reps(_FakeSession([("h1", 0, None)], []), "D1",
                                     root=tmp_path) == set()


# --------------------------------------------------------------------------------------
# composition — the delta as a gate@6 hold pass (readers + predicate monkeypatched)
# --------------------------------------------------------------------------------------
def _rec(rec_key, label="school_bell_table", files=("e.txt",)):
    return {"rec_key": rec_key, "url": f"http://x/{rec_key}", "tier": "A", "category": None,
            "signals": {"content_school_year": None}, "is_emergent": 0, "intended_schools": [],
            "label": label, "facets": {},
            "reps": [{"source": "extracted", "filename": f, "file_kind": "text",
                      "n_chars": 1000, "n_times": 26, "usable": 1} for f in files]}


def _patch(monkeypatch, records, already=frozenset()):
    monkeypatch.setattr(REL, "load_district",
                        lambda s, d: {"district_id": d, "name": "X", "state": "ZZ",
                                      "district_dir": "x", "labeled_topology": "mixed",
                                      "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, d: records)
    monkeypatch.setattr(BR.BM, "benchmark_provenance_rec_keys", lambda s, keys: set())
    monkeypatch.setattr(BR.XD, "already_extracted_reps",
                        lambda s, d, **kw: set(already))


def test_an_already_bought_rep_is_held_with_a_reason_not_dropped(monkeypatch):
    """THE acceptance case (#717): a district whose sendables were all extracted last week composes
    to an empty send set — and stays VISIBLE, reasoned, so the human sees it was considered. Four
    live specimens in batch_00043 alone (Little Rock, New Haven Unified, Washoe, Sweetwater)."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:a", "e.txt")})
    _, out = BR.district_release_input(None, "D717")
    assert [r["decision"] for r in out] == ["hold"]
    assert out[0]["reason"] == REASON
    assert out[0]["send"] == []


def test_a_rep_never_bought_still_sends(monkeypatch):
    """The delta only ever SUBTRACTS what a prior run bought, so it cannot strand new work."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:other", "e.txt")})
    _, out = BR.district_release_input(None, "D717")
    assert out[0]["decision"] == "send"


def test_a_sent_record_carries_exactly_one_rep_today(monkeypatch):
    """The premise behind the next test, pinned rather than assumed. `release.best_send` elects ONE
    rep per record, and the corpus agrees: 755 of 755 sent records across every frozen receipt
    carry exactly one rep (measured 2026-08-23), batch_00043's 34 included. So the per-rep
    subtraction below is DEFENSIVE, not a live path — stated plainly so a future reader does not
    mistake it for behaviour we have observed."""
    _patch(monkeypatch, [_rec("d:a", files=("one.txt", "two.txt"))])
    _, out = BR.district_release_input(None, "D717")
    assert len(out[0]["send"]) == 1


def test_partial_record_sends_only_the_unread_rep(monkeypatch):
    """DEFENSIVE (see above — no live record sends two reps). Held per REP, not per record: were a
    record ever to carry one rep bought last week beside a raster nobody has read, holding the
    whole record would strand the raster. `decide` is stubbed because no real input produces this
    shape; that stub is the honest way to reach the branch."""
    monkeypatch.setattr(REL, "decide", lambda rec: {
        "decision": "send", "reason": "test",
        "send": [{"file": "bought.txt", "kind": "text"}, {"file": "fresh.txt", "kind": "text"}]})
    _patch(monkeypatch, [_rec("d:a", files=("bought.txt", "fresh.txt"))],
           already={("d:a", "bought.txt")})
    _, out = BR.district_release_input(None, "D717")
    assert out[0]["decision"] == "send"
    assert [rp["file"] for rp in out[0]["send"]] == ["fresh.txt"]


def test_redo_readmits_every_already_extracted_rep(monkeypatch):
    """The declared-redo opt-in (REQ-170 posture) — a deliberate re-extraction must remain
    possible, and must reproduce today's pre-delta composition exactly."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:a", "e.txt")})
    _, out = BR.district_release_input(None, "D717", redo=True)
    assert out[0]["decision"] == "send"
    assert [rp["file"] for rp in out[0]["send"]] == ["e.txt"]


def test_a_benchmark_dispatch_never_subtracts(monkeypatch):
    """The Council Lab exists to re-extract the SAME reps under different councils (#679 already
    walls the two worlds apart); subtracting there would defeat its purpose."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:a", "e.txt")})
    _, out = BR.district_release_input(None, "D717", dispatch_type=BM.DISPATCH_BENCHMARK)
    assert out[0]["decision"] == "send"


def test_the_delta_runs_after_the_ranking_passes(monkeypatch):
    """Ordering is load-bearing, and in the OPPOSITE direction from #679's. The ranking passes
    (prefer-recent / sibling-variant / hub-priority) elect a winner among candidates; if the delta
    ran first it would remove a candidate from that contest and the district could compose a WORSE
    send rather than a cheaper one. Running last, it only ever subtracts from an already-made
    choice — it can change the price, never the choice.

    Here the labeled hub is already bought. Hub-priority must still crown it (holding the sibling
    for the 7->6 back-edge); the delta then holds the hub too. The district composes ZERO sends —
    NOT the sibling promoted in the hub's place, which is what an early delta would produce."""
    _patch(monkeypatch, [_rec("d:hub", label="district_hub_by_band"), _rec("d:sib")],
           already={("d:hub", "e.txt")})
    _, out = BR.district_release_input(None, "D717")
    by = {r["rec_key"]: r for r in out}
    assert by["d:hub"]["reason"] == REASON
    assert by["d:sib"]["decision"] == "hold"
    assert by["d:sib"]["reason"].startswith(BR.HUB_PRIORITY_REASON_PREFIX)
    assert [r["rec_key"] for r in out if r["decision"] == "send"] == []


# --------------------------------------------------------------------------------------
# the gate@6 cost preview — new vs re-extraction (#717 acceptance)
# --------------------------------------------------------------------------------------
def test_preview_separates_new_from_reextraction_spend_and_balances(monkeypatch):
    """The preview must price what you WILL pay separately from what the delta AVOIDED. The two
    are asserted to reconstruct the redo total exactly — a rep can be counted as new or as avoided,
    never as neither (silent loss) nor as both (double-counted savings)."""
    _patch(monkeypatch, [_rec("d:a"), _rec("d:b")], already={("d:a", "e.txt")})
    on = BR.release_bundle(None, ["D717"]).package
    off = BR.release_bundle(None, ["D717"], redo=True).package
    assert on["cost"]["reextraction"]["n_reps"] == 1
    assert on["cost"]["reextraction"]["usd"] > 0
    assert on["cost"]["n_reps"] + on["cost"]["reextraction"]["n_reps"] == off["cost"]["n_reps"]
    assert on["cost"]["total_usd"] + on["cost"]["reextraction"]["usd"] == \
        pytest.approx(off["cost"]["total_usd"])


def test_redo_reports_no_avoided_spend(monkeypatch):
    """Under redo every rep is priced as new, so the avoided figure must be a true zero rather than
    a stale leftover — the preview the human signs off has to mean what it says."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:a", "e.txt")})
    pkg = BR.release_bundle(None, ["D717"], redo=True).package
    assert pkg["cost"]["reextraction"] == {"n_reps": 0, "usd": 0.0}
    assert pkg["redo"] is True


def test_the_transient_delta_key_never_reaches_the_artifact(monkeypatch):
    """`ALREADY_EXTRACTED_KEY` carries the held reps to the pricing pass only. The frozen handoff is
    immutable and auditable; a private bookkeeping key leaking into it would become permanent."""
    _patch(monkeypatch, [_rec("d:a")], already={("d:a", "e.txt")})
    pkg = BR.release_bundle(None, ["D717"]).package
    assert BR.ALREADY_EXTRACTED_KEY not in json.dumps(pkg)


# --------------------------------------------------------------------------------------
# client <-> server rule literals (the arch-manifest boundary)
# --------------------------------------------------------------------------------------
def test_the_console_keys_its_held_row_on_the_servers_spelling():
    """DISPLAY, pinned as #679's and #691's are. The console has NO generic held-record row — it
    renders one block per known reason — so an unpinned reason string is not a cosmetic miss but
    total invisibility: the district would show a bare "no send-eligible records" and the reviewer
    could not tell "nothing found" from "we already have it". That is the state Ian's gate@6 call
    (show them, held, with the reason) exists to prevent, and it is four live districts wide on
    batch_00043."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/stage6.js").read_text()
    assert 'data-feat="s6-already-extracted"' in js
    assert 'data-feat="s6-already-extracted-summary"' in js
    assert REASON in js                                   # the client keys on the server's spelling
    assert "redo" in js                                   # the affordance is stated where the human acts


def test_the_console_renders_the_reextraction_split_from_server_numbers():
    """#717 acceptance: the preview separates new from re-extraction spend. Pinned on the payload
    key so a server rename cannot silently blank the line — and the client must READ `usd`, never
    re-price, since pricing lives in one place (the assembler)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/stage6.js").read_text()
    assert 'data-feat="s6-reextraction-avoided"' in js
    assert "cost.reextraction" in js


def test_redo_is_stamped_so_preview_and_freeze_agree(monkeypatch):
    """Same preview/freeze-parity discipline as `verified_only` and `dispatch_type` (#659): the
    flag rides ON the package, so the artifact records whether the delta applied."""
    _patch(monkeypatch, [_rec("d:a")], already=set())
    assert BR.release_bundle(None, ["D717"]).package["redo"] is False
