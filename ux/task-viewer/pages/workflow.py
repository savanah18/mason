import streamlit as st
import redis
import json


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


# 1. Get the ID from the URL
# If the URL is .../?id=system-prompts:deployer:...
params = st.query_params
persona = params.get("persona") or "chat"
workflow_id = params.get("workflow_id")



if workflow_id:
    st.info(f"Loading result for: {workflow_id}")
    
    # 2. Use that string as your Redis Hash Key
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
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