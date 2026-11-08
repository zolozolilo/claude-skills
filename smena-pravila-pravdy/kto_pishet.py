"""kto-pishet — кто ПИШЕТ и кто ЧИТАЕТ поле / функцию / ключ по всем корням.

Для раздела «Все пути» скилла smena-pravila-pravdy: до правки правила — таблица
«путь → роль» по всем репозиториям, где живёт имя (бэкенд, фронт, C#, скрипты).

    python kto_pishet.py stock_qty -k C:\\репо\\back -k C:\\репо\\front
    python kto_pishet.py Reserve Release -k . --json

Только stdlib; если на ПК есть ripgrep (rg) — ищет им, итог тот же.
Код возврата: 0 — найдено, 1 — НИЧЕГО НЕ НАЙДЕНО (тишина ≠ «никто не пишет»), 2 — ошибка.

Оглавление:
  1. Настройки: языки, пропуски, роли
  2. Данные: Nahodka, Otchet
  3. Варианты имени (snake / camel / Pascal / kebab)
  4. Роль вхождения в строке
  5. Недостижимый код Python (после return / raise / break / continue)
  5б. Динамический доступ (globals(), getattr, window[…], Reflection)
  6. Поиск: обход stdlib и ripgrep
  7. Отчёт: таблица Markdown и JSON
  8. Запуск
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ═══ 1. Настройки: языки, пропуски, роли ═══════════════════════════════
YAZYKI = {
    "py": {".py", ".pyw"},
    "js": {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue"},
    "cs": {".cs", ".razor", ".cshtml"},
    "dannye": {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg"},
    "tekst": {".md", ".txt", ".sh", ".ps1", ".psm1", ".bat", ".cmd", ".sql",
              ".html", ".htm", ".xml", ".csproj", ".config", ".xaml"},
}
PO_RASSHIRENIYU = {r: ya for ya, rr in YAZYKI.items() for r in rr}

PROPUSK_PAPOK = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".build",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist",
                 "build", "bin", "obj", ".idea", ".vs", "coverage", "htmlcov",
                 ".next", ".nuxt", "site-packages"}
MAKS_RAZMER = 2_000_000  # больше — сборки и минифицированное; называем в отчёте

PISHET, OPRED, VYZOV, CHITAET = "ПИШЕТ", "ОПРЕДЕЛЕНИЕ", "ВЫЗОВ", "ЧИТАЕТ"
DANNYE, UPOM, KOMM = "ДАННЫЕ", "УПОМИНАНИЕ", "КОММЕНТАРИЙ"
NEDOST = "НЕДОСТИЖИМ"
PORYADOK = [PISHET, OPRED, VYZOV, CHITAET, DANNYE, UPOM, KOMM]

NE_VIDIT = (
    "Не видит: имя из переменной (getattr(o, имя), obj[ключ]); вызовы через HTTP "
    "из репозиториев, которые не переданы в -k; код на сервере, которого нет на ПК. "
    "Роли — по шаблонам строки, не по типам: спорные строки открыть глазами."
)


# ═══ 2. Данные: Nahodka, Otchet ════════════════════════════════════════
@dataclass
class Nahodka:
    imya: str          # исходное имя из запроса (не вариант)
    koren: str
    put: str           # относительно корня
    nomer: int
    tekst: str
    roli: set = field(default_factory=set)


@dataclass
class Otchet:
    imena: dict        # имя → список вариантов
    korni: list
    nahodki: list
    poisk: str = "stdlib"
    prosmotreno: int | None = 0
    bolshie: list = field(default_factory=list)
    dinamika: list = field(default_factory=list)   # globals()/getattr/… — поиск по имени их не видит


# ═══ 3. Варианты имени (snake / camel / Pascal / kebab) ════════════════
def _slova(imya):
    if "_" in imya:
        return [s for s in imya.split("_") if s]
    return re.findall(r"[A-ZА-ЯЁ]?[a-zа-яё0-9]+|[A-ZА-ЯЁ]+(?![a-zа-яё])", imya)


def varianty(imya):
    """Одно поле в Python, JS и C# зовут по-разному: stock_qty / stockQty / StockQty."""
    if imya.startswith("_") or imya.isupper():
        return [imya]
    slova = [s.lower() for s in _slova(imya)]
    if not slova:
        return [imya]
    kandidaty = [
        imya,
        "_".join(slova),
        slova[0] + "".join(s.capitalize() for s in slova[1:]),
        "".join(s.capitalize() for s in slova),
    ]
    if len(slova) > 1:
        kandidaty.append("-".join(slova))
    return list(dict.fromkeys(kandidaty))


