"""pole_est — поле есть в живой записи или выдумано.

Закрывает урок «придумал поле, которого в данных нет»: тест строил
вход тем же выдуманным полем и был зелёным. До логики по полю — показать поле в
настоящем образце (выборка с тестового или живого стенда, только чтение).

    python pole_est.py sku stock_qty --obrazec snimok.json
    python pole_est.py price --obrazec items.jsonl

Образец: JSON (список, словарь по номеру, или один объект), JSONL, CSV. Печатает путь поля,
в скольких записях оно есть, сколько раз null, пример значения; чего нет — «НЕТ В ОБРАЗЦЕ»
и настоящая схема, чтобы увидеть реальные имена. Код выхода: 0 — все поля есть, 1 — чего-то нет.

Оглавление:
  1. Загрузка образца
  2. Схема: пути полей, доли, null
  3. Проверка полей (точное имя, snake/camel, похожие)
  4. Запуск
"""
import argparse
import csv
import difflib
import json
import re
import sys
from pathlib import Path

POKAZ_SHEMY = 40


# ═══ 1. Загрузка образца ════════════════════════════════════════════════
def zagruzit(put):
    put = Path(put)
    tekst = put.read_text(encoding="utf-8-sig", errors="replace")
    if put.suffix.lower() == ".csv":
        zapisi = list(csv.DictReader(tekst.splitlines()))
    elif put.suffix.lower() in (".jsonl", ".ndjson"):
        zapisi = [json.loads(s) for s in tekst.splitlines() if s.strip()]
    else:
        d = json.loads(tekst)
        if isinstance(d, list):
            zapisi = d
        elif isinstance(d, dict) and d and all(isinstance(v, dict) for v in d.values()):
            zapisi = list(d.values())     # словарь «номер → запись»
        else:
            zapisi = [d]
    zapisi = [z for z in zapisi if isinstance(z, dict)]
    if not zapisi:
        raise ValueError("образец пуст или без записей-объектов: взять другой снимок")
    return zapisi


# ═══ 2. Схема ═══════════════════════════════════════════════════════════
def _puti(obj, prefiks=""):
    for k, v in obj.items():
        p = f"{prefiks}.{k}" if prefiks else str(k)
        yield p, v
        if isinstance(v, dict):
            yield from _puti(v, p)


def shema(zapisi):
    """{путь: {est, null, vsego, primer, tipy}} по всем записям."""
    s = {}
    for z in zapisi:
        for p, v in _puti(z):
            d = s.setdefault(p, {"est": 0, "null": 0, "primer": None, "tipy": set()})
            d["est"] += 1
            d["tipy"].add(type(v).__name__)
            if v is None:
                d["null"] += 1
            elif d["primer"] is None and not isinstance(v, dict):
                d["primer"] = v
    for d in s.values():
        d["vsego"] = len(zapisi)
    return s


# ═══ 3. Проверка полей ══════════════════════════════════════════════════
def _slova(imya):
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", imya.replace("-", "_").replace("_", " "))]


def _tot_zhe(a, b):
    return _slova(a) == _slova(b)


def proverit(s, polya):
    itog = []
    for pole in polya:
        puti = [p for p in s if _tot_zhe(p.split(".")[-1], pole) or _tot_zhe(p, pole)]
        pohozhie = [] if puti else difflib.get_close_matches(
            pole, list(s) + [p.split(".")[-1] for p in s], n=4, cutoff=0.6)
        pohozhie = list(dict.fromkeys(
            next((p for p in s if p == x or p.split(".")[-1] == x), x) for x in pohozhie))
        itog.append({"pole": pole, "puti": puti, "net": not puti, "pohozhie": pohozhie,
                     "chasto_null": any(s[p]["null"] * 2 >= s[p]["vsego"] for p in puti)})
    return itog


# ═══ 4. Запуск ══════════════════════════════════════════════════════════
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="pole_est", description=__doc__.split("\n\n")[0])
    p.add_argument("polya", nargs="+", help="поле(я), по которому хотят писать логику")
    p.add_argument("--obrazec", required=True, help="файл с живыми записями (JSON/JSONL/CSV)")
    a = p.parse_args(argv)
    try:
        zapisi = zagruzit(a.obrazec)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"НЕ ЗНАЮ: образец не прочитан: {e}", file=sys.stderr)
        return 2
    s = shema(zapisi)
    itog = proverit(s, a.polya)
    print(f"## pole_est: образец {Path(a.obrazec).name}, записей {len(zapisi)}")
    for r in itog:
        if r["net"]:
            print(f"НЕТ В ОБРАЗЦЕ: «{r['pole']}»" + (f" · похожие: {', '.join(r['pohozhie'])}" if r["pohozhie"] else ""))
            continue
        for put in r["puti"]:
            d = s[put]
            print(f"ЕСТЬ: {put} · в {d['est']} из {d['vsego']} · null {d['null']} · "
                  f"типы {'/'.join(sorted(d['tipy']))} · пример {d['primer']!r}")
        if r["chasto_null"]:
            print(f"  ⚠ «{r['pole']}» чаще пусто, чем нет: пусто ≠ 0, в суммах не превращать в 0")
    if any(r["net"] for r in itog):
        print("--- настоящая схема образца (первые %d путей) ---" % POKAZ_SHEMY)
        for put in list(s)[:POKAZ_SHEMY]:
            print(f"  {put} ({'/'.join(sorted(s[put]['tipy']))}, {s[put]['est']}/{s[put]['vsego']})")
        print("Поля нет — значение None и пометка «источника нет», а не угадывание; тест — с настоящей записью.")
    return 1 if any(r["net"] for r in itog) else 0


if __name__ == "__main__":
    sys.exit(main())
