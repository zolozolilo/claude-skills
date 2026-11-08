# -*- coding: utf-8 -*-
"""Грабли: найти в файле уроков записи по словам задачи — чтобы не повторить прошлую ошибку.

Запуск:  python grabli.py pkill rsync          (слова — ИЛИ, без учёта регистра)
         python grabli.py --all tar            (без ограничения 15 находок)
         python grabli.py --pamyat опять       (ещё и файлы feedback_*.md из папки MEMORY_DIR)
Файл уроков — переменная GRABLI_LESSONS; по умолчанию uroki.md рядом со скриптом,
нет его — uroki.example.md. Новое — сверху.

ОГЛАВЛЕНИЕ
  1. Настройки
  2. Разбор уроков и поиск
  3. Запуск
"""
import os
import re
import sys
from pathlib import Path

# ═══ 1. Настройки ═══════════════════════════════════════════════════════════
HERE = Path(__file__).resolve().parent
CHANGED = re.compile(r"ИЗМЕНЕНО|вместо прежнего|отмен(ено|яет)|больше не действует|устарел", re.I)
LIMIT = 15
MEMORY_LINES = 3


def lessons_file():
    env = os.environ.get("GRABLI_LESSONS")
    if env:
        return Path(env)
    own = HERE / "uroki.md"
    return own if own.exists() else HERE / "uroki.example.md"


# ═══ 2. Разбор уроков и поиск ═══════════════════════════════════════════════
def read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def lesson_items(text):
    """Пункты уроков: [(раздел, пункт)] в порядке файла (разделы «## ...»)."""
    items, section, current = [], "", []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                items.append((section, " ".join(current)))
            section, current = line[3:].strip(), []
        elif line.startswith("- ") or re.match(r"\d+\.\s", line):
            if current:
                items.append((section, " ".join(current)))
            current = [re.sub(r"^(- |\d+\.\s+)", "", line).strip()]
        elif line.strip() and section:
            current.append(line.strip())
    if current:
        items.append((section, " ".join(current)))
    return items


def hit(text, words):
    low = text.lower()
    return any(w in low for w in words)


def memory_hits(words):
    """Файлы feedback_*.md из MEMORY_DIR, где встречаются слова (только чтение)."""
    folder = os.environ.get("MEMORY_DIR")
    if not folder:
        return []
    try:
        names = [n for n in os.listdir(folder) if n.startswith("feedback_") and n.endswith(".md")]
    except OSError:
        return []
    names.sort(key=lambda n: os.path.getmtime(os.path.join(folder, n)), reverse=True)
    found = []
    for name in names:
        lines = [l.strip() for l in read(os.path.join(folder, name)).splitlines() if hit(l, words)]
        if hit(name, words) or lines:
            found.append((name, lines[:MEMORY_LINES]))
    return found


# ═══ 3. Запуск ══════════════════════════════════════════════════════════════
def main(argv):
    show_all = "--all" in argv
    with_memory = "--pamyat" in argv
    words = [w.lower() for w in argv if w not in ("--all", "--pamyat")]
    if not words:
        print(__doc__)
        return 2
    limit = None if show_all else LIMIT
    path = lessons_file()
    lessons = [(s, t) for s, t in lesson_items(read(path)) if hit(s + " " + t, words)]
    lessons.reverse()
    print("== Уроки (%d): %s" % (len(lessons), path.name))
    for section, text in lessons[:limit]:
        mark = "  [ИЗМЕНЕНИЕ]" if CHANGED.search(text) else ""
        print("- [%s]%s %s" % (section[:60], mark, text[:420]))
    memory = memory_hits(words) if with_memory else []
    if with_memory:
        print("\n== Память feedback_*.md (%d):" % len(memory))
        for name, lines in memory[:limit]:
            print("  " + name)
            for line in lines:
                print("    " + line[:200])
    if not (lessons or memory):
        print("\nНичего не нашлось — попробуйте другие слова (модуль, файл, действие).")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
