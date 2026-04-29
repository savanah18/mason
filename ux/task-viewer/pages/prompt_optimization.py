import difflib
from datetime import datetime, timezone
import json
from io import StringIO
from pathlib import Path

import pandas as pd
import redis
import streamlit as st
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

yaml_loader = YAML(typ="safe")
yaml_dumper = YAML()
yaml_dumper.default_flow_style = False
yaml_dumper.indent(mapping=2, sequence=4, offset=2)


AGENT_BASE_DIR = Path("/root/workspace/lnd/aiops/apps/newbie-app/agent")
CANDIDATE_KEY_PATTERN = "prompt-optimization:candidate-prompts:*"

st.set_page_config(layout="wide")
st.markdown(
	"""
	<style>
		.block-container {
			max-width: 98% !important;
			padding-left: 1.5rem;
			padding-right: 1.5rem;
		}
	</style>
	""",
	unsafe_allow_html=True,
)


def _normalize_query_value(value, default=""):
	if isinstance(value, list):
		return value[0] if value else default
	if value is None:
		return default
	return str(value)


def _parse_json(value):
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


def _parse_candidate_key(candidate_key: str):
	if not isinstance(candidate_key, str):
		return "", ""
	parts = candidate_key.split(":", 4)
	if len(parts) != 5:
		return "", ""
	return parts[3], parts[4]


@st.cache_data(ttl=30, show_spinner=False)
def _load_candidate_records():
	r = redis.Redis(host="localhost", port=6379, decode_responses=True)
	records = []

	for key in sorted(r.scan_iter(match=CANDIDATE_KEY_PATTERN)):
		data = r.hgetall(key) or {}
		persona, workflow_id = _parse_candidate_key(key)
		records.append(
			{
				"key": key,
				"persona": persona,
				"workflow_id": workflow_id,
				"created_at": data.get("created_at", ""),
				"updated_at": data.get("updated_at", ""),
				"created_by": data.get("created_by", ""),
				"updated_by": data.get("updated_by", ""),
				"original_prompt": data.get("original_prompt", ""),
				"updated_prompt": data.get("updated_prompt", ""),
			}
		)

	return records


def _get_prompt_text(prompt_hash: dict):
	prompt_text = prompt_hash.get("prompt")
	if isinstance(prompt_text, str) and prompt_text.strip():
		return prompt_text

	alt_prompt_text = prompt_hash.get("system-prompt.prompt")
	if isinstance(alt_prompt_text, str) and alt_prompt_text.strip():
		return alt_prompt_text
	return ""


def _build_split_diff_rows(original_text: str, updated_text: str):
	original_lines = original_text.splitlines()
	updated_lines = updated_text.splitlines()
	matcher = difflib.SequenceMatcher(a=original_lines, b=updated_lines)

	rows = []
	for tag, i1, i2, j1, j2 in matcher.get_opcodes():
		if tag == "equal":
			for idx in range(i2 - i1):
				rows.append(
					{
						"Original": original_lines[i1 + idx],
						"Updated": updated_lines[j1 + idx],
						"Change": "unchanged",
					}
				)
		elif tag == "replace":
			left = original_lines[i1:i2]
			right = updated_lines[j1:j2]
			max_len = max(len(left), len(right))
			for idx in range(max_len):
				rows.append(
					{
						"Original": left[idx] if idx < len(left) else "",
						"Updated": right[idx] if idx < len(right) else "",
						"Change": "modified",
					}
				)
		elif tag == "delete":
			for line in original_lines[i1:i2]:
				rows.append(
					{
						"Original": line,
						"Updated": "",
						"Change": "removed",
					}
				)
		elif tag == "insert":
			for line in updated_lines[j1:j2]:
				rows.append(
					{
						"Original": "",
						"Updated": line,
						"Change": "added",
					}
				)
	return rows


def _highlight_diff_rows(row):
	change = row.get("Change", "")
	if change == "added":
		style = "background-color: #e6ffed; color: #1b5e20;"
	elif change == "removed":
		style = "background-color: #ffeef0; color: #8a1c1c;"
	elif change == "modified":
		style = "background-color: #fff8e1; color: #7a4f01;"
	else:
		style = ""
	return [style] * len(row)


