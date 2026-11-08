"""Контракт защитного инструмента (сторож, хук, предохранитель): 9 проверок.

Как пользоваться: скопировать папку shablon рядом с новым инструментом,
переписать только adapter.py (make_env) — остальное не трогать.
Проверки — обычные функции: тест зовёт их с фабрикой окружения make_env().

Что обязан уметь env (его строит adapter):
  env.guard.META   dict: owner, expires (date), max_actions (int), switch (текст: где выключатель)
  env.arm(n)       n объектов «в беде» на всех чтениях;  env.armed — их id
  env.arm_flap(n)  n объектов «в беде» только на первом чтении
  env.switch_off() выключатель в положение «выкл»;  env.set_today(date);  env.today
  env.run()        один проход инструмента
  env.acts         id объектов, над которыми сделано НЕОБРАТИМОЕ действие
  env.events       [("first_read"|"confirm"|"act", id)] по порядку
  env.journal      [{"reason": str, "items": [id, ...]}] — каждый отказ
Для проверок 7–9 (отказ человека, новый срез, повтор и сообщение владельцу):
  env.human_refuses(id)   человек отменил именно это действие
  env.stale_confirm()     повторное чтение — тот же срез (перезапуск, кэш), а не новый
  env.fail_act(id, times) действие над id срывается временным отказом первые `times` попыток
  env.alerts              id объектов, о которых сообщено владельцу
"""
from datetime import timedelta

MAX_SROK_DNEI = 366  # срок защиты — не дальше года, дальше — пересмотр владельцем


def _logged_items(env):
    items = []
    for entry in env.journal:
        assert entry.get("reason"), f"отказ без причины в журнале: {entry}"
        items.extend(entry["items"])
    return items


def check_switch(make_env):
    """Есть выход: включён — работает, выключен — не действует и пишет отказ."""
    env = make_env()
    assert str(env.guard.META.get("switch", "")).strip(), "в META нет описания выключателя"
    env.arm(3)
    env.run()
    assert len(env.acts) == 3, "включённый инструмент не работает: выключатель — отговорка"
    env = make_env()
    env.arm(3)
    env.switch_off()
    env.run()
    assert env.acts == [], "выключатель не выключает"
    assert sorted(_logged_items(env)) == sorted(env.armed), "отказ по выключателю не записан в журнал"


def check_owner_and_expiry(make_env):
    """Есть владелец и срок: не пустой владелец, срок в будущем и не дальше года."""
    env = make_env()
    meta = env.guard.META
    assert str(meta.get("owner", "")).strip(), "нет владельца: кто решает, нужен ли инструмент"
    expires = meta.get("expires")
    assert hasattr(expires, "year"), "нет срока (META['expires'] — date)"
    assert expires > env.today, "срок уже истёк при создании"
    assert expires <= env.today + timedelta(days=MAX_SROK_DNEI), "срок дальше года — это не срок"


def check_expired_goes_quiet(make_env):
    """После срока инструмент не действует необратимо и пишет отказ (безопасное умолчание)."""
    env = make_env()
    env.set_today(env.guard.META["expires"] + timedelta(days=1))
    env.arm(2)
    env.run()
    assert env.acts == [], "после срока инструмент продолжает действовать"
    assert sorted(_logged_items(env)) == sorted(env.armed), "отказ «срок вышел» не записан"


def check_blast_radius(make_env):
    """Предел действий за один проход: объявлен в META и соблюдается."""
    env = make_env()
    limit = env.guard.META.get("max_actions")
    assert isinstance(limit, int) and 1 <= limit <= 1000, "нет конечного max_actions"
    env.arm(limit + 7)
    env.run()
    assert 0 < len(env.acts) <= limit, f"за проход {len(env.acts)} действий при пределе {limit}"
    assert len(_logged_items(env)) == 7, "остаток сверх предела не записан в журнал"


