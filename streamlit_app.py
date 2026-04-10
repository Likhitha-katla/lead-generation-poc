
import asyncio
import json
import os
from typing import Any, Dict, List

import pandas as pd
from pathlib import Path
import streamlit as st

from icp_to_apollo_service import ICPToApolloService
from organization_fetch import ApolloOrganisationLeadService
from lead_verifier import verify_leads


st.set_page_config(page_title="ICP to Apollo Leads", layout="wide")


def _load_hexa_defaults() -> Dict[str, str]:
    defaults = {
        "segment_brief_description": "",
        "geography": "",
        "company_size": "",
        "annual_revenue": "",
        "essential_tools": "",
    }

    try:
        with open("hexa.json", "r", encoding="utf-8") as file:
            data = json.load(file)

        selected = data.get("selected_icp", {})
        company_profile = selected.get("company_profile", {})
        profile = data.get("profile", {})

        defaults["segment_brief_description"] = selected.get("segment_brief", "") or ""
        defaults["geography"] = "India"
        defaults["company_size"] = company_profile.get("company_size") or ""
        defaults["annual_revenue"] = company_profile.get("annual_revenue") or ""

        key_capabilities = profile.get("key_capabilities", [])
        tools = [
            item.get("title")
            for item in key_capabilities
            if isinstance(item, dict) and item.get("title")
        ]

        defaults["essential_tools"] = ", ".join(tools)

    except Exception:
        pass

    return defaults


HEX_DEFAULTS = _load_hexa_defaults()
DEFAULT_APOLLO_KEY = os.getenv("APOLLO_API_KEY", "").strip()
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def _init_state():
    defaults = {
        "stage": "input",
        "generated_filters": None,
        "apollo_key": DEFAULT_APOLLO_KEY,
        "gemini_key": DEFAULT_GEMINI_KEY,
        "lead_result": None,
        "edit_mode": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _parse_list(text: str) -> List[str]:
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


def _render_input_page():
    st.title("ICP to Apollo Lead Finder")

    segment = st.text_area(
        "Segment Brief Description",
        value=HEX_DEFAULTS.get("segment_brief_description", ""),
        height=180,
    )

    geography = st.text_input(
        "Geography",
        value=HEX_DEFAULTS.get("geography", ""),
    )

    company_size = st.text_input(
        "Company Size",
        value=HEX_DEFAULTS.get("company_size", ""),
    )

    annual_revenue = st.text_input(
        "Annual Revenue",
        value=HEX_DEFAULTS.get("annual_revenue", ""),
    )

    essential_tools = st.text_area(
        "Essential Tools",
        value=HEX_DEFAULTS.get("essential_tools", ""),
        height=100,
    )

    gemini_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=st.session_state.get("gemini_key", DEFAULT_GEMINI_KEY),
        help="Used for Apollo filter generation.",
        key="gemini_key_input_screen1",
    )
    st.session_state["gemini_key"] = gemini_key.strip()

    # If filters already exist (user returned from review), allow quick navigation
    if st.session_state.get("generated_filters"):
        if st.button("Next: Review Filters"):
            st.session_state["stage"] = "review"
            st.rerun()

    if st.button("Generate Apollo Filters"):
        gemini_key = st.session_state.get("gemini_key", "").strip()
        if not gemini_key:
            st.error("Gemini API key is required on this screen.")
            return

        tools = _parse_list(essential_tools)

        service = ICPToApolloService()

        with st.spinner("Generating Apollo filters..."):
            filters = asyncio.run(
                service.generate_apollo_filters(
                    segment_brief_description=segment,
                    company_size=company_size,
                    annual_revenue=annual_revenue,
                    geography=geography,
                    essential_tools=tools,
                    gemini_api_key=gemini_key,
                )
            )

        st.session_state["generated_filters"] = filters
        st.session_state["stage"] = "review"
        st.rerun()


