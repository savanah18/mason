import streamlit as st
import redis
import json
import pandas as pd


REDIS_HOST = "localhost"
REDIS_PORT = 6379
WORKFLOW_KEY_PATTERN = "workflow:dev:*:*"


st.set_page_config(layout="wide")
st.title("Workflow")


def _parse_possible_json(value):
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


def _render_key_value_table(title, data):
    parsed = _parse_possible_json(data)
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


def _parse_workflow_key(key: str):
    if not isinstance(key, str):
        return "", ""
    parts = key.split(":", 3)
    if len(parts) != 4:
        return "", ""
    return parts[2], parts[3]


@st.cache_data(ttl=30, show_spinner=False)
def _load_workflow_records():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    rows = []

    for key in sorted(client.scan_iter(match=WORKFLOW_KEY_PATTERN)):
        data = client.hgetall(key) or {}
        persona, workflow_id = _parse_workflow_key(key)
        metadata = _parse_possible_json(data.get("metadata")) or {}
        created_at = metadata.get("created_at", "") if isinstance(metadata, dict) else ""
        task = data.get("task", "")
        result = data.get("result", "")

        rows.append(
            {
                "key": key,
                "persona": persona,
                "workflow_id": workflow_id,
                "created_at": created_at,
                "task": task,
                "result": result,
                "metadata": metadata,
                "stats": _parse_possible_json(data.get("stats")) or {},
            }
        )

    return rows


# 1. Get the ID from the URL
# If the URL is .../?id=system-prompts:deployer:...
params = st.query_params
persona = params.get("persona") or "chat"
workflow_id = params.get("workflow_id")



if workflow_id:
    st.info(f"Loading result for: {workflow_id}")
    
    # 2. Use that string as your Redis Hash Key
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    # workflow:dev:chat:0a125ac1-014c-4ce1-8788-324968ee4f7f
    hkey = f"workflow:dev:{persona}:{workflow_id}"
    result_data = r.hgetall(hkey)

    if result_data:
        st.subheader("Task Info")
        st.text(result_data.get("task"))

        # 3. Render the Markdown
        st.subheader("Result")
        st.markdown(result_data.get("result", "No content found."))

        _render_key_value_table("Metadata", result_data.get("metadata"))
        _render_key_value_table("Stats", result_data.get("stats"))


    else:
        st.error("Key not found in Redis.")
else:
    st.warning("Please provide a workflow ID in the URL.")


records = _load_workflow_records()
if not records:
    st.info(f"No workflow hashes found matching {WORKFLOW_KEY_PATTERN}")
    st.stop()

frame = pd.DataFrame(records)
if "created_at" in frame.columns:
    frame["created_at_sort"] = pd.to_datetime(frame["created_at"], errors="coerce", utc=True)
else:
    frame["created_at_sort"] = pd.NaT

persona_options = ["All"] + sorted([p for p in frame["persona"].dropna().astype(str).unique().tolist() if p])
selected_persona = st.sidebar.selectbox("Filter Persona", persona_options, index=0)
search_text = st.sidebar.text_input(
    "Search Workflows",
    value="",
    placeholder="Search key, workflow_id, task, result, metadata...",
)

filtered = frame.copy()
if selected_persona != "All":
    filtered = filtered[filtered["persona"].astype(str) == selected_persona]

if search_text.strip():
    needle = search_text.strip().lower()

    def _matches(row):
        haystack = " ".join(
            [
                str(row.get("key", "")),
                str(row.get("persona", "")),
                str(row.get("workflow_id", "")),
                str(row.get("task", "")),
                str(row.get("result", "")),
                json.dumps(row.get("metadata", {}), ensure_ascii=False),
                json.dumps(row.get("stats", {}), ensure_ascii=False),
            ]
        ).lower()
        return needle in haystack

    filtered = filtered[filtered.apply(_matches, axis=1)]

filtered = filtered.sort_values(by="created_at_sort", ascending=False, na_position="last")

st.divider()
st.subheader("Workflow Index")
st.caption(f"Showing {len(filtered)} of {len(frame)} workflow records")

table_df = filtered[["key", "persona", "workflow_id", "created_at", "task", "result"]].copy()
table_df["task"] = table_df["task"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 180)
table_df["result"] = table_df["result"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 220)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    height=420,
)