# ═══ 4. Роль вхождения в строке ════════════════════════════════════════
# Шаблоны смотрят на текст ДО и ПОСЛЕ имени. Порядок проверок важен:
# комментарий → данные/текст → определение → запись → вызов → чтение.
_OP = r"(?:\*\*|//|>>|<<|\?\?|\|\||&&|[-+*/%|&^:])?=(?![=>])"
_PRISVOENIE = re.compile(r"""^["']?\]?\s*""" + _OP)
_ELEMENT = re.compile(r"""^["']?\]?\s*\[[^\]]*\]\s*""" + _OP)
_KLYUCH_V_KAVYCHKAH = re.compile(r"""^["']\s*:(?!:)""")
_DVOETOCHIE = re.compile(r"\s*:(?!:)")
_MENYAYUSHCHIY_METOD = re.compile(
    r"""^["']?\]?\s*\.\s*(?:append|extend|insert|add|update|pop|popitem|remove|"""
    r"""discard|clear|setdefault|sort|reverse|push|splice|unshift|shift|set|"""
    r"""delete|fill|Add|AddRange|Insert|Remove|RemoveAt|RemoveAll|Clear|TryAdd|"""
    r"""TryRemove|Enqueue|Dequeue|Push|Pop)\s*\(""")
_INKREMENT_POSLE = re.compile(r"^\s*(?:\+\+|--)")
_INKREMENT_DO = re.compile(r"(?:\+\+|--)\s*$")
_UDALENIE = re.compile(r"""\b(?:del|delete)\s+[\w.\[\]"']*$""")
_SETATTR = re.compile(r"""setattr\s*\(\s*[^,]+,\s*["']$""")
_POP_KLYUCH = re.compile(r"""\.(?:pop|setdefault)\(\s*["']$""")
_TS_TIP = re.compile(                                    # поле интерфейса TS: size: number;
    r"\s*\??:\s*(?:(?:string|number|boolean|any|unknown|null|undefined|void|"
    r"never|bigint|Date)\b(?:\[\])?\s*(?:[;,|)]|$)|(?:Record|Array)<)")
_CS_MODIFIKATORY = re.compile(
    r"\s*(?:\[[^\]]*\]\s*)*(?:(?:public|private|protected|internal|static|virtual|"
    r"override|async|readonly|sealed|abstract|partial|const|new|extern|unsafe|"
    r"volatile|required)\s+)+")


def _vne_kavychek(tekst, metka):
    """Есть ли метка комментария вне строковых кавычек (грубо, по чётности)."""
    kavychka = None
    i = 0
    while i < len(tekst):
        c = tekst[i]
        if kavychka:
            if c == "\\":
                i += 1
            elif c == kavychka:
                kavychka = None
        elif c in "\"'`":
            kavychka = c
        elif tekst.startswith(metka, i):
            return True
        i += 1
    return False


def _v_kommentarii(do, yazyk):
    if yazyk == "py":
        return _vne_kavychek(do, "#")
    nachalo = do.lstrip()
    return nachalo.startswith(("*", "/*")) or _vne_kavychek(do, "//")


def _opredelenie(stroka, do, posle, yazyk):
    if yazyk == "py":
        if re.search(r"(?:^|\s)(?:(?:async\s+)?def|class)\s+$", do):
            return True
        zagolovok = re.match(r"\s*(?:async\s+)?def\s+\w+\s*\(", stroka)
        if zagolovok and len(do) >= zagolovok.end():
            return True                                   # параметр функции
        return do.strip() == "" and re.match(r"\s*:\s*[^=\s]", posle) is not None
    if yazyk == "js":
        if re.search(r"(?:^|[\s(])(?:async\s+)?function\s*\*?\s*$", do):
            return True
        if re.search(r"(?:^|\s)(?:const|let|var|class)\s+$", do):
            return True
        metod = do.strip() in ("", "async", "static", "get", "set", "static async")
        if metod and re.match(r"\s*\([^)]*\)\s*\{", posle):
            return True
        return do.strip() == "" and _TS_TIP.match(posle) is not None
    if yazyk == "cs":
        if re.search(r"\b(?:class|record|struct|interface|enum|namespace)\s+$", do):
            return True
        return (_CS_MODIFIKATORY.match(stroka) is not None
                and re.search(r"[\w>\]?]\s+$", do) is not None
                and re.match(r"\s*(?:\(|\{|=>|;|=(?!=)|<)", posle) is not None)
    return False


