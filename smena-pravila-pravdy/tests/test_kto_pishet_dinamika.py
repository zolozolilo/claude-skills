"""Тесты расширения kto_pishet.py (уроки «правка не по всем путям»):
динамический доступ, который поиск по имени не видит, и предупреждение «корень один».

Оглавление:
  1. Строки динамического доступа (globals(), getattr, [переменная] …)
  2. Сбор по корням и показ в отчёте
  3. Предупреждение «корень один»
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kto_pishet as kp  # noqa: E402


# ═══ 1. Строки динамического доступа ════════════════════════════════════
@pytest.mark.parametrize("stroka", [
    "for name in NAMES: globals()[name] = make(name)",
    "v = getattr(obj, field)",
    "setattr(obj, field, 5)",
    "obj.__dict__.update(d)",
    "mod = importlib.import_module(name)",
    "eval(code)",
])
def test_py_dinamika(stroka):
    assert kp.dinamicheskie_stroki(stroka + "\n", "py")


@pytest.mark.parametrize("stroka", [
    "x = 1",
    "def getattr_safe(): pass",
    "# globals() в комментарии",
])
def test_py_ne_dinamika(stroka):
    assert kp.dinamicheskie_stroki(stroka + "\n", "py") == []


def test_py_nomer_stroki_i_tip():
    nar = kp.dinamicheskie_stroki("a = 1\n\nglobals()[n] = 2\n", "py")
    assert nar == [(3, "globals()")]


@pytest.mark.parametrize("stroka", [
    "window[name] = fn",
    "globalThis[key] = 1",
    "const v = this[field]",
    "eval(src)",
    "new Function('a', body)",
])
def test_js_dinamika(stroka):
    assert kp.dinamicheskie_stroki(stroka + "\n", "js")


@pytest.mark.parametrize("stroka", [
    "obj.GetType().GetProperty(name)",
    "Activator.CreateInstance(t)",
    "dynamic x = y;",
])
def test_cs_dinamika(stroka):
    assert kp.dinamicheskie_stroki(stroka + "\n", "cs")


# ═══ 2. Сбор по корням и показ в отчёте ═════════════════════════════════
@pytest.fixture
def repo(tmp_path):
    (tmp_path / "logic").mkdir()
    (tmp_path / "logic" / "a.py").write_text("stock_qty = 1\n", encoding="utf-8")
    (tmp_path / "logic" / "loader.py").write_text(
        "for n in NAMES:\n    globals()[n] = make(n)\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("window[x] = 1\n", encoding="utf-8")
    return tmp_path


def test_dinamika_najdena_v_faile_bez_imeni(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)
    assert any(d["put"].replace("\\", "/") == "logic/loader.py" and d["nomer"] == 2
               for d in o.dinamika)
    assert not any("node_modules" in d["put"] for d in o.dinamika)   # папки пропуска не читаем


def test_dinamika_v_tablice(repo):
    t = kp.tablica_md(kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)).replace("\\", "/")
    assert "Динамический доступ" in t and "logic/loader.py:2" in t and "globals()" in t


def test_dinamika_v_json(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)
    assert json.loads(kp.v_json(o))["dinamika"]


def test_bez_dinamiki_otklyuchaetsya(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False, dinamika=False)
    assert o.dinamika == []


def test_tablica_sжimaet_dlinnyy_spisok(tmp_path):
    (tmp_path / "x.py").write_text("stock_qty = 1\n" + "globals()[n] = 1\n" * 30, encoding="utf-8")
    t = kp.tablica_md(kp.naiti([str(tmp_path)], ["stock_qty"], ispolzovat_rg=False))
    assert "и ещё 22" in t       # показано 8, остальное — в --json


# ═══ 3. Предупреждение «корень один» ════════════════════════════════════
def test_koren_odin_preduprezhdaet(repo):
    t = kp.tablica_md(kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False))
    assert "Корень один" in t


def test_dva_kornya_bez_preduprezhdeniya(repo, tmp_path_factory):
    drugoy = tmp_path_factory.mktemp("front")
    (drugoy / "a.js").write_text("const stockQty = 1\n", encoding="utf-8")
    t = kp.tablica_md(kp.naiti([str(repo), str(drugoy)], ["stock_qty"], ispolzovat_rg=False))
    assert "Корень один" not in t