def check_second_read(make_env):
    """Перед необратимым — второе, отдельное чтение; расхождение = отказ."""
    env = make_env()
    env.arm_flap(4)
    env.run()
    assert env.acts == [], "действие по одному чтению: мигание принято за беду"
    env = make_env()
    env.arm(2)
    env.run()
    assert env.acts, "стабильную беду инструмент не обработал"
    for item in env.acts:
        first = env.events.index(("first_read", item))
        confirm = env.events.index(("confirm", item))
        act = env.events.index(("act", item))
        assert first < confirm < act, f"{item}: перед действием нет второго чтения"


def check_every_refusal_logged(make_env):
    """Любая судьба «в беде» объекта — действие или запись в журнал; ничего молча."""
    def sc_switch(env):
        env.arm(4)
        env.switch_off()

    def sc_expired(env):
        env.arm(4)
        env.set_today(env.guard.META["expires"] + timedelta(days=1))

    def sc_limit(env):
        env.arm(env.guard.META["max_actions"] + 3)

    def sc_flap(env):
        env.arm_flap(4)

    def sc_human(env):
        env.arm(4)
        env.human_refuses("bad1")

    def sc_stale(env):
        env.arm(4)
        env.stale_confirm()

    def sc_act_failed(env):
        env.arm(4)
        env.fail_act("bad2", times=99)

    for scenario in (sc_switch, sc_expired, sc_limit, sc_flap, sc_human, sc_stale, sc_act_failed):
        env = make_env()
        scenario(env)
        env.run()
        logged = _logged_items(env)
        assert not set(env.acts) & set(logged), f"{scenario.__name__}: объект и в действиях, и в отказах"
        assert sorted(env.acts + logged) == sorted(env.armed), (
            f"{scenario.__name__}: судьба части объектов не записана (молчаливый отказ)")


def check_human_refusal_wins(make_env):
    """Отказ человека главнее повтора автоматики."""
    env = make_env()
    env.arm(3)
    env.human_refuses("bad0")
    env.run()
    assert "bad0" not in env.acts, "сторож повторил действие, которое человек отменил"
    assert "bad0" in _logged_items(env), "отказ ради человека не записан в журнал"
    assert sorted(env.acts) == ["bad1", "bad2"], "остальным объектам отказ человека мешать не должен"


def check_independent_confirm(make_env):
    """Подтверждение — только НОВЫМ срезом: тот же срез повторно (перезапуск, кэш) не считается."""
    env = make_env()
    env.arm(2)
    env.stale_confirm()
    env.run()
    assert env.acts == [], "действие по повтору того же среза: два одинаковых чтения приняты за два"
    assert sorted(_logged_items(env)) == sorted(env.armed), "отказ «тот же срез» не записан в журнал"
    env = make_env()
    env.arm(2)
    env.run()
    assert sorted(env.acts) == sorted(env.armed), "новый срез подтвердил, а сторож не действует"


def check_urgent_retry_and_alert(make_env):
    """Временный отказ внешней системы — повтор сам; провал — в журнал И сообщение владельцу."""
    env = make_env()
    env.arm(2)
    env.fail_act("bad0", times=1)
    env.run()
    assert "bad0" in env.acts, "временный отказ внешней системы не повторён: объект застрял"
    env = make_env()
    env.arm(2)
    env.fail_act("bad0", times=99)
    env.run()
    assert "bad0" not in env.acts and "bad1" in env.acts, "провал одного не должен останавливать остальных"
    assert "bad0" in _logged_items(env), "провал действия не записан в журнал"
    assert "bad0" in env.alerts, "провал срочного действия не дошёл до владельца (только в журнал)"


ALL_CHECKS = (check_switch, check_owner_and_expiry, check_expired_goes_quiet,
              check_blast_radius, check_second_read, check_every_refusal_logged,
              check_human_refusal_wins, check_independent_confirm, check_urgent_retry_and_alert)