def _render_diff_table(diff_rows):
	if not diff_rows:
		st.info("No diff available. Original and updated prompts may both be empty.")
		return

	df = pd.DataFrame(diff_rows)
	styled_df = (
		df.style
		.apply(_highlight_diff_rows, axis=1)
		.hide(axis="index")
	)
	st.markdown(styled_df.to_html(), unsafe_allow_html=True)


def _request_editor_reload():
	st.session_state["candidate_prompt_editor_action"] = "reload"


def _request_editor_reset():
	st.session_state["candidate_prompt_editor_action"] = "reset"


def _request_editor_save():
	st.session_state["candidate_prompt_editor_action"] = "save"


def _save_candidate_prompt(candidate_key, editor_key):
	r = redis.Redis(host="localhost", port=6379, decode_responses=True)
	updated_prompt = st.session_state.get(editor_key, "")
	write_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
	r.hset(
		candidate_key,
		mapping={
			"updated_prompt": updated_prompt,
			"updated_at": write_time,
			"updated_by": "task-viewer-manual-edit",
		},
	)
	st.session_state["candidate_prompt_editor_action"] = "reload"


def _serialize_goal_yaml(goal_data, description_text):
	goal_map = CommentedMap()
	goal_map["apiVersion"] = goal_data.get("apiVersion", "agents/v1")
	goal_map["kind"] = goal_data.get("kind", "Goal")
	goal_map["metadata"] = CommentedMap(goal_data.get("metadata", {}) or {})

	spec = CommentedMap(goal_data.get("spec", {}) or {})
	spec["description"] = LiteralScalarString(description_text or "")
	if "playbook" in spec:
		spec["playbook"] = DoubleQuotedScalarString("")
	if "feedback" in spec:
		spec["feedback"] = DoubleQuotedScalarString("")
	if "remarks" in spec:
		remarks = spec.get("remarks")
		if isinstance(remarks, dict):
			spec["remarks"] = CommentedMap(remarks)
		elif remarks is None:
			spec["remarks"] = CommentedMap()
	goal_map["spec"] = spec

	stream = StringIO()
	yaml_dumper.dump(goal_map, stream)
	return stream.getvalue()


def _serialize_prompt_yaml(prompt_data, system_text):
	prompt_map = CommentedMap()
	prompt_map["system"] = LiteralScalarString(system_text or "")
	if "feedback" in prompt_data:
		prompt_map["feedback"] = DoubleQuotedScalarString("")
	if "remarks" in prompt_data:
		remarks = prompt_data.get("remarks")
		if isinstance(remarks, dict):
			prompt_map["remarks"] = CommentedMap(remarks)
		elif remarks is None:
			prompt_map["remarks"] = CommentedMap()

	stream = StringIO()
	yaml_dumper.dump(prompt_map, stream)
	return stream.getvalue()

def _accept_candidate_prompt(persona, editor_key, original_prompt_ref):
	if persona != "chat":
		goal_path = AGENT_BASE_DIR / "personas" / persona / "goal.yaml"
		if not goal_path.exists():
			raise FileNotFoundError(f"Goal file not found: {goal_path}")

		with goal_path.open("r", encoding="utf-8") as handle:
			goal_data = yaml_loader.load(handle) or {}

		spec = goal_data.setdefault("spec", {})
		if not isinstance(spec, dict):
			raise TypeError(f"spec must be a mapping in {goal_path}")

		spec["description"] = st.session_state.get(editor_key, "")
		spec["playbook"] = ""
		spec["remarks"] = {
			"created_by": "prompt-optimizer + user",
			"optimized_from": original_prompt_ref or "",
		}
		spec["feedback"] = ""
		goal_text = _serialize_goal_yaml(goal_data, spec["description"])
		goal_path.write_text(goal_text, encoding="utf-8")

		st.session_state["prompt_candidate_decision"] = "accepted"
		st.session_state["candidate_prompt_editor_action"] = "reload"
		st.session_state["prompt_candidate_goal_path"] = str(goal_path)
	else:
		goal_path = AGENT_BASE_DIR / "personas" / persona / "prompts.yaml"
		if not goal_path.exists():
			raise FileNotFoundError(f"Goal file not found: {goal_path}")

		with goal_path.open("r", encoding="utf-8") as handle:
			goal_data = yaml_loader.load(handle) or {}

		# spec = goal_data.setdefault("spec", {})
		# if not isinstance(spec, dict):
		# 	raise TypeError(f"spec must be a mapping in {goal_path}")

		goal_data["system"] = st.session_state.get(editor_key, "")
		goal_data["remarks"] = {
			"created_by": "prompt-optimizer + user",
			"optimized_from": original_prompt_ref or "",
		}
		goal_data["feedback"] = ""
		goal_text = _serialize_prompt_yaml(goal_data, goal_data["system"])
		goal_path.write_text(goal_text, encoding="utf-8")

		st.session_state["prompt_candidate_decision"] = "accepted"
		st.session_state["candidate_prompt_editor_action"] = "reload"
		st.session_state["prompt_candidate_goal_path"] = str(goal_path)


