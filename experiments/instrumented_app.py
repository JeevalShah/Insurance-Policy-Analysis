"""Run the existing Flask app with opt-in experimental timing hooks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from experiments.infrastructure import ExperimentRun, load_config
from experiments.instrumentation import install_instrumentation


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Experiment run config JSON")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--probe-services", action="store_true", help="Capture live service versions with read-only probes")
    args = parser.parse_args()

    backend = root / "backend"
    sys.path.insert(0, str(backend))
    config = load_config(root, args.config)
    run = ExperimentRun(root, config, probe_services=args.probe_services)
    try:
        import app as sentra_app

        install_instrumentation(sentra_app, run)
        print("Instrumented app run:", run.run_id)
        print("Results:", run.run_dir)
        print("Stop the server with Ctrl+C; results will be summarized on shutdown.")
        sentra_app.app.run(host=args.host, port=args.port, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        run.finish()
        try:
            if "sentra_app" in locals() and sentra_app.driver:
                sentra_app.driver.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
