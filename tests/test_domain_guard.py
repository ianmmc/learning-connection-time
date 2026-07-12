"""#229 Stage-1 empty/junk-domain admission guard (pure logic — no DB, no NCES files, CI-safe).

A district whose NCES CCD `WEBSITE` cell yields no usable scoping domain must NOT enter a batch of
record: an unusable domain flips Stage 2 into its UNSCOPED, national-scope branch, which for common
school names pulls same-named schools nationwide into the candidate set (the Millard cross-district
contamination traced in #227). These tests pin the normalizer + validator (`domain_of` /
`is_scoping_domain`), the `build_batch` first-run guard against a monkeypatched pool, Stage 2's own
fail-closed defense (`gate_urls`), and the gate@1 visibility of the refusals (PR #242 review)."""
from pathlib import Path

from infrastructure.acquisition.common import discover as D
from infrastructure.acquisition.stage1_queue import queue_batch as Q
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2


class TestDomainHelpers:
    def test_domain_of_normalizes_and_blanks(self):
        assert D.domain_of("foo.org") == "foo.org"
        assert D.domain_of("www.foo.org") == "foo.org"
        assert D.domain_of("http://foo.org/bell") == "foo.org"
        assert D.domain_of("HTTPS://Foo.Org") == "foo.org"
        assert D.domain_of("  bar.k12.ne.us  ") == "bar.k12.ne.us"
        # blank / prefix-only normalize to ''
        assert D.domain_of("") == ""
        assert D.domain_of(None) == ""
        assert D.domain_of("   ") == ""
        assert D.domain_of("http://") == ""

    def test_domain_of_junk_still_yields_a_nonsense_host(self):
        # the whole reason is_scoping_domain exists: these are NON-blank but useless. Real NCES values.
        assert D.domain_of("http://N/A") == "n"
        assert D.domain_of("http://none") == "none"
        assert D.domain_of("http://375 LEE ST") == "375 lee st"

    def test_is_scoping_domain_accepts_real_hosts(self):
        for h in ("foo.org", "mpsomaha.org", "a.b.co", "bar.k12.ne.us", "1.2.3.4"):
            assert D.is_scoping_domain(h), h

    def test_is_scoping_domain_rejects_blank_and_junk(self):
        for h in ("", "   ", "n", "na", "none", "localhost", "foo", "375 lee st", "605 bel air suite 21", None):
            assert not D.is_scoping_domain(h), repr(h)

    def test_junk_website_round_trips_to_rejection(self):
        # end-to-end: a junk WEBSITE cell must fail the guard even though it is non-empty.
        for web in ("http://N/A", "http://none", "http://375 LEE ST", "", "http://", "N/A", "see website"):
            assert not D.is_scoping_domain(D.domain_of(web)), web
        for web in ("foo.org", "http://mpsomaha.org", "www.district.k12.ne.us"):
            assert D.is_scoping_domain(D.domain_of(web)), web


def _sch(sid):
    return {"school_id": sid, "name": f"School {sid}", "level": "High", "gslo": "09", "gshi": "12",
            "is_charter": "No", "bands": ["high"]}


