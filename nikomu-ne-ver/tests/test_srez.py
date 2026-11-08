"""Тесты srez.py — свежий срез: время, двойное чтение, метка, контроль «нет».

Оглавление:
  1. Время среза (МСК)
  2. Запуск команды: успех, падение, нет команды, таймаут
  3. Решение по чтениям (reshit)
  4. Запуск целиком (main)
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import srez  # noqa: E402

PY = sys.executable


def chtenie(vyvod, kod=0, prichina=""):
    return srez.Rezultat(kod=kod, vyvod=vyvod, prichina=prichina)


# ═══ 1. Время среза (МСК) ═══════════════════════════════════════════════
def test_vremya_sreza_msk():
    t = datetime(2026, 1, 1, 15, 41, 5, tzinfo=timezone.utc)
    assert srez.vremya_sreza(t) == "18:41:05 МСК"


# ═══ 2. Запуск команды ══════════════════════════════════════════════════
def test_vypolnit_uspeh():
    r = srez.vypolnit([PY, "-c", "print('ok')"], timeout=20)
    assert r.kod == 0 and "ok" in r.vyvod


def test_vypolnit_padenie():
    r = srez.vypolnit([PY, "-c", "import sys; print('x'); sys.exit(3)"], timeout=20)
    assert r.kod == 3


def test_vypolnit_net_komandy():
    r = srez.vypolnit(["net-takoj-komandy-xyz"], timeout=5)
    assert r.kod is None and r.prichina


def test_vypolnit_taymaut():
    r = srez.vypolnit([PY, "-c", "import time; time.sleep(30)"], timeout=1)
    assert r.kod is None and "таймаут" in r.prichina


# ═══ 3. Решение по чтениям ══════════════════════════════════════════════
def test_stabilno_i_ok():
    kod, stroki = srez.reshit([chtenie("a 1\n"), chtenie("a 1\n")])
    assert kod == 0 and "СТАБИЛЬНО" in "\n".join(stroki)


def test_padenie_proverki_eto_ne_znayu():
    kod, stroki = srez.reshit([chtenie("", kod=1)])
    assert kod == 3 and "НЕ ЗНАЮ" in "\n".join(stroki)


def test_pustoy_vyvod_eto_ne_znayu():
    kod, stroki = srez.reshit([chtenie("  \n")])
    assert kod == 3 and "пуст" in "\n".join(stroki)


def test_net_komandy_eto_ne_znayu():
    kod, _ = srez.reshit([srez.Rezultat(kod=None, vyvod="", prichina="не найдена")])
    assert kod == 3


def test_metka_otvechayushchego_otsutstvuet():
    kod, stroki = srez.reshit([chtenie("версия 1.148\n")], ozhidat=["host-A"])
    assert kod == 4 and "МЕТКИ НЕТ" in "\n".join(stroki)


def test_metka_na_meste():
    kod, _ = srez.reshit([chtenie("host-A v1.149\n")] * 2, ozhidat=["host-A"])
    assert kod == 0


def test_menyaetsya_mezhdu_chteniyami():
    kod, stroki = srez.reshit([chtenie("md5 aaa\n"), chtenie("md5 bbb\n")])
    assert kod == 5 and "МЕНЯЕТСЯ" in "\n".join(stroki)


def test_net_dopustimo_tolko_s_kontrolem():
    vyvod = "id=1 PK K\nid=2 PK L\n"
    kod, stroki = srez.reshit([chtenie(vyvod)] * 2, ishchu="PK M", kontrol="PK K")
    assert kod == 0 and "«нет» допустимо" in "\n".join(stroki)


def test_poisk_negoden_bez_kontrolya():
    kod, stroki = srez.reshit([chtenie("пусто, но не то\n")], ishchu="PK M", kontrol="PK K")
    assert kod == 6 and "ПОИСК НЕГОДЕН" in "\n".join(stroki)


def test_ishchu_nashlos():
    kod, stroki = srez.reshit([chtenie("PK M\nPK K\n")] * 2, ishchu="PK M", kontrol="PK K")
    assert kod == 0 and "ЕСТЬ" in "\n".join(stroki)


def test_ishchu_trebuet_kontrol():
    kod, stroki = srez.reshit([chtenie("a\n")], ishchu="PK M", kontrol=None)
    assert kod == 6 and "контроль" in "\n".join(stroki)


# ═══ 4. Запуск целиком ══════════════════════════════════════════════════
def test_main_stabilno(capsys):
    assert srez.main(["--raza", "2", "--pauza", "0", "--", PY, "-c", "print('v1')"]) == 0
    out = capsys.readouterr().out
    assert "СРЕЗ" in out and "МСК" in out and "v1" in out


def test_main_menyaetsya(tmp_path, capsys):
    f = tmp_path / "n.txt"
    f.write_text("0")
    kod = ("import pathlib;p=pathlib.Path(r'%s');n=int(p.read_text())+1;"
           "p.write_text(str(n));print(n)" % f)
    assert srez.main(["--raza", "2", "--pauza", "0", "--", PY, "-c", kod]) == 5


def test_main_padenie(capsys):
    assert srez.main(["--raza", "1", "--", PY, "-c", "import sys; sys.exit(7)"]) == 3
