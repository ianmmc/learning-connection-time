"""#203 / epic #200 — property-based (hypothesis) stateful test of the promotion-pointer state machine.

Where the per-example tests in test_promotion_pointers.py pin specific transitions, this drives RANDOM
sequences of set_challenger / promote / rollback / prune / tick against a parallel Python model and asserts
the module's load-bearing invariants hold after EVERY step — the class of edge the PR #220 review caught by
hand (never-delete-set omissions, retention-window off-by-ones). No DB, no cash: the pointer state machine
is pure."""
import pytest
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from infrastructure.acquisition.stage5_filter import promotion_pointers as PP  # noqa: E402

_RETENTION = 3


class PointerStateMachine(RuleBasedStateMachine):
    """Drives PP against a shadow model. The model tracks (champion, challenger, [(version, demoted_cycle)])
    independently; every invariant asserts the real PP state agrees with it and with the module's contracts."""

    def __init__(self):
        super().__init__()
        self.state = PP.initial_state("v0", retention_cycles=_RETENTION)
        self.cycle = 0
        self._ctr = 0
        # shadow model
        self.m_champion = "v0"
        self.m_challenger = None
        self.m_fallbacks = []                       # list of (version, demoted_at_cycle), newest last

    def _fresh(self):
        self._ctr += 1
        return f"v{self._ctr}"                       # unique, never collides with champion/fallbacks

    # ----------------------------- rules (the transitions) -----------------------------
    @rule()
    def tick(self):
        self.cycle += 1

    @rule()
    def stage_challenger(self):
        v = self._fresh()
        self.state = PP.set_challenger(self.state, v)
        self.m_challenger = v                        # overwrites any prior (unpromoted) challenger

    @rule()
    def promote(self):
        v = self.m_challenger if self.m_challenger is not None else self._fresh()
        self.state = PP.promote(self.state, v, cycle=self.cycle)
        self.m_fallbacks.append((self.m_champion, self.cycle))
        self.m_champion, self.m_challenger = v, None

    @precondition(lambda self: self.m_fallbacks)
    @rule()
    def rollback(self):
        self.state = PP.rollback(self.state, cycle=self.cycle)
        ver, _ = self.m_fallbacks.pop()              # most-recent demoted champion returns
        self.m_champion, self.m_challenger = ver, None

    @rule()
    def prune(self):
        self.state, evicted = PP.prune(self.state, cycle=self.cycle)
        keep, dropped = [], []
        for entry in self.m_fallbacks:
            (dropped if self.cycle - entry[1] >= _RETENTION else keep).append(entry)
        self.m_fallbacks = keep
        assert set(evicted) == {v for v, _ in dropped}
        # a pruned version is, by construction, never the champion (champion is never in fallbacks)
        assert self.state["champion"] not in evicted

    # ----------------------------- invariants (hold after EVERY rule) -----------------------------
    @invariant()
    def champion_is_set_and_correct(self):
        assert self.state["champion"] is not None
        assert self.state["champion"] == self.m_champion

    @invariant()
    def active_versions_is_exactly_the_referenced_set(self):
        expected = {self.m_champion} | {v for v, _ in self.m_fallbacks}
        if self.m_challenger is not None:
            expected.add(self.m_challenger)
        assert PP.active_versions(self.state) == expected

    @invariant()
    def evictable_are_all_past_the_retention_window(self):
        demoted = {f["version"]: f["demoted_at_cycle"] for f in self.state["fallbacks"]}
        for v in PP.evictable(self.state, cycle=self.cycle):
            assert self.cycle - demoted[v] >= _RETENTION

    @invariant()
    def rollback_target_is_always_the_newest_fallback(self):
        # while any fallback remains, a rollback is available and returns the most-recent one — the
        # property that makes a just-promoted config exactly reversible.
        if self.state["fallbacks"]:
            newest = self.state["fallbacks"][-1]["version"]
            rolled = PP.rollback(self.state, cycle=self.cycle)   # pure — does not mutate self.state
            assert rolled["champion"] == newest


TestPointerStateMachine = PointerStateMachine.TestCase
TestPointerStateMachine.settings = settings(max_examples=200, stateful_step_count=40, deadline=None)


def test_state_machine_is_deterministic_smoke():
    """A trivial guard that the class wires up (the hypothesis TestCase does the real work)."""
    m = PointerStateMachine()
    assert m.state["champion"] == "v0"
