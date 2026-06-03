#!/usr/bin/env python3
"""
Offline test for the Persona Generator (009).

Never calls the real model: monkeypatches sc.read_company_intel to return a small
fake intel dict and sc.analyze to return a canned string. Asserts the user prompt
sent to analyze includes the fake intel, and that the report is written to both
outputs/ and inputs/<slug>-personas.md.

Run: <venv-python> tests/test_personas.py   (exit 0 = PASS)
"""

import sys
from pathlib import Path

# Make the suite root importable (signalyser_core + tools/).
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(SUITE_ROOT / "tools" / "personas"))

import signalyser_core as sc
import personas


FAKE_INTEL = {
    "acme-004.md": "Competitor page: ACME helps platform engineers ship faster.",
    "acme-005.md": "Job posting: hiring a Senior DevOps Engineer to own CI/CD reliability.",
}
CANNED_REPORT = "PERSONA NAME: Senior DevOps Engineer\nEVIDENCE BASE: acme-005.md\n"


def main() -> None:
    company = "ACME"
    captured = {}

    # ── Stub the model + the corpus reader (NEVER hit the real backend) ────────
    def fake_read_company_intel(name):
        captured["company"] = name
        return FAKE_INTEL

    def fake_analyze(system_prompt, user_prompt, *, processor, model_key, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return CANNED_REPORT

    # Patch on both the core and the imported-into-personas references.
    sc.read_company_intel = fake_read_company_intel
    sc.analyze = fake_analyze
    personas.sc.read_company_intel = fake_read_company_intel
    personas.sc.analyze = fake_analyze

    # Avoid touching .env / network during resolve_processing.
    personas.sc.load_env = lambda: None
    personas.sc.resolve_processing = lambda args: ("local", None)
    personas.sc.print_backend = lambda processor, model_key: None

    slug = sc.slugify(company)
    inputs_file = sc.INPUTS_DIR / f"{slug}-personas.md"
    pre_existing = inputs_file.exists()
    pre_content = inputs_file.read_text(encoding="utf-8") if pre_existing else None

    # Snapshot outputs/ so we can find the new report and clean it up.
    sc.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    before = set(sc.OUTPUTS_DIR.glob(f"{slug}-personas_*.md"))

    sys.argv = ["personas.py", "--company", company]

    failures = []
    new_reports = set()
    try:
        personas.main()

        # 1. The corpus reader was called with the company name.
        if captured.get("company") != company:
            failures.append(
                f"read_company_intel called with {captured.get('company')!r}, expected {company!r}"
            )

        # 2. The user prompt includes every fake intel file's content + filename.
        up = captured.get("user_prompt", "")
        for name, contents in FAKE_INTEL.items():
            if name not in up:
                failures.append(f"user prompt missing intel filename {name!r}")
            if contents not in up:
                failures.append(f"user prompt missing intel contents from {name!r}")

        # 3. System prompt is the evidence-based persona prompt.
        if "buyer personas" not in captured.get("system_prompt", "").lower():
            failures.append("system prompt does not look like the persona prompt")

        # 4. The report was written to inputs/<slug>-personas.md.
        if not inputs_file.exists():
            failures.append(f"inputs file not written: {inputs_file}")
        elif inputs_file.read_text(encoding="utf-8") != CANNED_REPORT:
            failures.append("inputs file content does not match the canned report")

        # 5. A timestamped report was written to outputs/.
        new_reports = set(sc.OUTPUTS_DIR.glob(f"{slug}-personas_*.md")) - before
        if not new_reports:
            failures.append("no timestamped report written to outputs/")
        elif not any(p.read_text(encoding="utf-8") == CANNED_REPORT for p in new_reports):
            failures.append("outputs report content does not match the canned report")
    finally:
        # Clean up artefacts this test created (do not pollute the corpus).
        for p in new_reports:
            p.unlink(missing_ok=True)
        if pre_existing:
            inputs_file.write_text(pre_content, encoding="utf-8")
        else:
            inputs_file.unlink(missing_ok=True)

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS")


if __name__ == "__main__":
    main()
