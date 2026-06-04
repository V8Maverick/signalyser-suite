#!/usr/bin/env python3
"""
Opportunity Finder (011) — where a company's strategy meets live demand.

Cross-references everything the suite knows about a company (its positioning arc,
personas and collected intel) with raw voice-of-customer signal from a subreddit,
and asks the model: given THIS business model, what unmet needs / grumbles in this
community map to products, services or messaging the company could offer — with
concrete routes to market and the SEO keywords real people are using.

Example: photobox does keepsakes + photo books — are there grumbles on r/giftideas
that reveal a product or angle photobox could own?

Usage: python opportunities.py --company <name> --subreddit <sub> [-n N] [-p ...] [-m ...]

Reads the company's corpus (run the collectors + synthesis tools first). Saves a
timestamped report to outputs/ and inputs/<slug>-opportunities.md so it joins the
session corpus.
"""
# Self-heal: re-exec under the suite .venv so signalyser_core and third-party deps
# resolve no matter which Python / working dir launched this tool. See _bootstrap.py.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if __name__ == "__main__":
    import _bootstrap
    _bootstrap.ensure_venv(__file__)

import sys
import argparse

import requests

import signalyser_core as sc
from signalyser_core import reddit as reddit_signal


SYSTEM_PROMPT = """\
You are a growth-focused Product Marketing strategist with an SEO specialism. You \
are given (A) what a company sells and how it positions itself, and (B) raw \
voice-of-customer chatter from a subreddit. Your job is to find where the two meet: \
real, unmet needs or frustrations in the community that THIS company — given its \
actual business model and capabilities — could credibly act on.

Ground every point in the source material. Quote the community's own words. Do not \
invent demand that isn't evidenced in the Reddit signal, and do not propose things \
outside the company's plausible reach. Produce the report in this markdown shape \
(keep the headers verbatim):

# Opportunity Scan — {company} × r/{subreddit}

## TL;DR
2-3 sentences: the single biggest opportunity and why it fits this company.

## Opportunities
For each (3-5), a `### <short name>` then:
- **Signal:** the grumble/need, with a short verbatim quote.
- **Fit:** why this company specifically can serve it (tie to its positioning/products).
- **Offer:** a concrete product, service, bundle or feature to consider.
- **Route to market:** the channel/message/campaign angle to reach these people.

## SEO keywords & search phrases
A bullet list of 10-20 concrete phrases in the community's actual language that this
company could target in content/SEO — group loosely by intent (problem / solution /
comparison) where useful.

## Watch-outs
Anything in the signal that warns against a move, or where demand looks thin.
"""


def build_corpus_text(intel: dict[str, str]) -> str:
    """Concatenate the company's intel files, each labelled by source filename."""
    blocks = []
    for name, contents in intel.items():
        blocks.append(f"### Source: {name}\n\n{contents.strip()}")
    return "\n\n---\n\n".join(blocks)


def build_user_prompt(company: str, subreddit: str, corpus: str, signal: str) -> str:
    return (
        f"COMPANY: {company}\nSUBREDDIT: r/{subreddit}\n\n"
        f"=== A. WHAT THIS COMPANY SELLS & HOW IT POSITIONS (from the corpus) ===\n\n"
        f"{corpus}\n\n"
        f"=== B. LIVE COMMUNITY SIGNAL (subreddit voice-of-customer) ===\n\n"
        f"{signal}\n\n"
        f"Now produce the Opportunity Scan for {company}, grounded in both sections."
    )


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    parser = argparse.ArgumentParser(
        description="Find actionable opportunities + SEO keywords for a company from a subreddit."
    )
    parser.add_argument("--company", required=True, metavar="NAME",
                        help="company to analyse (must already have inputs/<company>-*.md)")
    parser.add_argument("-r", "--subreddit", required=True, metavar="SUB",
                        help="subreddit to scan for demand signal, e.g. giftideas")
    parser.add_argument("-n", "--num", type=int, default=reddit_signal.DEFAULT_POSTS,
                        metavar="N", help=f"hot posts to scan (default {reddit_signal.DEFAULT_POSTS})")
    sc.add_processing_args(parser)
    args = parser.parse_args()

    company = args.company.strip()
    subreddit = args.subreddit.strip().lstrip("r/").strip("/")

    sc.load_env()
    processor, model_key = sc.resolve_processing(args)
    sc.print_backend(processor, model_key)

    intel = sc.read_company_intel(company)
    if not intel:
        print(
            f"\nError: no corpus found for '{company}' in this session.\n"
            "Run the collectors + synthesis tools first so there is positioning to "
            "work from, e.g.:\n"
            f"  page decoder on the company site, then positioning_arc --company {company}\n"
        )
        sys.exit(1)

    print(f"\nScanning r/{subreddit} for opportunities for {company} ...\n")
    print("=" * 70)
    try:
        signal = reddit_signal.fetch_signal(subreddit, num=args.num)
    except reddit_signal.RedditAuthError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"\nReddit fetch error for r/{subreddit}: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\nCould not reach Reddit: {e}")
        sys.exit(1)

    if signal.count("## Post") == 0:
        print(f"\nNo posts found in r/{subreddit} — is the name right?")
        sys.exit(1)

    report = sc.analyze(
        SYSTEM_PROMPT,
        build_user_prompt(company, subreddit, build_corpus_text(intel), signal),
        processor=processor, model_key=model_key,
    )

    print("\n" + "=" * 70 + "\n")
    out = sc.save_report(f"{company}-opportunities-{subreddit}", report)
    intel_file = sc.inputs_dir() / f"{sc.slugify(company)}-opportunities.md"
    intel_file.write_text(report, encoding="utf-8")
    print(f"Report saved:  {out}")
    print(f"Corpus file:   {intel_file}")


if __name__ == "__main__":
    main()
