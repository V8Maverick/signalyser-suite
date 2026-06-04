"""Run the Signalyser web app:  python -m signalyser_web  [--host H] [--port P].

Opens http://localhost:8000 by default. Uses the same venv interpreter, which is
also what launches each tool subprocess, so the child processes inherit the
suite's installed signalyser_core.
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Signalyser suite web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload (dev)")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "uvicorn is not installed. Install the web extras:\n"
            "  .venv/Scripts/python.exe -m pip install -r requirements.txt"
        )

    uvicorn.run("signalyser_web.app:app", host=args.host, port=args.port,
                reload=args.reload)


if __name__ == "__main__":
    main()