def _zapis(do, posle, yazyk):
    if _PRISVOENIE.match(posle) or _ELEMENT.match(posle):
        return True
    if _MENYAYUSHCHIY_METOD.match(posle) or _KLYUCH_V_KAVYCHKAH.match(posle):
        return True
    if _INKREMENT_POSLE.match(posle) or _INKREMENT_DO.search(do):
        return True
    if _UDALENIE.search(do) or _SETATTR.search(do) or _POP_KLYUCH.search(do):
        return True
    if _DVOETOCHIE.match(posle):
        hvost = do.rstrip()[-1:]
        if yazyk == "js" and hvost in ("", "{", ","):
            return True                                   # ключ объекта { size: 5 }
        if yazyk == "cs" and hvost in ("(", ","):
            return True                                   # именованный аргумент
    return False


def rol_vhozhdeniya(stroka, nachalo, konec, yazyk):
    do, posle = stroka[:nachalo], stroka[konec:]
    if yazyk in ("py", "js", "cs") and _v_kommentarii(do, yazyk):
        return KOMM
    if yazyk == "dannye":
        return DANNYE if re.match(r"""["']?\s*[:=]""", posle) else UPOM
    if yazyk not in ("py", "js", "cs"):
        return UPOM
    if _opredelenie(stroka, do, posle, yazyk):
        return OPRED
    if _zapis(do, posle, yazyk):
        return PISHET
    if re.match(r"\s*(?:<[^<>()]*>)?\s*\(", posle):
        return VYZOV
    return CHITAET


def _shablon(imena):
    vybor = "|".join(re.escape(i) for i in sorted(imena, key=len, reverse=True))
    return re.compile(r"(?<![\w$])(?:" + vybor + r")(?![\w$])")


def roli_v_stroke(stroka, imya, yazyk):
    """Множество ролей всех вхождений имени (целым словом) в строке."""
    return {rol_vhozhdeniya(stroka, m.start(), m.end(), yazyk)
            for m in _shablon([imya]).finditer(stroka)}


# ═══ 5. Недостижимый код Python (после return / raise / break / continue) ═
_KONEC_BLOKA = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def nedostizhimye_stroki(kod):
    """Номера строк, которые никогда не выполнятся (например, заплатка под return)."""
    try:
        derevo = ast.parse(kod)
    except (SyntaxError, ValueError):
        return set()
    mertvye = set()
    for uzel in ast.walk(derevo):
        for imya_polya in ("body", "orelse", "finalbody"):
            blok = getattr(uzel, imya_polya, None)
            if not isinstance(blok, list):
                continue
            for i, st in enumerate(blok):
                if isinstance(st, _KONEC_BLOKA):
                    for posle in blok[i + 1:]:
                        mertvye.update(range(posle.lineno, posle.end_lineno + 1))
                    break
    return mertvye


# ═══ 5б. Динамический доступ — то, что поиск по имени не видит ═════════
# «вынос раздела: имя перепривязывается через globals()[имя]» — поиск по имени
# молчал. Показываем такие строки отдельным списком: открыть те, что рядом с правкой.
_DINAMIKA = {
    "py": re.compile(r"(globals\(\)|locals\(\)|vars\(\)|\bgetattr\(|\bsetattr\(|__dict__|importlib"
                     r"|__import__\(|\beval\(|\bexec\()"),
    "js": re.compile(r"(window\[|globalThis\[|\bthis\[(?!['\"\d])|\beval\(|new Function\()"),
    "cs": re.compile(r"(GetProperty\(|GetField\(|GetMethod\(|Activator\.CreateInstance|\bdynamic\b|Reflection)"),
}
_KOMM_STROKI = {"py": "#", "js": "//", "cs": "//"}
POKAZ_DINAMIKI = 8


