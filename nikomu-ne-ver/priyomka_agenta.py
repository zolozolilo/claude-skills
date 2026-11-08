"""priyomka_agenta — приёмка работы агента без доверия к его отчёту: git-факты + итог тестов.

Закрывает уроки «утверждение без свежей проверки» / «выкладка по тестам автора»:
агент «сдал» без коммита, правка кода без теста, «зелёное» при 44 skipped.

    python priyomka_agenta.py --repo C:\\репо --base main
    python priyomka_agenta.py --repo C:\\репо --base main --testy вывод.txt --kod-testov 0
    pytest -q 2>&1 | python priyomka_agenta.py --repo . --base main --testy -

Коды выхода: 0 — замечаний нет и тесты зелёные (если вывод дан); 1 — есть замечания.
Это подсказка, где смотреть, а не вердикт: «зелёный» здесь = passed>0, failed 0, error 0,
skipped 0, без xfailed/deselected, код выхода 0 (и вывод прочитан МНОЙ, свежий).

Оглавление:
  1. Итог тестов (pytest, jest/vitest, dotnet)
  2. git-факты и замечания
  3. Запуск
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# ═══ 1. Итог тестов ═════════════════════════════════════════════════════
_CHISLO_SLOVO = re.compile(r"(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b", re.I)
_SLOVO_CHISLO = re.compile(r"\b(Passed|Failed|Skipped)\s*:\s*(\d+)")
_TEST = re.compile(r"(?:^|[\\/])(?:tests?|__tests__|spec)[\\/]|(?:^|[\\/])test_[^\\/]*$"
                   r"|_test\.py$|Tests?\.cs$|\.(?:test|spec)\.[jt]sx?$|[\\/][\w.]*Tests[\\/]")
_KOD = re.compile(r"\.(?:py|js|mjs|cjs|ts|tsx|vue|cs|sh|ps1|sql)$")


def schet_testov(tekst):
    """{'passed': n, 'failed': n, …} по любому из знакомых форматов; пусто — итога нет."""
    s = {}
    for n, slovo in _CHISLO_SLOVO.findall(tekst):
        k = "error" if slovo.lower().startswith("error") else slovo.lower()
        s[k] = max(s.get(k, 0), int(n))
    for slovo, n in _SLOVO_CHISLO.findall(tekst):
        k = slovo.lower()
        s[k] = max(s.get(k, 0), int(n))
    return s


def zelenyy(tekst, kod=None):
    """(зелёный?, причина). Зелёный только при failed 0, error 0, skipped 0 и passed > 0."""
    s = schet_testov(tekst)
    if not s:
        return False, "итога тестов в выводе нет — «не знаю», прогнать и прочитать самому"
    plohoe = [f"{k} {s[k]}" for k in ("failed", "error", "skipped") if s.get(k)]
    if plohoe:
        return False, "не зелёный: " + ", ".join(plohoe)
    if kod not in (None, 0):
        return False, f"не зелёный: код выхода {kod}"
    if not s.get("passed"):
        return False, "не зелёный: passed 0 — тесты не отработали"
    chuzhoe = [f"{k} {s[k]}" for k in ("xfailed", "deselected") if s.get(k)]
    if chuzhoe:
        return False, "назвать пользователю: " + ", ".join(chuzhoe) + " (часть тестов не выполнялась)"
    return True, f"passed {s['passed']}, failed 0, skipped 0"


# ═══ 2. git-факты и замечания ═══════════════════════════════════════════
def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: " + p.stderr.decode("utf-8", "replace").strip())
    return p.stdout.decode("utf-8", errors="replace")


def fakty_git(repo, base):
    kommity = [x for x in _git(repo, "log", "--oneline", f"{base}..HEAD").splitlines() if x]
    fayly = [x for x in _git(repo, "diff", "--name-only", f"{base}..HEAD").splitlines() if x]
    gryaz = [x for x in _git(repo, "status", "--porcelain").splitlines() if x]
    return {"kommitov": len(kommity), "kommity": kommity, "fayly": fayly, "gryaz": gryaz,
            "stat": _git(repo, "diff", "--stat", f"{base}..HEAD").strip()}


def zamechaniya(f):
    z = []
    if f["kommitov"] == 0:
        z.append("КОММИТОВ НЕТ: относительно базы ничего не сохранено — отчёт агента ничем не подтверждён")
    kod = [x for x in f["fayly"] if _KOD.search(x) and not _TEST.search(x)]
    testy = [x for x in f["fayly"] if _TEST.search(x)]
    if kod and not testy:
        z.append(f"КОД БЕЗ ТЕСТА: изменено {len(kod)} файл(ов) кода, ни одного теста "
                 f"({', '.join(kod[:4])}) — тест, падающий без правки, где?")
    if f["gryaz"]:
        z.append("НЕ ЗАКОММИЧЕНО: " + "; ".join(x.strip() for x in f["gryaz"][:6])
                 + " — слияние это не увидит")
    return z


# ═══ 3. Запуск ══════════════════════════════════════════════════════════
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="priyomka_agenta", description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", default=".")
    p.add_argument("--base", required=True, help="от чего считать работу агента (ветка продакшена/main)")
    p.add_argument("--testy", help="файл с выводом тестов («-» — со стандартного ввода)")
    p.add_argument("--kod-testov", type=int, help="код выхода команды тестов")
    a = p.parse_args(argv)
    try:
        f = fakty_git(Path(a.repo), a.base)
    except RuntimeError as e:
        print(f"НЕ ЗНАЮ: {e}", file=sys.stderr)
        return 2
    print(f"## Приёмка: {f['kommitov']} коммит(ов) после {a.base}")
    for k in f["kommity"][:10]:
        print("  " + k)
    if f["stat"]:
        print(f["stat"])
    z = zamechaniya(f)
    if a.testy:
        tekst = sys.stdin.read() if a.testy == "-" else Path(a.testy).read_text(encoding="utf-8", errors="replace")
        ok, prichina = zelenyy(tekst, a.kod_testov)
        print(("ТЕСТЫ ЗЕЛЁНЫЕ: " if ok else "ТЕСТЫ: ") + prichina)
        if not ok:
            z.append("тесты: " + prichina)
    else:
        print("Вывода тестов не дано (--testy): прогнать самому и дать — «зелёный» с чужих слов не принимается.")
    for x in z:
        print("⚠ " + x)
    return 1 if z else 0


if __name__ == "__main__":
    sys.exit(main())
