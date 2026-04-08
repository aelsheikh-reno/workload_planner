"""Import/sync gateway adapters for Integration-owned intake handoff."""

import hashlib

from services.integration_service import IntegrationService

from .contracts import ImportSyncExecutionReceipt, ImportSyncExecutionRequest
from .gateways import ImportSyncExecutionGateway


class IntegrationBackedImportSyncExecutionGateway(ImportSyncExecutionGateway):
    """Admits Integration-owned import/sync execution for the MVP baseline."""

    def __init__(self, integration_service: IntegrationService) -> None:
        self._integration_service = integration_service

    def submit_import_sync(
        self, request: ImportSyncExecutionRequest
    ) -> ImportSyncExecutionReceipt:
        return ImportSyncExecutionReceipt(
            handoff_id=_stable_id(
                "import-sync-handoff",
                request.workflow_instance_id,
                str(request.attempt_number),
                request.source_system or "unknown-source-system",
            ),
            accepted_at=request.requested_at,
        )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return "%s_%s" % (prefix, digest)
