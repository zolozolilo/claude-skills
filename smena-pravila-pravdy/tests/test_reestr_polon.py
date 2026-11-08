"""Тесты reestr_polon.py — каждый файл папки назван в реестре (и наоборот).

Оглавление:
  1. Имена файлов папки (шаблон, хвост-хэш)
  2. Сверка с одним реестром
  3. Несколько реестров (sections.js + скрипт выкладки)
  4. Запуск целиком
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reestr_polon as rp  # noqa: E402


@pytest.fixture
def proekt(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for imya in ("OrdersSection.js", "ReportsSection.js", "LoginSection-3fa9c1.js", "util.js"):
        (src / imya).write_text("//", encoding="utf-8")
    (tmp_path / "sections.js").write_text(
        "export default ['OrdersSection', 'ReportsSection']\n", encoding="utf-8")
    return tmp_path


# ═══ 1. Имена файлов папки ══════════════════════════════════════════════
def test_imena_po_shablonu(proekt):
    imena = rp.imena_v_papke(proekt / "src", ["*Section*.js"], ubrat=r"-[0-9a-f]{6}$")
    assert imena == {"OrdersSection", "ReportsSection", "LoginSection"}


def test_bez_shablona_berutsya_vse(proekt):
    assert "util" in rp.imena_v_papke(proekt / "src", ["*.js"], ubrat="")


# ═══ 2. Сверка с одним реестром ═════════════════════════════════════════
def test_poteryannyy_razdel_najden(proekt):
    otchet = rp.sverit(proekt / "src", ["*Section*.js"], [proekt / "sections.js"],
                       ubrat=r"-[0-9a-f]{6}$")
    assert otchet["net_v_reestre"][str(proekt / "sections.js")] == ["LoginSection"]
    assert not otchet["ok"]


def test_vse_na_meste(proekt):
    (proekt / "sections.js").write_text("OrdersSection ReportsSection LoginSection", encoding="utf-8")
    assert rp.sverit(proekt / "src", ["*Section*.js"], [proekt / "sections.js"],
                     ubrat=r"-[0-9a-f]{6}$")["ok"]


def test_podstroka_ne_zasчityvaetsya(proekt):
    (proekt / "sections.js").write_text("OrdersSectionOld ReportsSection LoginSection", encoding="utf-8")
    o = rp.sverit(proekt / "src", ["*Section*.js"], [proekt / "sections.js"], ubrat=r"-[0-9a-f]{6}$")
    assert o["net_v_reestre"][str(proekt / "sections.js")] == ["OrdersSection"]


def test_reestr_ssylaetsya_na_nesushchestvuyushchee(proekt):
    (proekt / "sections.js").write_text(
        "import 'OrdersSection'; 'ReportsSection'; 'LoginSection'; 'GhostSection'", encoding="utf-8")
    o = rp.sverit(proekt / "src", ["*Section*.js"], [proekt / "sections.js"],
                  ubrat=r"-[0-9a-f]{6}$", izvlech=r"\b(\w+Section)\b")
    assert o["net_faila"][str(proekt / "sections.js")] == ["GhostSection"]
    assert not o["ok"]


# ═══ 3. Несколько реестров ══════════════════════════════════════════════
def test_nuzhno_vo_vsekh_reestrah(proekt):
    (proekt / "sections.js").write_text("OrdersSection ReportsSection LoginSection", encoding="utf-8")
    (proekt / "deploy.sh").write_text("cp OrdersSection ReportsSection\n", encoding="utf-8")
    o = rp.sverit(proekt / "src", ["*Section*.js"],
                  [proekt / "sections.js", proekt / "deploy.sh"], ubrat=r"-[0-9a-f]{6}$")
    assert o["net_v_reestre"][str(proekt / "deploy.sh")] == ["LoginSection"]
    assert str(proekt / "sections.js") not in o["net_v_reestre"]


def test_net_takogo_reestra(proekt):
    with pytest.raises(FileNotFoundError):
        rp.sverit(proekt / "src", ["*.js"], [proekt / "net.js"])


def test_pustaya_papka_ne_ok(tmp_path):
    (tmp_path / "e").mkdir()
    (tmp_path / "r.txt").write_text("x", encoding="utf-8")
    o = rp.sverit(tmp_path / "e", ["*.js"], [tmp_path / "r.txt"])
    assert not o["ok"] and o["pusto"]


# ═══ 4. Запуск целиком ══════════════════════════════════════════════════
def test_main_kod_vyhoda(proekt, capsys):
    argv = ["--papka", str(proekt / "src"), "--shablon", "*Section*.js",
            "--reestr", str(proekt / "sections.js"), r"--ubrat=-[0-9a-f]{6}$"]
    assert rp.main(argv) == 1
    assert "LoginSection" in capsys.readouterr().out
    (proekt / "sections.js").write_text("OrdersSection ReportsSection LoginSection", encoding="utf-8")
    assert rp.main(argv) == 0
