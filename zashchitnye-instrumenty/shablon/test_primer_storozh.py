"""Тесты игрушечного сторожа: записанные снимки, свойства Hypothesis, контракт не вхолостую."""
import json
from pathlib import Path

import pytest
from hypothesis import example, given, strategies as st

import kontrakt
from adapter import Env, make_env

CASES = json.loads((Path(__file__).parent / "snimki" / "zapisannye.json").read_text(encoding="utf-8"))["cases"]


def _world(case):
    """Из описания снимка — два чтения: первое (с бедой/дырами) и второе (повторное)."""
    first = {f"c{i}": 5 for i in range(case["total"])}
    second = dict(first)
    for i in range(case["zero_first"]):
        first[f"c{i}"] = 0
    for i in range(case["zero_second"]):
        second[f"c{i}"] = 0
    for i in range(case["total"] - case["none_first"], case["total"]):
        first[f"c{i}"] = None
    return first, second


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_replay_recorded_snapshots(case):
    env = Env()
    env.set_world(*_world(case))
    env.run()
    assert len(env.acts) == case["expect_acts"], case["name"]


@example(zeros_first=set(range(20)), zeros_second=set(range(20)), nones=set())  # массовая беда на обоих чтениях
@given(
    zeros_first=st.sets(st.integers(0, 49)),
    zeros_second=st.sets(st.integers(0, 49)),
    nones=st.sets(st.integers(0, 49)),
)
def test_property_acts_only_on_stable_zero_within_limit(zeros_first, zeros_second, nones):
    env = Env()
    first = {f"c{i}": (None if i in nones else 0 if i in zeros_first else 5) for i in range(50)}
    second = {f"c{i}": (0 if i in zeros_second else 5) for i in range(50)}
    env.set_world(first, second)
    env.run()
    stable = {f"c{i}" for i in (zeros_first & zeros_second) - nones}
    assert set(env.acts) <= stable
    assert len(env.acts) <= env.guard.META["max_actions"]
    suspicious = (len(zeros_first - nones) + len(nones)) / 50 > env.guard.META["max_share"]
    if suspicious:
        assert env.acts == []


DEFECT_TO_CHECK = {
    "no_switch": kontrakt.check_switch,
    "no_owner": kontrakt.check_owner_and_expiry,
    "ignores_expiry": kontrakt.check_expired_goes_quiet,
    "no_limit": kontrakt.check_blast_radius,
    "no_confirm": kontrakt.check_second_read,
    "silent": kontrakt.check_every_refusal_logged,
    "ignores_human": kontrakt.check_human_refusal_wins,
    "accepts_same_slice": kontrakt.check_independent_confirm,
    "no_retry": kontrakt.check_urgent_retry_and_alert,
    "silent_fail": kontrakt.check_urgent_retry_and_alert,
}


@pytest.mark.parametrize("defect", DEFECT_TO_CHECK)
def test_contract_catches_bad_guard(defect):
    """Контракт не зелёный вхолостую: на сторожа с дефектом нужная проверка падает."""
    with pytest.raises(AssertionError):
        DEFECT_TO_CHECK[defect](lambda: make_env(defect))
