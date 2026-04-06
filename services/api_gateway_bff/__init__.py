"""API Gateway / BFF adapters for screen-facing contracts."""

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

__all__ = [
    "build_d01_task_drilldown_contract",
    "build_s01_portfolio_contract",
    "build_s02_setup_contract",
    "build_s03_resource_detail_contract",
    "build_m01_connected_change_set_contract",
    "build_s04_delta_review_contract",
    "build_s05_warnings_workspace_contract",
    "submit_m01_connected_set_acceptance_selection",
    "submit_s04_activation_command",
    "submit_s04_delta_acceptance_selection",
]
