import json
import os
import sys

import lead_verifier
from lead_verifier import verify_leads


def test_verify_single_lead():
    # This test invokes the real Gemini API. Ensure GEMINI_API_KEY is set.
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Set the environment variable to run this test.")
        raise SystemExit(2)

    # Load sample lead from apollo.json
    with open("apollo.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "leads" in data and len(data["leads"]) > 0
    lead = data["leads"][0]

    checked = verify_leads([lead], max_leads=1)

    assert len(checked) == 1
    verification = checked[0].get("verification")
    assert verification is not None
    assert isinstance(verification.get("qualified"), bool)
    assert isinstance(verification.get("score"), int)
    assert isinstance(verification.get("reasons"), list)
    assert isinstance(verification.get("source_urls"), list)


if __name__ == "__main__":
    # Run a live verification demo and print clear output to console
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Please set it to use the real Gemini API.")
        raise SystemExit(2)

    with open("apollo.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    if "leads" not in data or len(data["leads"]) == 0:
        print("No leads found in apollo.json")
        raise SystemExit(1)

    leads = data["leads"]

    print(f"Running live lead verification demo on {len(leads)} leads from apollo.json...\n")

    checked = verify_leads(leads, max_leads=len(leads))

    qualified_count = 0
    for item in checked:
        name = item.get("name") or item.get("company") or "<unknown>"
        verification = item.get("verification", {})
        q = verification.get('qualified')
        if q:
            qualified_count += 1

        print("------------------------------------------------------------")
        print(f"Company: {name}")
        print(f"  Qualified: {verification.get('qualified')}")
        print(f"  Score: {verification.get('score')}")
        reasons = verification.get('reasons') or []
        print(f"  Reasons: {', '.join(reasons) if reasons else '-' }")
        sources = verification.get('source_urls') or []
        print(f"  Source URLs: {', '.join(sources) if sources else '-' }\n")

    print("------------------------------------------------------------")
    print(f"Processed: {len(checked)} leads — Qualified: {qualified_count}")
    print("Demo complete.")
