"""External write-back gateway contracts for the Integration Service."""

from .contracts import BoundedWriteBackExecutionReceipt, BoundedWriteBackRequest


class ExternalWriteBackGatewayError(Exception):
    """Raised when the bounded external write-back hook is rejected or unavailable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExternalWriteBackGateway:
    """Stable contract boundary for bounded post-activation external write-back."""

    def execute_write_back(
        self,
        request: BoundedWriteBackRequest,
    ) -> BoundedWriteBackExecutionReceipt:
        raise NotImplementedError
