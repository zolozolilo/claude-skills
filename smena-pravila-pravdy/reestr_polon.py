"""reestr_polon — каждый файл папки назван в реестре (и реестр не ссылается на пустое место).

Закрывает класс «правка не по всем путям», вариант «забыли строку в списке»:
типичные случаи: скрипт выкладки не знает нового модуля; проверка ищет метку только в
главном файле; «раздел готов», а строки в sections.js нет.

    python reestr_polon.py --papka src --shablon "*Section*.js" --reestr src/sections.js
    python reestr_polon.py --papka app --shablon "*.py" --reestr deploy.sh --reestr nightly.sh
    python reestr_polon.py --papka src --shablon "*Section*.js" --reestr sections.js \\
        "--ubrat=-[0-9a-f]{6}$" "--izvlech=\\b(\\w+Section)\\b"

Имя файла = имя без расширения (--ubrat — regexp, который вырезать: хэш-хвост сборки).
Файл должен быть назван в КАЖДОМ реестре целым словом (подстрока «OrdersSectionOld» не считается).
--izvlech — regexp имён внутри реестра: покажет ссылки на несуществующие файлы.
Код выхода: 0 — всё на месте; 1 — есть расхождения или папка пуста; 2 — нет реестра/папки.
Это механическая сверка по имени: что реестр вызывает файл правильно — отдельный тест.

Оглавление:
  1. Имена файлов папки
  2. Сверка с реестрами
  3. Запуск
"""
import argparse
import fnmatch
import re
import sys
from pathlib import Path


# ═══ 1. Имена файлов папки ══════════════════════════════════════════════
def imena_v_papke(papka, shablony, ubrat=""):
    imena = set()
    for f in Path(papka).rglob("*"):
        if f.is_file() and any(fnmatch.fnmatch(f.name, sh) for sh in shablony):
            imya = f.stem
            imena.add(re.sub(ubrat, "", imya) if ubrat else imya)
    return imena


# ═══ 2. Сверка с реестрами ══════════════════════════════════════════════
def _nazvan(imya, tekst):
    return re.search(r"(?<!\w)" + re.escape(imya) + r"(?!\w)", tekst) is not None


def sverit(papka, shablony, reestry, ubrat="", izvlech=None):
    imena = imena_v_papke(papka, shablony, ubrat)
    otchet = {"ok": True, "pusto": not imena, "imena": sorted(imena),
              "net_v_reestre": {}, "net_faila": {}}
    for reestr in reestry:
        tekst = Path(reestr).read_text(encoding="utf-8", errors="replace")   # нет файла — исключение
        net = sorted(i for i in imena if not _nazvan(i, tekst))
        if net:
            otchet["net_v_reestre"][str(reestr)] = net
        if izvlech:
            nazvannye = {m if isinstance(m, str) else m[0] for m in re.findall(izvlech, tekst)}
            lishnie = sorted(nazvannye - imena)
            if lishnie:
                otchet["net_faila"][str(reestr)] = lishnie
    otchet["ok"] = not (otchet["pusto"] or otchet["net_v_reestre"] or otchet["net_faila"])
    return otchet


# ═══ 3. Запуск ══════════════════════════════════════════════════════════
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="reestr_polon", description=__doc__.split("\n\n")[0])
    p.add_argument("--papka", required=True)
    p.add_argument("--shablon", action="append", required=True, help="маска имени файла, можно несколько")
    p.add_argument("--reestr", action="append", required=True, help="файл-реестр (sections.js, скрипт выкладки…)")
    p.add_argument("--ubrat", default="", help="regexp, который вырезать из имени файла (хэш-хвост)")
    p.add_argument("--izvlech", help="regexp имён внутри реестра (группа 1) — искать ссылки в пустоту")
    a = p.parse_args(argv)
    if not Path(a.papka).is_dir():
        print(f"нет папки: {a.papka}", file=sys.stderr)
        return 2
    try:
        o = sverit(a.papka, a.shablon, a.reestr, a.ubrat, a.izvlech)
    except FileNotFoundError as e:
        print(f"нет реестра: {e.filename}", file=sys.stderr)
        return 2
    print(f"## reestr_polon: в папке {len(o['imena'])} имён ({', '.join(o['imena'][:8])}"
          f"{'…' if len(o['imena']) > 8 else ''}), реестров {len(a.reestr)}")
    if o["pusto"]:
        print("⚠ ПАПКА ПУСТА по маске — проверь папку и маску: пустая сверка ничего не доказывает")
    for r, net in o["net_v_reestre"].items():
        print(f"⚠ НЕ В РЕЕСТРЕ {r}: {', '.join(net)}")
    for r, net in o["net_faila"].items():
        print(f"⚠ В РЕЕСТРЕ {r}, НО ФАЙЛА НЕТ: {', '.join(net)}")
    if o["ok"]:
        print("OK: все файлы названы во всех реестрах")
    return 0 if o["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
