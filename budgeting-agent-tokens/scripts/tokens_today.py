"""Расход токенов за день по журналам Claude Code: мои ответы и агенты.

Только чтение. Запуск:
    PYTHONUTF8=1 python tokens_today.py [--date 2026-10-02] [--session <id>]
По умолчанию — сегодня и самая свежая сессия.

Каждый вызов модели заново читает весь контекст, поэтому «расход» здесь —
сумма размеров контекста по всем вызовам плюс написанное.
"""
import argparse
import datetime as dt
import glob
import json
import os

PROJECTS = os.path.expanduser("~/.claude/projects")
LIMIT = 300_000  # порог контекста агента: дальше — записка передачи и свежий агент


def scan(path, day):
    """Вызовы модели за день: (время, контекст, написано).

    Одно сообщение пишется в журнал несколькими строками — берём последнюю по id.
    """
    calls = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            ts = d.get("timestamp")
            if not u or not m.get("id") or not ts:
                continue
            local = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            if local.date() != day:
                continue
            ctx = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                   + u.get("cache_creation_input_tokens", 0))
            calls[m["id"]] = (ts, ctx, u.get("output_tokens", 0))
    return sorted(calls.values())


def session_log(sid):
    """Журнал сессии: по id или самый свежий из всех проектов."""
    pattern = (sid or "*") + ".jsonl"
    files = glob.glob(os.path.join(PROJECTS, "*", pattern))
    if not files:
        raise SystemExit("журнал сессии не найден: " + pattern)
    return max(files, key=os.path.getmtime)


def agent_name(path):
    """Описание агента из соседнего .meta.json, иначе имя файла."""
    meta = path[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f).get("description") or os.path.basename(path)
    except (OSError, ValueError):
        return os.path.basename(path)


def mln(n):
    return f"{n / 1e6:.1f} млн"


def main():
    ap = argparse.ArgumentParser(description="Расход токенов за день: мои ответы и агенты")
    ap.add_argument("--date", help="день ГГГГ-ММ-ДД, по умолчанию сегодня")
    ap.add_argument("--session", help="id сессии, по умолчанию самая свежая")
    args = ap.parse_args()
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    log = session_log(args.session)

    me = scan(log, day)
    me_total = sum(c[1] + c[2] for c in me)
    print(f"День {day}, сессия {os.path.basename(log)[:8]}")
    if me:
        print(f"Мои ответы: {len(me)} вызовов, {mln(me_total)}; "
              f"контекст сейчас {me[-1][1] // 1000} тыс., наибольший {max(c[1] for c in me) // 1000} тыс.")

    # Журналы агентов лежат в папке с именем сессии
    agents = []
    for p in glob.glob(os.path.join(log[: -len(".jsonl")], "**", "*.jsonl"), recursive=True):
        calls = scan(p, day)
        if calls:
            agents.append((sum(c[1] + c[2] for c in calls), len(calls), calls[-1][1], agent_name(p)))
    agents.sort(reverse=True)
    ag_total = sum(a[0] for a in agents)
    total = me_total + ag_total
    share = f" — {ag_total * 100 // total} % всего" if total else ""
    print(f"Агенты: {len(agents)}, {mln(ag_total)}{share}")
    print("Самые дорогие агенты (расход, шагов, контекст на последнем шаге):")
    for spent, steps, last, name in agents[:8]:
        flag = "  ← больше 300 тыс." if last > LIMIT else ""
        print(f"  {mln(spent):>10}  {steps:4} шагов  {last // 1000:4} тыс.  {name[:60]}{flag}")


if __name__ == "__main__":
    main()
