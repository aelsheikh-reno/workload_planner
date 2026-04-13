"""Run the API Gateway / BFF HTTP server."""

import argparse
from wsgiref.simple_server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the resource scheduling server.")
    parser.add_argument(
        "--runtime",
        choices=("float", "local-demo", "empty"),
        default="float",
        help="Runtime: float (default, SQLite-backed), local-demo (fixtures), empty.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.runtime == "float":
        from .float_runtime import build_float_runtime
        runtime, app = build_float_runtime()
        print("Resource Scheduling Server (SQLite-backed)")
        print("  DB: float_planner.db")
        print("  API: http://%s:%d" % (args.host, args.port))
    elif args.runtime == "local-demo":
        from .local_runtime import build_local_demo_runtime
        runtime = build_local_demo_runtime()
        app = runtime.build_application()
        print("API Gateway / BFF — local-demo runtime")
    else:
        from .transport import build_default_application
        runtime = None
        app = build_default_application()

    with make_server(args.host, args.port, app) as server:
        print("Listening on http://%s:%d" % (args.host, args.port))
        if runtime is not None:
            progressor = getattr(runtime, "workflow_auto_progressor", None)
            if progressor is not None:
                progressor.start()
        try:
            server.serve_forever()
        finally:
            if runtime is not None:
                progressor = getattr(runtime, "workflow_auto_progressor", None)
                if progressor is not None:
                    progressor.stop()


if __name__ == "__main__":
    main()
