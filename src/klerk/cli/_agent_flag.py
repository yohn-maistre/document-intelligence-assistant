"""Midday-pattern ``--agent`` / ``--json`` dual-mode for klerk's CLI verbs.

The CLI verbs are klerk's **external** tool contract (Claude Code, cron jobs,
recruiters' manual shell sessions, a future TS rewrite). Those callers want a
machine-parseable result, not a Rich table. This module makes any Typer verb
dual-mode:

  * **human mode** (default): the verb's existing Rich output is untouched.
  * **agent mode** (``--agent`` / its alias ``--json``): Rich/human text is
    routed to **stderr**, and the verb hands its structured result to
    :func:`emit`, which writes **exactly one** JSON object to **stdout** with
    no ANSI escapes.

Contract (documented, single + consistent):

  * stdout in agent mode carries EXACTLY ONE JSON object and nothing else.
  * On success: exit code 0; the JSON object is the verb's structured payload.
  * On error: exit code is non-zero (1 by default, or the original
    ``typer.Exit`` code) and stdout carries ONE JSON object of the shape
    ``{"error": "<type>", "message": "<str>"}``. (We chose JSON-on-stdout for
    errors too, so an agent only ever has to parse stdout — stderr is purely
    advisory human text.)

Usage in a verb module::

    from klerk.cli._agent_flag import with_agent_mode, emit, agent_console

    console = agent_console()  # routes to stderr when --agent is active

    @with_agent_mode
    def my_cmd(query: str, *, agent: bool = False) -> None:
        result = do_work(query)
        console.print(rich_table(result))   # human: stdout / agent: stderr
        emit({"query": query, "hits": result})  # agent: one JSON obj on stdout

The decorator injects the ``--agent`` / ``--json`` option itself, so the
wrapped function just needs to accept an ``agent: bool`` keyword (Typer reads
the annotation the decorator adds). ``emit`` is a no-op in human mode, so verbs
can call it unconditionally.
"""

from __future__ import annotations

import functools
import inspect
import json
import sys
from collections.abc import Callable
from contextvars import ContextVar
from typing import Annotated, Any, TypeVar

import typer
from rich.console import Console

# Module-level (contextvar) flag so nested helpers + the shared console can ask
# "are we in agent mode?" without threading the bool through every call.
_AGENT_MODE: ContextVar[bool] = ContextVar("klerk_agent_mode", default=False)

# One JSON object per invocation: guard against a verb calling emit() twice.
_EMITTED: ContextVar[bool] = ContextVar("klerk_agent_emitted", default=False)

F = TypeVar("F", bound=Callable[..., Any])


def is_agent_mode() -> bool:
    """True when the current verb is running under ``--agent`` / ``--json``."""
    return _AGENT_MODE.get()


def agent_console() -> Console:
    """A Rich :class:`Console` that respects agent mode.

    In agent mode it writes to **stderr** (so stdout stays pure JSON) and
    disables markup-driven ANSI on a non-tty automatically. In human mode it is
    an ordinary stdout console. The returned object is a live proxy: it reads
    the contextvar at print time, so a single module-level instance is correct
    even though the flag flips per-invocation.
    """
    return _AgentConsole()


def emit(payload: dict[str, Any] | list[Any]) -> None:
    """Write the verb's structured result as exactly one JSON object on stdout.

    No-op outside agent mode (so verbs can call it unconditionally). Raises if
    called more than once in a single agent-mode invocation — the contract is
    one JSON object per run.
    """
    if not _AGENT_MODE.get():
        return
    if _EMITTED.get():
        raise RuntimeError("emit() called more than once in a single --agent run")
    _EMITTED.set(True)
    json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


class _AgentConsole:
    """Proxy Console: stderr+no-ANSI under --agent, plain stdout otherwise."""

    def __init__(self) -> None:
        # Two real consoles; pick at call time based on the contextvar.
        self._human = Console()
        self._agent = Console(stderr=True)

    def _active(self) -> Console:
        return self._agent if _AGENT_MODE.get() else self._human

    def __getattr__(self, name: str) -> Any:
        # Delegate everything (print, rule, log, status, ...) to the active console.
        return getattr(self._active(), name)


def with_agent_mode(func: F) -> F:
    """Decorate a Typer verb so it gains an ``--agent`` / ``--json`` flag.

    The wrapper:
      * injects the ``agent: bool`` option into the verb's signature (Typer
        picks it up from the merged ``__signature__``),
      * sets/resets the ``_AGENT_MODE`` contextvar around the call,
      * in agent mode, converts any uncaught exception (or non-zero
        ``typer.Exit``) into a single ``{"error", "message"}`` JSON object on
        stdout + a non-zero exit, so external callers only parse stdout.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, agent: bool = False, **kwargs: Any) -> Any:
        token = _AGENT_MODE.set(agent)
        emitted_token = _EMITTED.set(False)
        try:
            try:
                return func(*args, **kwargs)
            except typer.Exit as exc:
                code = getattr(exc, "exit_code", 0) or 0
                if agent and code != 0:
                    _emit_error("CommandError", f"command exited with code {code}", code)
                raise
            except Exception as exc:  # noqa: BLE001
                if agent:
                    _emit_error(type(exc).__name__, str(exc), 1)
                    raise typer.Exit(code=1) from exc
                raise
        finally:
            _EMITTED.reset(emitted_token)
            _AGENT_MODE.reset(token)

    # Merge an `agent` Typer option into the wrapped signature so Typer renders
    # `--agent` / `--json` and passes the parsed value through to `wrapper`.
    _inject_agent_param(wrapper, func)
    return wrapper  # type: ignore[return-value]


_AGENT_OPTION = typer.Option(
    "--agent",
    "--json",
    help="Agent mode: emit one JSON object to stdout; human text → stderr.",
)


def _inject_agent_param(wrapper: Callable[..., Any], original: Callable[..., Any]) -> None:
    """Append a keyword-only ``agent`` parameter (Annotated Typer option) to
    the wrapper's public signature so Typer exposes ``--agent`` / ``--json``."""
    sig = inspect.signature(original)
    params = list(sig.parameters.values())
    # Drop any **kwargs so we can append a clean keyword-only param.
    params = [p for p in params if p.kind is not inspect.Parameter.VAR_KEYWORD]
    agent_param = inspect.Parameter(
        "agent",
        kind=inspect.Parameter.KEYWORD_ONLY,
        default=False,
        annotation=Annotated[bool, _AGENT_OPTION],
    )
    wrapper.__signature__ = sig.replace(parameters=[*params, agent_param])  # type: ignore[attr-defined]


def _emit_error(err_type: str, message: str, code: int) -> None:
    """Emit the standard error JSON object on stdout (idempotent-safe)."""
    if _EMITTED.get():
        return
    _EMITTED.set(True)
    json.dump(
        {"error": err_type, "message": message, "exit_code": code},
        sys.stdout,
        ensure_ascii=False,
        default=str,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