def dinamicheskie_stroki(tekst, yazyk):
    """[(номер строки, чем именно)] — globals(), getattr(, window[…], Reflection и т.п."""
    shablon = _DINAMIKA.get(yazyk)
    if shablon is None:
        return []
    itog = []
    for nomer, stroka in enumerate(tekst.splitlines(), 1):
        if stroka.lstrip().startswith(_KOMM_STROKI[yazyk]):
            continue
        m = shablon.search(stroka)
        if m:
            itog.append((nomer, m.group(1)))
    return itog


def sobrat_dinamiku(korni, vse=False, propusk=()):
    itog = []
    for koren in korni:
        fayly, _ = obhod(koren, vse, propusk)
        for put in fayly:
            yazyk = yazyk_fayla(put)
            if yazyk not in _DINAMIKA:
                continue
            try:
                tekst = prochitat(put)
            except OSError:
                continue
            for nomer, tip in dinamicheskie_stroki(tekst, yazyk):
                stroka = tekst.splitlines()[nomer - 1].strip()
                itog.append({"koren": koren, "put": os.path.relpath(put, koren),
                             "nomer": nomer, "tip": tip, "tekst": stroka})
    return itog


# ═══ 6. Поиск: обход stdlib и ripgrep ══════════════════════════════════
def yazyk_fayla(put):
    return PO_RASSHIRENIYU.get(Path(put).suffix.lower())


def prochitat(put):
    dannye = Path(put).read_bytes()
    for kodirovka in ("utf-8-sig", "cp1251"):
        try:
            return dannye.decode(kodirovka)
        except UnicodeDecodeError:
            continue
    return dannye.decode("utf-8", errors="replace")


def obhod(koren, vse=False, propusk=()):
    """Файлы известных типов; (пути, большие файлы)."""
    lishnie = set() if vse else PROPUSK_PAPOK | set(propusk)
    fayly, bolshie = [], []
    for papka, podpapki, imena in os.walk(koren):
        podpapki[:] = [p for p in podpapki if p not in lishnie]
        for imya in imena:
            put = os.path.join(papka, imya)
            if yazyk_fayla(put) is None:
                continue
            try:
                razmer = os.path.getsize(put)
            except OSError:
                continue
            (bolshie if razmer > MAKS_RAZMER else fayly).append(put)
    return fayly, bolshie


def razobrat_vyvod_rg(vyvod):
    """Строки `rg -n --null`: путь\\0номер:текст → [(путь, номер, текст)]."""
    stroki = []
    for zapis in vyvod.splitlines():
        put, _, ostatok = zapis.partition("\x00")
        nomer, _, tekst = ostatok.partition(":")
        if put and nomer.isdigit():
            stroki.append((put, int(nomer), tekst))
    return stroki


