"""Council Lab judge-replay — the PURE reconstruction helpers (#80/#82). The paid replay itself is a
CLI experiment; here we lock the receipt-reading logic that feeds it: voter facts are reconstructed
from the recorded VOTER calls only (never the judge), so a replay reuses exactly what consensus saw."""
from infrastructure.acquisition.process_governance import council_lab as CL


def _rep(judged=False):
    return {
        "rec_key": "D1:abc", "file": "raster_p-1.png", "kind": "image", "judged": judged,
        "calls": [
            {"model": "google/gemini-2.5-flash", "role": "voter",
             "facts": [{"school_name": "A", "start_time": "08:00", "end_time": "14:00"}]},
            {"model": "mistralai/mistral-large-2512", "role": "voter",
             "facts": [{"school_name": "A", "start_time": "08:00", "end_time": "15:00"}]},
            # the dead judge call is present in the receipt but must NOT feed reconstruction
            {"model": "deepseek/deepseek-v3.2", "role": "judge", "ok": False, "facts": []},
        ],
    }


def test_voter_rows_excludes_the_judge():
    rows = CL._voter_rows(_rep())
    assert set(rows) == {"google/gemini-2.5-flash", "mistralai/mistral-large-2512"}
    assert "deepseek/deepseek-v3.2" not in rows          # the judge call is never a voter input
    assert len(rows["google/gemini-2.5-flash"]) == 1


def test_voter_rows_handles_missing_facts():
    rep = {"calls": [{"model": "m1", "role": "voter"}]}   # a voter call with no facts key
    assert CL._voter_rows(rep) == {"m1": []}


def test_tag_attaches_rep_provenance():
    facts = [{"band": "high", "school": "A", "gross": 400}]
    tagged = CL._tag(facts, _rep())
    assert tagged[0]["rec_key"] == "D1:abc" and tagged[0]["source_file"] == "raster_p-1.png"
