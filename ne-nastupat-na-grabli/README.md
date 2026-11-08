# ne-nastupat-na-grabli — уроки прошлых ошибок сами приходят к команде

Скилл ведёт файл уроков («что случилось → правило»). Хук перед каждой командой Bash/PowerShell подкладывает подходящий урок (не больше одного, без повторов в сессии), а при старте сессии — выжимку главных правил. Нет совпадения или нет файла — молчит.

## Что внутри

| Файл | Что делает |
|---|---|
| `SKILL.md` | Сам скилл: поиск перед задачей, запись после ошибки, разбор повтора |
| `grabli.py` | Поиск по словам в файле уроков (`--pamyat` — ещё и `feedback_*.md` из `MEMORY_DIR`) |
| `hooks/grabli_hook.py` | Хук PreToolUse и SessionStart; сигналы «команда -> слова урока» — список `SIGNALS` |
| `uroki.example.md` | Пример файла уроков (5 общих уроков); свои — в `uroki.md` рядом |
| `uroki-glavnye.example.md` | Пример выжимки главных правил; свои — в `uroki-glavnye.md` |
| `test_grabli_hook.py` | Тесты подбора урока и работы без файла |

## Установка

```bash
cp -r ne-nastupat-na-grabli ~/.claude/skills/
cp ~/.claude/skills/ne-nastupat-na-grabli/uroki.example.md ~/.claude/skills/ne-nastupat-na-grabli/uroki.md
```

Файлы уроков можно положить куда угодно: `GRABLI_LESSONS` (файл уроков) и `GRABLI_DIGEST` (выжимка). Без них хук берёт `uroki.md` / `uroki.example.md` и `uroki-glavnye.md` рядом со скиллом.

Подключение хука — в `~/.claude/settings.json` (замените путь на свой; на Windows слэши прямые):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          { "type": "command", "command": "python \"~/.claude/skills/ne-nastupat-na-grabli/hooks/grabli_hook.py\"", "timeout": 5 }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          { "type": "command", "command": "python \"~/.claude/skills/ne-nastupat-na-grabli/hooks/grabli_hook.py\"", "timeout": 5 }
        ]
      }
    ]
  }
}
```

Если `~` в команде не раскрывается, пропишите полный путь. Новый урок о команде: допишите раздел `## ...` в файл уроков и строку `(регулярка, [слова из урока])` в `SIGNALS`.

## Нужно

Python 3.8+, Claude Code. Тесты: `pip install pytest`, затем `python -m pytest -q -p no:cacheprovider`.
