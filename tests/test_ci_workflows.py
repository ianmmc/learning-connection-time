"""REQ-130 (#251, epic #482; 2026-07-15 audit sweep) — a fitness-function test for the stacked-PR CI
guardrail. Prior to this test, PR #483's guard mechanism (a PR must target main; both CI workflows must
run on every PR base, not just main) was enforced by CI running, not by an assertion in the pytest
suite — a future edit reintroducing a `branches: [main]` filter on a pull_request trigger, or weakening
pr-base-guard.yml's condition, would NOT have been caught by `pytest -q`; it would only surface the next
time someone opened a stacked PR and watched it silently skip CI, exactly the #251 incident this
guardrail exists to prevent.

Pure YAML parse + structural assertions (mirrors test_arch_manifest.py's/test_suite_hygiene.py's
filesystem-scan style) — no GitHub API, no network."""
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"


def _load(name):
    path = WORKFLOWS / name
    if not path.exists():
        pytest.fail(f"{name} is missing from .github/workflows/ — the stacked-PR guardrail (#251) "
                    f"depends on it")
    # PyYAML's default loader treats the bare key `on:` as the boolean True (YAML 1.1's on/off/yes/no
    # truthy words) — GitHub Actions workflow files are YAML 1.1 in practice and this is a well-known
    # gotcha; read with True as the fallback key so this test doesn't break on a real, valid workflow.
    doc = yaml.safe_load(path.read_text())
    return doc


def _triggers(doc):
    return doc.get("on") or doc.get(True) or {}


def test_pr_base_guard_workflow_exists_and_fails_on_a_non_main_base():
    doc = _load("pr-base-guard.yml")
    triggers = _triggers(doc)
    assert "pull_request" in triggers, "pr-base-guard.yml must trigger on pull_request"
    pr_types = set((triggers.get("pull_request") or {}).get("types") or [])
    # 'edited' is the trigger that makes retargeting the base to main go green WITHOUT a new commit
    # (the workflow's own header comment promises this) — losing it would silently strand a
    # correctly-retargeted PR on a stale red X.
    assert "edited" in pr_types, "pr-base-guard.yml must re-evaluate on the 'edited' trigger (retargeting a stacked PR's base must re-check without a new commit)"
    assert {"opened", "synchronize"} <= pr_types, "pr-base-guard.yml must also check on open/push"
    jobs = doc.get("jobs") or {}
    steps = [s for job in jobs.values() for s in (job.get("steps") or [])]
    run_bodies = " ".join(s.get("run", "") for s in steps)
    # base_ref is read into an env var (env: BASE: ${{ github.base_ref }}) and referenced as $BASE in
    # the run script — check both the step envs and the run bodies so this doesn't require one
    # specific plumbing style.
    env_values = " ".join(str(v) for s in steps for v in (s.get("env") or {}).values())
    assert "github.base_ref" in env_values or "github.base_ref" in run_bodies, \
        "pr-base-guard.yml's step must inspect github.base_ref (directly or via a step env var)"
    assert "exit 1" in run_bodies, "pr-base-guard.yml must actually FAIL (exit 1) on a non-main base, not just warn"
    assert "main" in run_bodies


@pytest.mark.parametrize("workflow_name", ["lint.yml", "test.yml"])
def test_ci_workflows_run_on_every_pr_base_not_just_main(workflow_name):
    # the #251 root cause: a `pull_request: branches: [main]` filter means a stacked PR (whose base is
    # a feature branch, not main) runs ZERO checks. The fix was removing the branches filter entirely
    # from the pull_request trigger — a future re-add of that filter must fail this test.
    doc = _load(workflow_name)
    triggers = _triggers(doc)
    assert "pull_request" in triggers, f"{workflow_name} must trigger on pull_request (not push-only)"
    pr_trigger = triggers.get("pull_request")
    # a bare `pull_request:` (no sub-keys) parses as None — that IS the no-filter state we want;
    # a dict WITH a 'branches' key is the regression this test exists to catch.
    if isinstance(pr_trigger, dict):
        assert "branches" not in pr_trigger, (
            f"{workflow_name}'s pull_request trigger has a 'branches' filter ({pr_trigger.get('branches')}) "
            f"— this is the exact #251 regression: a stacked PR (base != main) would run zero CI checks. "
            f"Remove the filter so pull_request fires on every base.")
