"""#808 — the spec ledger must not silently lose content to YAML's duplicate-key rule.

`yaml.safe_load` keeps only the LAST duplicate key in a mapping, with no warning. REQ-174 briefly
declared `notes:` twice, and the entire #793 narrative — the rationale the ledger exists to hold —
vanished at parse time while the raw text sat in the file looking fine. The ledger is the durable
record that outlives context windows; a requirement whose rationale disappears on load is the
ledger failing at its one job. DB-free, whole-file, catches every future recurrence.
"""
from pathlib import Path

import yaml

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "REQUIREMENTS.yaml"


class _DuplicateKey(Exception):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that REJECTS duplicate mapping keys instead of last-write-wins."""


def _no_dup_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise _DuplicateKey(
                f"duplicate mapping key {key!r} at line {key_node.start_mark.line + 1} — "
                f"yaml.safe_load would silently discard all but the last")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup_mapping)


def test_ledger_has_no_duplicate_mapping_keys():
    with LEDGER.open() as f:
        doc = yaml.load(f, Loader=_StrictLoader)   # raises _DuplicateKey on the #808 shape
    assert doc["requirements"], "ledger parsed but empty — wrong file?"


def test_req174_notes_survive_parse():
    """The specific casualty: REQ-174's #793 narrative must be reachable THROUGH a parser, not
    just present as raw text."""
    doc = yaml.safe_load(LEDGER.read_text())
    req = next(r for r in doc["requirements"] if r["id"] == "REQ-174")
    assert "#793" in req["notes"]
    assert "window_truncated" in str(req)