def _render_review_page():
    st.title("Apollo Filters Review")

    filters = st.session_state["generated_filters"]
    action_col_1, action_col_2 = st.columns([1, 1])
    with action_col_1:
        if st.button("Back to Input"):
            st.session_state["stage"] = "input"
            st.session_state["edit_mode"] = False
            st.rerun()
    with action_col_2:
        if st.button("Edit Filters" if not st.session_state["edit_mode"] else "Cancel Edit"):
            st.session_state["edit_mode"] = not st.session_state["edit_mode"]
            st.rerun()

    col_key_1, col_key_2 = st.columns(2)
    with col_key_1:
        gemini_key = st.text_input(
            "Gemini API Key",
            type="password",
            value=st.session_state.get("gemini_key", DEFAULT_GEMINI_KEY),
            help="Used for lead verification.",
            key="gemini_key_input_review",
        )
        st.session_state["gemini_key"] = gemini_key.strip()
    with col_key_2:
        apollo_key = st.text_input(
            "Apollo API Key",
            type="password",
            value=st.session_state.get("apollo_key", DEFAULT_APOLLO_KEY),
            help="Used when fetching leads from Apollo.",
            key="apollo_key_input_review",
        )
        st.session_state["apollo_key"] = apollo_key.strip()

    if not st.session_state["edit_mode"]:
        col_1, col_2 = st.columns(2)
        with col_1:
            st.markdown("**Industries**")
            st.info(", ".join(filters.get("organization_industries", [])) or "-")
            st.markdown("**Employee Ranges**")
            st.info(", ".join(filters.get("organization_num_employees_ranges", [])) or "-")
            st.markdown("**Locations**")
            st.info(", ".join(filters.get("organization_locations", [])) or "-")
        with col_2:
            st.markdown("**Revenue Min**")
            st.info(str(filters.get("revenue_min", 0)))
            st.markdown("**Revenue Max**")
            st.info(str(filters.get("revenue_max", 0)))
            st.markdown("**Keywords**")
            st.info(filters.get("q_keywords", "") or "-")
    else:
        industries = st.text_area(
            "Industries",
            value=", ".join(filters.get("organization_industries", [])),
        )

        employees = st.text_area(
            "Employee Ranges",
            value=", ".join(filters.get("organization_num_employees_ranges", [])),
        )

        locations = st.text_area(
            "Locations",
            value=", ".join(filters.get("organization_locations", [])),
        )

        revenue_min = st.number_input(
            "Revenue Min",
            value=int(filters.get("revenue_min", 0)),
        )

        revenue_max = st.number_input(
            "Revenue Max",
            value=int(filters.get("revenue_max", 0)),
        )

        keywords = st.text_area(
            "Keywords",
            value=filters.get("q_keywords", ""),
        )

        if st.button("Save Filter Changes"):
            filters["organization_industries"] = _parse_list(industries)
            filters["organization_num_employees_ranges"] = _parse_list(employees)
            filters["organization_locations"] = _parse_list(locations)
            filters["revenue_min"] = revenue_min
            filters["revenue_max"] = revenue_max
            filters["q_keywords"] = keywords
            st.session_state["generated_filters"] = filters
            st.session_state["edit_mode"] = False
            st.rerun()

    if st.button("Fetch Leads"):
        apollo_key = st.session_state.get("apollo_key", "").strip()
        if not apollo_key:
            st.error("Apollo API key is required on this screen.")
            return

        payload = dict(filters)
        payload["apollo_key"] = apollo_key

        with st.spinner("Fetching leads from Apollo..."):
            service = ApolloOrganisationLeadService(
                apollo_api_key=apollo_key
            )

            result = service.fetch_organisation_leads(payload)

        st.session_state["lead_result"] = result
        st.session_state["stage"] = "result"
        st.rerun()


