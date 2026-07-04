"""Stage 7 model-output parser (REQ-117) — pure, no network. The paid call itself is a gated
manual run (like the Stage-2 reliability harness), so these cover only the deterministic parse."""
from infrastructure.acquisition.stage7_extract import parse as P


def test_clean_json():
    out = P.parse_schedules('{"schedules":[{"grade_level":"high","start_time":"08:10",'
                            '"end_time":"14:35","school_name":"Central High","confidence":"high"}]}')
    assert len(out) == 1
    assert out[0]["school_name"] == "Central High"
    assert out[0]["start_time"] == "08:10"


def test_empty_schedules():
    assert P.parse_schedules('{"schedules":[]}') == []


def test_none_and_blank():
    assert P.parse_schedules("") == []
    assert P.parse_schedules("   ") == []
    assert P.parse_schedules(None) == []


def test_markdown_fenced():
    out = P.parse_schedules('```json\n{"schedules":[{"grade_level":"elementary",'
                            '"start_time":"09:10","end_time":"15:50","school_name":"Brick Mill"}]}\n```')
    assert len(out) == 1 and out[0]["school_name"] == "Brick Mill"


def test_salvage_truncated_tail():
    # A long reply cut off mid-array: clean parse fails, individual objects are salvaged.
    truncated = ('{"schedules":[{"grade_level":"high","start_time":"08:00","end_time":"15:00",'
                 '"school_name":"A High"},{"grade_level":"middle","start_time":"07:30",'
                 '"end_time":"14:10","school_name":"B Middle"},{"grade_level":"eleme')
    out = P.parse_schedules(truncated)
    assert len(out) == 2
    assert {o["school_name"] for o in out} == {"A High", "B Middle"}


def test_bare_list_form():
    out = P.parse_schedules('[{"grade_level":"high","start_time":"08:00","end_time":"14:00",'
                            '"school_name":"X"}]')
    assert len(out) == 1 and out[0]["school_name"] == "X"


def test_non_dict_members_dropped():
    out = P.parse_schedules('{"schedules":[{"school_name":"ok","start_time":"08:00"}, "garbage", 42]}')
    assert len(out) == 1 and out[0]["school_name"] == "ok"


def test_prompt_leak_placeholder_dropped_real_school_survives():
    """The leak guard drops the prompt's self-evident placeholder — and ONLY that (#144): 'Fivay
    High' is a REAL school (Pasco County FL), and the prompt no longer contains it, so a row naming
    it is far more likely real data than a leak. Blacklisting a real school name permanently blinded
    extraction to it; never add real names here — fix the prompt instead."""
    out = P.parse_schedules(
        '{"schedules":['
        '{"grade_level":"high","start_time":"08:30","end_time":"15:35","school_name":"Fivay High"},'
        '{"grade_level":"high","start_time":"08:10","end_time":"14:35","school_name":"[SCHOOL NAME]"},'
        '{"grade_level":"high","start_time":"08:40","end_time":"15:15","school_name":"Essex High"}]}')
    assert [s["school_name"] for s in out] == ["Fivay High", "Essex High"]


def test_prompt_leak_dropped_in_salvage_path():
    # truncated JSON → salvage; the placeholder leak is dropped there too (the garbled-input path is
    # exactly where the original leak happened)
    truncated = ('{"schedules":[{"grade_level":"high","start_time":"08:30","end_time":"15:35",'
                 '"school_name":"[SCHOOL NAME]"},{"grade_level":"middle","start_time":"07:30",'
                 '"end_time":"14:10","school_name":"Real Middle"},{"grade_level":"eleme')
    out = P.parse_schedules(truncated)
    assert [s["school_name"] for s in out] == ["Real Middle"]


def test_no_real_school_names_in_leak_blacklist():
    """Regression guard for #144: the blacklist may contain only self-evident placeholders (bracketed
    tokens) — a real school name here silently blinds extraction to that school forever."""
    for name in P._PROMPT_LEAK_NAMES:
        assert name.startswith("[") and name.endswith("]"), (
            f"_PROMPT_LEAK_NAMES contains a non-placeholder entry {name!r} — real school names must "
            f"never be blacklisted (fix the prompt instead, #144)")