def _iskat_rg(rg, koren, vse_imena, vse, propusk):
    komanda = [rg, "-n", "--null", "--no-heading", "--color", "never",
               "--no-ignore", "--hidden", "-w", "-F", "--max-filesize", "2M"]
    for imya in vse_imena:
        komanda += ["-e", imya]
    for rasshirenie in PO_RASSHIRENIYU:
        komanda += ["-g", "*" + rasshirenie]
    for papka in (set() if vse else PROPUSK_PAPOK | set(propusk)):
        komanda += ["-g", "!**/" + papka + "/**"]
    komanda.append(koren)
    gotovo = subprocess.run(komanda, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if gotovo.returncode not in (0, 1):
        raise RuntimeError(gotovo.stderr.strip())
    return razobrat_vyvod_rg(gotovo.stdout)


def _iskat_stdlib(fayly, shablon):
    for put in fayly:
        try:
            tekst = prochitat(put)
        except OSError:
            continue
        if not shablon.search(tekst):
            continue
        for nomer, stroka in enumerate(tekst.splitlines(), 1):
            if shablon.search(stroka):
                yield put, nomer, stroka


def naiti(korni, imena, tochno=False, vse=False, propusk=(), ispolzovat_rg=None, dinamika=True):
    vse_varianty = {i: ([i] if tochno else varianty(i)) for i in imena}
    variant_k_imeni = {v: i for i, vv in vse_varianty.items() for v in vv}
    shablon = _shablon(variant_k_imeni)
    rg = shutil.which("rg") if ispolzovat_rg is not False else None
    otchet = Otchet(imena=vse_varianty, korni=list(korni), nahodki=[],
                    poisk="rg" if rg else "stdlib", prosmotreno=None if rg else 0)
    kesh_mertvyh = {}
    for koren in korni:
        if rg:
            stroki = _iskat_rg(rg, koren, variant_k_imeni, vse, propusk)
            _, bolshie = obhod(koren, vse, propusk)
        else:
            fayly, bolshie = obhod(koren, vse, propusk)
            otchet.prosmotreno += len(fayly)
            stroki = _iskat_stdlib(fayly, shablon)
        otchet.bolshie += bolshie
        for put, nomer, stroka in stroki:
            yazyk = yazyk_fayla(put)
            if yazyk is None:
                continue
            if yazyk == "py" and put not in kesh_mertvyh:
                kesh_mertvyh[put] = nedostizhimye_stroki(prochitat(put))
            mertvyy = nomer in kesh_mertvyh.get(put, ())
            po_imenam = {}
            for m in shablon.finditer(stroka):
                imya = variant_k_imeni[m.group(0)]
                po_imenam.setdefault(imya, set()).add(
                    rol_vhozhdeniya(stroka, m.start(), m.end(), yazyk))
            for imya, roli in po_imenam.items():
                if mertvyy:
                    roli.add(NEDOST)
                otchet.nahodki.append(Nahodka(
                    imya=imya, koren=koren, put=os.path.relpath(put, koren),
                    nomer=nomer, tekst=stroka.strip(), roli=roli))
    otchet.nahodki.sort(key=_klyuch_sortirovki)
    if dinamika:
        otchet.dinamika = sobrat_dinamiku(korni, vse, propusk)
    return otchet


_TEST = re.compile(r"(?:^|[\\/])(?:tests?|__tests__|spec)[\\/]|(?:^|[\\/])test_[^\\/]*$"
                   r"|_test\.py$|Tests?\.cs$|\.(?:test|spec)\.[jt]sx?$|[\\/][\w.]*Tests[\\/]")


def eto_test(put):
    """Путь теста: писатель в тесте ≠ писатель в коде."""
    return _TEST.search(put) is not None


def _glavnaya_rol(roli):
    return min((PORYADOK.index(r) for r in roli if r in PORYADOK), default=len(PORYADOK))


def _klyuch_sortirovki(n):
    return (n.imya, _glavnaya_rol(n.roli), eto_test(n.put), n.koren, n.put.lower(), n.nomer)


# ═══ 7. Отчёт: таблица Markdown и JSON ═════════════════════════════════
def _podpis_roli(roli):
    osnovnye = [r for r in PORYADOK if r in roli]
    return "+".join(osnovnye) + (" ⚠" + NEDOST if NEDOST in roli else "")


def _yacheyka(tekst, dlina=110):
    tekst = tekst if len(tekst) <= dlina else tekst[:dlina - 1] + "…"
    return tekst.replace("|", "\\|")


def tablica_md(otchet):
    neskolko_korney = len(otchet.korni) > 1
    vyvod = []
    for imya, vv in otchet.imena.items():
        svoi = [n for n in otchet.nahodki if n.imya == imya]
        dop = [v for v in vv if v != imya]
        vyvod.append(f"## kto-pishet: {imya}" + (f" (+ {', '.join(dop)})" if dop else ""))
        if not svoi:
            vyvod += ["НИЧЕГО НЕ НАЙДЕНО — проверь имя и корни (-k).", ""]
            continue
        vyvod += ["| Роль | Где | Строка |", "|---|---|---|"]
        for n in svoi:
            gde = f"{n.put}:{n.nomer}" + (" (тест)" if eto_test(n.put) else "")
            if neskolko_korney:
                gde = f"[{Path(n.koren).name}] {gde}"
            vyvod.append(f"| {_podpis_roli(n.roli)} | {_yacheyka(gde)} | `{_yacheyka(n.tekst)}` |")
        schet = {r: sum(1 for n in svoi if r in n.roli) for r in PORYADOK + [NEDOST]}
        fayly_pishut = len({(n.koren, n.put) for n in svoi if PISHET in n.roli})
        itog = (f"Итого: пишут {schet[PISHET]} мест в {fayly_pishut} файлах · "
                f"определение {schet[OPRED]} · вызов {schet[VYZOV]} · читают {schet[CHITAET]} · "
                f"данные {schet[DANNYE]} · упоминаний {schet[UPOM]} · комментариев {schet[KOMM]} · "
                f"из них в тестах {sum(1 for n in svoi if eto_test(n.put))}")
        if schet[NEDOST]:
            itog += f" · ⚠ НЕДОСТИЖИМЫХ {schet[NEDOST]} — разобрать до правки"
        vyvod += [itog, ""]
    prosmotreno = "—" if otchet.prosmotreno is None else otchet.prosmotreno
    vyvod.append(f"Корни: {', '.join(otchet.korni)} · поиск: {otchet.poisk} · "
                 f"файлов просмотрено: {prosmotreno}")
    if otchet.bolshie:
        pervye, eshche = otchet.bolshie[:5], len(otchet.bolshie) - 5
        vyvod.append(f"Пропущено файлов > {MAKS_RAZMER // 1_000_000} МБ: "
                     f"{len(otchet.bolshie)} — " + ", ".join(pervye)
                     + (f" и ещё {eshche} (весь список — --json)" if eshche > 0 else ""))
    vyvod.append("Пропущены папки (без --vse): " + ", ".join(sorted(PROPUSK_PAPOK)))
    if otchet.dinamika:
        pokaz = otchet.dinamika[:POKAZ_DINAMIKI]
        vyvod.append(f"Динамический доступ в корнях (имя из переменной — поиск его не видит): "
                     f"{len(otchet.dinamika)} строк; открыть те, что рядом с правкой:")
        for d in pokaz:
            vyvod.append(f"  {d['put']}:{d['nomer']} · {d['tip']} · `{_yacheyka(d['tekst'], 80)}`")
        if len(otchet.dinamika) > len(pokaz):
            vyvod.append(f"  … и ещё {len(otchet.dinamika) - len(pokaz)} (весь список — --json)")
    if len(otchet.korni) == 1:
        vyvod.append("⚠ Корень один: читатели в других репозиториях (фронт, C#, скрипты выкладки, "
                     "внутренние API, сверки) не видны — добавь -k для каждого.")
    vyvod.append(NE_VIDIT)
    return "\n".join(vyvod)


def v_json(otchet):
    return json.dumps({
        "imena": otchet.imena, "korni": otchet.korni, "poisk": otchet.poisk,
        "prosmotreno": otchet.prosmotreno, "bolshie": otchet.bolshie, "dinamika": otchet.dinamika,
        "nahodki": [{"imya": n.imya, "koren": n.koren, "put": n.put, "nomer": n.nomer,
                     "roli": [r for r in PORYADOK + [NEDOST] if r in n.roli],
                     "tekst": n.tekst} for n in otchet.nahodki],
    }, ensure_ascii=False, indent=1)


# ═══ 8. Запуск ═════════════════════════════════════════════════════════
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="kto-pishet", description=__doc__.split("\n\n")[0])
    p.add_argument("imena", nargs="+", help="поле, функция или ключ (можно несколько)")
    p.add_argument("-k", "--koren", action="append", help="корень поиска; повторять для каждого репозитория")
    p.add_argument("--tochno", action="store_true", help="без вариантов snake/camel/Pascal")
    p.add_argument("--vse", action="store_true", help="не пропускать node_modules, dist, build…")
    p.add_argument("--propusk", action="append", default=[], help="ещё папка для пропуска")
    p.add_argument("--json", action="store_true", help="вывод JSON (для агентов)")
    p.add_argument("--bez-rg", action="store_true", help="не звать ripgrep, только stdlib")
    p.add_argument("--bez-dinamiki", action="store_true", help="не искать globals()/getattr/… (быстрее)")
    a = p.parse_args(argv)
    korni = a.koren or ["."]
    for koren in korni:
        if not os.path.isdir(koren):
            print(f"нет папки: {koren}", file=sys.stderr)
            return 2
    otchet = naiti(korni, a.imena, tochno=a.tochno, vse=a.vse,
                   propusk=a.propusk, ispolzovat_rg=False if a.bez_rg else None,
                   dinamika=not a.bez_dinamiki)
    print(v_json(otchet) if a.json else tablica_md(otchet))
    nastoyashchie = [n for n in otchet.nahodki if n.roli - {KOMM}]
    return 0 if nastoyashchie else 1


if __name__ == "__main__":
    sys.exit(main())
