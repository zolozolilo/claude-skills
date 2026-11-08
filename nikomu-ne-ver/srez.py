"""srez — свежий срез: команда читается заново, с временем, двойным чтением и контролем.

Закрывает уроки «утверждение без свежей проверки»: число из старого
подсчёта, «ответ пришёл» без метки отвечавшего, упавшая проверка принята за «нет»,
md5 по одному чтению, «нет такой записи» без проверки поиска на заведомо живой.

    python srez.py -- ssh myhost "md5sum /opt/app/app.py"
    python srez.py --raza 2 --pauza 60 -- ssh myhost "systemctl is-active app"
    python srez.py --ozhidat "host-A" -- curl -s https://example.com/health
    python srez.py --ishchu "item-1" --kontrol "item-2" -- ssh myhost "cat /srv/data.json"

Коды выхода: 0 — можно говорить; 3 — «НЕ ЗНАЮ» (упала, нет команды, пустой вывод);
4 — метки отвечавшего нет; 5 — между чтениями изменилось; 6 — поиск «нет» негоден.
Только stdlib. Команда выполняется без оболочки (список аргументов после «--»).

Оглавление:
  1. Время среза (МСК)
  2. Запуск команды
  3. Решение по чтениям
  4. Запуск
"""
import argparse
import hashlib
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
STROK_V_OTVETE = 40


# ═══ 1. Время среза (МСК) ═══════════════════════════════════════════════
def vremya_sreza(sejchas=None):
    """«18:41:05 МСК» — время, которое пишется рядом с цифрой пользователю."""
    t = (sejchas or datetime.now(timezone.utc)).astimezone(MSK)
    return t.strftime("%H:%M:%S") + " МСК"


# ═══ 2. Запуск команды ══════════════════════════════════════════════════
@dataclass
class Rezultat:
    kod: int | None        # None — команда не запустилась или не уложилась во время
    vyvod: str
    prichina: str = ""


def vypolnit(komanda, timeout=60):
    try:
        p = subprocess.run(komanda, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return Rezultat(None, "", f"команда не найдена: {komanda[0]}")
    except subprocess.TimeoutExpired:
        return Rezultat(None, "", f"таймаут {timeout} с")
    except OSError as e:
        return Rezultat(None, "", f"не запустилась: {e}")
    vyvod = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    return Rezultat(p.returncode, vyvod)


# ═══ 3. Решение по чтениям ══════════════════════════════════════════════
def _hesh(tekst):
    return hashlib.md5(tekst.encode("utf-8")).hexdigest()[:8]


def reshit(chteniya, ozhidat=(), ishchu=None, kontrol=None):
    """(код выхода, строки вывода). Порядок важности: НЕ ЗНАЮ → метка → поиск → изменилось."""
    for i, r in enumerate(chteniya, 1):
        if r.kod is None or r.kod != 0:
            pri = r.prichina or f"код выхода {r.kod}"
            return 3, [f"НЕ ЗНАЮ: проверка не удалась (чтение {i}: {pri}). "
                       "Падение — это не «нет» и не «всё хорошо»; так и сказать пользователю."]
        if not r.vyvod.strip():
            return 3, [f"НЕ ЗНАЮ: пустой вывод (чтение {i}). Пустое — это «не знаю», а не «нет»: "
                       "проверь, что команда читает то, что нужно."]
    vyvod = chteniya[-1].vyvod
    for m in ozhidat:
        if m not in vyvod:
            return 4, [f"МЕТКИ НЕТ: «{m}» не найдена в ответе. Отвечал, возможно, не тот "
                       "(своя копия, старая служба, другая машина) — закрыть свои копии и повторить."]
    if ishchu is not None:
        if not kontrol:
            return 6, ["ПОИСК НЕГОДЕН: для «нет» нужен --kontrol — запись, которая заведомо есть "
                       "(положительный контроль), иначе «нет» ничего не доказывает."]
        if kontrol not in vyvod:
            return 6, [f"ПОИСК НЕГОДЕН: контроль «{kontrol}» не найден — читается не то "
                       "(другая форма данных, другой файл). Слово «нет» говорить нельзя."]
    heshi = [_hesh(r.vyvod) for r in chteniya]
    if len(set(heshi)) > 1:
        return 5, [f"МЕНЯЕТСЯ: чтения дали разное ({' ≠ '.join(heshi)}) — файл копируют или данные "
                   "живые. Называть число только с оговоркой «меняется», или подождать и повторить."]
    stroki = [f"СТАБИЛЬНО: {len(chteniya)} чт., хэш {heshi[0]}, строк {len(vyvod.splitlines())}"]
    if ishchu is not None:
        if ishchu in vyvod:
            stroki.append(f"ЕСТЬ: «{ishchu}» найдена (контроль «{kontrol}» тоже на месте).")
        else:
            stroki.append(f"«нет» допустимо: «{ishchu}» не найдена, контроль «{kontrol}» найден.")
    return 0, stroki


# ═══ 4. Запуск ══════════════════════════════════════════════════════════
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="srez", description=__doc__.split("\n\n")[0])
    p.add_argument("--raza", type=int, default=2, help="сколько раз прочитать (по умолчанию 2)")
    p.add_argument("--pauza", type=float, default=3, help="секунд между чтениями")
    p.add_argument("--timeout", type=float, default=60, help="секунд на одно чтение")
    p.add_argument("--ozhidat", action="append", default=[], help="метка, которая должна быть в ответе")
    p.add_argument("--ishchu", help="что ищем; «нет» допустимо только с --kontrol")
    p.add_argument("--kontrol", help="запись, которая заведомо есть в ответе")
    p.add_argument("--stroki", type=int, default=STROK_V_OTVETE, help="сколько строк вывода показать")
    p.add_argument("komanda", nargs=argparse.REMAINDER, help="после «--»: команда и аргументы")
    a = p.parse_args(argv)
    komanda = a.komanda[1:] if a.komanda[:1] == ["--"] else a.komanda
    if not komanda:
        print("нужна команда после «--»", file=sys.stderr)
        return 2
    chteniya = []
    for i in range(max(a.raza, 1)):
        if i:
            time.sleep(a.pauza)
        chteniya.append(vypolnit(komanda, a.timeout))
        if chteniya[-1].kod != 0:
            break
    kod, stroki = reshit(chteniya, a.ozhidat, a.ishchu, a.kontrol)
    print(f"СРЕЗ {vremya_sreza()} · {' '.join(komanda)[:100]}")
    print("\n".join(stroki))
    pokaz = chteniya[-1].vyvod.splitlines()
    if pokaz and kod in (0, 4, 5, 6):
        print("--- вывод (последнее чтение) ---")
        print("\n".join(pokaz[:a.stroki]) + (f"\n… ещё {len(pokaz) - a.stroki} строк" if len(pokaz) > a.stroki else ""))
    return kod


if __name__ == "__main__":
    sys.exit(main())
