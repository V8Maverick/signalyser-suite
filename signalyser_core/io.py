"""Shared I/O: slugs, report saving, and the cross-tool inputs/ intel corpus."""
import re
from pathlib import Path
from datetime import datetime

SUITE_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = SUITE_ROOT / "inputs"
OUTPUTS_DIR = SUITE_ROOT / "outputs"

# Map a source-tool id to its intel-file suffix (the suite's shared naming).
SOURCE_IDS = {
    "youtube": "001",
    "g2": "002",
    "reddit": "003",
    "page": "004",
    "jobs": "005",
    "tenk": "006",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def save_report(name: str, text: str, outdir: Path | str = OUTPUTS_DIR) -> Path:
    """Save a timestamped markdown report; returns the path."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = outdir / f"{slugify(name)}_{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return path


def intel_path(company: str, source_id: str) -> Path:
    """Path for a company's intelligence file from a given source (e.g. '004')."""
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return INPUTS_DIR / f"{slugify(company)}-{source_id}.md"


def save_intel(company: str, source_id: str, text: str) -> Path:
    """Write a collector's output into the shared inputs/ corpus."""
    path = intel_path(company, source_id)
    path.write_text(text, encoding="utf-8")
    return path


def read_company_intel(company: str) -> dict[str, str]:
    """Return {filename: contents} for all inputs/{company}-*.md files."""
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(company)
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(INPUTS_DIR.glob(f"{slug}-*.md"))
    }