class TestBuildBatchGuard:
    """build_batch (first-run / gate@1 console) must hard-drop unusable-domain districts from the
    pool and report them in `domain_excluded`, never carry one into the batch of record."""

    def _patch_pool(self, monkeypatch, pool, sch_idx):
        monkeypatch.setattr(Q, "eligible_pool", lambda year, registry: (pool, sch_idx, []))
        monkeypatch.setattr(Q.S, "school_level_counts", lambda year: {})

    def test_blank_and_junk_domains_are_excluded_and_reported(self, monkeypatch):
        pool = {
            "GOOD": {"name": "Good SD", "state": "IA", "website": "good.org",
                     "claimed_bands": {"high"}, "enrollment_k12": 5000},
            "BLANK": {"name": "Blank SD", "state": "NE", "website": "",
                      "claimed_bands": {"high"}, "enrollment_k12": 4000},
            "JUNK": {"name": "Junk SD", "state": "TX", "website": "http://N/A",
                     "claimed_bands": {"high"}, "enrollment_k12": 3000},
        }
        sch_idx = {k: {"high": [_sch(f"{k}-s1")]} for k in pool}
        self._patch_pool(monkeypatch, pool, sch_idx)

        doc, gap_excluded, domain_excluded, n_eligible = Q.build_batch(
            "2024_25", n=6, batch_id="batch_test_guard", registry={"districts": {}})

        picked = {d["district_id"] for d in doc["districts"]}
        assert picked == {"GOOD"}, "only the usable-domain district survives"
        assert doc["districts"][0]["domain"] == "good.org"
        assert {e["district_id"] for e in domain_excluded} == {"BLANK", "JUNK"}
        # the report carries enough to explain the drop at gate@1
        for e in domain_excluded:
            assert set(e) >= {"district_id", "name", "state", "website"}
        assert n_eligible == 1, "eligible count reflects the post-guard pool"

    def test_all_usable_domains_excludes_nothing(self, monkeypatch):
        pool = {"A": {"name": "A", "state": "IA", "website": "a.org",
                      "claimed_bands": {"high"}, "enrollment_k12": 5000},
                "B": {"name": "B", "state": "NE", "website": "http://b.k12.ne.us",
                      "claimed_bands": {"high"}, "enrollment_k12": 4000}}
        sch_idx = {k: {"high": [_sch(f"{k}-s1")]} for k in pool}
        self._patch_pool(monkeypatch, pool, sch_idx)
        doc, _gap, domain_excluded, n_eligible = Q.build_batch(
            "2024_25", n=6, batch_id="batch_test_guard2", registry={"districts": {}})
        assert domain_excluded == []
        assert {d["district_id"] for d in doc["districts"]} == {"A", "B"}
        assert n_eligible == 2

    def test_refusals_travel_in_the_batch_doc_for_persistence(self, monkeypatch):
        """PR #242 review: domain_excluded must ride IN the batch_doc (-> Batch.meta_json ->
        to_view/receipt) so the refusals survive reloads at gate@1 — not only the create response."""
        pool = {"BLANK": {"name": "Blank SD", "state": "NE", "website": "",
                          "claimed_bands": {"high"}, "enrollment_k12": 4000},
                "GOOD": {"name": "Good SD", "state": "IA", "website": "good.org",
                         "claimed_bands": {"high"}, "enrollment_k12": 5000}}
        sch_idx = {k: {"high": [_sch(f"{k}-s1")]} for k in pool}
        self._patch_pool(monkeypatch, pool, sch_idx)
        doc, _gap, domain_excluded, _n = Q.build_batch(
            "2024_25", n=6, batch_id="batch_test_guard3", registry={"districts": {}})
        assert doc["domain_excluded"] == domain_excluded and len(doc["domain_excluded"]) == 1
        assert "domain_excluded" in BSTORE._META_KEYS, \
            "domain_excluded must persist via Batch.meta_json (create_batch/to_view/receipt)"


class TestStage2FailsClosed:
    """PR #242 review (defense-in-depth): Stage 2's own gating chokepoint must refuse to run
    unscoped — a blank/junk domain reaching it through ANY path (manual DB edit, a future batch
    builder, remediation tooling) must yield zero kept URLs, never a national-scope keep-all."""

    URLS = ["http://reaganhs.example/bells", "http://mpsomaha.org/reagan/bells"]

    def test_blank_domain_rejects_everything(self):
        gated = D2.gate_urls(self.URLS, "")
        assert all(not g["kept"] for g in gated)
        assert all("#229" in g["reason"] for g in gated)

    def test_junk_domain_rejects_everything(self):
        for junk in ("n", "none", "375 lee st"):
            gated = D2.gate_urls(self.URLS, junk)
            assert all(not g["kept"] for g in gated), junk

    def test_real_domain_still_scopes_normally(self):
        gated = D2.gate_urls(self.URLS, "mpsomaha.org")
        by_url = {g["url"]: g for g in gated}
        assert by_url["http://mpsomaha.org/reagan/bells"]["kept"] is True
        assert by_url["http://reaganhs.example/bells"]["kept"] is False


def test_gate1_console_renders_the_domain_refusals():
    """UI-visibility regression (the project's own convention): the gate@1 console must actually
    READ + RENDER domain_excluded — PR #242's review found the server returned it but the client
    silently dropped it, so the operator never saw which districts were kept out."""
    repo = Path(__file__).resolve().parent.parent   # the test_arch_manifest.py cwd-proof convention
    js = (repo / "infrastructure/acquisition/process_governance/static/gate1.js").read_text()
    assert "domain_excluded" in js, "gate1.js must render the #229 refusals"
    assert "v.domain_excluded" in js, "renderDetail must read the field off the to_view payload"
