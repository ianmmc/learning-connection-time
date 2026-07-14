"""Shared-config schema fitness functions (#205 part 1; governance §10).

The config-as-data knobs under `infrastructure/acquisition/common/config/` are read by BOTH the
Python pipeline (common/config_loader.py) and the Node scraper (capture_discovery.mjs reads the same
JSON natively) — a cross-language edge no import tool sees. The manifest's `shared_config` section
declares a JSON Schema per knob file; these tests validate every knob against its schema so a
malformed/renamed key fails the suite, not a stage at runtime.

Coverage is enforced both ways: a knob file with no `shared_config` declaration fails (the manifest
edit is the review surface — CLAUDE.md's arch-manifest rule), and a declared file that doesn't exist
fails. Part 2 of #205 (datacontract-cli on the stage receipt artifacts) is tracked separately —
deferred until #478 stabilizes the Stage 8 artifacts.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((REPO / "arch-manifest.json").read_text())
SHARED = MANIFEST["shared_config"]
CONFIG_DIR = REPO / SHARED["dir"]
SCHEMA_DIR = REPO / SHARED["schemas_dir"]
DECLARED = {e["file"]: e["schema"] for e in SHARED["files"]}


def _knob_files():
    return sorted(p.name for p in CONFIG_DIR.glob("*.json"))


def test_manifest_section_is_nonempty():
    """A manifest edit that empties shared_config must fail loudly, not silently collect zero tests
    (the same guard test_arch_manifest.py applies to its own sections)."""
    assert DECLARED, "shared_config.files is empty"
    assert _knob_files(), f"no knob files found under {SHARED['dir']}"


def test_every_knob_file_is_declared():
    """A NEW config/*.json must be declared in the manifest (path -> schema) — the declaration is
    the review surface for the cross-language edge."""
    undeclared = [f for f in _knob_files() if f not in DECLARED]
    assert not undeclared, (
        f"knob files with no shared_config declaration in arch-manifest.json: {undeclared}"
    )


def test_every_declared_file_exists():
    missing = [f for f in DECLARED if not (CONFIG_DIR / f).exists()]
    assert not missing, f"shared_config declares files that don't exist: {missing}"


@pytest.mark.parametrize("schema_name", sorted(set(DECLARED.values())))
def test_schema_itself_is_valid(schema_name):
    schema = json.loads((SCHEMA_DIR / schema_name).read_text())
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("file_name", sorted(DECLARED))
def test_knob_validates_against_its_schema(file_name):
    doc = json.loads((CONFIG_DIR / file_name).read_text())
    schema = json.loads((SCHEMA_DIR / DECLARED[file_name]).read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, (
        f"{file_name} violates {DECLARED[file_name]}:\n"
        + "\n".join(f"  at {list(e.path)}: {e.message}" for e in errors[:10])
    )


@pytest.mark.parametrize("file_name", sorted(DECLARED))
def test_knob_name_matches_filename(file_name):
    """Every knob doc self-identifies via its `knob` field; it must equal the file stem so
    config_loader.load(name) and the doc's own identity can never disagree."""
    doc = json.loads((CONFIG_DIR / file_name).read_text())
    assert doc.get("knob") == Path(file_name).stem, (
        f"{file_name}: knob field {doc.get('knob')!r} != file stem {Path(file_name).stem!r}"
    )
