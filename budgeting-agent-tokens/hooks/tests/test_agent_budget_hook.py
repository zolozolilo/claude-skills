"""Тесты хука бюджета подагента (agent_budget_hook.py).

Оглавление
  1. Заготовки: транскрипт, событие, изолированные пути
  2. Контекст из хвоста транскрипта
  3. Предупреждение и предел
  4. Разрешённые команды после предела
  5. Экономия: длинный Read, повтор команды
  6. Главная сессия и сбои
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent_budget_hook as hook  # noqa: E402


# ═══ 1. Заготовки: транскрипт, событие, изолированные пути ═════

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Журнал, состояние и конфиг — во временной папке, настоящие не трогаем."""
    monkeypatch.setattr(hook, "CONFIG_PATH", tmp_path / "agent_budget.json")
    monkeypatch.setattr(hook, "LOG_PATH", tmp_path / "agent_budget.log")
    monkeypatch.setattr(hook, "STATE_DIR", tmp_path / "state")
    return tmp_path


def assistant_line(context, filler=0):
    usage = {"input_tokens": 2, "cache_read_input_tokens": context - 2, "cache_creation_input_tokens": 0}
    return json.dumps({"type": "assistant", "message": {"usage": usage, "text": "x" * filler}})


def make_agent(tmp_path, context, filler=0, agent_id="a1"):
    """Транскрипт подагента на том месте, где его ищет хук; возвращает общий кусок события."""
    session = "s1"
    sub = tmp_path / session / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"agent-{agent_id}.jsonl").write_text(assistant_line(context, filler) + "\n", encoding="utf-8")
    return {
        "session_id": session, "agent_id": agent_id, "agent_type": "general-purpose",
        "transcript_path": str(tmp_path / f"{session}.jsonl"),
    }


def event(base, name, tool, **tool_input):
    return {**base, "hook_event_name": name, "tool_name": tool, "tool_input": tool_input}


def text_of(answer):
    return answer["hookSpecificOutput"]["additionalContext"]


def decision_of(answer):
    return answer["hookSpecificOutput"]["permissionDecision"]


# ═══ 2. Контекст из хвоста транскрипта ═════════════════════════

def test_context_is_sum_of_input_and_cache_of_last_step(isolated):
    """Контекст — input + cache_read + cache_creation последнего шага."""
    usage = {"input_tokens": 5, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 200}
    assert hook.context_of_usage(usage) == 1205


def test_last_step_wins_over_earlier_steps(isolated):
    text = assistant_line(10_000) + "\n" + assistant_line(20_000) + "\n"
    assert hook.last_usage_in(text) == 20_000


def test_tail_skips_cut_first_line_and_still_finds_last_step(isolated):
    """Хвост в 1 КБ режет файл посреди строки: первая строка отбрасывается, последний шаг находится."""
    base = make_agent(isolated, 50_000)
    path = hook.subagent_transcript(event(base, "PreToolUse", "Bash"))
    with path.open("a", encoding="utf-8") as f:
        for _ in range(200):
            f.write(json.dumps({"type": "user", "pad": "y" * 1000}) + "\n")
        f.write(assistant_line(123_456) + "\n")
    assert hook.agent_context(path, tail_bytes=3000) == 123_456


def test_huge_last_line_widens_window(isolated):
    """Шаг не влез в хвост — окно расширяется, а не молчит."""
    base = make_agent(isolated, 77_000, filler=2_000_000)
    path = hook.subagent_transcript(event(base, "PreToolUse", "Bash"))
    assert hook.agent_context(path, tail_bytes=300_000) == 77_000


def test_tail_does_not_read_whole_file(isolated):
    base = make_agent(isolated, 50_000)
    path = hook.subagent_transcript(event(base, "PreToolUse", "Bash"))
    with path.open("a", encoding="utf-8") as f:
        for _ in range(3000):
            f.write(json.dumps({"type": "user", "pad": "y" * 1000}) + "\n")
        f.write(assistant_line(88_000) + "\n")
    assert len(hook.read_tail(path, 300_000).encode()) <= 300_000
    assert hook.agent_context(path, 300_000) == 88_000


