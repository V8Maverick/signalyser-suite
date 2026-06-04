#!/usr/bin/env python3
"""
Signalyser — one launcher for the whole suite.

Dispatches a friendly subcommand to the matching tool script, forwarding every
remaining argument unchanged. The tool runs in its own process using the same
Python interpreter that launched this (so it picks up the suite venv).

    python signalyser.py <command> [tool args...]

Examples:
    python signalyser.py page https://www.notion.com
    python signalyser.py jobs notion -p cloud -m sonnet-4.6
    python signalyser.py personas --company notion
    python signalyser.py assets --company notion

Run with no command (or `help`) to list the available tools.
"""

import sys
import subprocess
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent

# command -> (tool script relative to the suite root, one-line description)
COMMANDS: dict[str, tuple[str, str]] = {
    "reddit":   ("tools/reddit/reddit_miner.py", "003 Reddit signal -> PMM report (own interface)"),
    "page":     ("tools/page_decoder/decode.py", "004 Competitor page -> strategic briefing"),
    "jobs":     ("tools/job_postings/analyse.py", "005 Ashby/Greenhouse jobs -> hiring signals"),
    "tenk":     ("tools/tenk/analyse.py", "006 SEC 10-K -> competitive intel"),
    "youtube":  ("tools/youtube/summarize.py", "001 YouTube transcript -> B2B summary"),
    "personas": ("tools/personas/personas.py", "009 intel corpus -> buyer personas"),
    "arc":      ("tools/positioning_arc/arc.py", "008 intel corpus -> 3-horizon positioning arc"),
    "quadrant": ("tools/quadrant/quadrant.py", "007 intel corpus -> competitive quadrant chart"),
    "assets":   ("tools/assets/assets.py", "010 personas + positioning -> written assets"),
}


def print_help() -> None:
    print("Signalyser suite launcher\n")
    print("Usage: python signalyser.py <command> [tool args...]\n")
    print("Commands:")
    width = max(len(c) for c in COMMANDS)
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name.ljust(width)}  {desc}")
    print("\nEach command forwards its remaining args to the tool unchanged.")
    print("Run a command with -h for that tool's own options, e.g.:")
    print("  python signalyser.py jobs -h")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    command, *rest = argv
    entry = COMMANDS.get(command)
    if entry is None:
        print(f"Unknown command: {command!r}\n")
        print_help()
        return 2

    script = SUITE_ROOT / entry[0]
    if not script.exists():
        print(f"Error: tool script not found for {command!r}: {script}")
        return 1

    # Run the tool with the current interpreter (inherits the suite venv).
    return subprocess.run([sys.executable, str(script), *rest]).returncode


if __name__ == "__main__":
    # Self-heal: run the launcher (and thus every tool it spawns) under the suite
    # venv, so it works no matter which Python invoked `signalyser.py`.
    import _bootstrap
    _bootstrap.ensure_venv(__file__, root=str(SUITE_ROOT))
    raise SystemExit(main(sys.argv[1:]))
