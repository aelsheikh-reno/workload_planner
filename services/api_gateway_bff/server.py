"""Run the minimal API Gateway / BFF HTTP server."""

import argparse
from wsgiref.simple_server import make_server

from .local_runtime import build_local_demo_runtime
from .transport import build_default_application


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the API Gateway / BFF server.")
    parser.add_argument(
        "--runtime",
        choices=("local-demo", "empty"),
        default="local-demo",
        help="Choose the seeded local-demo runtime or an empty in-memory runtime.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    runtime = None
    if args.runtime == "local-demo":
        runtime = build_local_demo_runtime()
        app = runtime.build_application()
    else:
        app = build_default_application()

    with make_server(args.host, args.port, app) as server:
        print("API Gateway / BFF listening on http://%s:%d" % (args.host, args.port))
        if runtime is not None:
            runtime.workflow_auto_progressor.start()
            print("Local demo seed loaded:")
            print("  planning_context_key=%s" % runtime.seed_state.planning_context_key)
            print("  source_snapshot_id=%s" % runtime.seed_state.source_snapshot_id)
            print("  planning_run_id=%s" % runtime.seed_state.planning_run_id)
            print("  review_context_id=%s" % runtime.seed_state.review_context_id)
            print("  resource_external_id=%s" % runtime.seed_state.resource_external_id)
        try:
            server.serve_forever()
        finally:
            if runtime is not None:
                runtime.workflow_auto_progressor.stop()


if __name__ == "__main__":
    main()