st.title("Prompt Optimization Candidate")

candidate_records = _load_candidate_records()
if candidate_records:
	candidate_frame = pd.DataFrame(candidate_records)
	candidate_frame["created_at_sort"] = pd.to_datetime(candidate_frame["created_at"], errors="coerce", utc=True)

	persona_options = ["All"] + sorted(
		[p for p in candidate_frame["persona"].dropna().astype(str).unique().tolist() if p]
	)
	selected_persona_filter = st.sidebar.selectbox("Filter Persona", persona_options, index=0)
	search_text = st.sidebar.text_input(
		"Search Candidates",
		value="",
		placeholder="Search key, workflow_id, original/updated prompt...",
	)

	filtered_candidates = candidate_frame.copy()
	if selected_persona_filter != "All":
		filtered_candidates = filtered_candidates[
			filtered_candidates["persona"].astype(str) == selected_persona_filter
		]

	if search_text.strip():
		needle = search_text.strip().lower()

		def _candidate_matches(row):
			haystack = " ".join(
				[
					str(row.get("key", "")),
					str(row.get("persona", "")),
					str(row.get("workflow_id", "")),
					str(row.get("original_prompt", "")),
					str(row.get("updated_prompt", "")),
				]
			).lower()
			return needle in haystack

		filtered_candidates = filtered_candidates[
			filtered_candidates.apply(_candidate_matches, axis=1)
		]

	filtered_candidates = filtered_candidates.sort_values(
		by="created_at_sort", ascending=False, na_position="last"
	)

	st.subheader("Prompt Optimization Index")
	st.caption(
		f"Showing {len(filtered_candidates)} of {len(candidate_frame)} prompt optimization candidates"
	)

	table_columns = [
		"key",
		"persona",
		"workflow_id",
		"created_at",
		"updated_at",
		"created_by",
		"updated_by",
		"updated_prompt",
	]
	table_df = filtered_candidates[table_columns].copy()
	table_df["updated_prompt"] = (
		table_df["updated_prompt"]
		.astype(str)
		.str.replace(r"\s+", " ", regex=True)
		.str.slice(0, 220)
	)

	st.dataframe(
		table_df,
		use_container_width=True,
		hide_index=True,
		height=360,
	)

	if not filtered_candidates.empty:
		selected_candidate_key = st.selectbox(
			"Quick Select Candidate",
			filtered_candidates["key"].tolist(),
			index=0,
		)
		quick_persona, quick_workflow_id = _parse_candidate_key(selected_candidate_key)
		st.caption(
			f"Selected candidate maps to persona={quick_persona or '-'} workflow_id={quick_workflow_id or '-'}"
		)

	st.divider()
else:
	st.info(f"No candidate prompt hashes found matching {CANDIDATE_KEY_PATTERN}")

params = st.query_params
persona_from_query = _normalize_query_value(params.get("persona"), "deployer")
workflow_id_from_query = _normalize_query_value(params.get("workflow_id"), "")

persona = st.text_input("Persona", value=persona_from_query)
workflow_id = st.text_input("Workflow ID", value=workflow_id_from_query)

