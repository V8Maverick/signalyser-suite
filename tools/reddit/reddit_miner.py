#!/usr/bin/env python3
"""
Reddit Signal Miner — fetches posts + comments from any subreddit, sends them
to either a LOCAL Ollama model (Qwen) or the CLOUD Anthropic API (Claude) for
PMM analysis, and saves a markdown report.

Usage: python3 reddit_miner.py <subreddit> [-n NUM] [-p local|cloud] [-m MODEL] [-u USERNAME]

The processor (-p) is sticky: once set it persists in .env for every run until
changed. -m selects the cloud model and is only needed for cloud.

Requires:
  1. Local: a running Ollama server with the target model pulled.
     Cloud: an ANTHROPIC_API_KEY (the tool offers to save a pasted key to .env).
  2. Your Reddit username set in a .env file next to this script (run
     ./setup.sh <username>). Reddit data is read from public RSS by default;
     no API credentials are needed. See .env.example.

Environment variables (loaded from .env):
    PROCESSOR             local | cloud (sticky; set via -p)
    CLOUD_MODEL           opus-4.8 | sonnet-4.6 | haiku-4.5 (sticky; set via -m)
    ANTHROPIC_API_KEY     required for cloud processing
    OLLAMA_HOST           default http://localhost:11434
    OLLAMA_MODEL          default qwen3.6:35b-a3b
    OLLAMA_FALLBACK_MODEL default qwen3.5:9b (used if the primary can't run)
    REDDIT_USERNAME      REQUIRED — your Reddit handle; used in the User-Agent
    REDDIT_CLIENT_ID     optional — switches to the authenticated Reddit API
    REDDIT_CLIENT_SECRET optional — secret for the authenticated API
    REDDIT_PASSWORD      optional — with the username, enables a password grant
"""

import sys
import os
import re
import argparse
import time
import json
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────

ENV_FILE = Path(__file__).resolve().parent / ".env"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6:35b-a3b")
# If the primary model can't run (e.g. not enough memory), fall back to this one.
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen3.5:9b")

# Cloud processing (Anthropic). Selectable models, keyed by the friendly name
# the user passes to -m, mapped to the canonical API model ID.
CLOUD_MODELS = {
    "opus-4.8": "claude-opus-4-8",
    "sonnet-4.6": "claude-sonnet-4-6",
    "haiku-4.5": "claude-haiku-4-5",
}
# Display labels for the status line, in the exact casing we print.
CLOUD_MODEL_LABELS = {
    "opus-4.8": "Opus-4.8",
    "sonnet-4.6": "Sonnet-4.6",
    "haiku-4.5": "Haiku-4.5",
}
CLOUD_MAX_TOKENS = 8192

# Reddit requires a unique, descriptive User-Agent that names the account
# making the requests. The username is REQUIRED and has no default — each user
# must set REDDIT_USERNAME in .env (run ./setup.sh). Values below are rejected.
USER_AGENT_TEMPLATE = "redalyser:gtm-signal-miner:v1.0 (by /u/{username})"
USERNAME_PLACEHOLDERS = {
    "", "your_username", "your-reddit-username", "reddit_username",
    "username", "changeme", "unknown",
}
REDDIT_OAUTH = "https://oauth.reddit.com"
REDDIT_PUBLIC = "https://www.reddit.com"
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

ATOM = "{http://www.w3.org/2005/Atom}"

POSTS_TO_FETCH = 25        # minimum posts pulled from subreddit listing
POSTS_TO_ANALYZE = 15      # default top N posts sent to the model (override with -n)
COMMENTS_PER_POST = 8      # top comments per post
REQUEST_DELAY = 0.5        # seconds between Reddit API calls (be polite)


# ── Settings persistence ──────────────────────────────────────────────────────

def set_env_var(key: str, value: str) -> None:
    """Create or update KEY=value in the project .env file (sticky settings)."""
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value  # reflect immediately for this run


def prompt_for_api_key() -> str | None:
    """Ask the user to paste an Anthropic API key. Returns None if they decline."""
    if not sys.stdin.isatty():
        return None
    try:
        entered = input(
            "\nNo ANTHROPIC_API_KEY found. Paste your Anthropic API key "
            "(sk-ant-...), or press Enter to use Local processing instead: "
        ).strip()
    except EOFError:
        return None
    return entered or None

