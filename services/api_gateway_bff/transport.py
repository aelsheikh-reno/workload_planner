"""Minimal frontend-consumable transport surface for the API Gateway / BFF."""

import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs

from services.decision_support_service import DecisionSupportService
from services.integration_service import IntegrationService
from services.planning_engine_service import PlanningEngineService
from services.planning_engine_service.gateway import PlanningEngineWorkflowGateway
from services.review_approval_service import ReviewApprovalService
from services.workflow_orchestrator_service import (
    ActivationWorkflowAdmissionError,
    ImportSyncTrigger,
    IntegrationBackedActivationExecutionGateway,
    IntegrationBackedImportSyncExecutionGateway,
    PlanningRunAdmissionError,
    PlanningRunTrigger,
    WorkflowOrchestratorService,
)

from .s01_portfolio_contract import (
    build_d01_task_drilldown_contract,
    build_s01_portfolio_contract,
)
from .s02_setup_contract import build_s02_setup_contract
from .s03_resource_detail_contract import build_s03_resource_detail_contract
from .s04_delta_review_contract import (
    build_m01_connected_change_set_contract,
    build_s04_delta_review_contract,
    submit_m01_connected_set_acceptance_selection,
    submit_s04_activation_command,
    submit_s04_delta_acceptance_selection,
)
from .s05_warnings_contract import build_s05_warnings_workspace_contract


JSON_HEADERS = [("Content-Type", "application/json; charset=utf-8")]
SERVICE_NAME = "API Gateway / BFF"


@dataclass(frozen=True)
class ApiGatewayBffDependencies:
    integration_service: IntegrationService
    planning_engine_service: PlanningEngineService
    review_approval_service: ReviewApprovalService
    decision_support_service: DecisionSupportService
    workflow_orchestrator_service: WorkflowOrchestratorService


