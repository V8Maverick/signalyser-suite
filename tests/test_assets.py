#!/usr/bin/env python3
"""
Offline test for the Written Asset Generator (010).

Never calls the real model. Monkeypatches sc.read_company_intel to return a fake
personas + positioning-arc corpus, and sc.analyze to return canned output keyed
by which system prompt it was handed (plan / generate / reflect / revise). This
exercises the full pipeline — plan, generate, the reflection loop, and a
score-below-threshold revision — and asserts the asset files + content plan are
written to outputs/<slug>/.

Run: <venv-python> tests/test_assets.py   (exit 0 = PASS)
"""

import sys
import shutil
from pathlib import Path

# Make the suite root importable (signalyser_core + tools/).
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "assets"))

import signalyser_core as sc
import assets


COMPANY = "ZetaTest"
SLUG = sc.slugify(COMPANY)

FAKE_INTEL = {
    f"{SLUG}-personas.md": (
        "PERSONA NAME: Senior DevOps Engineer\n"
        "WHY THEY BUY: CI/CD reliability\n"
        "EXACT LANGUAGE THEY USE: \"flaky pipelines are killing us\"\n"
    ),
    f"{SLUG}-positioning-arc.md": (
        "HORIZON 1: the reliable deploy platform for platform engineers.\n"
    ),
    # An unrelated collector file that must NOT be mistaken for the two required ones.
    f"{SLUG}-004.md": "Competitor page copy.",
}

PLANNED_ASSETS = (
    '[{"persona": "Senior DevOps Engineer", "asset_type": "one-pager", '
    '"why": "trigger is flaky pipelines"}, '
    '{"persona": "Senior DevOps Engineer", "asset_type": "cold email", '
    '"why": "reach them in inbox"}]'
)


def main() -> None:
    captured = {"prompts": []}
    # Reflect is called once per asset (more if it revises). Return a passing
    # score first, then a failing one (forces a revision), then a passing one.
    reflect_scores = iter([
        '{"traceable": 9, "objection": 8, "cta": 9}',   # asset 1 -> passes
        '{"traceable": 4, "objection": 8, "cta": 9}',   # asset 2 -> revise
        '{"traceable": 9, "objection": 9, "cta": 9}',   # asset 2 after revise
    ])

    def fake_read_company_intel(name):
        captured["company"] = name
        return FAKE_INTEL

    def fake_analyze(system_prompt, user_prompt, *, processor, model_key, **kwargs):
        captured["prompts"].append((system_prompt, user_prompt))
        if system_prompt == assets.PLAN_SYSTEM:
            return PLANNED_ASSETS
        if system_prompt == assets.GENERATE_SYSTEM:
            return "# One-Pager\n\nFix your flaky pipelines.\n"
        if system_prompt == assets.REFLECT_SYSTEM:
            # Tolerate a code fence to also exercise parse_json's fence stripping.
            return "```json\n" + next(reflect_scores) + "\n```"
        if system_prompt == assets.REVISE_SYSTEM:
            captured["revised"] = True
            return "# One-Pager (revised)\n\nFix your flaky pipelines, traced to source.\n"
        raise AssertionError("analyze called with an unexpected system prompt")

    # Patch on both the core and the imported-into-assets references.
    sc.read_company_intel = fake_read_company_intel
    sc.analyze = fake_analyze
    assets.sc.read_company_intel = fake_read_company_intel
    assets.sc.analyze = fake_analyze

    # Avoid touching .env / network during resolve_processing.
    assets.sc.load_env = lambda: None
    assets.sc.resolve_processing = lambda args: ("local", None)
    assets.sc.print_backend = lambda processor, model_key: None

    out_dir = sc.OUTPUTS_DIR / SLUG
    pre_existing_dir = out_dir.exists()

    sys.argv = ["assets.py", "--company", COMPANY]

    failures = []
    try:
        # ── 0. load_sources requires BOTH files; missing one => exit 1 ──────────
        try:
            assets.load_sources("nonexistent-co")
            failures.append("load_sources did not exit when intel was missing")
        except SystemExit as e:
            if e.code != 1:
                failures.append(f"missing-intel exit code was {e.code}, expected 1")

        # ── 1. Full run ─────────────────────────────────────────────────────────
        assets.main()

        # The corpus reader saw the real company name.
        if captured.get("company") != COMPANY:
            failures.append(
                f"read_company_intel called with {captured.get('company')!r}, expected {COMPANY!r}"
            )

        # Plan prompt carried both required sources (and their exact language).
        plan_prompts = [u for s, u in captured["prompts"] if s == assets.PLAN_SYSTEM]
        if not plan_prompts:
            failures.append("no PLAN step was sent to analyze")
        else:
            up = plan_prompts[0]
            if "flaky pipelines are killing us" not in up:
                failures.append("plan prompt missing persona source language")
            if "HORIZON 1" not in up:
                failures.append("plan prompt missing positioning-arc source")

        # The low-scoring asset triggered a revision.
        if not captured.get("revised"):
            failures.append("a below-threshold reflect score did not trigger a revision")

        # ── 2. Output files ─────────────────────────────────────────────────────
        if not out_dir.exists():
            failures.append(f"output dir not created: {out_dir}")
        else:
            # Two planned assets + one content plan should all be written.
            plan_file = out_dir / f"{SLUG}-content-plan.md"
            if not plan_file.exists():
                failures.append("content-plan.md not written")
            else:
                pc = plan_file.read_text(encoding="utf-8")
                if "| Persona |" not in pc:
                    failures.append("content plan missing the scores table")
                if "Senior DevOps Engineer" not in pc:
                    failures.append("content plan missing the persona row")

            one_pager = out_dir / f"{SLUG}-senior-devops-engineer-one-pager.md"
            if not one_pager.exists():
                failures.append(f"expected asset file missing: {one_pager.name}")
            else:
                body = one_pager.read_text(encoding="utf-8")
                if not body.startswith("---"):
                    failures.append("asset file missing YAML frontmatter")
                for key in ("persona:", "asset_type:", "scores:", "traceable:"):
                    if key not in body:
                        failures.append(f"asset frontmatter missing {key!r}")

            # The cold-email asset (the one revised) should hold the revised text.
            email = out_dir / f"{SLUG}-senior-devops-engineer-cold-email.md"
            if email.exists() and "revised" not in email.read_text(encoding="utf-8"):
                failures.append("revised asset did not contain the revised content")
    finally:
        # Clean up only what this test created; never touch a pre-existing dir.
        if out_dir.exists() and not pre_existing_dir:
            shutil.rmtree(out_dir, ignore_errors=True)

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS  assets: plan -> generate -> reflect -> revise -> write")


if __name__ == "__main__":
    main()