# ── Reddit authentication ─────────────────────────────────────────────────────

def require_username() -> str:
    """Return the configured Reddit username, or exit if it hasn't been set.

    RedAlyser refuses to run until the user provides their own Reddit username,
    so requests are never sent under someone else's handle. Tolerates a leading
    'u/' or '/u/' and rejects known placeholder values.
    """
    raw = (os.getenv("REDDIT_USERNAME") or "").strip().lstrip("/")
    if raw.lower().startswith("u/"):
        raw = raw[2:].strip()
    if raw.lower() in USERNAME_PLACEHOLDERS:
        print(
            "Error: no Reddit username set — RedAlyser won't run without one.\n\n"
            "Your Reddit username identifies your requests in the User-Agent\n"
            "(Reddit asks for this, and it keeps requests under YOUR name).\n\n"
            "Set it one of two ways:\n"
            "  1. Run the setup script:  ./setup.sh <your_reddit_username>\n"
            f"  2. Or edit {ENV_FILE} and set:  REDDIT_USERNAME=your_reddit_username\n"
        )
        sys.exit(1)
    return raw


def build_user_agent() -> str:
    """Build the Reddit User-Agent from the (required) configured username."""
    return USER_AGENT_TEMPLATE.format(username=require_username())


def make_reddit_session(user_agent: str) -> requests.Session:
    """Authenticate against the Reddit API and return a ready-to-use session.

    Uses the OAuth2 'password' grant when REDDIT_USERNAME/REDDIT_PASSWORD are
    set (script app, user context), otherwise falls back to the application-only
    'client_credentials' grant (read-only public data).
    """
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            f"Error: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not found in {ENV_FILE}.\n"
            "Create a free 'script' app at https://www.reddit.com/prefs/apps and "
            "copy the values into .env (see .env.example)."
        )
        sys.exit(1)

    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")

    if username and password:
        grant = {"grant_type": "password", "username": username, "password": password}
    else:
        grant = {"grant_type": "client_credentials"}

    resp = requests.post(
        REDDIT_TOKEN_URL,
        auth=HTTPBasicAuth(client_id, client_secret),
        data=grant,
        headers={"User-Agent": user_agent},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Reddit auth failed ({resp.status_code}): {resp.text[:300]}")
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        print(f"Reddit auth returned no access_token: {resp.text[:300]}")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"bearer {token}",
        "User-Agent": user_agent,
    })
    return session


# ── Reddit fetching ──────────────────────────────────────────────────────────

def fetch_subreddit_posts(session: requests.Session, subreddit: str, limit: int = 25) -> list[dict]:
    url = f"{REDDIT_OAUTH}/r/{subreddit}/hot?limit={limit}"
    resp = session.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [child["data"] for child in data["data"]["children"] if child["kind"] == "t3"]


def fetch_post_comments(session: requests.Session, subreddit: str, post_id: str, limit: int = 10) -> list[str]:
    url = f"{REDDIT_OAUTH}/r/{subreddit}/comments/{post_id}?limit={limit}&depth=1&sort=top"
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        comments = []
        for child in data[1]["data"]["children"]:
            if child["kind"] != "t1":
                continue
            body = child["data"].get("body", "").strip()
            if body and body not in ("[removed]", "[deleted]"):
                comments.append(body)
        return comments[:limit]
    except Exception:
        return []


def collect_data(session: requests.Session, subreddit: str, analyze: int = POSTS_TO_ANALYZE) -> list[dict]:
    """Fetch hot posts and their top comments for a subreddit (authenticated API)."""
    posts = fetch_subreddit_posts(session, subreddit, max(POSTS_TO_FETCH, analyze))
    enriched = []
    for post in posts[:analyze]:
        time.sleep(REQUEST_DELAY)
        comments = fetch_post_comments(session, subreddit, post["id"], COMMENTS_PER_POST)
        enriched.append({
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "comments": comments,
        })
    return enriched


# ── Reddit fetching (RSS fallback, no auth) ────────────────────────────────────
# Used when no Reddit API credentials are configured. Reddit's public Atom feeds
# remain reachable without OAuth, though they expose fewer posts/comments and no
# score metadata. Good enough to run the pipeline while awaiting API approval.