# ═══ 3. Предупреждение и предел ════════════════════════════════

def test_no_warning_below_250k(isolated):
    base = make_agent(isolated, 249_000)
    assert hook.run(event(base, "PostToolUse", "Bash", command="ls")) is None


def test_warning_at_250k_names_context_and_handoff(isolated):
    base = make_agent(isolated, 252_000)
    answer = hook.run(event(base, "PostToolUse", "Bash", command="ls"))
    assert "252 тыс. из 300" in text_of(answer) and "handoff" in text_of(answer)


def test_warning_once_per_10k(isolated):
    """На одной отметке — одно предупреждение; следующее — через +10 тыс."""
    base = make_agent(isolated, 252_000)
    assert hook.run(event(base, "PostToolUse", "Bash", command="a")) is not None
    assert hook.run(event(base, "PostToolUse", "Bash", command="b")) is None
    make_agent(isolated, 259_000)
    assert hook.run(event(base, "PostToolUse", "Bash", command="c")) is None
    make_agent(isolated, 262_000)
    assert hook.run(event(base, "PostToolUse", "Bash", command="d")) is not None


def test_deny_everything_at_290k(isolated):
    base = make_agent(isolated, 291_000)
    for tool, args in [("Read", {"file_path": "x.py"}), ("Grep", {"pattern": "a"}),
                       ("Bash", {"command": "pytest"}), ("Write", {"file_path": "src/a.py"})]:
        answer = hook.run(event(base, "PreToolUse", tool, **args))
        assert decision_of(answer) == "deny", tool
    assert "300" in answer["hookSpecificOutput"]["permissionDecisionReason"]


def test_thresholds_come_from_config(isolated):
    """Пороги берутся из agent_budget.json — так опыт идёт на малых цифрах."""
    (isolated / "agent_budget.json").write_text(json.dumps({"warn_at": 15_000, "deny_at": 20_000}), encoding="utf-8")
    base = make_agent(isolated, 21_000)
    assert decision_of(hook.run(event(base, "PreToolUse", "Bash", command="ls"))) == "deny"


def test_disabled_config_is_silent(isolated):
    (isolated / "agent_budget.json").write_text(json.dumps({"enabled": False}), encoding="utf-8")
    base = make_agent(isolated, 295_000)
    assert hook.run(event(base, "PreToolUse", "Bash", command="ls")) is None


# ═══ 4. Разрешённые команды после предела ══════════════════════

@pytest.mark.parametrize("command", [
    "git add -A", "git commit -m 'готово; записка'", "git status", "git diff --stat",
    "git log -1", "git -C C:/repo commit -m \"a && b\"",
    'git commit -m "$(cat <<\'EOF\'\nтекст\nEOF\n)"',
])
def test_git_commands_allowed(command):
    assert hook.is_safe_git_command(command)


@pytest.mark.parametrize("command", [
    "git push", "git log -5", "git diff", "git status && rm -rf x", "git add . ; curl x",
    "git status | tee f", "git commit -m a > out", "pytest", "ls",
])
def test_other_commands_denied(command):
    assert not hook.is_safe_git_command(command)


def test_after_limit_only_handoff_files_may_be_written(isolated):
    base = make_agent(isolated, 295_000)
    ok = event(base, "PreToolUse", "Write", file_path=r"C:\tmp\scratchpad\handoff\branch.md")
    bad = event(base, "PreToolUse", "Write", file_path=r"C:\proj\src\main.py")
    assert hook.run(ok) is None
    assert decision_of(hook.run(bad)) == "deny"


def test_after_limit_git_commit_passes_but_git_push_denied(isolated):
    base = make_agent(isolated, 295_000)
    assert hook.run(event(base, "PreToolUse", "Bash", command="git commit -m done")) is None
    assert decision_of(hook.run(event(base, "PreToolUse", "Bash", command="git push"))) == "deny"


# ═══ 5. Экономия: длинный Read, повтор команды ═════════════════

