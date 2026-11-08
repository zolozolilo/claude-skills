"""Контрактный тест: гоняет kontrakt.ALL_CHECKS на инструменте, заданном в adapter.py."""
import pytest

from adapter import make_env
from kontrakt import ALL_CHECKS


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
def test_kontrakt(check):
    check(make_env)