def _strip_html(text: str) -> str:
    """Convert Reddit's HTML feed content to plain text."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)   # SC_OFF/SC_ON markers
    text = re.sub(r"<[^>]+>", " ", text)                        # tags
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _rss_get(rss_user_agent: str, url: str) -> list[ET.Element]:
    resp = requests.get(url, headers={"User-Agent": rss_user_agent}, timeout=15)
    resp.raise_for_status()
    return ET.fromstring(resp.text).findall(f"{ATOM}entry")


def collect_data_rss(subreddit: str, user_agent: str, analyze: int = POSTS_TO_ANALYZE) -> list[dict]:
    """Fetch hot posts and their top comments via public RSS feeds (no auth)."""
    feed = f"{REDDIT_PUBLIC}/r/{subreddit}/hot.rss?limit={max(POSTS_TO_FETCH, analyze)}"
    entries = _rss_get(user_agent, feed)

    enriched = []
    for entry in entries[:analyze]:
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        link_el = entry.find(f"{ATOM}link")
        permalink = link_el.get("href") if link_el is not None else None
        selftext = _strip_html(entry.findtext(f"{ATOM}content") or "")

        comments: list[str] = []
        if permalink:
            time.sleep(REQUEST_DELAY)
            try:
                centries = _rss_get(user_agent, permalink.rstrip("/") + "/.rss")
                for c in centries:
                    body = _strip_html(c.findtext(f"{ATOM}content") or "")
                    if body:
                        comments.append(body)
                    if len(comments) >= COMMENTS_PER_POST:
                        break
            except Exception:
                pass

        enriched.append({
            "title": title,
            "selftext": selftext,
            "score": 0,
            "num_comments": 0,
            "comments": comments,
        })
    return enriched


# ── Content formatting ────────────────────────────────────────────────────────

def _clean(text: str, max_chars: int = 600) -> str:
    text = text.strip()
    if text in ("[removed]", "[deleted]", ""):
        return ""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def format_posts_for_prompt(subreddit: str, posts: list[dict]) -> str:
    lines = [f"# Reddit data from r/{subreddit}\n"]
    for i, post in enumerate(posts, 1):
        title = post["title"]
        body = _clean(post.get("selftext", ""), 500)
        lines.append(f"## Post {i} — {title}")
        if body:
            lines.append(f"**Body:** {body}")
        comments = [_clean(c, 300) for c in post.get("comments", []) if _clean(c)]
        if comments:
            lines.append("**Top comments:**")
            for c in comments:
                lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines)


# ── Ollama / Qwen analysis ────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior Product Marketing Manager (PMM). Your job is to extract \
actionable go-to-market signals from raw community data. Be specific, quote \
real language where possible, and avoid generic filler."""

def build_user_prompt(subreddit: str, reddit_data: str) -> str:
    return f"""\
Analyze the following Reddit posts and comments from r/{subreddit}.

Produce a signal report in **exactly** this markdown format (keep the headers verbatim):

## Reddit Signal Report: r/{subreddit}

### Top recurring complaints
List the most common pain points, frustrations, and problems — be specific.

### Top recurring praise
What users consistently love, appreciate, or recommend.

### Exact Reddit language
Verbatim phrases, slang, metaphors the community uses. These are copywriting gold.

### Questions nobody is answering well
Gaps where users are confused or not getting helpful answers.

### Emerging themes
Trends, new topics, or shifting concerns gaining traction in the community.

### PMM action items
Concrete, numbered recommendations for positioning, messaging, or product marketing.

---

{reddit_data}"""


class ModelUnavailable(Exception):
    """Raised when a model can't run (e.g. not enough memory, not pulled)."""


def _stream_chat(model: str, messages: list[dict]) -> str:
    """Stream one chat completion, printing tokens live. Returns the full text.

    Raises ModelUnavailable if the model fails to start (before producing any
    output) — the signal to try a fallback model. Other failures propagate.
    """
    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": model,
        "stream": True,
        "messages": messages,
        "options": {"temperature": 0.4, "num_ctx": 8192},
    }

    chunks: list[str] = []
    with requests.post(url, json=payload, stream=True, timeout=600) as resp:
        if resp.status_code != 200:
            try:
                reason = resp.json().get("error", resp.text[:200])
            except ValueError:
                reason = resp.text[:200]
            raise ModelUnavailable(reason)
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            event = json.loads(line)
            if "error" in event:
                # Error before any tokens → recoverable via fallback.
                if not chunks:
                    raise ModelUnavailable(event["error"])
                raise RuntimeError(f"{model} failed mid-stream: {event['error']}")
            text = event.get("message", {}).get("content", "")
            if text:
                print(text, end="", flush=True)
                chunks.append(text)
            if event.get("done"):
                break
    return "".join(chunks)


