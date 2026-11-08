#!/usr/bin/env python
"""Бюджет контекста подагента: держит агента в пределах 300 тыс. токенов.

Подключается к PreToolUse и PostToolUse (matcher "*"). В главной сессии молчит.
Любой сбой — выход 0 без вывода: агентов не ломаем, строка уходит в agent_budget.log.

Оглавление
  1. Настройки и пути
  2. Журнал и состояние агента
  3. Контекст агента из хвоста транскрипта
  4. Правила: предел, длинный Read, повтор команды
  5. Ответы хука (PreToolUse / PostToolUse)
  6. Запуск
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# ═══ 1. Настройки и пути ═══════════════════════════════════════
# Пороги лежат рядом, в agent_budget.json; здесь — значения на случай, если файла нет.

HOOKS_DIR = Path(os.environ.get("AGENT_BUDGET_DIR") or Path(__file__).resolve().parent)
CONFIG_PATH = HOOKS_DIR / "agent_budget.json"
LOG_PATH = HOOKS_DIR / "agent_budget.log"
STATE_DIR = HOOKS_DIR / ".agent_budget_state"

DEFAULTS = {
    "enabled": True,
    "limit_tokens": 300_000,    # предел из скилла budgeting-agent-tokens
    "warn_at": 250_000,         # с этого контекста — «закругляйся»
    "warn_step": 10_000,        # повторять предупреждение на каждые +10 тыс.
    "deny_at": 290_000,         # с этого контекста — только записка и коммит
    "tail_bytes": 300_000,      # сколько читать с конца транскрипта
    "read_max_lines": 1500,     # Read длиннее без limit — запрет
    "repeat_limit": 3,          # одна и та же Bash-команда подряд
}

BINARY_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".ipynb"}
LOG_MAX_BYTES = 1_000_000
STATE_MAX_AGE_SEC = 3 * 24 * 3600


def load_config():
    config = dict(DEFAULTS)
    try:
        config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass  # нет файла или он битый — работаем на значениях по умолчанию
    return config


# ═══ 2. Журнал и состояние агента ══════════════════════════════
# Состояние (на какой отметке уже предупредили, последние команды) — файл на агента.

def log(message):
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.write_text("", encoding="utf-8")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass  # журнал не должен ронять хук


def state_path(agent_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", agent_id)
    return STATE_DIR / f"{safe}.json"


def load_state(agent_id):
    try:
        return json.loads(state_path(agent_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"warned_bucket": -1, "recent_commands": []}


def save_state(agent_id, state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path(agent_id).write_text(json.dumps(state), encoding="utf-8")


def forget_old_states():
    """Раз в запуск нового агента выбрасываем состояния старше трёх суток."""
    now = time.time()
    for file in STATE_DIR.glob("*.json"):
        try:
            if now - file.stat().st_mtime > STATE_MAX_AGE_SEC:
                file.unlink()
        except OSError:
            pass


# ═══ 3. Контекст агента из хвоста транскрипта ══════════════════
# Контекст = usage последнего шага агента: input + cache_read + cache_creation.
# Читаем только хвост файла: транскрипт большого агента — десятки мегабайт.

def subagent_transcript(event):
    """Транскрипт подагента лежит рядом с транскриптом главной сессии."""
    main = Path(event["transcript_path"])
    return main.parent / event["session_id"] / "subagents" / f"agent-{event['agent_id']}.jsonl"


def context_of_usage(usage):
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def last_usage_in(text):
    """Контекст последнего шага ассистента в куске текста; None, если шага нет."""
    for line in reversed(text.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            message = json.loads(line).get("message")
        except ValueError:
            continue  # обрезанная первая строка хвоста
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            return context_of_usage(message["usage"])
    return None


def read_tail(path, size):
    with open(path, "rb") as f:
        total = f.seek(0, os.SEEK_END)
        start = max(0, total - size)
        f.seek(start)
        data = f.read()
    text = data.decode("utf-8", errors="ignore")
    if start > 0:
        text = text.split("\n", 1)[-1]  # первая строка хвоста может быть оборвана
    return text


def agent_context(path, tail_bytes):
    """Контекст агента в токенах. Если в хвосте шага нет (огромный вывод) — расширяем окно."""
    size = tail_bytes
    for _ in range(6):  # 300 КБ → 1,2 МБ → 4,8 МБ → … редкий огромный вывод не должен ослеплять хук
        used = last_usage_in(read_tail(path, size))
        if used is not None:
            return used
        size *= 4
    return None


# ═══ 4. Правила: предел, длинный Read, повтор команды ══════════
# Каждое правило — чистая функция: данные на входе, решение на выходе.

GIT_ALLOWED = re.compile(
    r"^\s*git(\s+-C\s+\S+)?\s+(add|commit|status|diff\s+--stat|log\s+-1)\b"
)
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
CHAINING = re.compile(r"[;&|`<>]|\$\(")


def is_safe_git_command(command):
    """Один простой git-вызов из списка; цепочки команд и перенаправления не пускаем."""
    if not GIT_ALLOWED.match(command):
        return False
    outside_quotes = QUOTED.sub("", command)
    return not CHAINING.search(outside_quotes)


def path_of(tool_input):
    return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")


def allowed_after_limit(tool_name, tool_input):
    """Что агенту можно делать после предела: записка передачи, коммит и сдача отчёта."""
    if tool_name in ("SubagentHandback", "SendMessage"):
        return True  # отчёт и сообщения — единственный способ закончить работу
    if tool_name in ("Write", "Edit", "Read"):
        return "handoff" in path_of(tool_input).lower()
    if tool_name == "Bash":
        return is_safe_git_command(tool_input.get("command", ""))
    return False


def count_lines(path):
    lines = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            lines += chunk.count(b"\n")
    return lines + 1


def read_is_too_long(tool_input, max_lines):
    """Read без limit файла длиннее max_lines строк (с учётом offset)."""
    if tool_input.get("limit"):
        return False
    path = path_of(tool_input)
    if not path or Path(path).suffix.lower() in BINARY_SUFFIXES:
        return False
    try:
        offset = int(tool_input.get("offset") or 0)
        return count_lines(path) - offset > max_lines
    except (OSError, ValueError):
        return False  # нет файла — пусть Read сам скажет


def repeated_command(state, command, limit):
    """Запоминает команду; True, если она идёт подряд уже `limit`-й раз."""
    recent = (state.get("recent_commands", []) + [command])[-limit:]
    state["recent_commands"] = recent
    return len(recent) == limit and len(set(recent)) == 1


def warn_text(context):
    return (
        f"Контекст {context // 1000} тыс. из 300: закругляйся — коммит, записка передачи "
        r"scratchpad\handoff\<ветка>.md, отчёт. Не читай файлы целиком."
    )


# ═══ 5. Ответы хука (PreToolUse / PostToolUse) ═════════════════

def deny(reason):
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def add_context(text):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}


def before_tool(event, config, context):
    tool_name, tool_input = event["tool_name"], event.get("tool_input") or {}

    if context is not None and context >= config["deny_at"]:
        if allowed_after_limit(tool_name, tool_input):
            return None
        log(f"deny-limit agent={event['agent_id']} ctx={context} tool={tool_name}")
        return deny(
            f"Предел {config['limit_tokens'] // 1000} тыс.: сохрани записку передачи "
            "(scratchpad\\handoff\\<ветка>.md), закоммить и закончи отчётом — продолжит свежий агент."
        )

    if tool_name == "Read" and read_is_too_long(tool_input, config["read_max_lines"]):
        log(f"deny-read agent={event['agent_id']} file={path_of(tool_input)}")
        return deny(
            f"Файл длиннее {config['read_max_lines']} строк: укажи offset/limit или используй Grep."
        )
    return None


def after_tool(event, config, context):
    agent_id = event["agent_id"]
    state = load_state(agent_id)
    texts = []

    if context is not None and context >= config["warn_at"]:
        bucket = (context - config["warn_at"]) // config["warn_step"]
        if bucket > state.get("warned_bucket", -1):
            state["warned_bucket"] = bucket
            texts.append(warn_text(context))
            log(f"warn agent={agent_id} ctx={context}")

    if event["tool_name"] == "Bash":
        command = (event.get("tool_input") or {}).get("command", "")
        if repeated_command(state, command, config["repeat_limit"]):
            texts.append(f"Эта команда уже {config['repeat_limit']}-й раз подряд — повтор, смени подход.")
            state["recent_commands"] = []  # напомним снова только после новой серии повторов

    save_state(agent_id, state)
    return add_context(" ".join(texts)) if texts else None


# ═══ 6. Запуск ═════════════════════════════════════════════════

def run(event):
    """Ответ хука (словарь) или None. Вне подагента — всегда None."""
    config = load_config()
    if not config["enabled"] or not event.get("agent_id"):
        return None

    if not state_path(event["agent_id"]).exists():
        forget_old_states()

    context = agent_context(subagent_transcript(event), config["tail_bytes"])
    if event["hook_event_name"] == "PreToolUse":
        return before_tool(event, config, context)
    if event["hook_event_name"] == "PostToolUse":
        return after_tool(event, config, context)
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        answer = run(json.loads(sys.stdin.read()))
        if answer:
            print(json.dumps(answer, ensure_ascii=False))
    except BaseException as error:  # хук не имеет права ломать работу агента
        log(f"ERROR {type(error).__name__}: {error}")
    sys.exit(0)


if __name__ == "__main__":
    main()
