# -*- coding: utf-8 -*-
"""Тесты хука грабель: подбор урока к команде и работа без файла уроков."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "hooks" / "grabli_hook.py"
EXAMPLE = Path(__file__).resolve().parent / "uroki.example.md"


def run(event, env_extra):
    env = {**os.environ, **env_extra}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event).encode("utf-8"),
                       capture_output=True, env=env, timeout=20)
    return r.returncode, r.stdout.decode("utf-8")


def pre(command, **env):
    return run({"hook_event_name": "PreToolUse", "session_id": "t-" + command[:5],
                "tool_input": {"command": command}}, env)


def test_matching_command_gets_lesson(tmp_path):
    code, out = pre("pkill -f server", GRABLI_LESSONS=str(EXAMPLE), TMP=str(tmp_path), TEMP=str(tmp_path), TMPDIR=str(tmp_path))
    assert code == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "pkill -f" in ctx


def test_unrelated_command_is_silent(tmp_path):
    code, out = pre("ls -la", GRABLI_LESSONS=str(EXAMPLE), TMP=str(tmp_path), TEMP=str(tmp_path), TMPDIR=str(tmp_path))
    assert code == 0 and out == ""


def test_lesson_not_repeated_in_session(tmp_path):
    env = dict(GRABLI_LESSONS=str(EXAMPLE), TMP=str(tmp_path), TEMP=str(tmp_path), TMPDIR=str(tmp_path))
    event = {"hook_event_name": "PreToolUse", "session_id": "same", "tool_input": {"command": "pkill -f x"}}
    assert run(event, env)[1] != ""
    assert run(event, env)[1] == ""


def test_missing_lessons_file_is_silent(tmp_path):
    code, out = pre("pkill -f server", GRABLI_LESSONS=str(tmp_path / "net.md"),
                    TMP=str(tmp_path), TEMP=str(tmp_path), TMPDIR=str(tmp_path))
    assert code == 0 and out == ""


def test_session_start_without_digest_is_silent(tmp_path):
    code, out = run({"hook_event_name": "SessionStart", "source": "startup"},
                    {"GRABLI_DIGEST": str(tmp_path / "net.md")})
    assert code == 0 and out == ""


def test_session_start_with_digest(tmp_path):
    d = tmp_path / "d.md"
    d.write_text("# Главные\n- правило\n", encoding="utf-8")
    code, out = run({"hook_event_name": "SessionStart", "source": "startup"}, {"GRABLI_DIGEST": str(d)})
    assert code == 0 and "правило" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_garbage_input_does_not_fail():
    r = subprocess.run([sys.executable, str(HOOK)], input=b"not json", capture_output=True, timeout=20)
    assert r.returncode == 0
