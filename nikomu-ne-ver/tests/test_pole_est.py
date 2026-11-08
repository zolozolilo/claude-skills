"""Тесты pole_est.py — поле есть в живой записи или выдумано.

Оглавление:
  1. Разбор образца (JSON, JSONL, CSV)
  2. Проверка полей: есть / нет / похожее / чаще null
  3. Запуск целиком
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pole_est as pe  # noqa: E402

ZAPISI = [
    {"id": 1, "n": "Футболка", "q": {"stock": 5, "post": 2}, "sz": "M", "col": None},
    {"id": 2, "n": "Лонг", "q": {"stock": 0, "post": 1}, "sz": "L", "col": None},
    {"id": 3, "n": "Худи", "q": {"stock": 7}, "sz": None, "col": "чёрный"},
]


# ═══ 1. Разбор образца ══════════════════════════════════════════════════
def test_json_spisok(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(ZAPISI), encoding="utf-8")
    assert len(pe.zagruzit(f)) == 3


def test_json_slovar_po_nomeru(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"101": ZAPISI[0], "102": ZAPISI[1]}), encoding="utf-8")
    z = pe.zagruzit(f)
    assert len(z) == 2 and z[0]["id"] == 1


def test_jsonl(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(z, ensure_ascii=False) for z in ZAPISI), encoding="utf-8")
    assert len(pe.zagruzit(f)) == 3


def test_csv(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("id,name\n1,a\n2,b\n", encoding="utf-8")
    assert pe.zagruzit(f) == [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]


def test_pustoy_obrazec(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        pe.zagruzit(f)


# ═══ 2. Проверка полей ══════════════════════════════════════════════════
def test_pole_est_s_putem_i_dolej():
    s = pe.shema(ZAPISI)
    assert s["q.stock"]["est"] == 3 and s["q.post"]["est"] == 2 and s["id"]["vsego"] == 3


def test_proverit_najdeno():
    r = pe.proverit(pe.shema(ZAPISI), ["stock"])[0]
    assert r["pole"] == "stock" and r["puti"] == ["q.stock"] and not r["net"]


def test_proverit_net():
    r = pe.proverit(pe.shema(ZAPISI), ["barcode", "size"])
    assert all(x["net"] for x in r)


def test_pohozhee_po_opechatke():
    r = pe.proverit(pe.shema(ZAPISI), ["pos"])[0]
    assert r["net"] and "q.post" in r["pohozhie"]


def test_chasto_null_otmecheno():
    s = pe.shema(ZAPISI)
    assert s["col"]["null"] == 2
    assert pe.proverit(s, ["col"])[0]["chasto_null"]


def test_variant_imeni_camel():
    r = pe.proverit(pe.shema([{"stockQty": 5}]), ["stock_qty"])[0]
    assert not r["net"] and r["puti"] == ["stockQty"]


# ═══ 3. Запуск целиком ══════════════════════════════════════════════════
def test_main_net_polya(tmp_path, capsys):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(ZAPISI), encoding="utf-8")
    assert pe.main(["barcode", "--obrazec", str(f)]) == 1
    out = capsys.readouterr().out
    assert "НЕТ В ОБРАЗЦЕ" in out and "q.stock" in out   # настоящая схема показана


def test_main_est_pole(tmp_path, capsys):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(ZAPISI), encoding="utf-8")
    assert pe.main(["stock", "--obrazec", str(f)]) == 0
    assert "q.stock" in capsys.readouterr().out
