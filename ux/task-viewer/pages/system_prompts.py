import json
from datetime import datetime
from typing import Any

import pandas as pd
import redis
import streamlit as st


PAGE_TITLE = "System Prompts"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
KEY_PATTERN = "system-prompts:*"


st.set_page_config(layout="wide")
st.title(PAGE_TITLE)


def _parse_json_value(value: Any):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        return value


def _parse_system_prompt_key(key: str):
    if not isinstance(key, str) or not key.startswith("system-prompts:"):
        return "", ""

    remainder = key[len("system-prompts:"):]
    parts = remainder.split(":", 1)
    if len(parts) != 2:
        return remainder, ""

    return parts[0], parts[1]


def _render_key_value_table(title, data):
    parsed = _parse_json_value(data)
    if not isinstance(parsed, dict) or not parsed:
        return

    rows = []
    for key, value in parsed.items():
        if isinstance(value, (dict, list)):
            rendered_value = json.dumps(value, ensure_ascii=False)
        else:
            rendered_value = value
        rows.append({"Field": key, "Value": rendered_value})

    st.subheader(title)
    st.table(rows)


def _remarks_to_editor_text(value: Any) -> str:
    parsed = _parse_json_value(value)
    if parsed is None:
        return ""
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    return str(parsed)


def _serialize_remarks_for_storage(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    try:
        parsed = json.loads(text)
    except Exception:
        return text

    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False)

    return text


def _save_system_prompt_annotations(key: str, feedback: str, remarks: str):
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    client.hset(
        key,
        mapping={
            "feedback": feedback,
            "remarks": _serialize_remarks_for_storage(remarks),
        },
    )
    _load_system_prompt_records.clear()


def _render_annotation_editor(key: str, feedback_value: Any, remarks_value: Any):
    with st.form(key=f"system_prompt_editor_{key}"):
        feedback_text = st.text_area(
            "Feedback",
            value=str(feedback_value or ""),
            height=140,
            placeholder="Write feedback here...",
        )
        remarks_text = st.text_area(
            "Remarks",
            value=_remarks_to_editor_text(remarks_value),
            height=180,
            placeholder='Write remarks here or paste JSON, for example {"created_by": "..."}',
        )
        save_clicked = st.form_submit_button("Save feedback / remarks")

        if save_clicked:
            _save_system_prompt_annotations(key, feedback_text, remarks_text)
            st.success("Saved feedback and remarks.")


@st.cache_data(ttl=30, show_spinner=False)
def _load_system_prompt_records():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    records = []

    for key in sorted(client.scan_iter(match=KEY_PATTERN)):
        prompt_data = client.hgetall(key) or {}
        metadata = _parse_json_value(prompt_data.get("metadata")) or {}
        remarks = _parse_json_value(prompt_data.get("remarks")) or {}
        key_persona, key_created_at = _parse_system_prompt_key(key)
        created_at = metadata.get("created_at", key_created_at) if isinstance(metadata, dict) else key_created_at
        persona = metadata.get("persona", key_persona) if isinstance(metadata, dict) else key_persona

        if not persona and isinstance(key, str) and key.startswith("system-prompts:"):
            key_parts = key.split(":", 2)
            if len(key_parts) >= 2:
                persona = key_parts[1]

        records.append(
            {
                "key": key,
                "persona": persona,
                "created_at": created_at,
                "prompt": prompt_data.get("prompt", ""),
                "feedback": prompt_data.get("feedback", ""),
                "remarks": remarks,
                "metadata": metadata,
                "created_by": remarks.get("created_by", "") if isinstance(remarks, dict) else "",
                "optimized_from": remarks.get("optimized_from", "") if isinstance(remarks, dict) else "",
            }
        )

    return records


records = _load_system_prompt_records()
if not records:
    st.warning(f"No Redis hashes found matching {KEY_PATTERN}")
    st.stop()

frame = pd.DataFrame(records)

if "created_at" in frame.columns:
    frame["created_at_sort"] = pd.to_datetime(frame["created_at"], errors="coerce", utc=True)
else:
    frame["created_at_sort"] = pd.NaT

params = st.query_params
direct_key = params.get("id") or params.get("key")
direct_persona = params.get("persona")
direct_created_at = params.get("created_at")

