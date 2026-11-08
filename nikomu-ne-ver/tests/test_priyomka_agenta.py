"""Тесты priyomka_agenta.py — приёмка отчёта агента: git-факты и итог тестов.

Оглавление:
  1. Итог тестов: зелёный только при failed 0, skipped 0
  2. git-факты во временном репозитории
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import priyomka_agenta as pa  # noqa: E402


# ═══ 1. Итог тестов ═════════════════════════════════════════════════════
@pytest.mark.parametrize("tekst", [
    "===== 71 passed in 3.2s =====",
    "Tests: 12 passed, 12 total",
    "Passed!  - Failed: 0, Passed: 40, Skipped: 0, Total: 40",
])
def test_zelenyy(tekst):
    ok, prichina = pa.zelenyy(tekst, kod=0)
    assert ok, prichina


@pytest.mark.parametrize("tekst, slovo", [
    ("== 1 failed, 70 passed in 3s ==", "failed"),
    ("== 44 skipped, 100 passed in 3s ==", "skipped"),
    ("Tests: 2 failed, 5 passed, 7 total", "failed"),
    ("Failed: 0, Passed: 40, Skipped: 3, Total: 43", "skipped"),
    ("== 3 errors in 1s ==", "error"),
    ("все прошло, честно", "итога"),
    ("", "итога"),
])
def test_ne_zelenyy(tekst, slovo):
    ok, prichina = pa.zelenyy(tekst, kod=0)
    assert not ok and slovo in prichina


def test_kod_vyhoda_nenulevoy_ne_zelenyy():
    ok, prichina = pa.zelenyy("== 5 passed in 1s ==", kod=1)
    assert not ok and "код" in prichina


def test_xfail_i_deselected_nazvany():
    ok, prichina = pa.zelenyy("== 5 passed, 2 deselected, 1 xfailed in 1s ==", kod=0)
    assert not ok and ("deselected" in prichina and "xfailed" in prichina)


def test_nol_proshedshih_ne_zelenyy():
    ok, _ = pa.zelenyy("== 0 passed in 0.1s ==", kod=0)
    assert not ok


# ═══ 2. git-факты ═══════════════════════════════════════════════════════
def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_net_kommitov(repo):
    f = pa.fakty_git(repo, "main")
    assert f["kommitov"] == 0
    assert any("КОММИТОВ НЕТ" in x for x in pa.zamechaniya(f))


def test_kod_bez_testa(repo):
    git(repo, "checkout", "-qb", "agent")
    (repo / "a.py").write_text("x = 2\n")
    git(repo, "commit", "-aqm", "правка")
    f = pa.fakty_git(repo, "main")
    z = "\n".join(pa.zamechaniya(f))
    assert f["kommitov"] == 1 and "КОД БЕЗ ТЕСТА" in z


def test_kod_s_testom_chisto(repo):
    git(repo, "checkout", "-qb", "agent")
    (repo / "a.py").write_text("x = 2\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "правка с тестом")
    assert pa.zamechaniya(pa.fakty_git(repo, "main")) == []


def test_ne_zakommicheno(repo):
    git(repo, "checkout", "-qb", "agent")
    (repo / "a.py").write_text("x = 2\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("pass\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ok")
    (repo / "b.py").write_text("y = 1\n")
    z = "\n".join(pa.zamechaniya(pa.fakty_git(repo, "main")))
    assert "НЕ ЗАКОММИЧЕНО" in z and "b.py" in z


def test_main_kod_vyhoda(repo, capsys):
    assert pa.main(["--repo", str(repo), "--base", "main"]) == 1
    assert "КОММИТОВ НЕТ" in capsys.readouterr().out
