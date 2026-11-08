# budgeting-agent-tokens

Скилл Claude Code: бюджет токенов субагентов (порог контекста 300 тыс., записка передачи, протокол задания и отчёта), скрипт замера расхода за день и хук, который держит агента в пределах порога.

| Файл | Что |
|---|---|
| SKILL.md | сам скилл |
| scripts/tokens_today.py | расход дня по журналам `~/.claude/projects/`: мои ответы и самые дорогие агенты |
| hooks/agent_budget_hook.py | хук PreToolUse/PostToolUse: предупреждение с 250 тыс., запрет с 290 тыс., длинный Read, повтор команды |
| hooks/agent_budget.json | пороги хука |
| hooks/tests/test_agent_budget_hook.py | тесты хука (pytest) |

Установка: `cp -r budgeting-agent-tokens ~/.claude/skills/`. Нужен Python 3.8+; для тестов — pytest.

Замер: `PYTHONUTF8=1 python ~/.claude/skills/budgeting-agent-tokens/scripts/tokens_today.py [--date ГГГГ-ММ-ДД]`.

Подключение хука (опционально) — добавить в `~/.claude/settings.json` (на Windows `python` вместо `python3`):

```json
{
  "hooks": {
    "PreToolUse":  [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5,
      "command": "python3 \"$HOME/.claude/skills/budgeting-agent-tokens/hooks/agent_budget_hook.py\""}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 5,
      "command": "python3 \"$HOME/.claude/skills/budgeting-agent-tokens/hooks/agent_budget_hook.py\""}]}]
  }
}
```

Состояние и журнал хук держит рядом с собой (переопределить папку — `AGENT_BUDGET_DIR`).
