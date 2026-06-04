"""Public-RSS Reddit signal fetch (no auth) — reusable voice-of-customer source.

Mirrors the proven RedAlyser approach: pull a subreddit's hot posts and their top
comments from Reddit's public `.rss` feeds, formatted for an LLM prompt. Reddit
requires a descriptive User-Agent that names the account, so a username is required
(REDDIT_USERNAME in .env, or passed explicitly).
"""
from __future__ import annotations

import os
import re
import html
import time
import xml.etree.ElementTree as ET

import requests

ATOM = "{http://www.w3.org/2005/Atom}"
REDDIT_PUBLIC = "https://www.reddit.com"

DEFAULT_POSTS = 12
COMMENTS_PER_POST = 8
REQUEST_DELAY = 0.6   # be polite to the public feed


class RedditAuthError(Exception):
    """Raised when no Reddit username is configured (needed for the User-Agent)."""


def reddit_username() -> str | None:
    return (os.getenv("REDDIT_USERNAME") or "").strip() or None


def _user_agent(username: str) -> str:
    return f"signalyser-suite/0.2 (market intelligence) by /u/{username}"


def _strip_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _rss_get(user_agent: str, url: str) -> list[ET.Element]:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=15)
    resp.raise_for_status()
    return ET.fromstring(resp.text).findall(f"{ATOM}entry")


def collect(subreddit: str, user_agent: str, num: int = DEFAULT_POSTS) -> list[dict]:
    """Fetch hot posts + their top comments via public RSS (no auth)."""
    feed = f"{REDDIT_PUBLIC}/r/{subreddit}/hot.rss?limit={max(num, 10)}"
    entries = _rss_get(user_agent, feed)

    posts = []
    for entry in entries[:num]:
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        link_el = entry.find(f"{ATOM}link")
        permalink = link_el.get("href") if link_el is not None else None
        body = _strip_html(entry.findtext(f"{ATOM}content") or "")

        comments: list[str] = []
        if permalink:
            time.sleep(REQUEST_DELAY)
            try:
                for c in _rss_get(user_agent, permalink.rstrip("/") + "/.rss"):
                    text = _strip_html(c.findtext(f"{ATOM}content") or "")
                    if text:
                        comments.append(text)
                    if len(comments) >= COMMENTS_PER_POST:
                        break
            except Exception:
                pass
        posts.append({"title": title, "body": body, "comments": comments})
    return posts


def _clean(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if text in ("[removed]", "[deleted]", ""):
        return ""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def format_signal(subreddit: str, posts: list[dict]) -> str:
    lines = [f"# Reddit signal from r/{subreddit}\n"]
    for i, post in enumerate(posts, 1):
        lines.append(f"## Post {i} — {post['title']}")
        body = _clean(post.get("body", ""), 500)
        if body:
            lines.append(f"**Body:** {body}")
        comments = [_clean(c, 300) for c in post.get("comments", [])]
        comments = [c for c in comments if c]
        if comments:
            lines.append("**Top comments:**")
            lines.extend(f"- {c}" for c in comments)
        lines.append("")
    return "\n".join(lines)


def fetch_signal(subreddit: str, *, username: str | None = None,
                 num: int = DEFAULT_POSTS) -> str:
    """Return formatted hot-post + comment text for a subreddit. Raises on no username."""
    username = (username or reddit_username() or "").strip()
    if not username:
        raise RedditAuthError(
            "A Reddit username is required (sent in the request User-Agent). "
            "Set REDDIT_USERNAME in .env or the Settings tab."
        )
    posts = collect(subreddit, _user_agent(username), num)
    return format_signal(subreddit, posts)
