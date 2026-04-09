"""
Guardrail Prevention Detector

Labs-only detector for guardrail challenges where the user's webhook
must successfully **block** a specific hook event. Works for both tool
hooks (e.g. block a dangerous tool call) and model hooks (e.g. block
model output containing sensitive data).

Detection logic:
  1. Match guardrail webhook events (agent.guardrail.*)
  2. Check the hook_kind matches the required hook kind
  3. Optionally filter by tool_name (tool hooks only)
  4. If outcome is "completed" and verdict is "block" -> detected
  5. Timeout / error / invalid_verdict -> not detected (guardrail failed)

Configuration:
  required_hook_kind: str — hook kind that must produce a block verdict.
      One of: before_model, after_model, before_tool, after_tool.
      Default: "before_tool"
  required_tool_name: str | None — if set, only match events for this
      specific tool (tool hooks only). Default: None (any)
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("GuardrailPreventionDetector")
class GuardrailPreventionDetector(BaseDetector):
    """Detects successful guardrail prevention via webhook block verdict."""

    def _validate_config(self) -> None:
        valid_kinds = {"before_model", "after_model", "before_tool", "after_tool"}
        kind = self.config.get("required_hook_kind", "before_tool")
        if kind not in valid_kinds:
            raise ValueError(
                f"required_hook_kind must be one of {valid_kinds}, got '{kind}'"
            )

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.guardrail.*"]

    async def check_event(
        self, event: dict[str, Any], db: Session
    ) -> DetectionResult:
        event_type = event.get("event_type", "")

        if not event_type.startswith("agent.guardrail."):
            return DetectionResult(detected=False, message="Not a guardrail event")

        hook_kind = event.get("hook_kind")
        required_kind = self.config.get("required_hook_kind", "before_tool")
        if hook_kind != required_kind:
            return DetectionResult(
                detected=False,
                message=f"Hook kind '{hook_kind}' does not match required '{required_kind}'",
            )

        required_tool = self.config.get("required_tool_name")
        if required_tool:
            tool_name = event.get("tool_name")
            if tool_name != required_tool:
                return DetectionResult(
                    detected=False,
                    message=f"Tool '{tool_name}' does not match required '{required_tool}'",
                )

        outcome = event.get("outcome")
        verdict = event.get("verdict")

        if outcome == "completed" and verdict == "block":
            is_tool_hook = hook_kind in ("before_tool", "after_tool")
            context = (
                f" for tool '{event.get('tool_name')}'"
                if is_tool_hook and event.get("tool_name")
                else f" on model '{event.get('model')}'"
                if event.get("model")
                else ""
            )

            evidence: dict[str, Any] = {
                "hook_kind": hook_kind,
                "outcome": outcome,
                "verdict": verdict,
                "reason": event.get("reason"),
                "latency_ms": event.get("latency_ms"),
            }
            if is_tool_hook:
                evidence["tool_name"] = event.get("tool_name")
                evidence["tool_source"] = event.get("tool_source")
            else:
                evidence["model"] = event.get("model")

            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"Guardrail prevention successful: webhook returned 'block' on {hook_kind}{context}",
                evidence=evidence,
            )

        return DetectionResult(
            detected=False,
            message=f"Guardrail did not block: outcome={outcome}, verdict={verdict}",
            evidence={
                "hook_kind": hook_kind,
                "outcome": outcome,
                "verdict": verdict,
                "error_detail": event.get("error_detail"),
            },
        )
