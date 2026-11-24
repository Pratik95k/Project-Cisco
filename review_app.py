"""
NetSage AI - Human Review Layer
A Streamlit app where a human reviewer goes through each AI diagnosis,
compares it to the ground truth, and marks it Accepted / Edited / Rejected.
Review decisions are saved to reviews.json.
"""

import json
import os
import streamlit as st

st.set_page_config(page_title="NetSage AI - Human Review", layout="wide")

CASES_PATH = "cases.json"
RESULTS_PATH = "results.json"
REVIEWS_PATH = "reviews.json"


@st.cache_data
def load_data():
    with open(CASES_PATH) as f:
        cases = json.load(f)
    with open(RESULTS_PATH) as f:
        results = json.load(f)
    cases_by_id = {c["case_id"]: c for c in cases}
    results_by_id = {r["case_id"]: r for r in results}
    return cases, cases_by_id, results_by_id


def load_reviews():
    if os.path.exists(REVIEWS_PATH):
        with open(REVIEWS_PATH) as f:
            return json.load(f)
    return {}


def save_review(case_id: str, status: str, note: str, reviews: dict):
    reviews[case_id] = {"status": status, "note": note}
    with open(REVIEWS_PATH, "w") as f:
        json.dump(reviews, f, indent=2)


cases, cases_by_id, results_by_id = load_data()
reviews = load_reviews()

st.title("NetSage AI — Human Review")
st.caption("Review each AI diagnosis against the known-correct answer, then Accept / Edit / Reject.")

# --- Sidebar: case list with review status ---
st.sidebar.header("Cases")
case_ids = list(cases_by_id.keys())

status_icons = {"accepted": "✅", "edited": "✏️", "rejected": "❌"}
options = [f"{status_icons.get(reviews.get(cid, {}).get('status'), '⬜')} {cid}" for cid in case_ids]
selected_display = st.sidebar.radio("Select a case", options, index=0)
selected_case_id = selected_display.split(" ", 1)[1]

reviewed_count = len(reviews)
st.sidebar.metric("Reviewed", f"{reviewed_count} / {len(case_ids)}")

# --- Main panel ---
case = cases_by_id[selected_case_id]
result = results_by_id.get(selected_case_id, {})

st.subheader(f"{selected_case_id} — {case['category']} ({case['difficulty']})")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### Case Details")
    st.markdown(f"**Symptom:** {case['symptom']}")
    st.markdown(f"**Topology:** {case['topology_notes']}")
    with st.expander("Command output"):
        st.json(case["command_outputs"])

    st.markdown("### Ground Truth")
    gt = case["ground_truth"]
    st.success(f"**Root cause:** {gt['root_cause']}")
    st.markdown(f"**OSI layer:** {gt['osi_layer']}")
    st.markdown("**Fix steps:**")
    for step in gt["fix_steps"]:
        st.markdown(f"- {step}")

with col2:
    st.markdown("### AI Diagnosis")
    if result.get("_parse_status") == "ok":
        st.info(f"**Root cause:** {result['root_cause']}")
        st.markdown(f"**OSI layer:** {result.get('osi_layer')}")
        st.markdown(f"**Confidence:** {result.get('confidence')}%")
        st.markdown(f"**Next command:** `{result.get('next_command')}`")
        st.markdown("**Evidence:**")
        for e in result.get("evidence", []):
            st.markdown(f"- {e}")
        st.markdown("**Fix steps:**")
        for step in result.get("fix_steps", []):
            st.markdown(f"- {step}")
    else:
        st.error(f"AI failed to produce a valid diagnosis: {result.get('_error')}")

st.divider()

# --- Review controls ---
st.markdown("### Your Review")
existing = reviews.get(selected_case_id, {})

review_note = st.text_area(
    "Notes (required if editing/rejecting — explain what the AI got wrong)",
    value=existing.get("note", ""),
    key=f"note_{selected_case_id}",
)

btn_col1, btn_col2, btn_col3 = st.columns(3)
with btn_col1:
    if st.button("✅ Accept", use_container_width=True):
        save_review(selected_case_id, "accepted", review_note, reviews)
        st.rerun()
with btn_col2:
    if st.button("✏️ Edited", use_container_width=True):
        save_review(selected_case_id, "edited", review_note, reviews)
        st.rerun()
with btn_col3:
    if st.button("❌ Reject", use_container_width=True):
        save_review(selected_case_id, "rejected", review_note, reviews)
        st.rerun()

if selected_case_id in reviews:
    st.caption(f"Current status: **{reviews[selected_case_id]['status']}**")
