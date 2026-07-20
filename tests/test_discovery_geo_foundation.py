"""#164 foundation (PR 1): the geo-scoped discovery primitives.

DB-free half: geo query rendering (one vocabulary, two scoping forms) + the derive-and-re-gate
majority-host derivation (pure). The govdb half (policy events, discovered domains, the
Batch.discovery_scope axis) lives in class TestGeoGovdb below, marked like the other
working-store tests."""
import pytest

from infrastructure.acquisition.common import discover as D
from infrastructure.acquisition.common import discovery_policy as DP
from infrastructure.acquisition.common import discovered_domain as DD
from infrastructure.acquisition.stage2_discover import discover_stage2 as S2


# ---------------------------------------------------------------- geo rendering (DB-free)
def test_geo_queries_render_the_standard_vocabulary_with_geo_tokens():
    qs = S2.geo_queries("Reagan Middle School", "NE", "OMAHA", "68137")
    assert qs == ["Reagan Middle School NE bell schedule start and end times OMAHA 68137"]


def test_geo_queries_widened_adds_the_differentiated_vocabulary_geo_rendered():
    qs = S2.geo_queries("Reagan Middle School", "NE", "OMAHA", "68137", widened=True)
    assert qs[0].endswith("OMAHA 68137")
    assert len(qs) == 1 + len(S2.differentiated_queries("Reagan Middle School", "NE"))
    assert all(q.endswith("OMAHA 68137") for q in qs)      # every vocabulary line geo-rendered
    assert len(set(qs)) == len(qs)                          # no duplicate queries


def test_geo_queries_tolerate_missing_geo_fields():
    assert S2.geo_queries("X School", "VT", "", "")[0] == "X School VT bell schedule start and end times"
    assert S2.geo_queries("X School", "VT", "Burlington", "")[0].endswith("Burlington")


# ---------------------------------------------------------------- derive-and-re-gate (DB-free)
def _tally(**hosts):
    return {h: {"n": n, "schools": schools} for h, (n, schools) in hosts.items()}


def test_derive_domain_majority_host_clears_both_thresholds():
    tally = {"mpsomaha.org": {"n": 60, "schools": ["s1", "s2", "s3", "s4"]},
             "reaganisd.tx.us": {"n": 20, "schools": ["s1"]},
             "other.org": {"n": 20, "schools": ["s2"]}}
    host, receipt = D.derive_domain(tally)
    assert host == "mpsomaha.org"
    assert receipt["outcome"] == "derived" and receipt["share"] == 0.6 and receipt["n_schools"] == 4
    assert receipt["tally"]["mpsomaha.org"]["n"] == 60      # the auditor sees the full tally


def test_derive_domain_below_share_threshold_keeps_nothing():
    tally = {"a.org": {"n": 30, "schools": ["s1", "s2", "s3"]},
             "b.org": {"n": 30, "schools": ["s4", "s5", "s6"]},
             "c.org": {"n": 40, "schools": ["s7"]}}       # top host c.org: 40% share but 1 school
    host, receipt = D.derive_domain(tally)
    assert host is None and receipt["outcome"] == "below threshold"


def test_derive_domain_needs_three_distinct_schools_not_three_results():
    tally = {"one-school.org": {"n": 100, "schools": ["s1", "s1", "s1"]}}   # 100% share, 1 school
    host, receipt = D.derive_domain(tally)
    assert host is None and receipt["n_schools"] == 1


def test_derive_domain_empty_tally_is_no_results():
    host, receipt = D.derive_domain({})
    assert host is None and receipt["outcome"] == "no results"


def test_derive_domain_rejects_non_scoping_hosts():
    # a host that can't scope discovery (no TLD dot) must never be derived
    host, _ = D.derive_domain({"localhost": {"n": 10, "schools": ["s1", "s2", "s3"]}})
    assert host is None


# ---------------------------------------------------------------- working store (govdb)
@pytest.mark.integration
@pytest.mark.govdb
class TestGeoGovdb:
    def test_policy_defaults_then_advances_exactly_one_step(self, gov_session):
        from infrastructure.acquisition.common import db as gdb
        gdb.init_precious_schema()
        assert DP.get_policy(gov_session) == "domain_only"
        out = DP.advance_one_step(gov_session, actor="auto:stage1", trigger="pool drained (0 left)")
        assert out == "geo_for_blank" and DP.get_policy(gov_session) == "geo_for_blank"
        # a second auto-advance is a no-op — it NEVER goes further than geo_for_blank
        assert DP.advance_one_step(gov_session, actor="auto:stage1", trigger="again") is None
        assert DP.get_policy(gov_session) == "geo_for_blank"

    def test_policy_set_is_validated_audited_and_idempotent(self, gov_session):
        from infrastructure.acquisition.common import db as gdb
        gdb.init_precious_schema()
        DP.set_policy(gov_session, "geo_all", actor="ian")
        DP.set_policy(gov_session, "geo_all", actor="ian")          # unchanged -> no event spam
        events = gov_session.query(DP.DiscoveryPolicyEvent).all()
        assert len(events) == 1
        assert events[0].previous == "domain_only" and events[0].policy == "geo_all"
        with pytest.raises(ValueError):
            DP.set_policy(gov_session, "bogus", actor="ian")

    def test_discovered_domain_confirm_upserts_and_validates(self, gov_session):
        from infrastructure.acquisition.common import db as gdb
        gdb.init_precious_schema()
        DD.confirm(gov_session, "3173740", "mpsomaha.org", derived_in_batch="batch_00099",
                   tally={"outcome": "derived"}, actor="ian")
        assert DD.get_domain(gov_session, "3173740") == "mpsomaha.org"
        DD.confirm(gov_session, "3173740", "millard.org", actor="ian")   # re-confirm upserts
        assert DD.all_confirmed(gov_session) == {"3173740": "millard.org"}
        with pytest.raises(ValueError):
            DD.confirm(gov_session, "3173740", "not a domain", actor="ian")
