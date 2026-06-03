"""Offline tests for the Job Posting Analyzer (tool 005).

No network and no model calls: requests.get is monkeypatched to return fixture
responses, and sc.analyze is never invoked. Verifies job extraction + digest
building from Ashby, and the Greenhouse fallback when Ashby returns no jobs.

Run:  .venv/bin/python tests/test_job_postings.py   (exit 0 = all pass)
"""
import sys
import importlib.util
from pathlib import Path

# Make the suite root importable and load the tool module by path.
SUITE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE_ROOT))

import signalyser_core as sc  # noqa: E402  (ensures core imports cleanly)

_spec = importlib.util.spec_from_file_location(
    "job_postings_analyse",
    SUITE_ROOT / "tools" / "job_postings" / "analyse.py",
)
analyse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyse)


failures = []

def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


# ── Fake HTTP plumbing ────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_fake_get(route_map):
    """Return a requests.get replacement that matches by URL substring.

    route_map: list of (substring, FakeResponse). First match wins.
    """
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        for needle, resp in route_map:
            if needle in url:
                return resp
        return FakeResponse(404, {})

    fake_get.calls = calls
    return fake_get


# ── Fixtures ──────────────────────────────────────────────────────────────────

ASHBY_PAYLOAD = {
    "jobs": [
        {
            "title": "Senior Backend Engineer",
            "department": {"name": "Engineering"},
            "location": {"name": "Remote - US"},
            "descriptionHtml": "<p>Build scalable <b>Kubernetes</b> services.</p>"
                               "<li>Experience with Go and PostgreSQL</li>",
        },
        {
            "title": "Product Marketing Manager",
            "department": "Marketing",          # plain-string department variant
            "location": "New York",             # plain-string location variant
            "description": "Own positioning and messaging for the platform.",
        },
    ]
}

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "title": "Data Scientist",
            "departments": [{"name": "Data"}],
            "offices": [{"name": "San Francisco"}],
            "content": "<p>Work with Snowflake and dbt to model usage data.</p>",
        }
    ]
}


# ── Test (a): Ashby JSON -> jobs extracted + digest built ──────────────────────

orig_get = analyse.requests.get
try:
    analyse.requests.get = make_fake_get([
        ("api.ashbyhq.com", FakeResponse(200, ASHBY_PAYLOAD)),
    ])

    jobs, source = analyse.fetch_jobs("acme")
    check("ashby: source is Ashby", source == "Ashby")
    check("ashby: two jobs extracted", len(jobs) == 2)

    j0 = jobs[0]
    check("ashby: title extracted", j0["title"] == "Senior Backend Engineer")
    check("ashby: dict department extracted", j0["department"] == "Engineering")
    check("ashby: dict location extracted", j0["location"] == "Remote - US")
    check("ashby: html stripped from description",
          "<p>" not in j0["description"] and "Kubernetes" in j0["description"])

    j1 = jobs[1]
    check("ashby: string department handled", j1["department"] == "Marketing")
    check("ashby: string location handled", j1["location"] == "New York")

    digest = analyse.build_digest("acme", jobs, source)
    check("digest: company present", "Company: acme" in digest)
    check("digest: total roles present", "Total open roles: 2" in digest)
    check("digest: titles present",
          "Senior Backend Engineer" in digest and "Product Marketing Manager" in digest)
    check("digest: department present", "Department: Engineering" in digest)
    check("digest: description snippet present", "Kubernetes" in digest)
finally:
    analyse.requests.get = orig_get


# ── Test (b): Ashby empty -> Greenhouse fallback used ──────────────────────────

orig_get = analyse.requests.get
try:
    fake = make_fake_get([
        ("api.ashbyhq.com", FakeResponse(200, {"jobs": []})),       # Ashby empty
        ("boards-api.greenhouse.io", FakeResponse(200, GREENHOUSE_PAYLOAD)),
    ])
    analyse.requests.get = fake

    jobs, source = analyse.fetch_jobs("acme")
    check("fallback: source is Greenhouse", source == "Greenhouse")
    check("fallback: one job extracted", len(jobs) == 1)
    check("fallback: title extracted", jobs[0]["title"] == "Data Scientist")
    check("fallback: department from departments[]", jobs[0]["department"] == "Data")
    check("fallback: office from offices[]", jobs[0]["location"] == "San Francisco")
    check("fallback: html stripped", "<p>" not in jobs[0]["description"]
          and "Snowflake" in jobs[0]["description"])
    check("fallback: ashby was tried first",
          any("api.ashbyhq.com" in u for u in fake.calls)
          and any("boards-api.greenhouse.io" in u for u in fake.calls))
finally:
    analyse.requests.get = orig_get


# ── Test (c): neither source has jobs -> empty result, source 'none' ───────────

orig_get = analyse.requests.get
try:
    analyse.requests.get = make_fake_get([
        ("api.ashbyhq.com", FakeResponse(200, {"jobs": []})),
        ("boards-api.greenhouse.io", FakeResponse(404, {})),
    ])
    jobs, source = analyse.fetch_jobs("nope")
    check("missing: no jobs", jobs == [])
    check("missing: source none", source == "none")
finally:
    analyse.requests.get = orig_get


print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
