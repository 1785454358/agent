"""Measured provider usage, kept separate from admission estimates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from deeptrace.models.metrics import TokenUsage, UsageBreakdown, add_token_usages


def response_usage(response: Any) -> TokenUsage | None:
    usage = getattr(response, "usage_metadata", None) or {}
    if not usage:
        metadata = getattr(response, "response_metadata", None) or {}
        usage = (
            (metadata.get("token_usage") or {}) if isinstance(metadata, Mapping) else {}
        )
    if not isinstance(usage, Mapping):
        return None
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    if any(
        type(value) is not int or value < 0 for value in (input_tokens, output_tokens)
    ):
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


class ModelMetrics(BaseModel):
    """Admitted gateway attempts and measured usage, not a transport billing ledger.

    Production disables internal retries. An admitted attempt can still fail
    validation or binding before it reaches the remote provider.
    """

    attempts: int = Field(default=0, ge=0)
    measured_attempts: int = Field(default=0, ge=0)
    roles: dict[str, TokenUsage] = Field(default_factory=dict)
    stage_seconds: dict[str, float] = Field(default_factory=dict)

    def record(self, role: str, usage: TokenUsage | None, seconds: float) -> None:
        role = "writer" if role == "responder" else role
        self.stage_seconds[role] = self.stage_seconds.get(role, 0) + max(0, seconds)
        if usage is not None:
            self.measured_attempts += 1
            self.roles[role] = add_token_usages(
                self.roles.get(role, TokenUsage()), usage
            )

    def payload(self) -> dict[str, Any]:
        observed = add_token_usages(*self.roles.values())
        missing = self.attempts - self.measured_attempts
        role_usage = UsageBreakdown.model_validate(self.roles)
        role_usage.other = add_token_usages(
            role_usage.other,
            *(
                usage
                for role, usage in self.roles.items()
                if role not in UsageBreakdown.model_fields
            ),
        )
        return {
            "provider_attempts": self.attempts,
            "measured_usage_attempts": self.measured_attempts,
            "missing_usage_attempts": missing,
            "usage_complete": missing == 0,
            **{
                key: value if not missing else None
                for key, value in observed.model_dump().items()
            },
            "observed_usage": observed.model_dump(),
            "role_usage": role_usage.model_dump(),
            "observed_role_usage": {
                role: usage.model_dump() for role, usage in self.roles.items()
            },
            "stage_seconds": dict(self.stage_seconds),
        }


def run_usage_payload(context) -> dict[str, Any] | None:
    """Production contexts expose usage; third-party contexts may not."""
    gateway = getattr(context, "model_gateway", None)
    snapshot = getattr(gateway, "usage_payload", None)
    return snapshot() if snapshot is not None else None
