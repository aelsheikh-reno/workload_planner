"""External service gateway contracts for workflow orchestration."""

from .contracts import (
    ActivationExecutionStepReceipt,
    ActivationExecutionStepRequest,
    PlanningEngineExecutionReceipt,
    PlanningEngineExecutionRequest,
)


class PlanningEngineGatewayError(Exception):
    """Raised when the Planning Engine handoff is rejected or unavailable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PlanningEngineGateway:
    """Stable contract boundary between Workflow Orchestrator and Planning Engine."""

    def submit_planning_run(
        self, request: PlanningEngineExecutionRequest
    ) -> PlanningEngineExecutionReceipt:
        raise NotImplementedError


class ActivationExecutionGatewayError(Exception):
    """Raised when a downstream activation step hook is rejected or unavailable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ActivationExecutionGateway:
    """Stable contract boundary for activation-triggered async downstream hooks."""

    def submit_step(
        self, request: ActivationExecutionStepRequest
    ) -> ActivationExecutionStepReceipt:
        raise NotImplementedError
