# zashchitnye-instrumenty

Навык Claude Code: как писать защитные инструменты (хуки, сторожа, выключатели, скрипты проверок, режимы песочницы) так, чтобы сама защита была проверена. В `shablon/` — контракт из 9 проверок и игрушечный сторож-образец с тестами и мутантами.

| Файл | Назначение |
|---|---|
| SKILL.md | правила, чек-лист, красные флаги |
| shablon/kontrakt.py | 9 проверок контракта защиты |
| shablon/adapter.py | привязка инструмента к контракту (переписывается под свой) |
| shablon/primer_storozh.py | игрушечный сторож-образец |
| shablon/test_kontrakt_zashchity.py, test_primer_storozh.py | контрактный тест, мутанты, replay |
| shablon/snimki/zapisannye.json | записанные снимки для replay |

## Установка
`cp -r zashchitnye-instrumenty ~/.claude/skills/`

Нужно: Python 3, pytest; для property-тестов — hypothesis (по желанию). Проверка: `cd shablon && python -m pytest -q`.