def _render_result_page():
    st.title("Qualified Leads")

    result = st.session_state["lead_result"]
    gemini_key = st.session_state.get("gemini_key", "").strip()

    # Run verification for top leads (Gemini + Google Search) to provide final verdicts
    try:
        leads = result.get("leads", [])
        if leads:
            if not gemini_key:
                st.warning("Gemini API key is missing, so lead verification was skipped.")
            else:
                with st.spinner("Verifying leads against ICP (web search)..."):
                    verified = verify_leads(leads, max_leads=20, gemini_api_key=gemini_key)
                    result["leads"] = verified
                    st.session_state["lead_result"] = result
    except Exception:
        # If verification fails, continue to display the raw results
        pass

    summary_col_1, summary_col_2, summary_col_3, summary_col_4 = st.columns(4)
    summary_col_1.metric("Total", result.get("total_fetched", 0))
    summary_col_2.metric("Qualified", result.get("qualified", 0))
    summary_col_3.metric("Rejected", result.get("rejected", 0))
    summary_col_4.metric("Deleted", result.get("deleted", 0))

    def _join_nonempty(values: List[str], sep: str = "; ") -> str:
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        return sep.join(cleaned) if cleaned else "-"

    def _format_contacts(contacts: List[Dict[str, Any]]) -> str:
        items = []
        for contact in contacts or []:
            if not isinstance(contact, dict):
                continue
            name = str(contact.get("name", "")).strip()
            title = str(contact.get("title", "")).strip()
            linkedin_url = str(contact.get("linkedin_url", "")).strip()
            reason = str(contact.get("reason", "")).strip()

            parts = []
            if name:
                parts.append(name)
            if title:
                parts.append(title)
            if linkedin_url:
                parts.append(linkedin_url)
            if reason:
                parts.append(reason)

            if parts:
                items.append(" | ".join(parts))

        return _join_nonempty(items)

    def _stringify(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    def _flatten(prefix: str, value: Any, out: Dict[str, Any]) -> None:
        if isinstance(value, dict):
            if not value:
                out[prefix] = "-"
                return
            for key, nested in value.items():
                _flatten(f"{prefix} {key}".strip(), nested, out)
            return
        if isinstance(value, list):
            out[prefix] = _stringify(value)
            return
        out[prefix] = _stringify(value)

    display_rows = []
    for lead in result.get("leads", [])[:50]:
        verification = lead.get("verification") or {}
        icp = verification.get("icp_match") or {}

        matched = "Yes" if icp.get("matched") else "No"
        score = icp.get("score") if isinstance(icp.get("score"), (int, float)) else "-"
        reasons = icp.get("reasons") or []
        top_reasons = _join_nonempty([str(r) for r in reasons[:3]])

        contacts_str = _format_contacts(verification.get("contacts") or [])
        pain_str = _join_nonempty([str(p) for p in (verification.get("pain_points") or [])])
        sources_str = _join_nonempty([str(u) for u in (verification.get("source_urls") or [])], sep=", ")

        row: Dict[str, Any] = {}

        # Apollo data: include the full lead payload except verification.
        for key, value in lead.items():
            if key == "verification":
                continue
            _flatten(f"Apollo {key}", value, row)

        # AI data: include the full verification payload in a readable form.
        _flatten("AI icp_match matched", icp.get("matched"), row)
        _flatten("AI icp_match score", icp.get("score"), row)
        _flatten("AI icp_match reasons", icp.get("reasons"), row)
        _flatten("AI icp_match source_urls", icp.get("source_urls"), row)
        _flatten("AI contacts", verification.get("contacts") or [], row)
        _flatten("AI pain_points", verification.get("pain_points") or [], row)
        _flatten("AI source_urls", verification.get("source_urls") or [], row)
        _flatten("AI raw", verification.get("raw"), row)

        # Convenience fields at the front of the table.
        row = {
            "Apollo Name": lead.get("name") or lead.get("company") or "-",
            "Apollo Website": lead.get("website_url") or lead.get("validated_domain") or "-",
            "Apollo LinkedIn": lead.get("linkedin_url") or "-",
            "AI ICP Match": matched,
            "AI Score": score,
            "AI Reasons": top_reasons,
            "AI Contacts": contacts_str,
            "AI Pain Points": pain_str,
            "AI Sources": sources_str,
            **row,
        }

        display_rows.append(row)

    df = pd.DataFrame(display_rows)

    st.subheader("Lead List (Apollo + AI)")
    st.dataframe(df, use_container_width=True)

    # Save human-friendly JSON to workspace and provide download
    try:
        json_str = json.dumps(display_rows, indent=2)
        save_path = Path("verified_leads_human.json")
        with save_path.open("w", encoding="utf-8") as wf:
            wf.write(json_str)
    except Exception:
        save_path = None

    col_download, _ = st.columns([1, 3])
    with col_download:
        if save_path:
            st.download_button("Download JSON", data=json_str, file_name=save_path.name, mime="application/json")
            st.success(f"Saved {save_path}")
        else:
            st.warning("Could not save JSON to disk; you can still download via the button if available.")


_init_state()

if st.session_state["stage"] == "input":
    _render_input_page()

elif st.session_state["stage"] == "review":
    _render_review_page()

elif st.session_state["stage"] == "result":
    _render_result_page()
