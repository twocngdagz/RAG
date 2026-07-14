"""Tests for the grounding judge's pluggable backend.

audit_book_claim_support.py decides whether generated claims are actually
supported by the source. It was hardwired to the metered NVIDIA endpoint running
Mistral, so the weakest available model was judging the grounding of stronger
models' output -- and every audit cost API spend. It can now run the judge on the
subscription-backed agent CLIs instead.
"""

import argparse

import pytest

import audit_book_claim_support as audit
import generate_book_learning_materials as backends


def make_args(**overrides):
    defaults = {
        "backend": "nvidia",
        "model": "mistralai/mistral-medium-3.5-128b",
        "claude_model": "sonnet",
        "codex_model": "gpt-5.5",
        "codex_reasoning_effort": "high",
        "model_timeout_seconds": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# --------------------------------------------------------------------------- #
# Backend dispatch
# --------------------------------------------------------------------------- #

def test_injected_complete_fn_always_wins():
    sentinel = lambda _prompt: "injected"
    resolved = audit.resolve_audit_complete_fn(make_args(backend="codex-cli"), sentinel)
    assert resolved is sentinel


def test_nvidia_backend_keeps_the_existing_default_path():
    # None means "fall through to the module's NVIDIA default_complete".
    assert audit.resolve_audit_complete_fn(make_args(backend="nvidia")) is None


def test_codex_backend_routes_to_codex(monkeypatch):
    seen = {}

    def fake_codex(prompt, *, model, reasoning_effort, timeout_seconds):
        seen.update(
            prompt=prompt, model=model, effort=reasoning_effort, timeout=timeout_seconds
        )
        return "verdict"

    monkeypatch.setattr(backends, "complete_via_codex_cli", fake_codex)
    fn = audit.resolve_audit_complete_fn(
        make_args(backend="codex-cli", codex_model="gpt-5.5", codex_reasoning_effort="high")
    )

    assert fn("JUDGE THIS") == "verdict"
    assert seen["model"] == "gpt-5.5"
    assert seen["effort"] == "high"
    assert seen["timeout"] == backends.DEFAULT_CLI_TIMEOUT_SECONDS


def test_claude_backend_routes_to_claude(monkeypatch):
    seen = {}

    def fake_claude(prompt, *, model, timeout_seconds):
        seen.update(model=model, timeout=timeout_seconds)
        return "verdict"

    monkeypatch.setattr(backends, "complete_via_claude_cli", fake_claude)
    fn = audit.resolve_audit_complete_fn(make_args(backend="claude-cli", claude_model="opus"))

    assert fn("JUDGE THIS") == "verdict"
    assert seen["model"] == "opus"


# --------------------------------------------------------------------------- #
# Backend errors must surface as this module's own types, so the surrounding
# retry/repair handling keeps working unchanged.
# --------------------------------------------------------------------------- #

def test_backend_call_error_is_translated(monkeypatch):
    def boom(prompt, **_kwargs):
        raise backends.ModelCallError("cli exploded", reason="codex_cli_failed")

    monkeypatch.setattr(backends, "complete_via_codex_cli", boom)
    fn = audit.resolve_audit_complete_fn(make_args(backend="codex-cli"))

    with pytest.raises(audit.ModelCallError):
        fn("p")


def test_backend_json_error_is_translated(monkeypatch):
    def boom(prompt, **_kwargs):
        raise backends.ModelJSONError("empty response")

    monkeypatch.setattr(backends, "complete_via_codex_cli", boom)
    fn = audit.resolve_audit_complete_fn(make_args(backend="codex-cli"))

    with pytest.raises(audit.ModelJSONError):
        fn("p")


# --------------------------------------------------------------------------- #
# Timeouts
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("backend", ["claude-cli", "codex-cli"])
def test_cli_judge_gets_the_long_timeout(backend):
    assert (
        audit.resolve_audit_timeout_seconds(make_args(backend=backend))
        == backends.DEFAULT_CLI_TIMEOUT_SECONDS
    )


def test_nvidia_judge_keeps_the_short_timeout():
    assert (
        audit.resolve_audit_timeout_seconds(make_args(backend="nvidia"))
        == backends.DEFAULT_API_TIMEOUT_SECONDS
    )


def test_explicit_timeout_wins():
    args = make_args(backend="codex-cli", model_timeout_seconds=30)
    assert audit.resolve_audit_timeout_seconds(args) == 30