if direct_key:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    prompt_data = redis_client.hgetall(direct_key) or {}

    if not prompt_data:
        st.error("Key not found in Redis.")
        st.stop()

    direct_metadata = _parse_json_value(prompt_data.get("metadata")) or {}
    direct_remarks = _parse_json_value(prompt_data.get("remarks")) or {}
    key_persona, key_created_at = _parse_system_prompt_key(direct_key)
    prompt_persona = (
        direct_persona
        or (direct_metadata.get("persona", "") if isinstance(direct_metadata, dict) else "")
        or key_persona
    )
    prompt_created_at = (
        direct_created_at
        or (direct_metadata.get("created_at", "") if isinstance(direct_metadata, dict) else "")
        or key_created_at
    )

    st.info(f"Loading result for: {direct_key}")
    st.subheader("Task Info")
    st.text(direct_key)

    st.subheader("Result")
    st.markdown(prompt_data.get("prompt", "No content found."))

    info_cols = st.columns(3)
    info_cols[0].metric("Persona", prompt_persona or "-")
    info_cols[1].metric("Created At", prompt_created_at or "-")
    info_cols[2].metric("Feedback Present", "Yes" if str(prompt_data.get("feedback", "")).strip() else "No")

    _render_annotation_editor(direct_key, prompt_data.get("feedback", ""), direct_remarks)

    _render_key_value_table("Remarks", direct_remarks)
    _render_key_value_table("Metadata", direct_metadata)

    st.divider()

persona_options = ["All"] + sorted([p for p in frame["persona"].dropna().astype(str).unique().tolist() if p])
selected_persona = st.sidebar.selectbox("Persona", persona_options, index=0)
search_text = st.sidebar.text_input("Search", value="", placeholder="Search key, prompt, feedback, remarks...")
show_only_with_feedback = st.sidebar.checkbox("Only prompts with feedback", value=False)
show_only_with_remarks = st.sidebar.checkbox("Only prompts with remarks", value=False)

filtered = frame.copy()
if selected_persona != "All":
    filtered = filtered[filtered["persona"].astype(str) == selected_persona]

if search_text.strip():
    needle = search_text.strip().lower()

    def _matches(row):
        haystack_parts = [
            str(row.get("key", "")),
            str(row.get("persona", "")),
            str(row.get("created_at", "")),
            str(row.get("prompt", "")),
            str(row.get("feedback", "")),
            json.dumps(row.get("metadata", {}), ensure_ascii=False),
            json.dumps(row.get("remarks", {}), ensure_ascii=False),
        ]
        return needle in " ".join(haystack_parts).lower()

    filtered = filtered[filtered.apply(_matches, axis=1)]

if show_only_with_feedback:
    filtered = filtered[filtered["feedback"].astype(str).str.strip().ne("")]

if show_only_with_remarks:
    filtered = filtered[filtered["remarks"].apply(lambda value: bool(value) and value != {})]

filtered = filtered.sort_values(by="created_at_sort", ascending=False, na_position="last")

st.caption(f"Showing {len(filtered)} of {len(frame)} system prompt records")

view_columns = ["key", "persona", "created_at", "created_by", "optimized_from", "feedback", "prompt"]
scrollable_table = filtered[view_columns].copy()
scrollable_table["prompt"] = scrollable_table["prompt"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 220)
scrollable_table["feedback"] = scrollable_table["feedback"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 160)

st.dataframe(
    scrollable_table,
    use_container_width=True,
    hide_index=True,
    height=420,
)

if filtered.empty:
    st.info("No matching system prompts for the current filters.")
    st.stop()

selected_key = st.selectbox(
    "Inspect prompt details",
    filtered["key"].tolist(),
    index=0,
)

selected_row = filtered.loc[filtered["key"] == selected_key].iloc[0].to_dict()

st.subheader("Prompt Details")
meta_cols = st.columns(4)
meta_cols[0].metric("Persona", selected_row.get("persona") or "-")
meta_cols[1].metric("Created At", selected_row.get("created_at") or "-")
meta_cols[2].metric("Created By", selected_row.get("created_by") or "-")
meta_cols[3].metric("Optimized From", selected_row.get("optimized_from") or "-")

st.markdown("**Prompt**")
st.text_area(
    "prompt",
    value=str(selected_row.get("prompt", "")),
    height=220,
    disabled=True,
    label_visibility="collapsed",
)

_render_annotation_editor(selected_key, selected_row.get("feedback", ""), selected_row.get("remarks", {}))

json_cols = st.columns(2)
with json_cols[0]:
    st.markdown("**Remarks**")
    st.code(json.dumps(selected_row.get("remarks", {}), indent=2, ensure_ascii=False), language="json")
with json_cols[1]:
    st.markdown("**Metadata**")
    st.code(json.dumps(selected_row.get("metadata", {}), indent=2, ensure_ascii=False), language="json")
