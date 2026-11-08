# -*- coding: utf-8 -*-
"""Грабли сами: уроки из файла подкладываются в контекст Claude без ручного поиска.

Две роли:
  PreToolUse  (Bash, PowerShell) — по командной строке ищет подходящие уроки и подкладывает
              не больше MAX_LESSONS. Нет совпадений — молчит. Урок, уже показанный в этой
              сессии, не повторяет.
  SessionStart (startup, resume, compact) — подкладывает выжимку главных правил;
              после сжатия контекста забывает, какие уроки уже показаны.

Хук никогда не мешает команде: любая ошибка — молча выход 0. Нет файла уроков — тоже молча.

Файлы уроков (по умолчанию лежат рядом со скиллом, в папке выше hooks/):
  GRABLI_LESSONS — файл уроков (по умолчанию uroki.md, если его нет — uroki.example.md)
  GRABLI_DIGEST  — выжимка главных правил (по умолчанию uroki-glavnye.md, нет файла — не показываем)

Проверка руками:
  echo {"hook_event_name":"PreToolUse","tool_input":{"command":"pkill -f x"}} | python grabli_hook.py

ОГЛАВЛЕНИЕ
  1. Настройки и сигналы (команда -> слова для поиска)
  2. Уроки: разбор файла на разделы
  3. Подбор уроков к команде
  4. Ответ хука
"""
import json
import os
import re
import sys
import tempfile

# ═══ 1. Настройки и сигналы ═════════════════════════════════════════════════
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_DIR = os.path.join(tempfile.gettempdir(), "grabli_hook")
MAX_LESSONS = 1          # уроков на одну команду
MAX_CHARS = 300          # длина одного урока в подсказке


def lessons_path():
    path = os.environ.get("GRABLI_LESSONS")
    if path:
        return path
    own = os.path.join(SKILL_DIR, "uroki.md")
    return own if os.path.exists(own) else os.path.join(SKILL_DIR, "uroki.example.md")


def digest_path():
    return os.environ.get("GRABLI_DIGEST") or os.path.join(SKILL_DIR, "uroki-glavnye.md")


# Сигнал в команде -> слова, по которым ищем раздел урока (без учёта регистра).
# Новый урок о команде = одна строка здесь. Слова — те, что стоят в тексте урока.
SIGNALS = [
    (r"\bp(kill|grep)\b[^|;]*\s-f\b",                ["pgrep -f", "pkill -f"]),
    (r"\btaskkill\b[^|;]*\s/im\b|Stop-Process[^|;]*-Name|\bkillall\b", ["pgrep -f", "pkill -f"]),
    (r"\btar\b.*--exclude",                           ["tar --exclude"]),
    (r"(^|[\s;&])python3?(\.exe)?\s+-m\s+pytest",     ["no module named pytest"]),
    (r"<<\s*'?\w+'?[\s\S]*\\",                        ["heredoc"]),
    (r"(^|[\s;&|('\"])rsync\s",                       ["rsync"]),
    (r"\bmktemp\b",                                   ["mktemp"]),
    (r"\balembic\b",                                  ["alembic"]),
]


# ═══ 2. Уроки: разбор файла на разделы ═════════════════════════════════════
def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def lesson_sections():
    """[(номер по порядку, заголовок, текст)] — разделы «## ...» файла, новые в конце."""
    parts = re.split(r"\n(?=## )", read(lessons_path()))
    return [(i, p.splitlines()[0][3:].strip(), p) for i, p in enumerate(parts) if p.startswith("## ")]


def short(section_text):
    """Суть урока: строка «Правило/Как не повторять», иначе начало текста — в MAX_CHARS знаков."""
    m = re.search(r"\*\*(Правило|Как не повторять|Вывод)[^*]*\*\*:?\s*(.+)", section_text)
    body = m.group(2) if m else " ".join(section_text.splitlines()[1:])
    body = re.sub(r"\s+", " ", body).strip()
    return body[:MAX_CHARS] + ("…" if len(body) > MAX_CHARS else "")


# ═══ 3. Подбор уроков к команде ════════════════════════════════════════════
def words_for(command):
    words = []
    for pattern, keys in SIGNALS:
        if re.search(pattern, command, re.I):
            words += [k for k in keys if k not in words]
    return words


def pick(command, seen):
    """Разделы с наибольшим числом совпавших слов; при равенстве — новее. Уже показанные — пропуск."""
    words = words_for(command)
    if not words:
        return []
    scored = []
    for order, title, text in lesson_sections():
        low = text.lower()
        hits = sum(1 for w in words if w.lower() in low)
        if hits and title not in seen:
            scored.append((hits, order, title, text))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return scored[:MAX_LESSONS]


def seen_file(session_id):
    safe = re.sub(r"[^\w-]", "_", session_id or "nosession")
    return os.path.join(SEEN_DIR, safe + ".txt")


def load_seen(session_id):
    return set(read(seen_file(session_id)).splitlines())


def remember(session_id, titles):
    os.makedirs(SEEN_DIR, exist_ok=True)
    with open(seen_file(session_id), "a", encoding="utf-8") as f:
        f.writelines(t + "\n" for t in titles)


# ═══ 4. Ответ хука ═════════════════════════════════════════════════════════
def answer(event, text):
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


def on_pre_tool_use(data):
    command = str((data.get("tool_input") or {}).get("command") or "")
    session_id = data.get("session_id", "")
    found = pick(command, load_seen(session_id))
    if not found:
        return
    remember(session_id, [title for _, _, title, _ in found])
    lines = ["Грабли (урок из файла уроков, к этой команде):"]
    lines += [f"- [{title[:80]}] {short(text)}" for _, _, title, text in found]
    answer("PreToolUse", "\n".join(lines))


def on_session_start(data):
    if data.get("source") == "compact":                     # текст прежних подсказок сжат — показывать заново
        try:
            os.remove(seen_file(data.get("session_id", "")))
        except OSError:
            pass
    digest = re.sub(r"\A---\n.*?\n---\n", "", read(digest_path()), flags=re.S).strip()
    if digest:
        answer("SessionStart", digest)


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw or "{}")
    sys.stdout.reconfigure(encoding="utf-8")
    event = data.get("hook_event_name", "")
    if event == "PreToolUse":
        on_pre_tool_use(data)
    elif event == "SessionStart":
        on_session_start(data)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # хук не должен мешать работе ни при какой ошибке
        pass
    sys.exit(0)
