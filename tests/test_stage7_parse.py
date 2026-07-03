"""Stage 7 model-output parser (REQ-117) — pure, no network. The paid call itself is a gated
manual run (like the Stage-2 reliability harness), so these cover only the deterministic parse."""
from infrastructure.acquisition.stage7_extract import parse as P


def test_clean_json():
    out = P.parse_schedules('{"schedules":[{"grade_level":"high","start_time":"08:10",'
                            '"end_time":"14:35","school_name":"Fivay High","confidence":"high"}]}')
    assert len(out) == 1
    assert out[0]["school_name"] == "Fivay High"
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