def test_read_long_file_without_limit_denied(isolated):
    big = isolated / "big.txt"
    big.write_text("строка\n" * 2000, encoding="utf-8")
    base = make_agent(isolated, 50_000)
    answer = hook.run(event(base, "PreToolUse", "Read", file_path=str(big)))
    assert decision_of(answer) == "deny" and "offset/limit" in answer["hookSpecificOutput"]["permissionDecisionReason"]


def test_read_with_limit_or_short_file_allowed(isolated):
    big = isolated / "big.txt"
    big.write_text("строка\n" * 2000, encoding="utf-8")
    small = isolated / "small.txt"
    small.write_text("a\n" * 100, encoding="utf-8")
    base = make_agent(isolated, 50_000)
    assert hook.run(event(base, "PreToolUse", "Read", file_path=str(big), limit=200)) is None
    assert hook.run(event(base, "PreToolUse", "Read", file_path=str(small))) is None
    assert hook.run(event(base, "PreToolUse", "Read", file_path=str(isolated / "нет.txt"))) is None


def test_read_offset_counts_toward_remaining_lines(isolated):
    big = isolated / "big.txt"
    big.write_text("строка\n" * 2000, encoding="utf-8")
    assert not hook.read_is_too_long({"file_path": str(big), "offset": 1000}, 1500)


def test_same_bash_command_third_time_warns(isolated):
    base = make_agent(isolated, 50_000)
    ev = event(base, "PostToolUse", "Bash", command="pytest -x")
    assert hook.run(ev) is None
    assert hook.run(ev) is None
    assert "смени подход" in text_of(hook.run(ev))


def test_different_command_resets_repeat(isolated):
    base = make_agent(isolated, 50_000)
    for command in ["a", "a", "b", "a", "a"]:
        assert hook.run(event(base, "PostToolUse", "Bash", command=command)) is None


# ═══ 6. Главная сессия и сбои ══════════════════════════════════

def test_main_session_is_untouched(isolated):
    """Без agent_id (главная сессия) — тишина, даже когда «контекст» огромен."""
    ev = {"session_id": "s1", "transcript_path": str(isolated / "s1.jsonl"),
          "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert hook.run(ev) is None


def test_missing_transcript_means_no_decision(isolated):
    base = {"session_id": "s1", "agent_id": "ghost", "transcript_path": str(isolated / "s1.jsonl")}
    with pytest.raises(OSError):  # run() бросает, main() ловит и пишет в журнал
        hook.run(event(base, "PreToolUse", "Bash", command="ls"))


def run_as_process(payload, tmp_path):
    env = {**__import__("os").environ, "AGENT_BUDGET_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, hook.__file__], input=payload, capture_output=True,
                          text=True, encoding="utf-8", env=env)


def test_garbage_input_exits_zero_silently_and_logs(isolated):
    done = run_as_process("не json", isolated)
    assert done.returncode == 0 and done.stdout == ""
    assert "ERROR" in (isolated / "agent_budget.log").read_text(encoding="utf-8")


def test_missing_transcript_exits_zero_silently_and_logs(isolated):
    ev = event({"session_id": "s1", "agent_id": "ghost", "transcript_path": str(isolated / "s1.jsonl")},
               "PreToolUse", "Bash", command="ls")
    done = run_as_process(json.dumps(ev), isolated)
    assert done.returncode == 0 and done.stdout == ""
    assert "ERROR" in (isolated / "agent_budget.log").read_text(encoding="utf-8")


def test_process_prints_deny_json_for_agent_over_limit(isolated):
    base = make_agent(isolated, 295_000)
    done = run_as_process(json.dumps(event(base, "PreToolUse", "Bash", command="ls")), isolated)
    assert done.returncode == 0
    assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ═══ Сдача отчёта после предела (хук не должен запирать агента без выхода) ═══

@pytest.mark.parametrize("tool", ["SubagentHandback", "SendMessage"])
def test_after_limit_agent_can_still_report(tool):
    assert hook.allowed_after_limit(tool, {})