if persona and workflow_id:
	r = redis.Redis(host="localhost", port=6379, decode_responses=True)

	candidate_key = f"prompt-optimization:candidate-prompts:{persona}:{workflow_id}"
	report_key = f"workflow:dev:prompt-optimizer:{workflow_id}"

	candidate_data = r.hgetall(candidate_key) or {}

	if not candidate_data:
		st.error(f"Candidate prompt not found: {candidate_key}")
	else:
		original_prompt_ref = candidate_data.get("original_prompt", "")
		updated_prompt = candidate_data.get("updated_prompt", "")
		updated_at = candidate_data.get("updated_at", "")
		updated_by = candidate_data.get("updated_by", "")
		created_at = candidate_data.get("created_at", "")
		created_by = candidate_data.get("created_by", "")

		st.caption(f"Candidate Key: {candidate_key}")

		metadata_cols = st.columns(5)
		metadata_cols[0].metric("Created At", created_at or "-")
		metadata_cols[1].metric("Created By", created_by or "-")
		metadata_cols[2].metric("Original Prompt Ref", original_prompt_ref or "-")
		metadata_cols[3].metric("Updated At", updated_at or "-")
		metadata_cols[4].metric("Updated By", updated_by or "-")

		original_prompt_hash = r.hgetall(original_prompt_ref) if original_prompt_ref else {}
		original_prompt = _get_prompt_text(original_prompt_hash)

		editor_key = f"candidate_prompt_editor::{persona}::{workflow_id}"
		action_key = "candidate_prompt_editor_action"
		loaded_key = "candidate_prompt_editor_loaded_for"
		pending_action = st.session_state.get(action_key)
		if st.session_state.get(loaded_key) != candidate_key:
			st.session_state[editor_key] = updated_prompt or ""
			st.session_state[loaded_key] = candidate_key
		elif pending_action in {"reload", "reset", "save"}:
			refreshed_candidate = r.hgetall(candidate_key) or {}
			if pending_action == "save":
				st.session_state[editor_key] = refreshed_candidate.get("updated_prompt", "")
			else:
				st.session_state[editor_key] = refreshed_candidate.get("updated_prompt", "")
			st.session_state.pop(action_key, None)

		edited_prompt = st.text_area(
			"Edit Candidate Prompt",
			key=editor_key,
			height=360,
			help="Edit and save to update Redis candidate prompt for this persona/workflow.",
		)

		edit_action_cols = st.columns(3)
		if edit_action_cols[0].button(
			"Save Edited Candidate Prompt",
			use_container_width=True,
			on_click=_save_candidate_prompt,
			args=(candidate_key, editor_key),
		):
			st.success("Saved edited candidate prompt to Redis. Refreshing view...")
			st.rerun()

		if edit_action_cols[1].button(
			"Reset Editor to Stored Value",
			use_container_width=True,
			on_click=_request_editor_reset,
		):
			st.rerun()

		if edit_action_cols[2].button(
			"Reload Candidate from Redis",
			use_container_width=True,
			on_click=_request_editor_reload,
		):
			st.rerun()

		st.subheader("Split Prompt Diff")
		diff_rows = _build_split_diff_rows(original_prompt or "", edited_prompt or "")
		_render_diff_table(diff_rows)

		raw_cols = st.columns(2)
		with raw_cols[0]:
			st.markdown("**Original Prompt**")
			st.text_area("", value=original_prompt or "", height=320, disabled=True, key="original_prompt_text")
		with raw_cols[1]:
			st.markdown("**Candidate Prompt (Editor Value)**")
			st.text_area("", value=edited_prompt or "", height=320, disabled=True, key="updated_prompt_text")

		report_data = r.hgetall(report_key) or {}
		report_md = report_data.get("result", "")

		with st.expander("Prompt Optimization Report", expanded=False):
			if isinstance(report_md, str) and report_md.strip():
				st.markdown(report_md)
			else:
				st.info(f"No report markdown found at key: {report_key}")

		action_cols = st.columns(2)
		if action_cols[0].button(
			"Accept Candidate Prompt",
			use_container_width=True,
			on_click=_accept_candidate_prompt,
			args=(persona, editor_key, original_prompt_ref),
		):
			st.success(f"Accepted. Updated {st.session_state.get('prompt_candidate_goal_path', 'persona goal file')}.")

		if action_cols[1].button("Reject Candidate Prompt", use_container_width=True):
			st.session_state["prompt_candidate_decision"] = "rejected"
			st.warning("Rejected. Placeholder: mark candidate prompt as rejected.")

		if st.session_state.get("prompt_candidate_decision"):
			st.info(f"Current decision: {st.session_state['prompt_candidate_decision']}")
else:
	st.warning("Please provide persona and workflow_id (query params or input fields).")
