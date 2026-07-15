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


def test_campus_names_verbatim_kept_and_placeholder_scrubbed():
    # #499 REQ-148 (v4): campus_names passes through verbatim; the prompt-example placeholder gets
    # the same leak guard as school_name; a non-list value normalizes away.
    from infrastructure.acquisition.stage7_extract.parse import parse_schedules
    out = parse_schedules(
        '{"schedules":[{"grade_level":"middle","start_time":"08:00","end_time":"15:00",'
        '"school_name":"k8 schools","campus_names":["Milagro Middle School","[SCHOOL NAME]","  "]}]}')
    assert out[0]["campus_names"] == ["Milagro Middle School"]
    out2 = parse_schedules(
        '{"schedules":[{"grade_level":"middle","start_time":"08:00","end_time":"15:00",'
        '"school_name":"k8 schools","campus_names":"not a list"}]}')
    assert "campus_names" not in out2[0]
    out3 = parse_schedules(
        '{"schedules":[{"grade_level":"middle","start_time":"08:00","end_time":"15:00",'
        '"school_name":"oak"}]}')
    assert "campus_names" not in out3[0]          # pre-v4 rows byte-identical


def test_non_list_schedules_value_returns_empty():
    """#362: a valid-JSON reply whose 'schedules' value is not a list (null/scalar/dict) must
    return [] — the contract for 'found nothing' — not TypeError out of the list comprehension."""
    for payload in ('{"schedules": null}', '{"schedules": 42}', '{"schedules": false}',
                    '{"schedules": "none found"}', '{"schedules": {"oops": 1}}'):
        assert P.parse_schedules(payload) == [], payload


def test_salvage_brace_inside_string_value():
    """#276: a brace inside a string value must not truncate salvage — captured text carries
    parens/brackets/braces in school names and notes."""
    truncated = ('{"schedules":[{"grade_level":"high","start_time":"08:00","end_time":"15:00",'
                 '"school_name":"P.S. 42 {Annex} High"},{"grade_level":"middle","start_time":"07:30",'
                 '"end_time":"14:10","school_name":"B Middle"},{"grade_level":"eleme')
    out = P.parse_schedules(truncated)
    assert {o["school_name"] for o in out} == {"P.S. 42 {Annex} High", "B Middle"}


def test_salvage_nested_object():
    """#276: a schedule object carrying a nested dict must still be salvaged whole."""
    truncated = ('{"schedules":[{"grade_level":"high","start_time":"08:00","end_time":"15:00",'
                 '"school_name":"A High","meta":{"source":"handbook"}},{"grade_level":"eleme')
    out = P.parse_schedules(truncated)
    assert len(out) == 1 and out[0]["school_name"] == "A High"
    assert out[0]["meta"] == {"source": "handbook"}


def test_salvage_prose_wrapped_full_payload():
    # clean parse fails on the surrounding prose; the complete wrapper parses mid-text and its
    # schedules list is harvested
    txt = ('Here are the schedules I found:\n'
           '{"schedules":[{"grade_level":"high","start_time":"08:00","end_time":"15:00",'
           '"school_name":"A High"}]}\nLet me know if you need anything else!')
    out = P.parse_schedules(txt)
    assert len(out) == 1 and out[0]["school_name"] == "A High"


def test_campus_names_scrubbed_in_salvage_path():
    from infrastructure.acquisition.stage7_extract.parse import parse_schedules
    txt = ('{"schedules":[{"grade_level":"middle","start_time":"08:00","end_time":"15:00",'
           '"school_name":"k8 schools","campus_names":["[SCHOOL NAME]","Ortiz MS"]}  TRUNCATED')
    out = parse_schedules(txt)
    assert out and out[0]["campus_names"] == ["Ortiz MS"]
