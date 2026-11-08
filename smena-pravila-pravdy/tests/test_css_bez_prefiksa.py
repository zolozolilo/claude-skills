"""Тесты css_bez_prefiksa.py — правило CSS раздела только внутри его контейнера.

Оглавление:
  1. Селекторы CSS: с приставкой / без
  2. Вложенность @media, пропуск @keyframes и @font-face, комментарии
  3. Vue: <style> проверяется, <style scoped> нет
  4. Только добавленные строки (git diff)
  5. Запуск целиком
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import css_bez_prefiksa as cp  # noqa: E402

P = [".orders"]


def selektory(tekst, prefiksy=P, vue=False):
    return [s for _, s in cp.narusheniya(tekst, prefiksy, vue=vue)]


# ═══ 1. Селекторы ═══════════════════════════════════════════════════════
def test_s_pristavkoy_chisto():
    assert selektory(".orders .btn { color: red }\n.orders{margin:0}") == []


def test_bez_pristavki_naruschenie():
    assert selektory(".btn { color: red }") == [".btn"]


@pytest.mark.parametrize("s", ["html", "body", "*", ":root", "table", "td:hover", "#app", "a"])
def test_globalnye_selektory(s):
    assert selektory(s + " { x: 1 }") == [s]


def test_spisok_cherez_zapyatuyu_kazhdyy_proveryaetsya():
    assert selektory(".orders .a, .other .b, .orders .c { x: 1 }") == [".other .b"]


def test_zapyataya_vnutri_skobok_ne_delit():
    assert selektory(".orders .a:is(.x, .y) { x: 1 }") == []


def test_prefiks_ne_podstroka():
    assert selektory(".orders-old .a { x: 1 }") == [".orders-old .a"]


def test_neskolko_prefiksov():
    assert selektory(".tree-row{x:1}\n.other{x:1}", prefiksy=[".tree-", ".orders"]) == [".other"]


def test_prefiks_s_tire_dopuskaet_prodolzhenie():
    assert selektory(".tree-row .x{x:1}", prefiksy=[".tree-"]) == []


def test_nomer_stroki():
    nar = cp.narusheniya("\n\n.bad { x: 1 }", P)
    assert nar == [(3, ".bad")]


# ═══ 2. Вложенность, пропуски, комментарии ══════════════════════════════
def test_media_vnutri_proveryaetsya():
    css = "@media (min-width: 1200px) {\n .orders .a { x: 1 }\n .b { x: 1 }\n}"
    assert selektory(css) == [".b"]


def test_keyframes_i_fontface_ne_selektory():
    css = "@keyframes pulse { from { x: 1 } to { x: 2 } }\n@font-face { font-family: F; }"
    assert selektory(css) == []


def test_kommentarii_ne_schitayutsya():
    css = "/* .bad { x: 1 } */\n.orders .a { x: 1 } /* } { */"
    assert selektory(css) == []


def test_stroki_so_skobkami_v_znacheniyah():
    css = '.orders .a::after { content: "}{"; }\n.bad { x: 1 }'
    assert selektory(css) == [".bad"]


# ═══ 3. Vue ═════════════════════════════════════════════════════════════
VUE = """<template><div/></template>
<style>
.glob { x: 1 }
</style>
<style scoped>
.loc { x: 1 }
</style>
"""


def test_vue_style_proveryaetsya_scoped_net():
    nar = cp.narusheniya(VUE, P, vue=True)
    assert [s for _, s in nar] == [".glob"] and nar[0][0] == 3   # номер строки в файле .vue


# ═══ 4. Только добавленные строки ═══════════════════════════════════════
def test_tolko_dobavlennye():
    nar = cp.narusheniya(".old { x: 1 }\n.orders .a{x:1}\n.new { x: 1 }", P)
    assert cp.tolko_dobavlennye(nar, {3}) == [(3, ".new")]


def test_razobrat_diff():
    diff = ("diff --git a/a.css b/a.css\n--- a/a.css\n+++ b/a.css\n"
            "@@ -1,0 +2,2 @@\n+.x{}\n+.y{}\n@@ -9 +12 @@\n-a\n+b\n")
    assert cp.dobavlennye_iz_diff(diff) == {"a.css": {2, 3, 12}}


# ═══ 5. Запуск целиком ══════════════════════════════════════════════════
def test_main_fayl(tmp_path, capsys):
    f = tmp_path / "a.css"
    f.write_text(".bad { x: 1 }\n.orders .ok{x:1}\n", encoding="utf-8")
    assert cp.main([str(f), "--prefiks", ".orders"]) == 1
    assert ".bad" in capsys.readouterr().out
    f.write_text(".orders .ok{x:1}\n", encoding="utf-8")
    assert cp.main([str(f), "--prefiks", ".orders"]) == 0


def test_main_diff(tmp_path, capsys):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (tmp_path / "a.css").write_text(".old { x: 1 }\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    (tmp_path / "a.css").write_text(".old { x: 1 }\n.new { x: 1 }\n", encoding="utf-8")
    assert cp.main(["--diff", "HEAD", "--repo", str(tmp_path), "--prefiks", ".orders"]) == 1
    out = capsys.readouterr().out
    assert ".new" in out and ".old" not in out      # старое не ругаем, только добавленное
