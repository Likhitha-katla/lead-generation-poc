
import asyncio
import json
import os
from typing import Any, Dict, List

import pandas as pd
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

    df = pd.DataFrame(result.get("leads", [])[:50])

    st.subheader("Lead List")
    st.dataframe(df, use_container_width=True)


_init_state()

if st.session_state["stage"] == "input":
    _render_input_page()

elif st.session_state["stage"] == "review":
    _render_review_page()

elif st.session_state["stage"] == "result":
    _render_result_page()
