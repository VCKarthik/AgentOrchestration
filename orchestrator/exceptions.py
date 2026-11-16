"""
Typed exceptions for orchestrator-level failures.
Each failure class is distinct — no bare except, no silent swallowing.
"""
from __future__ import annotations

from pydantic import ValidationError


class AgentUnreachableError(Exception):
    def __init__(self, agent_name: str, port: int) -> None:
        self.agent_name = agent_name
        self.port = port
        super().__init__(f"{agent_name} unreachable on port {port}")


class AgentResponseError(Exception):
    def __init__(self, agent_name: str, status_code: int, body: str) -> None:
        self.agent_name = agent_name
        self.status_code = status_code
        self.body = body
        super().__init__(f"{agent_name} returned HTTP {status_code}: {body[:200]}")


class AgentSchemaError(Exception):
    def __init__(self, agent_name: str, validation_error: ValidationError) -> None:
        self.agent_name = agent_name
        self.validation_error = validation_error
        super().__init__(f"{agent_name} response failed schema validation: {validation_error}")


class StagePartialFailureError(Exception):
    def __init__(self, stage: int, failed_agents: list[str], errors: dict[str, str]) -> None:
        self.stage = stage
        self.failed_agents = failed_agents
        self.errors = errors
        super().__init__(
            f"Stage {stage} partial failure — {len(failed_agents)} agent(s) failed: {failed_agents}"
        )
