# claude-skills — скиллы для Claude Code

Набор скиллов из ежедневной работы с агентами: чтобы агенты не повторяли старых ошибок, не верили на слово, не ломали молча общие поля и тратили меньше токенов. Тексты — на русском, у каждого скилла свои скрипты и тесты.

Главный скилл набора — **[octopus](https://github.com/zolozolilo/octopus-skill)**: дерево задачи, два конца навстречу, всё параллельно. Там же агент-критик `kritik`, на которого ссылаются скиллы ниже.

## Скиллы

| Скилл | Что делает | Скрипты · тесты |
|---|---|---|
| [`ne-nastupat-na-grabli`](ne-nastupat-na-grabli/) | Уроки прошлых ошибок сами приходят к команде: хук перед каждой командой подкладывает агенту подходящие уроки из файла, при старте сессии — выжимку главных правил | `grabli.py`, `hooks/grabli_hook.py` · 7 |
| [`nikomu-ne-ver`](nikomu-ne-ver/) | Число, вердикт и «готово» — только со своей свежей проверкой; приёмка работы агента по git и тестам, а не по его отчёту | `priyomka_agenta.py`, `pole_est.py`, `srez.py` · 50 |
| [`smena-pravila-pravdy`](smena-pravila-pravdy/) | Меняешь источник правды, поле, ключ JSON или метод — сначала найти всех, кто их пишет и читает; иначе ломается молча | `kto_pishet.py`, `reestr_polon.py`, `css_bez_prefiksa.py` · 131 |
| [`zashchitnye-instrumenty`](zashchitnye-instrumenty/) | Хуки, сторожа, выключатели и скрипты проверок пишутся так, чтобы сама защита была проверена: контракт и шаблон сторожа | `shablon/` · 25 |
| [`orkestrator`](orkestrator/) | Координатор — мозг: черновую работу отдаёт агентам подходящей модели, сам проверяет и сливает | — |
| [`budgeting-agent-tokens`](budgeting-agent-tokens/) | Бюджет токенов агентов: хук-предел и подсчёт расхода за день | `tokens_today.py`, `hooks/agent_budget_hook.py` · 41 |
| [`saving-tokens`](saving-tokens/) | Наименьший расход токенов на каждом ходу | — |

## Установка

Весь набор:

```bash
git clone https://github.com/zolozolilo/claude-skills
cp -r claude-skills/*/ ~/.claude/skills/
```

Один скилл — скопировать только его папку. Хуки (`ne-nastupat-na-grabli`, `budgeting-agent-tokens`) подключаются в `~/.claude/settings.json` — кусок настроек в README скилла.

Тесты (нужны Python 3 и pytest), например:

```bash
cd claude-skills/nikomu-ne-ver && python -m pytest -q
```

## English

Claude Code skills from daily work with agents: lessons from past mistakes injected into each command by a hook, "trust nobody" verification of agent reports, finding every reader and writer before changing a shared field, tested protective hooks and watchdogs, an orchestrator that delegates to cheaper models, and token budgeting. Skill texts are in Russian; scripts come with tests (254 in total). The main skill is [octopus](https://github.com/zolozolilo/octopus-skill).

## Лицензия

MIT — см. [LICENSE](LICENSE).
