"""Привязка сторожа к контракту. В новом инструменте переписывается только этот файл.

Здесь — игрушечный сторож primer_storozh: выключает запись, у которой счётчик 0.
"""
from datetime import date

from primer_storozh import ActFailed, ToyGuard  # <- заменить на свой инструмент


class Env:
    """Игрушечный мир: 100 здоровых записей + записи «в беде» (счётчик 0)."""

    def __init__(self, defect=None):
        self.today = date(2026, 10, 24)
        self.switch_on = True
        self.first, self.second = {}, {}
        self.armed, self.acts, self.events, self.journal = [], [], [], []
        self.refused, self.fail_plan, self.alerts, self.stale = set(), {}, [], False
        healthy = {f"ok{i}": 5 for i in range(100)}
        self.set_world(healthy, healthy)
        self.guard = ToyGuard(read=self._read, confirm=self._confirm, act=self._act,
                              journal=self.journal.append, switch_on=lambda: self.switch_on,
                              today=lambda: self.today, defect=defect,
                              human_refused=lambda item: item in self.refused,
                              confirm_is_new=lambda: not self.stale,
                              alert=self.alerts.extend)

    def set_world(self, first, second):
        """Что покажет первое чтение и что — повторное."""
        self.first, self.second = dict(first), dict(second)

    def arm(self, n):
        for i in range(n):
            self.first[f"bad{i}"] = self.second[f"bad{i}"] = 0
            self.armed.append(f"bad{i}")

    def arm_flap(self, n):
        for i in range(n):
            self.first[f"flap{i}"], self.second[f"flap{i}"] = 0, 5
            self.armed.append(f"flap{i}")

    def switch_off(self):
        self.switch_on = False

    def human_refuses(self, item):
        """Человек отменил именно это действие (отменил наряд, нажал «не надо»)."""
        self.refused.add(item)

    def stale_confirm(self):
        """Повторное чтение — тот же срез (перезапуск, кэш), а не новый."""
        self.stale = True

    def fail_act(self, item, times):
        """Действие над item сорвётся временным отказом первые `times` попыток."""
        self.fail_plan[item] = times

    def set_today(self, d):
        self.today = d

    def run(self):
        return self.guard.run()

    def _read(self):
        self.events.extend(("first_read", k) for k in self.first)
        return dict(self.first)

    def _confirm(self, item):
        self.events.append(("confirm", item))
        return self.second.get(item)

    def _act(self, item):
        if self.fail_plan.get(item, 0) > 0:
            self.fail_plan[item] -= 1
            raise ActFailed(item)
        self.events.append(("act", item))
        self.acts.append(item)


def make_env(defect=None):
    return Env(defect)
