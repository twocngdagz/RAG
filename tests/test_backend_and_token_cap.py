"""Tests for the pluggable model backend and the v2 token-cap truncation guard.

Covers:
- resolve_complete_fn dispatch (injected wins; --backend claude-cli vs nvidia).
- complete_via_claude_cli subprocess handling (success, errors, plain text).
- default_complete_direct_openai_like raising a retryable error on truncation.
"""

import argparse
import json
import subprocess
import sys
import types

import pytest

import generate_book_learning_materials as book


def make_args(**overrides):
    defaults = {
        "nvidia_model": "test-model",
        "backend": "nvidia",
        "claude_model": "sonnet",
        "model_max_tokens": 8000,
        "model_timeout_seconds": 180,
        "model_max_retries": 2,
        "model_retry_backoff_seconds": 0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def fake_openai_module(*, content, finish_reason):
    """Build a stand-in `openai` module whose OpenAI client returns one choice."""

    class FakeMessage:
        def __init__(self):
            self.content = content

    class FakeChoice:
        def __init__(self):
            self.message = FakeMessage()
            self.finish_reason = finish_reason

    class FakeResponse:
        def __init__(self):
            self.choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **_kwargs):
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = FakeChat()

    module = types.ModuleType("openai")
    module.OpenAI = FakeOpenAI
    return module


# --------------------------------------------------------------------------- #
# resolve_complete_fn dispatch
# --------------------------------------------------------------------------- #

def test_injected_complete_fn_always_wins():
    sentinel = lambda _prompt: "injected"
    assert book.resolve_complete_fn(make_args(), sentinel, direct=True) is sentinel
    assert book.resolve_complete_fn(make_args(backend="claude-cli"), sentinel, direct=False) is sentinel


def test_backend_claude_cli_routes_to_claude(monkeypatch):
    seen = {}

    def fake_claude(prompt, *, model, timeout_seconds):
        seen["prompt"] = prompt
        seen["model"] = model
        seen["timeout"] = timeout_seconds
        return "claude-result"

    monkeypatch.setattr(book, "complete_via_claude_cli", fake_claude)
    fn = book.resolve_complete_fn(
        make_args(backend="claude-cli", claude_model="opus", model_timeout_seconds=300),
        None,
        direct=True,
    )
    assert fn("PROMPT") == "claude-result"
    assert seen == {"prompt": "PROMPT", "model": "opus", "timeout": 300}


def test_backend_nvidia_direct_passes_max_tokens(monkeypatch):
    seen = {}

    def fake_direct(prompt, *, model, timeout_seconds, max_tokens):
        seen["max_tokens"] = max_tokens
        seen["model"] = model
        return "nvidia-result"

    monkeypatch.setattr(book, "default_complete_direct_openai_like", fake_direct)
    fn = book.resolve_complete_fn(
        make_args(backend="nvidia", model_max_tokens=8000, nvidia_model="m"),
        None,
        direct=True,
    )
    assert fn("PROMPT") == "nvidia-result"
    assert seen == {"max_tokens": 8000, "model": "m"}


# --------------------------------------------------------------------------- #
# complete_via_claude_cli
# --------------------------------------------------------------------------- #

def _patch_run(monkeypatch, *, returncode=0, stdout="", stderr="", capture=None, raises=None):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        if capture is not None:
            capture["cmd"] = cmd
            capture["input"] = input
            capture["timeout"] = timeout
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(book.subprocess, "run", fake_run)


def test_claude_cli_success_extracts_result_and_pipes_stdin(monkeypatch):
    capture = {}
    envelope = json.dumps({"result": '{"ok": true}', "is_error": False})
    _patch_run(monkeypatch, stdout=envelope, capture=capture)

    out = book.complete_via_claude_cli("BIG PROMPT", model="sonnet", timeout_seconds=42)

    assert out == '{"ok": true}'
    # Prompt goes on stdin (not as a positional arg), and model/timeout are wired.
    assert capture["input"] == "BIG PROMPT"
    assert capture["timeout"] == 42
    assert "-p" in capture["cmd"]
    assert "--model" in capture["cmd"] and "sonnet" in capture["cmd"]
    assert "--bare" not in capture["cmd"]  # must stay on subscription auth


def test_claude_cli_plain_text_stdout_is_returned_directly(monkeypatch):
    _patch_run(monkeypatch, stdout="just plain text, not an envelope")
    assert book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=10) == (
        "just plain text, not an envelope"
    )


def test_claude_cli_is_error_envelope_raises(monkeypatch):
    _patch_run(monkeypatch, stdout=json.dumps({"result": "boom", "is_error": True}))
    with pytest.raises(book.ModelCallError):
        book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=10)


def test_claude_cli_empty_result_raises_json_error(monkeypatch):
    _patch_run(monkeypatch, stdout=json.dumps({"result": "", "is_error": False}))
    with pytest.raises(book.ModelJSONError):
        book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=10)


def test_claude_cli_nonzero_exit_raises_call_error(monkeypatch):
    _patch_run(monkeypatch, returncode=2, stdout="", stderr="auth failure")
    with pytest.raises(book.ModelCallError) as exc:
        book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=10)
    assert "auth failure" in str(exc.value)


def test_claude_cli_missing_binary_raises_clear_error(monkeypatch):
    _patch_run(monkeypatch, raises=FileNotFoundError())
    with pytest.raises(book.ModelCallError) as exc:
        book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=10)
    assert getattr(exc.value, "reason", None) == "claude_cli_not_found"


def test_claude_cli_timeout_raises_call_error(monkeypatch):
    _patch_run(monkeypatch, raises=subprocess.TimeoutExpired(cmd="claude", timeout=1))
    with pytest.raises(book.ModelCallError):
        book.complete_via_claude_cli("p", model="sonnet", timeout_seconds=1)


# --------------------------------------------------------------------------- #
# Token-cap truncation guard (H-1)
# --------------------------------------------------------------------------- #

def test_truncated_response_raises_retryable_json_error(monkeypatch):
    monkeypatch.setattr(book, "require_env", lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        fake_openai_module(content='{"partial": "trunc', finish_reason="length"),
    )
    with pytest.raises(book.ModelJSONError) as exc:
        book.default_complete_direct_openai_like(
            "p", model="m", timeout_seconds=5, max_tokens=10
        )
    assert "truncat" in str(exc.value).lower()


def test_complete_response_returns_content(monkeypatch):
    monkeypatch.setattr(book, "require_env", lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        fake_openai_module(content='{"ok": true}', finish_reason="stop"),
    )
    out = book.default_complete_direct_openai_like(
        "p", model="m", timeout_seconds=5, max_tokens=8000
    )
    assert out == '{"ok": true}'


def test_default_max_tokens_is_generous():
    # Guards against a regression back to the old 1500 cap that truncated v2.
    assert book.DEFAULT_MODEL_MAX_TOKENS >= 4000