class ApiGatewayTransportError(Exception):
    """Transport-layer error with HTTP response metadata."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ApiGatewayBffApplication:
    """WSGI application exposing the minimal MVP BFF transport surface."""

    def __init__(self, dependencies: ApiGatewayBffDependencies) -> None:
        self._dependencies = dependencies
        self._routes: Dict[
            Tuple[str, str],
            Callable[[Dict[str, List[str]], Optional[Dict[str, Any]]], Tuple[int, Any]],
        ] = {
            ("GET", "/health"): self._handle_health,
            ("GET", "/api/screens/s01/portfolio"): self._handle_get_s01_portfolio,
            ("GET", "/api/drawers/d01/task-drilldown"): self._handle_get_d01_task_drilldown,
            ("GET", "/api/screens/s02/setup"): self._handle_get_s02_setup,
            ("POST", "/api/screens/s02/import-sync"): self._handle_post_s02_import_sync,
            ("POST", "/api/screens/s02/planning-runs"): self._handle_post_s02_planning_runs,
            ("GET", "/api/screens/s02/planning-runs/status"): self._handle_get_s02_planning_run_status,
            ("GET", "/api/screens/s03/resource-detail"): self._handle_get_s03_resource_detail,
            ("GET", "/api/screens/s03/recommendation-context"): self._handle_get_s03_recommendation_context,
            ("POST", "/api/screens/s03/recommendation-context/refresh"): self._handle_post_s03_recommendation_refresh,
            ("GET", "/api/screens/s04/delta-review"): self._handle_get_s04_delta_review,
            ("POST", "/api/screens/s04/review-context"): self._handle_post_s04_review_context,
            ("POST", "/api/screens/s04/acceptance-selection"): self._handle_post_s04_acceptance_selection,
            ("GET", "/api/modals/m01/connected-change-set"): self._handle_get_m01_connected_change_set,
            ("POST", "/api/modals/m01/connected-change-set/acceptance-selection"): self._handle_post_m01_connected_change_set_acceptance_selection,
            ("POST", "/api/screens/s04/activation"): self._handle_post_s04_activation,
            ("GET", "/api/screens/s04/activation-status"): self._handle_get_s04_activation_status,
            ("GET", "/api/screens/s05/warnings-workspace"): self._handle_get_s05_warnings_workspace,
        }

    def __call__(self, environ: Dict[str, Any], start_response) -> Iterable[bytes]:
        try:
            status_code, payload = self.dispatch(
                method=environ.get("REQUEST_METHOD", "GET"),
                path=environ.get("PATH_INFO", "/"),
                query_string=environ.get("QUERY_STRING", ""),
                body_stream=environ.get("wsgi.input"),
                content_length=environ.get("CONTENT_LENGTH"),
            )
        except ApiGatewayTransportError as error:
            status_code = error.status_code
            payload = {
                "error": {
                    "code": error.code,
                    "message": error.message,
                }
            }
        response_body = json.dumps(payload, sort_keys=True).encode("utf-8")
        start_response(
            "%d %s" % (status_code, _http_status_text(status_code)),
            JSON_HEADERS + [("Content-Length", str(len(response_body)))],
        )
        return [response_body]

    def dispatch(
        self,
        method: str,
        path: str,
        query_string: str = "",
        body_stream=None,
        content_length: Optional[str] = None,
    ) -> Tuple[int, Any]:
        route = self._routes.get((method.upper(), path))
        if route is None:
            raise ApiGatewayTransportError(
                404,
                "route_not_found",
                "No API Gateway / BFF route matched %s %s." % (method.upper(), path),
            )
        query = parse_qs(query_string, keep_blank_values=False)
        body = _read_json_body(body_stream=body_stream, content_length=content_length)
        try:
            return route(query, body)
        except PlanningRunAdmissionError as error:
            raise ApiGatewayTransportError(409, error.code, error.message)
        except ActivationWorkflowAdmissionError as error:
            raise ApiGatewayTransportError(409, error.code, error.message)
        except ValueError as error:
            raise ApiGatewayTransportError(400, "invalid_request", str(error))

    def _handle_health(
        self,
        _query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, {"service": SERVICE_NAME, "status": "ok"}

    def _handle_get_s01_portfolio(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_s01_portfolio_contract(
            planning_engine_service=self._dependencies.planning_engine_service,
            planning_run_id=_optional_query_value(query, "planningRunId"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_get_d01_task_drilldown(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_d01_task_drilldown_contract(
            planning_engine_service=self._dependencies.planning_engine_service,
            planning_run_id=_optional_query_value(query, "planningRunId"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
            resource_id=_optional_query_value(query, "resourceId"),
            resource_external_id=_optional_query_value(query, "resourceExternalId"),
            task_id=_optional_query_value(query, "taskId"),
            task_external_id=_optional_query_value(query, "taskExternalId"),
            date=_optional_query_value(query, "date"),
            week_start_date=_optional_query_value(query, "weekStartDate"),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_get_s02_setup(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_s02_setup_contract(
            integration_service=self._dependencies.integration_service,
            planning_engine_service=self._dependencies.planning_engine_service,
            decision_support_service=self._dependencies.decision_support_service,
            workflow_orchestrator_service=self._dependencies.workflow_orchestrator_service,
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_post_s02_planning_runs(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        result = self._dependencies.workflow_orchestrator_service.start_planning_run(
            PlanningRunTrigger(
                planning_context_key=_require_body_value(payload, "planningContextKey"),
                source_snapshot_id=_require_body_value(payload, "sourceSnapshotId"),
                requested_by=_require_body_value(payload, "requestedBy"),
                requested_at=_require_body_value(payload, "requestedAt"),
                idempotency_key=payload.get("idempotencyKey"),
                max_attempts=int(payload.get("maxAttempts", 2)),
            )
        )
        return 202, result.to_dict()

    def _handle_post_s02_import_sync(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        result = self._dependencies.workflow_orchestrator_service.start_import_sync(
            ImportSyncTrigger(
                raw_payload=_require_body_object(payload, "rawPayload"),
                requested_by=_require_body_value(payload, "requestedBy"),
                requested_at=_require_body_value(payload, "requestedAt"),
                idempotency_key=payload.get("idempotencyKey"),
                max_attempts=int(payload.get("maxAttempts", 1)),
            )
        )
        return 202, result.to_dict()

    def _handle_get_s02_planning_run_status(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        status_view = self._dependencies.workflow_orchestrator_service.get_planning_run_status(
            workflow_instance_id=_optional_query_value(query, "workflowInstanceId"),
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
        )
        if status_view is None:
            raise ApiGatewayTransportError(
                404,
                "planning_run_status_not_found",
                "No planning-run workflow status matched the supplied query context.",
            )
        return 200, status_view.to_dict()

    def _handle_get_s03_resource_detail(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_s03_resource_detail_contract(
            planning_engine_service=self._dependencies.planning_engine_service,
            decision_support_service=self._dependencies.decision_support_service,
            planning_run_id=_optional_query_value(query, "planningRunId"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            resource_id=_optional_query_value(query, "resourceId"),
            resource_external_id=_optional_query_value(query, "resourceExternalId"),
            origin_screen_id=_optional_query_value(query, "originScreenId") or "S01",
            is_loading=_query_bool(query, "isLoading", False),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_get_s03_recommendation_context(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        recommendation_context = self._dependencies.decision_support_service.get_resource_recommendation_context(
            resource_external_id=_require_query_value(query, "resourceExternalId"),
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
        )
        if recommendation_context is None:
            raise ApiGatewayTransportError(
                404,
                "recommendation_context_not_found",
                "No recommendation context matched the supplied resource and planning context.",
            )
        return 200, recommendation_context.to_dict()

    def _handle_post_s03_recommendation_refresh(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        execution_result = self._dependencies.planning_engine_service.get_execution_result(
            planning_run_id=_require_body_value(payload, "planningRunId")
        )
        if execution_result is None:
            raise ApiGatewayTransportError(
                404,
                "planning_run_not_found",
                "A saved planning run is required before recommendation refresh.",
            )
        context = self._dependencies.decision_support_service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id=_require_body_value(payload, "resourceExternalId"),
        )
        return 200, context.to_dict()

    def _handle_get_s04_delta_review(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_s04_delta_review_contract(
            review_approval_service=self._dependencies.review_approval_service,
            workflow_orchestrator_service=self._dependencies.workflow_orchestrator_service,
            decision_support_service=self._dependencies.decision_support_service,
            review_context_id=_optional_query_value(query, "reviewContextId"),
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            origin_screen_id=_optional_query_value(query, "originScreenId"),
            origin_scope_type=_optional_query_value(query, "originScopeType"),
            origin_scope_id=_optional_query_value(query, "originScopeId"),
            origin_scope_external_id=_optional_query_value(query, "originScopeExternalId"),
            origin_scope_label=_optional_query_value(query, "originScopeLabel"),
            focused_delta_id=_optional_query_value(query, "focusedDeltaId"),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_post_s04_review_context(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        planning_run_id = _require_body_value(payload, "planningRunId")
        execution_result = self._dependencies.planning_engine_service.get_execution_result(
            planning_run_id=planning_run_id
        )
        if execution_result is None:
            raise ApiGatewayTransportError(
                404,
                "planning_run_not_found",
                "A saved planning run is required before generating the S04 review context.",
            )

        approved_plan_id = payload.get("approvedPlanId")
        approved_plan_snapshot = (
            self._dependencies.review_approval_service.get_approved_operating_plan_snapshot(
                approved_plan_id=approved_plan_id,
                current=approved_plan_id is None,
            )
        )
        if approved_plan_snapshot is None:
            if approved_plan_id is None:
                raise ApiGatewayTransportError(
                    404,
                    "current_approved_plan_not_found",
                    "A current approved operating plan is required before generating the S04 review context.",
                )
            raise ApiGatewayTransportError(
                404,
                "approved_plan_not_found",
                "No approved operating plan matched approvedPlanId %s." % approved_plan_id,
            )

        review_context = (
            self._dependencies.review_approval_service.generate_reviewable_delta_set(
                execution_result=execution_result,
                approved_plan_snapshot=approved_plan_snapshot,
            )
        )
        return 200, review_context.to_dict()

    def _handle_post_s04_acceptance_selection(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        result = submit_s04_delta_acceptance_selection(
            review_approval_service=self._dependencies.review_approval_service,
            review_context_id=_require_body_value(payload, "reviewContextId"),
            delta_id=_require_body_value(payload, "deltaId"),
            selected=_require_body_bool(payload, "selected"),
        )
        return 200, result

    def _handle_get_m01_connected_change_set(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_m01_connected_change_set_contract(
            review_approval_service=self._dependencies.review_approval_service,
            review_context_id=_require_query_value(query, "reviewContextId"),
            requested_delta_id=_require_query_value(query, "requestedDeltaId"),
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )

    def _handle_post_m01_connected_change_set_acceptance_selection(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        result = submit_m01_connected_set_acceptance_selection(
            review_approval_service=self._dependencies.review_approval_service,
            review_context_id=_require_body_value(payload, "reviewContextId"),
            requested_delta_id=_require_body_value(payload, "requestedDeltaId"),
            selected=_require_body_bool(payload, "selected"),
        )
        return 200, result

    def _handle_post_s04_activation(
        self,
        _query: Dict[str, List[str]],
        body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        payload = _require_json_body(body)
        result = submit_s04_activation_command(
            review_approval_service=self._dependencies.review_approval_service,
            review_context_id=_require_body_value(payload, "reviewContextId"),
            requested_by=_require_body_value(payload, "requestedBy"),
            requested_at=_require_body_value(payload, "requestedAt"),
            workflow_orchestrator_service=self._dependencies.workflow_orchestrator_service,
        )
        return 200, result

    def _handle_get_s04_activation_status(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        review_context_id = _optional_query_value(query, "reviewContextId")
        planning_context_key = _optional_query_value(query, "planningContextKey")
        if review_context_id is not None:
            contract = build_s04_delta_review_contract(
                review_approval_service=self._dependencies.review_approval_service,
                workflow_orchestrator_service=self._dependencies.workflow_orchestrator_service,
                decision_support_service=self._dependencies.decision_support_service,
                review_context_id=review_context_id,
                planning_context_key=planning_context_key,
            )
            return 200, {
                "reviewContextId": review_context_id,
                "activation": contract["activation"],
            }

        activation_id = _optional_query_value(query, "activationId")
        if activation_id is None:
            raise ApiGatewayTransportError(
                400,
                "missing_required_param",
                "reviewContextId or activationId is required for activation-status queries.",
            )
        activation_state = self._dependencies.review_approval_service.get_activation_state(
            activation_id=activation_id
        )
        if activation_state is None:
            raise ApiGatewayTransportError(
                404,
                "activation_state_not_found",
                "No activation state matched activationId %s." % activation_id,
            )
        workflow_status = self._dependencies.workflow_orchestrator_service.get_activation_workflow_status(
            activation_id=activation_id
        )
        return 200, {
            "activationState": activation_state.to_dict(),
            "downstreamWorkflowStatus": None
            if workflow_status is None
            else workflow_status.to_dict(),
        }

    def _handle_get_s05_warnings_workspace(
        self,
        query: Dict[str, List[str]],
        _body: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        return 200, build_s05_warnings_workspace_contract(
            decision_support_service=self._dependencies.decision_support_service,
            planning_context_key=_optional_query_value(query, "planningContextKey"),
            source_snapshot_id=_optional_query_value(query, "sourceSnapshotId"),
            origin_screen_id=_optional_query_value(query, "originScreenId"),
            origin_scope_type=_optional_query_value(query, "originScopeType"),
            origin_scope_id=_optional_query_value(query, "originScopeId"),
            origin_scope_external_id=_optional_query_value(query, "originScopeExternalId"),
            origin_scope_label=_optional_query_value(query, "originScopeLabel"),
            workflow_filter_ids=query.get("workflowFilterId"),
            classification_filters=query.get("classificationFilter"),
            signal_type_filters=query.get("signalTypeFilter"),
            is_loading=_query_bool(query, "isLoading", False),
            is_refreshing=_query_bool(query, "isRefreshing", False),
        )


def build_default_dependencies() -> ApiGatewayBffDependencies:
    integration_service = IntegrationService()
    planning_engine_service = PlanningEngineService()
    decision_support_service = DecisionSupportService()
    review_approval_service = ReviewApprovalService()
    workflow_orchestrator_service = WorkflowOrchestratorService(
        integration_service=integration_service,
        planning_engine_gateway=PlanningEngineWorkflowGateway(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
        ),
        import_sync_execution_gateway=IntegrationBackedImportSyncExecutionGateway(
            integration_service=integration_service
        ),
        activation_execution_gateway=IntegrationBackedActivationExecutionGateway(
            integration_service=integration_service
        ),
    )
    return ApiGatewayBffDependencies(
        integration_service=integration_service,
        planning_engine_service=planning_engine_service,
        review_approval_service=review_approval_service,
        decision_support_service=decision_support_service,
        workflow_orchestrator_service=workflow_orchestrator_service,
    )


def build_default_application() -> ApiGatewayBffApplication:
    return ApiGatewayBffApplication(build_default_dependencies())


def build_test_environ(
    method: str,
    path: str,
    query_string: str = "",
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body_bytes = b""
    if body is not None:
        body_bytes = json.dumps(body, sort_keys=True).encode("utf-8")
    return {
        "REQUEST_METHOD": method.upper(),
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": str(len(body_bytes)),
        "CONTENT_TYPE": "application/json" if body is not None else "",
        "wsgi.input": BytesIO(body_bytes),
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "wsgi.url_scheme": "http",
        "wsgi.version": (1, 0),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }


def _read_json_body(body_stream, content_length: Optional[str]) -> Optional[Dict[str, Any]]:
    if body_stream is None:
        return None
    length = int(content_length or "0")
    if length <= 0:
        return None
    payload = body_stream.read(length)
    if not payload:
        return None
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ApiGatewayTransportError(
            400,
            "invalid_json_body",
            "Request body must be valid JSON: %s" % str(error),
        )
    if not isinstance(loaded, dict):
        raise ApiGatewayTransportError(
            400,
            "invalid_json_body",
            "Request body must be a JSON object.",
        )
    return loaded


def _optional_query_value(query: Dict[str, List[str]], key: str) -> Optional[str]:
    values = query.get(key)
    if not values:
        return None
    return values[-1]


def _require_query_value(query: Dict[str, List[str]], key: str) -> str:
    value = _optional_query_value(query, key)
    if value is None or value == "":
        raise ApiGatewayTransportError(
            400,
            "missing_required_param",
            "%s is required." % key,
        )
    return value


def _query_bool(query: Dict[str, List[str]], key: str, default: bool) -> bool:
    value = _optional_query_value(query, key)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ApiGatewayTransportError(
        400,
        "invalid_boolean_param",
        "%s must be a boolean-compatible query parameter." % key,
    )


def _require_json_body(body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if body is None:
        raise ApiGatewayTransportError(
            400,
            "missing_json_body",
            "A JSON request body is required.",
        )
    return body


def _require_body_value(body: Dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise ApiGatewayTransportError(
            400,
            "missing_required_field",
            "%s is required." % key,
        )
    return value


def _require_body_bool(body: Dict[str, Any], key: str) -> bool:
    value = body.get(key)
    if not isinstance(value, bool):
        raise ApiGatewayTransportError(
            400,
            "invalid_boolean_field",
            "%s must be a boolean field." % key,
        )
    return value


def _require_body_object(body: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = body.get(key)
    if not isinstance(value, dict) or not value:
        raise ApiGatewayTransportError(
            400,
            "invalid_object_field",
            "%s must be a non-empty object field." % key,
        )
    return value


def _http_status_text(status_code: int) -> str:
    return {
        200: "OK",
        202: "Accepted",
        400: "Bad Request",
        404: "Not Found",
        409: "Conflict",
        500: "Internal Server Error",
    }.get(status_code, "OK")
