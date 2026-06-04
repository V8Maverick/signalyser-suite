"""Tool registry: the single source of truth the web layer renders forms from
and builds subprocess argv from. Mirrors each tool's real argparse interface.
"""
from __future__ import annotations

from dataclasses import dataclass

from signalyser_core.io import SUITE_ROOT


@dataclass(frozen=True)
class ToolField:
    """One tool-specific input (the -p/-m backend selectors are handled globally)."""
    name: str                 # form field name
    label: str
    kind: str                 # "positional" | "option"
    flag: str | None = None   # for options, e.g. "-n" or "--company"
    type: str = "text"        # "text" | "url" | "number"
    required: bool = False
    placeholder: str = ""
    help: str = ""
    default: str = ""


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    script: str               # path relative to SUITE_ROOT
    category: str             # "collector" | "synthesis" | "generation"
    source_id: str | None     # intel suffix written to inputs/, if any
    blurb: str
    fields: tuple[ToolField, ...] = ()
    needs_reddit_username: bool = False

    @property
    def script_path(self):
        return SUITE_ROOT / self.script


# Ordered so the UI groups collect -> synthesize -> generate, matching the pipeline.
TOOLS: dict[str, Tool] = {
    "page": Tool(
        key="page", label="Competitor Page Decoder", script="tools/page_decoder/decode.py",
        category="collector", source_id="004",
        blurb="Decode a competitor's web page into a PMM positioning briefing.",
        fields=(ToolField("url", "Competitor page URL", "positional", type="url",
                          required=True, placeholder="https://www.notion.com"),),
    ),
    "jobs": Tool(
        key="jobs", label="Job Posting Analyzer", script="tools/job_postings/analyse.py",
        category="collector", source_id="005",
        blurb="Read a company's open roles (Ashby/Greenhouse) for hiring signals.",
        fields=(ToolField("slug", "Company job-board slug or URL", "positional",
                          required=True, placeholder="notion"),),
    ),
    "tenk": Tool(
        key="tenk", label="10-K / Earnings Analyzer", script="tools/tenk/analyse.py",
        category="collector", source_id="006",
        blurb="Analyse a company's latest SEC 10-K/20-F for competitive signals.",
        fields=(ToolField("ticker", "Stock ticker", "positional",
                          required=True, placeholder="CRM"),),
    ),
    "youtube": Tool(
        key="youtube", label="YouTube Summarizer", script="tools/youtube/summarize.py",
        category="collector", source_id="001",
        blurb="Summarize a YouTube video's transcript for B2B marketers.",
        fields=(ToolField("url", "YouTube URL", "positional", type="url",
                          required=True, placeholder="https://youtu.be/<id>"),),
    ),
    "reddit": Tool(
        key="reddit", label="Reddit Signal (RedAlyser)", script="tools/reddit/reddit_miner.py",
        category="collector", source_id="003",
        blurb="Mine a subreddit's hot posts + comments into a PMM signal report.",
        fields=(
            ToolField("subreddit", "Subreddit", "positional",
                      required=True, placeholder="devops"),
            ToolField("num", "Posts to analyze", "option", flag="-n", type="number",
                      default="15", help="Number of top posts (default 15)."),
            ToolField("user", "Reddit username (this run only)", "option", flag="-u",
                      help="Overrides the saved REDDIT_USERNAME for this run; not saved."),
        ),
        needs_reddit_username=True,
    ),
    "personas": Tool(
        key="personas", label="Persona Generator", script="tools/personas/personas.py",
        category="synthesis", source_id=None,
        blurb="Synthesize evidence-based buyer personas from a company's intel corpus.",
        fields=(ToolField("company", "Company", "option", flag="--company",
                          required=True, placeholder="notion",
                          help="Must already have inputs/<company>-*.md from collectors."),),
    ),
    "arc": Tool(
        key="arc", label="Positioning Arc", script="tools/positioning_arc/arc.py",
        category="synthesis", source_id=None,
        blurb="Build a three-horizon company positioning arc from the corpus.",
        fields=(ToolField("company", "Company", "option", flag="--company",
                          required=True, placeholder="notion"),),
    ),
    "quadrant": Tool(
        key="quadrant", label="Competitive Quadrant", script="tools/quadrant/quadrant.py",
        category="synthesis", source_id=None,
        blurb="Plot a data-driven competitive quadrant (needs >=2 companies in the corpus).",
        fields=(),  # defaults to the suite inputs/ folder
    ),
    "assets": Tool(
        key="assets", label="Written Asset Generator", script="tools/assets/assets.py",
        category="generation", source_id=None,
        blurb="Generate persona-targeted written assets with a reflection loop.",
        fields=(ToolField("company", "Company", "option", flag="--company",
                          required=True, placeholder="notion",
                          help="Needs inputs/<company>-personas.md and -positioning-arc.md."),),
    ),
    "opportunities": Tool(
        key="opportunities", label="Opportunity Finder", script="tools/opportunities/opportunities.py",
        category="generation", source_id=None,
        blurb="Cross-reference a company's positioning with subreddit demand for "
              "actionable opportunities + SEO keywords.",
        fields=(
            ToolField("company", "Company", "option", flag="--company",
                      required=True, placeholder="photobox",
                      help="Must already have positioning/personas in the corpus."),
            ToolField("subreddit", "Subreddit", "option", flag="--subreddit",
                      required=True, placeholder="giftideas"),
            ToolField("num", "Posts to scan", "option", flag="-n", type="number",
                      default="12", help="Hot posts to read (default 12)."),
        ),
        needs_reddit_username=True,
    ),
}

CATEGORY_LABELS = {
    "collector": "Collect",
    "synthesis": "Synthesize",
    "generation": "Generate",
}


def build_argv(tool: Tool, form: dict[str, str], processor: str,
               model: str | None) -> tuple[list[str], list[str]]:
    """Translate submitted form values into tool arguments.

    Returns (args, errors). `args` is the list of CLI tokens for the tool (NOT
    including the python executable or script path). `errors` lists missing
    required fields — callers must refuse to launch if it is non-empty.
    """
    args: list[str] = []
    errors: list[str] = []

    for f in tool.fields:
        raw = (form.get(f.name) or "").strip()
        if not raw:
            if f.required:
                errors.append(f"{f.label} is required.")
            elif f.default and f.kind == "option":
                raw = f.default
            else:
                continue
        if f.kind == "positional":
            args.append(raw)
        elif f.flag:  # option (flag is always set for options)
            args.extend([f.flag, raw])

    # Universal sticky backend selectors.
    args.extend(["-p", processor])
    if processor == "cloud" and model:
        args.extend(["-m", model])

    return args, errors
