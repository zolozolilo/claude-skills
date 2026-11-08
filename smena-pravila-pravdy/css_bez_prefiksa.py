"""css_bez_prefiksa — правило CSS раздела только внутри его контейнера.

Закрывает класс «глобальный стиль одного раздела сломал соседние»: любой селектор, который
не начинается с приставки раздела, действует на всю страницу.

    python css_bez_prefiksa.py orders.css App.vue --prefiks .orders
    python css_bez_prefiksa.py --diff main --repo C:\\репо --prefiks .orders --prefiks .tree-

--diff REF проверяет только ДОБАВЛЕННЫЕ строки (git diff -U0 REF) в .css/.scss/.vue и новые
неотслеживаемые файлы; старый долг не ругается. В .vue проверяются блоки <style> без scoped.
Приставка, оканчивающаяся на «-», допускает продолжение (.tree-row); иначе после неё
не может идти буква/цифра/«-» (.orders-old — чужой). @keyframes, @font-face и т.п. пропускаются,
@media/@supports/@layer проверяются внутри. Вложенные правила (CSS nesting) внутри правила не
проверяются. Код выхода: 0 — чисто, 1 — есть селекторы вне приставки, 2 — ошибка.
Это проверка текста, не вёрстки: ширины (ноутбук/большой монитор/телефон) и соседние разделы
смотреть глазами.

Оглавление:
  1. Разбор CSS: селекторы с номерами строк
  2. Проверка приставки, Vue-блоки
  3. Строки, добавленные в git diff
  4. Запуск
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PROPUSK_AT = ("keyframes", "font-face", "page", "property", "counter-style", "font-feature-values",
              "viewport", "-webkit-keyframes", "-moz-keyframes")
VNUTRI_AT = ("media", "supports", "layer", "container", "document", "scope", "starting-style")


# ═══ 1. Разбор CSS: селекторы с номерами строк ═════════════════════════
def _bez_kommentariev(tekst):
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), tekst, flags=re.S)


def _spisok_selektorov(prelyudiya):
    """Делит «.a, .b:is(.c, .d)» по запятым вне скобок."""
    chasti, glub, tek = [], 0, []
    for ch in prelyudiya:
        if ch in "([":
            glub += 1
        elif ch in ")]":
            glub -= 1
        if ch == "," and glub == 0:
            chasti.append("".join(tek))
            tek = []
        else:
            tek.append(ch)
    chasti.append("".join(tek))
    return [" ".join(c.split()) for c in chasti if c.strip()]


def selektory_css(tekst):
    """[(номер строки, селектор)] верхнего уровня и внутри @media/@supports/@layer."""
    tekst = _bez_kommentariev(tekst)
    nomer, kuchi = 1, []          # kuchi: стек видов блоков: "nest" | "rule" | "skip"
    nachalo, prel = None, []      # где началась преамбула и её символы
    kavychka = None
    itog = []
    for ch in tekst:
        if kavychka:
            if ch == kavychka:
                kavychka = None
            if ch == "\n":
                nomer += 1
            if prel is not None and nachalo is not None:
                prel.append(ch)
            continue
        if ch in "\"'":
            kavychka = ch
            if nachalo is None:
                nachalo = nomer
            prel.append(ch)
            continue
        if ch == "{":
            tekst_prel = "".join(prel).strip()
            vnutri_skip = any(k in ("skip", "rule") for k in kuchi)
            if vnutri_skip:
                kuchi.append("skip")
            elif tekst_prel.startswith("@"):
                imya = re.match(r"@([\w-]+)", tekst_prel)
                imya = imya.group(1).lower() if imya else ""
                kuchi.append("nest" if imya in VNUTRI_AT else "skip")
            else:
                for s in _spisok_selektorov(tekst_prel):
                    itog.append((nachalo or nomer, s))
                kuchi.append("rule")
            nachalo, prel = None, []
        elif ch == "}":
            if kuchi:
                kuchi.pop()
            nachalo, prel = None, []
        elif ch == ";":
            nachalo, prel = None, []
        else:
            if nachalo is None and not ch.isspace():
                nachalo = nomer
            if nachalo is not None:
                prel.append(ch)
        if ch == "\n":
            nomer += 1
    return itog


# ═══ 2. Проверка приставки, Vue-блоки ═══════════════════════════════════
def pod_pristavkoy(selektor, prefiksy):
    for p in prefiksy:
        if selektor.startswith(p):
            sled = selektor[len(p):len(p) + 1]
            if p.endswith("-") or not sled or not re.match(r"[\w-]", sled):
                return True
    return False


def narusheniya(tekst, prefiksy, vue=False):
    """[(номер строки, селектор)] — селекторы не под приставкой раздела."""
    if not vue:
        bloki = [(0, tekst)]
    else:
        bloki = []
        for m in re.finditer(r"<style([^>]*)>(.*?)</style>", tekst, flags=re.S | re.I):
            if "scoped" not in m.group(1).lower():
                bloki.append((tekst.count("\n", 0, m.start(2)), m.group(2)))
    itog = []
    for smeshenie, css in bloki:
        for nomer, s in selektory_css(css):
            if not pod_pristavkoy(s, prefiksy):
                itog.append((nomer + smeshenie, s))
    return itog


# ═══ 3. Строки, добавленные в git diff ═════════════════════════════════
def tolko_dobavlennye(nar, dobavlennye):
    return [(n, s) for n, s in nar if n in dobavlennye]


def dobavlennye_iz_diff(diff):
    """{файл: {номера добавленных строк}} из `git diff -U0`."""
    itog, fayl, novaya = {}, None, 0
    for st in diff.splitlines():
        if st.startswith("+++ "):
            put = st[4:].strip()
            fayl = put[2:] if put.startswith("b/") else None
            if fayl:
                itog.setdefault(fayl, set())
        elif st.startswith("@@"):
            m = re.search(r"\+(\d+)", st)
            novaya = int(m.group(1)) if m else 0
        elif fayl and st.startswith("+") and not st.startswith("+++"):
            itog[fayl].add(novaya)
            novaya += 1
    return itog


# ═══ 4. Запуск ══════════════════════════════════════════════════════════
def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace").strip())
    return p.stdout.decode("utf-8", errors="replace")


def _proverit_fayl(put, prefiksy, dobavlennye=None):
    tekst = Path(put).read_text(encoding="utf-8", errors="replace")
    nar = narusheniya(tekst, prefiksy, vue=str(put).lower().endswith(".vue"))
    return tolko_dobavlennye(nar, dobavlennye) if dobavlennye is not None else nar


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="css_bez_prefiksa", description=__doc__.split("\n\n")[0])
    p.add_argument("fayly", nargs="*", help=".css/.scss/.vue для полной проверки")
    p.add_argument("--prefiks", action="append", required=True, help="приставка раздела (.orders), можно несколько")
    p.add_argument("--diff", help="проверить только строки, добавленные относительно REF")
    p.add_argument("--repo", default=".")
    a = p.parse_args(argv)
    spisok = []   # (путь для показа, [(номер, селектор)])
    try:
        if a.diff:
            repo = Path(a.repo)
            diff = _git(repo, "diff", "-U0", a.diff, "--", "*.css", "*.scss", "*.vue")
            for fayl, nomera in dobavlennye_iz_diff(diff).items():
                if (repo / fayl).is_file():
                    spisok.append((fayl, _proverit_fayl(repo / fayl, a.prefiks, nomera)))
            novye = _git(repo, "ls-files", "--others", "--exclude-standard", "--", "*.css", "*.scss", "*.vue")
            for fayl in novye.splitlines():
                spisok.append((fayl, _proverit_fayl(repo / fayl, a.prefiks)))
        for f in a.fayly:
            spisok.append((f, _proverit_fayl(f, a.prefiks)))
    except (RuntimeError, OSError) as e:
        print(f"НЕ ЗНАЮ: {e}", file=sys.stderr)
        return 2
    if not spisok and not a.fayly and not a.diff:
        print("нужны файлы или --diff REF", file=sys.stderr)
        return 2
    plohie = 0
    for put, nar in spisok:
        for nomer, s in nar:
            plohie += 1
            print(f"⚠ {put}:{nomer}  {s}  — вне {' / '.join(a.prefiks)}: действует на всю страницу")
    print(f"css_bez_prefiksa: файлов {len(spisok)}, селекторов вне приставки {plohie}")
    return 1 if plohie else 0


if __name__ == "__main__":
    sys.exit(main())
