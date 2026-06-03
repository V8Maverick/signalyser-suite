"""Shared CLI wiring so every tool gets identical -p/-m flags and status line."""
import argparse

from .processing import CLOUD_MODEL_LABELS


def add_processing_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared --processor / --model flags to a tool's parser."""
    parser.add_argument(
        "-p", "--processor", type=lambda s: s.lower(), choices=["local", "cloud"],
        metavar="LOCAL|CLOUD",
        help="processing backend: Local (Ollama) or Cloud (Anthropic). "
             "Sticky — persists in .env for every run until changed.",
    )
    parser.add_argument(
        "-m", "--model", type=lambda s: s.lower(), metavar="MODEL",
        help="cloud model (cloud only): Opus-4.8 | Sonnet-4.6 | Haiku-4.5",
    )


def print_backend(processor: str, model_key: str | None) -> None:
    """Print the standard 'Using ... Processing with model ...' status line."""
    if processor == "cloud":
        print(f"Using Cloud Processing with model {CLOUD_MODEL_LABELS[model_key]}")
    else:
        print("Using Local Processing with model QWEN")
