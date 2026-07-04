"""The agent contract REWIND can drive during replay.

REWIND records *any* agent as a black box through the proxy. But to replay a fork
one-click on the server (re-running the loop from the edit point), it needs to
know two agent-specific things: how to shape a model request from a message list,
and how to execute a named tool. Agents that want server-driven replay implement
:class:`Agent`; the bundled flight demo does. Agents that don't can still be
forked and replayed by re-running them externally against the fork session (the
proxy serves the recorded prefix either way).
"""

from __future__ import annotations

from typing import Any, Protocol


class Agent(Protocol):
    """Minimal surface REWIND needs to re-drive an agent loop during replay."""

    model: str

    def build_request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Turn the running message list into a model-completion request body."""
        ...

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run a tool and return its result payload (must be JSON-serializable)."""
        ...