def analyze_with_ollama(subreddit: str, reddit_data: str) -> str:
    """Stream a PMM analysis, trying the primary model then the fallback."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(subreddit, reddit_data)},
    ]

    # Ordered, de-duplicated list of models to try.
    candidates: list[str] = [OLLAMA_MODEL]
    if OLLAMA_FALLBACK_MODEL and OLLAMA_FALLBACK_MODEL not in candidates:
        candidates.append(OLLAMA_FALLBACK_MODEL)

    last_error: Exception | None = None
    for i, model in enumerate(candidates):
        print(f"Analyzing with Ollama model '{model}'...\n")
        print("=" * 70)
        try:
            return _stream_chat(model, messages)
        except requests.ConnectionError:
            print(
                f"\nError: could not reach Ollama at {OLLAMA_HOST}. "
                "Is the Ollama server running? (`ollama serve`)"
            )
            sys.exit(1)
        except ModelUnavailable as e:
            last_error = e
            remaining = candidates[i + 1:]
            if remaining:
                print(
                    f"\n[!] '{model}' can't run: {e}\n"
                    f"    Falling back to '{remaining[0]}'...\n"
                )
            else:
                print(f"\n[!] '{model}' can't run: {e}")

    print("\nError: no usable Ollama model. Last error: " f"{last_error}")
    sys.exit(1)


def analyze_with_cloud(subreddit: str, reddit_data: str, model_key: str) -> str:
    """Stream a PMM analysis from the Anthropic API (cloud processing)."""
    try:
        import anthropic
    except ImportError:
        print(
            "\nError: the 'anthropic' package is required for cloud processing.\n"
            "Install it:  .venv/bin/python -m pip install -r requirements.txt"
        )
        sys.exit(1)

    model_id = CLOUD_MODELS[model_key]
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    print(f"Analyzing with Anthropic model '{model_id}'...\n")
    print("=" * 70)

    chunks: list[str] = []
    try:
        with client.messages.stream(
            model=model_id,
            max_tokens=CLOUD_MAX_TOKENS,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": build_user_prompt(subreddit, reddit_data)}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                chunks.append(text)
    except anthropic.AuthenticationError:
        print(
            "\nError: Anthropic rejected the API key (authentication failed).\n"
            "Check ANTHROPIC_API_KEY in .env, or switch back to local with -p local."
        )
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\nAnthropic API error: {e}")
        sys.exit(1)

    return "".join(chunks)


# ── Output ────────────────────────────────────────────────────────────────────

def save_report(subreddit: str, report: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reddit_signal_{subreddit}_{timestamp}.md"
    Path(filename).write_text(report, encoding="utf-8")
    return filename


# ── Processor selection ───────────────────────────────────────────────────────

def resolve_processing(args: argparse.Namespace) -> tuple[str, str | None]:
    """Decide local vs cloud (and which cloud model), honoring sticky .env state.

    `-p` persists the processor; `-m` persists the cloud model. With neither flag,
    the saved preference is reused. Returns (processor, model_key); model_key is
    None for local. Handles the no-model and no-API-key cases.
    """
    # Processor: an explicit -p flag is sticky; otherwise read the saved value.
    if args.processor:
        processor = args.processor
        set_env_var("PROCESSOR", processor)
    else:
        processor = (os.getenv("PROCESSOR") or "local").strip().lower()
        if processor not in ("local", "cloud"):
            processor = "local"

    if processor == "local":
        return "local", None

    # Cloud: resolve the model (sticky). -m is required when switching to cloud
    # unless a model was previously saved.
    if args.model:
        if args.model not in CLOUD_MODELS:
            print(f"Unknown model '{args.model}'. Choose: Opus-4.8 | Sonnet-4.6 | Haiku-4.5")
            sys.exit(1)
        model_key = args.model
        set_env_var("CLOUD_MODEL", model_key)
    else:
        model_key = (os.getenv("CLOUD_MODEL") or "").strip().lower()
        if model_key not in CLOUD_MODELS:
            print("Which model? Opus-4.8 | Sonnet-4.6 | Haiku-4.5?")
            sys.exit(1)

    # Cloud needs an API key. Offer to paste one (saved to .env), else fall back.
    if not os.getenv("ANTHROPIC_API_KEY"):
        key = prompt_for_api_key()
        if key:
            set_env_var("ANTHROPIC_API_KEY", key)
        else:
            print("No API key provided — falling back to Local processing.\n")
            return "local", None

    return "cloud", model_key


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Make streaming print() tolerate emoji/arrows the model emits (Windows cp1252
    # console otherwise crashes mid-stream with UnicodeEncodeError, losing the report).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    parser = argparse.ArgumentParser(
        description="Mine PMM signals from a subreddit using a local Ollama model."
    )
    parser.add_argument("subreddit", help="subreddit to analyze, e.g. devops")
    parser.add_argument(
        "-n", "--num", type=int, default=POSTS_TO_ANALYZE,
        metavar="NUM",
        help=f"number of top posts to analyze (default: {POSTS_TO_ANALYZE})",
    )
    parser.add_argument(
        "-p", "--processor", type=lambda s: s.lower(), choices=["local", "cloud"],
        metavar="LOCAL|CLOUD",
        help="processing backend: Local (Ollama) or Cloud (Anthropic). "
             "Sticky — once set it persists for every run until changed.",
    )
    parser.add_argument(
        "-m", "--model", type=lambda s: s.lower(),
        metavar="MODEL",
        help="cloud model (cloud only): Opus-4.8 | Sonnet-4.6 | Haiku-4.5",
    )
    parser.add_argument(
        "-u", "--user", metavar="USERNAME",
        help="Reddit username for THIS run only (overrides .env, not saved). "
             "Handy for quick testing.",
    )
    args = parser.parse_args()

    if args.num < 1:
        parser.error("-n/--num must be a positive integer")

    subreddit = args.subreddit.strip().lstrip("r/")
    num = args.num

    # Load credentials from the project .env file
    load_dotenv(ENV_FILE)

    # -u overrides the username for this run only (not written to .env).
    if args.user:
        os.environ["REDDIT_USERNAME"] = args.user

    # Require a Reddit username before doing anything (also builds the User-Agent).
    user_agent = build_user_agent()

    # Resolve the processing backend (sticky via .env) and, for cloud, the model.
    processor, model_key = resolve_processing(args)

    if processor == "cloud":
        print(f"Using Cloud Processing with model {CLOUD_MODEL_LABELS[model_key]}")
    else:
        print("Using Local Processing with model QWEN")

    print(f"\nMining signals from r/{subreddit} (top {num} posts)...\n")

    # 0 — Pick a data source: authenticated API if creds exist, else RSS fallback
    use_api = bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))

    try:
        if use_api:
            print("Authenticating with Reddit API...")
            session = make_reddit_session(user_agent)
            print(f"Fetching posts from r/{subreddit} (authenticated API)...")
            posts = collect_data(session, subreddit, num)
        else:
            print(
                "No Reddit API credentials found — using public RSS feeds "
                "(fewer posts/comments, no scores).\n"
                "Add REDDIT_CLIENT_ID/SECRET to .env for full API access.\n"
            )
            print(f"Fetching posts from r/{subreddit} (RSS)...")
            posts = collect_data_rss(subreddit, user_agent, num)
    except requests.HTTPError as e:
        print(f"Reddit fetch error: {e}")
        sys.exit(1)

    print(f"Fetched {len(posts)} posts with comments.\n")

    # 2 — Format for the model
    reddit_data = format_posts_for_prompt(subreddit, posts)

    # 3 — Analyze (cloud, or local Ollama with primary→fallback)
    if processor == "cloud":
        report = analyze_with_cloud(subreddit, reddit_data, model_key)
    else:
        report = analyze_with_ollama(subreddit, reddit_data)
    print("\n" + "=" * 70 + "\n")

    # 4 — Save
    filename = save_report(subreddit, report)
    print(f"Report saved: {filename}\n")


if __name__ == "__main__":
    main()
