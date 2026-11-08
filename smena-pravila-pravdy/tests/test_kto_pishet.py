"""Тесты kto_pishet.py — кто пишет и кто читает поле/функцию/ключ.

Оглавление:
  1. Python — писатели
  2. Python — читатели, определения, вызовы
  3. JS / TS
  4. C#
  5. Комментарии, данные, текст
  6. Недостижимый код (после return)
  7. Варианты имени (snake / camel / Pascal)
  8. Обход дерева и отчёт
  9. Выбор поиска (rg / stdlib)
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kto_pishet as kp  # noqa: E402

PISHET, CHITAET = "ПИШЕТ", "ЧИТАЕТ"
OPRED, VYZOV = "ОПРЕДЕЛЕНИЕ", "ВЫЗОВ"
KOMM, DANNYE, UPOM = "КОММЕНТАРИЙ", "ДАННЫЕ", "УПОМИНАНИЕ"


def roli(stroka, yazyk="py", imya="size"):
    return kp.roli_v_stroke(stroka, imya, yazyk)


# ═══ 1. Python — писатели ═══════════════════════════════════════════════
@pytest.mark.parametrize("stroka", [
    "size = 5",
    "row.size = new_size",
    "self.size += 1",
    'row["size"] = 5',
    "row['size'] = 5",
    'data = {"size": 5}',
    "Model(size=5)",
    'setattr(obj, "size", 5)',
    "self.size[code] = x",
    "self.size.append(x)",
    'row.pop("size")',
    'del row["size"]',
    "(size := compute())",
    'cur.execute("UPDATE t SET size = ?", (v,))',
])
def test_py_pishet(stroka):
    assert PISHET in roli(stroka)


# ═══ 2. Python — читатели, определения, вызовы ════════════════════════
@pytest.mark.parametrize("stroka", [
    "x = row.size",
    'x = row.get("size")',
    "if row.size == 5:",
    "if row.size <= 5:",
    'x = getattr(obj, "size")',
    'x = row["size"]',
])
def test_py_chitaet(stroka):
    r = roli(stroka)
    assert CHITAET in r and PISHET not in r


def test_py_pishet_i_chitaet_v_odnoy_stroke():
    assert roli("a.size = b.size + 1") == {PISHET, CHITAET}


@pytest.mark.parametrize("stroka", [
    "def size(self):",
    "async def size(self):",
    "class size:",
    "    size: int = 0",
    "def f(a, size=1):",
])
def test_py_opredelenie(stroka):
    assert roli(stroka) == {OPRED}


def test_py_vyzov():
    assert roli("x = size(a, b)") == {VYZOV}


def test_tselye_slova_tolko():
    assert roli("x.size = 5")
    assert roli("sizes = 5") == set()
    assert roli("max_size = 5") == set()


# ═══ 3. JS / TS ═════════════════════════════════════════════════════════
@pytest.mark.parametrize("stroka", [
    "obj.size = 5;",
    "const o = { size: 5 };",
    '  "size": 5,',
    "  size: 5,",
    "delete obj.size;",
    "obj.size++;",
    "state.size.push(x);",
])
def test_js_pishet(stroka):
    assert PISHET in roli(stroka, "js")


@pytest.mark.parametrize("stroka", [
    "const { size } = props;",
    "return a ? size : b;",
    "if (obj.size === 5) {}",
    "const f = size => size * 2;",
])
def test_js_ne_pishet(stroka):
    r = roli(stroka, "js")
    assert r and PISHET not in r


@pytest.mark.parametrize("stroka", [
    "function size(a) {",
    "const size = 5;",
    "  async size(a, b) {",
    "  size: number;",
])
def test_js_opredelenie(stroka):
    assert roli(stroka, "js") == {OPRED}


def test_js_vyzov():
    assert roli("const x = size(a);", "js") == {VYZOV}


# ═══ 4. C# ══════════════════════════════════════════════════════════════
@pytest.mark.parametrize("stroka", [
    "    public int Size { get; set; }",
    "    public void Size(string code)",
    "    private readonly Dictionary<string, int> Size = new();",
    "public class Size",
])
def test_cs_opredelenie(stroka):
    assert roli(stroka, "cs", "Size") == {OPRED}


@pytest.mark.parametrize("stroka", [
    "item.Size = 5;",
    "var t = new T { Size = 5 };",
    "Make(name: x, Size: 5);",
    "public void X() { Size = 5; }",
])
def test_cs_pishet(stroka):
    assert PISHET in roli(stroka, "cs", "Size")


@pytest.mark.parametrize("stroka", [
    "if (item.Size == 5) {}",
    "public int Total => Size * 2;",
    "var x = flag ? Size : 0;",
])
def test_cs_ne_pishet(stroka):
    r = roli(stroka, "cs", "Size")
    assert r and PISHET not in r


# ═══ 5. Комментарии, данные, текст ══════════════════════════════════════
def test_kommentarii():
    assert roli("# size = 5 — старое") == {KOMM}
    assert roli("x = 1  # size тут") == {KOMM}
    assert roli("// size = 5", "js") == {KOMM}
    assert roli(" * size меняется", "cs") == {KOMM}
    assert roli('url = "http://x/#size"') != {KOMM}


def test_dannye_i_tekst():
    assert roli('  "size": 5,', "dannye") == {DANNYE}
    assert roli("size: 5", "dannye") == {DANNYE}
    assert roli("python orders.py --size", "tekst") == {UPOM}


def test_yazyk_fayla():
    assert kp.yazyk_fayla("a/b.py") == "py"
    assert kp.yazyk_fayla("a/b.vue") == "js"
    assert kp.yazyk_fayla("a/b.ts") == "js"
    assert kp.yazyk_fayla("a/B.cs") == "cs"
    assert kp.yazyk_fayla("a/b.json") == "dannye"
    assert kp.yazyk_fayla("nightly.sh") == "tekst"
    assert kp.yazyk_fayla(".env") is None
    assert kp.yazyk_fayla("img.png") is None


# ═══ 6. Недостижимый код (после return) ═════════════════════════════════
def test_nedostizhimye_posle_return():
    kod = (
        "def f(row):\n"          # 1
        "    if row:\n"          # 2
        "        return 1\n"     # 3
        "    return 2\n"         # 4
        "    row.size = 5\n"     # 5  ← заплатка под return
        "    log(row)\n"         # 6
        "\n"
        "def g():\n"             # 8
        "    for x in y:\n"      # 9
        "        continue\n"     # 10
        "        x.size = 1\n"   # 11
    )
    assert kp.nedostizhimye_stroki(kod) == {5, 6, 11}


def test_nedostizhimye_bitiy_kod():
    assert kp.nedostizhimye_stroki("def f():\n    return\n    x = 1\n") == {3}
    assert kp.nedostizhimye_stroki("def f(:\n") == set()


# ═══ 7. Варианты имени ══════════════════════════════════════════════════
def test_varianty_snake():
    v = kp.varianty("stock_qty")
    assert v[0] == "stock_qty"
    assert {"stockQty", "StockQty", "stock-qty"} <= set(v)


def test_varianty_camel():
    assert {"stock_qty", "StockQty"} <= set(kp.varianty("stockQty"))


def test_varianty_bez_lishnego():
    assert len(kp.varianty("res_qty")) > 1
    assert kp.varianty("_rez") == ["_rez"]
    assert kp.varianty("MAX_SIZE") == ["MAX_SIZE"]
    assert len(kp.varianty("size")) == len(set(kp.varianty("size")))


# ═══ 8. Обход дерева и отчёт ════════════════════════════════════════════
@pytest.fixture
def repo(tmp_path):
    (tmp_path / "back").mkdir()
    (tmp_path / "back" / "orders.py").write_text(
        "def vydat(row):\n"
        "    row['stock_qty'] = 0\n"
        "    return row\n"
        "    row['stock_qty'] = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "front").mkdir()
    (tmp_path / "front" / "Orders.vue").write_text(
        "<script>\nconst n = item.stockQty;\n</script>\n", encoding="utf-8")
    (tmp_path / "nightly.sh").write_text("python orders.py\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("x.stock_qty = 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("stock_qty=SECRET\n", encoding="utf-8")
    (tmp_path / "cp.py").write_bytes("# старый файл\nstock_qty = 2  # остаток\n".encode("cp1251"))
    (tmp_path / "aaa.py").write_text("x = row.stock_qty\n", encoding="utf-8")  # читатель раньше в обходе
    big = tmp_path / "bundle.js"
    big.write_text("x.stock_qty=1;" + " " * 2_100_000, encoding="utf-8")
    return tmp_path


def test_naiti_vse_puti(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)
    mesta = {(n.put.replace("\\", "/"), n.nomer): n for n in o.nahodki}
    assert PISHET in mesta[("back/orders.py", 2)].roli
    assert "НЕДОСТИЖИМ" in mesta[("back/orders.py", 4)].roli
    assert CHITAET in mesta[("front/Orders.vue", 2)].roli      # вариант camelCase
    assert PISHET in mesta[("cp.py", 2)].roli                 # файл в cp1251
    assert "остаток" in mesta[("cp.py", 2)].tekst             # и прочитан как cp1251
    puti = {p for p, _ in mesta}
    assert not any("node_modules" in p for p in puti)
    assert ".env" not in puti
    assert "bundle.js" not in puti
    assert [Path(b).name for b in o.bolshie] == ["bundle.js"]
    assert o.poisk == "stdlib"


def test_tablica_md(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)
    t = kp.tablica_md(o)
    assert "| ПИШЕТ" in t and "back/orders.py:2" in t.replace("\\", "/")
    assert "НЕДОСТИЖИМ" in t
    assert "bundle.js" in t                    # пропуск назван, а не молча
    assert t.index("| ПИШЕТ") < t.index("| ЧИТАЕТ")  # писатели первыми


def test_main_kod_vozvrata_i_json(repo, capsys):
    assert kp.main(["stock_qty", "-k", str(repo), "--bez-rg", "--json"]) == 0
    dannye = json.loads(capsys.readouterr().out)
    assert any(d["roli"] == ["ПИШЕТ"] for d in dannye["nahodki"])
    assert kp.main(["netu_takogo_polya", "-k", str(repo), "--bez-rg"]) == 1
    assert "НИЧЕГО НЕ НАЙДЕНО" in capsys.readouterr().out


def test_testy_otdelno_ot_koda(repo):
    (repo / "tests").mkdir()
    (repo / "tests" / "test_orders.py").write_text("row.stock_qty = 9\n", encoding="utf-8")
    (repo / "zzz.py").write_text("row.stock_qty = 7\n", encoding="utf-8")
    o = kp.naiti([str(repo)], ["stock_qty"], ispolzovat_rg=False)
    assert kp.eto_test("tests/test_orders.py") and kp.eto_test("src/A.Tests/BTests.cs")
    assert kp.eto_test("web/x.spec.ts") and not kp.eto_test("back/orders.py")
    t = kp.tablica_md(o).replace("\\", "/")
    assert t.index("zzz.py:1") < t.index("tests/test_orders.py:1 (тест)")  # код раньше тестов
    assert "из них в тестах 1" in t


def test_spisok_bolshih_szhat():
    o = kp.Otchet(imena={"x": ["x"]}, korni=["."], nahodki=[],
                  bolshie=[f"b{i}.html" for i in range(9)])
    t = kp.tablica_md(o)
    assert "Пропущено файлов > 2 МБ: 9" in t and "b4.html" in t
    assert "b5.html" not in t and "и ещё 4" in t


def test_vse_vklyuchaet_propushchennye_papki(repo):
    o = kp.naiti([str(repo)], ["stock_qty"], vse=True, ispolzovat_rg=False)
    assert any("node_modules" in n.put for n in o.nahodki)


# ═══ 9. Выбор поиска (rg / stdlib) ══════════════════════════════════════
def test_bez_rg_na_pk_idyot_stdlib(repo, monkeypatch):
    monkeypatch.setattr(kp.shutil, "which", lambda _: None)
    assert kp.naiti([str(repo)], ["stock_qty"]).poisk == "stdlib"


def test_razobrat_vyvod_rg():
    vyvod = "C:\\r\\back\\orders.py\x002:    row['stock_qty'] = 0\nC:\\r\\a.py\x0010:x = 1:2\n"
    assert kp.razobrat_vyvod_rg(vyvod) == [
        ("C:\\r\\back\\orders.py", 2, "    row['stock_qty'] = 0"),
        ("C:\\r\\a.py", 10, "x = 1:2"),
    ]
