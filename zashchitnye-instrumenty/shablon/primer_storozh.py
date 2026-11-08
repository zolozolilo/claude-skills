"""Игрушечный сторож: выключает запись, у которой счётчик 0 (например, товар без остатка). Образец для контракта.

Что в нём «по правилам» (каждое проверяется kontrakt.py):
  выключатель · владелец и срок · предел действий за проход · второе чтение перед необратимым
  · журнал каждого отказа · неполный/массовый снимок отвергается целиком
  · отказ человека главнее повтора автоматики · подтверждение только новым срезом
  · временный отказ внешней системы — повтор, провал — сообщение владельцу.
Параметр defect вставляет по одному дефекту — на них проверяется, что контракт ловит плохих сторожей.
"""
from datetime import date

META = {
    "name": "toy-snyatie",
    "owner": "maintainer",                  # кто решает, нужен ли сторож
    "expires": date(2027, 1, 31),      # после срока — не действует, пока владелец не продлит
    "max_actions": 5,                  # предел необратимых действий за один проход
    "max_share": 0.3,                  # доля «в беде»+«нет данных» в снимке, выше — снимок подозрителен
    "retries": 3,                      # попыток необратимого действия при временном отказе внешней системы
    "switch": "файл toy_guard.OFF рядом со сторожем или TOY_GUARD_OFF=1",
}


class ActFailed(Exception):
    """Временный отказ внешней системы при необратимом действии («внешний сервис не ответил»)."""


class ToyGuard:
    def __init__(self, read, confirm, act, journal, switch_on, today, defect=None,
                 human_refused=None, confirm_is_new=None, alert=None):
        self._read, self._confirm, self._act = read, confirm, act
        self._journal, self._switch_on, self._today = journal, switch_on, today
        self._human_refused = human_refused or (lambda item: False)    # человек отменил именно это
        self._confirm_is_new = confirm_is_new or (lambda: True)        # повторное чтение — новый срез
        self._alert = alert or (lambda items: None)                    # сообщение владельцу
        self.defect = defect
        self.META = dict(META)
        if defect == "no_owner":
            self.META["owner"] = ""
        if defect == "no_retry":
            self.META["retries"] = 1

    def _refuse(self, reason, items):
        if items and self.defect != "silent":
            self._journal({"reason": reason, "items": list(items)})

    def _blocked_reason(self):
        """Причина, по которой действовать нельзя вообще (чтение при этом безвредно)."""
        if self.defect != "no_switch" and not self._switch_on():
            return "switch_off"
        if self.defect != "ignores_expiry" and self._today() > self.META["expires"]:
            return "expired"
        return None

    def run(self):
        snapshot = self._read()
        trouble = [k for k, v in snapshot.items() if v == 0]
        if not trouble:
            return []
        missing = sum(1 for v in snapshot.values() if v is None)
        if (len(trouble) + missing) / len(snapshot) > self.META["max_share"]:
            self._refuse("suspicious_snapshot", trouble)  # неполный или массовый снимок — решает человек
            return []
        blocked = self._blocked_reason()
        if blocked:
            self._refuse(blocked, trouble)
            return []
        if self.defect != "accepts_same_slice" and not self._confirm_is_new():
            # «два одинаковых чтения — одно»: повтор того же среза (перезапуск, кэш) подтверждением не считается
            self._refuse("same_slice", trouble)
            return []
        limit = len(trouble) if self.defect == "no_limit" else self.META["max_actions"]
        done, over, unconfirmed, declined, failed = [], [], [], [], []
        for item in trouble:
            if self.defect != "ignores_human" and self._human_refused(item):
                declined.append(item)               # отказ человека главнее повтора автоматики
            elif len(done) >= limit:
                over.append(item)
            elif self.defect != "no_confirm" and self._confirm(item) != 0:
                unconfirmed.append(item)
            elif self._act_with_retry(item):
                done.append(item)
            else:
                failed.append(item)
        self._refuse("limit", over)
        self._refuse("unconfirmed", unconfirmed)
        self._refuse("human_refused", declined)
        self._refuse("act_failed", failed)
        if failed and self.defect != "silent_fail":
            self._alert(failed)                     # провал срочного — человеку, а не только в журнал
        return done

    def _act_with_retry(self, item):
        """Временный отказ — повтор сам (до META['retries'] раз); True — действие выполнено."""
        for _ in range(self.META["retries"]):
            try:
                self._act(item)
                return True
            except ActFailed:
                continue
        return False
