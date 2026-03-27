"""Lightweight Kubernetes builtin tools to reduce MCP context payload size."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from ..utils.traceability import TRACEABILITY_PARAMS_ADD_ONS, MemoryTraceableTool, ToolExecStatus

def _parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    if isinstance(params, str):
        parsed = json5.loads(params)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _run_kubectl(args: List[str], timeout_sec: int = 30) -> Tuple[bool, str, str]:
    cmd = ["kubectl"] + args
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    return proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validate_cpu_unit(value: str) -> bool:
    return bool(re.fullmatch(r"[1-9][0-9]*m", value))


def _validate_memory_unit(value: str) -> bool:
    return bool(re.fullmatch(r"[1-9][0-9]*(Mi|Gi)", value))


def _extract_containers_for_kind(kind: str, obj: Dict[str, Any]) -> Dict[str, Any]:
    spec = obj.get("spec", {})
    status = obj.get("status", {})

    if kind == "cronjob":
        pod_spec = (
            spec.get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
        )
    elif kind in {"deployment", "statefulset", "daemonset", "job"}:
        pod_spec = spec.get("template", {}).get("spec", {})
    else:
        pod_spec = {}

    containers: List[Dict[str, Any]] = []
    for c in pod_spec.get("containers", []):
        resources = c.get("resources", {})
        requests = resources.get("requests", {})
        limits = resources.get("limits", {})

        containers.append(
            {
                "name": c.get("name"),
                "resources": {
                    "cpu": {
                        "request": requests.get("cpu"),
                        "limit": limits.get("cpu"),
                    },
                    "memory": {
                        "request": requests.get("memory"),
                        "limit": limits.get("memory"),
                    },
                },
            }
        )

    result: Dict[str, Any] = {
        "containers": containers,
    }

    if kind in {"deployment", "statefulset"}:
        result["replicas"] = {
            "desired": _safe_int(spec.get("replicas", 0), 0),
            "ready": _safe_int(status.get("readyReplicas", 0), 0),
        }
    elif kind == "daemonset":
        result["replicas"] = {
            "desired": _safe_int(status.get("desiredNumberScheduled", 0), 0),
            "ready": _safe_int(status.get("numberReady", 0), 0),
        }

    return result


def _merge_resource_updates(
    obj: Dict[str, Any],
    kind: str,
    target_container: Optional[str],
    cpu_request: Optional[str],
    cpu_limit: Optional[str],
    memory_request: Optional[str],
    memory_limit: Optional[str],
    replicas: Optional[int],
) -> Dict[str, Any]:
    spec = obj.setdefault("spec", {})

    if replicas is not None and kind in {"deployment", "statefulset"}:
        spec["replicas"] = replicas

    if kind == "cronjob":
        containers = (
            spec.setdefault("jobTemplate", {})
            .setdefault("spec", {})
            .setdefault("template", {})
            .setdefault("spec", {})
            .setdefault("containers", [])
        )
    elif kind in {"deployment", "statefulset", "daemonset", "job"}:
        containers = (
            spec.setdefault("template", {})
            .setdefault("spec", {})
            .setdefault("containers", [])
        )
    elif kind == "pod":
        containers = spec.setdefault("containers", [])
    else:
        containers = []

    for container in containers:
        name = container.get("name")
        if target_container and name != target_container:
            continue

        resources = container.setdefault("resources", {})
        requests = resources.setdefault("requests", {})
        limits = resources.setdefault("limits", {})

        if cpu_request is not None:
            requests["cpu"] = cpu_request
        if memory_request is not None:
            requests["memory"] = memory_request
        if cpu_limit is not None:
            limits["cpu"] = cpu_limit
        if memory_limit is not None:
            limits["memory"] = memory_limit

    return obj


@register_tool("kubernetes-list-workloads")
class KubernetesListWorkloads(MemoryTraceableTool):
    """List key Kubernetes workloads with compact output."""
    tool_name = "kubernetes-list-workloads"

    description = (
        "List workloads in a namespace as a compact mapping by kind and workload name. "
        "Returns deployments, sts, job, cronjob, and ds with container names and cpu/memory request/limit."
    )

    parameters = [
        {
            "name": "namespace",
            "type": "string",
            "description": "Target namespace",
            "required": True,
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            namespace = args.get("namespace")
            execution_id = args.get("execution_id")

            # Pods are intentionally excluded to keep payloads compact.
            kinds = ["deployment", "statefulset", "job", "cronjob", "daemonset"]
            output_key_by_kind = {
                "deployment": "deployments",
                "statefulset": "sts",
                "job": "job",
                "cronjob": "cronjob",
                "daemonset": "ds",
            }

            output: Dict[str, Any] = {
                "success": True,
                "namespace": namespace,
                "summary": {},
                "deployments": {},
                "sts": {},
                "job": {},
                "cronjob": {},
                "ds": {},
            }

            base_ns_args = ["-n", namespace]

            for kind in kinds:
                ok, stdout, stderr = _run_kubectl(
                    ["get", kind, *base_ns_args, "-o", "json"],
                    timeout_sec=30,
                )
                if not ok:
                    output["summary"][kind] = {"count": 0, "error": stderr or "kubectl failed"}
                    continue

                parsed = json.loads(stdout) if stdout else {"items": []}
                mapped: Dict[str, Any] = {}
                for item in parsed.get("items", []):
                    name = item.get("metadata", {}).get("name")
                    if not name:
                        continue
                    mapped[name] = _extract_containers_for_kind(kind, item)

                output[output_key_by_kind[kind]] = mapped
                output["summary"][kind] = {"count": len(mapped)}

            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=output)
            return json.dumps(output, ensure_ascii=False)
        except Exception as e:
            output = {
                "success": False,
                "error": str(e),
                "exec_id": exec_id
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
            return json.dumps(output, ensure_ascii=False)


@register_tool("kubernetes-get-namespace-resource-quota")
class KubernetesGetNamespaceResourceQuota(BaseTool):
    """Get ResourceQuota status for a namespace with compact, tabular-friendly output."""
    tool_name = "kubernetes-get-namespace-resource-quota"
    
    description = (
        "Get namespace ResourceQuota status (used vs hard) with compact output. "
        "Returns raw quota maps and flattened rows for each tracked resource."
    )

    parameters = [
        {
            "name": "namespace",
            "type": "string",
            "description": "Target namespace",
            "required": True,
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            namespace = args.get("namespace")

            ok, stdout, stderr = _run_kubectl(
                ["get", "resourcequota", "-n", namespace, "-o", "json"],
                timeout_sec=30,
            )
            if not ok:
                output = {
                    "success": False,
                    "namespace": namespace,
                    "error": stderr or "kubectl failed",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            parsed = json.loads(stdout) if stdout else {"items": []}
            items = parsed.get("items", [])

            resource_quotas: Dict[str, Any] = {}
            quota_rows: List[Dict[str, Any]] = []

            for item in items:
                metadata = item.get("metadata", {})
                spec = item.get("spec", {})
                status = item.get("status", {})

                quota_name = metadata.get("name")
                if not quota_name:
                    continue

                hard = status.get("hard", {}) or {}
                used = status.get("used", {}) or {}
                scopes = spec.get("scopes", []) or []

                resource_quotas[quota_name] = {
                    "hard": hard,
                    "used": used,
                    "scopes": scopes,
                }

                tracked_resources = sorted(set(hard.keys()) | set(used.keys()))
                for resource_name in tracked_resources:
                    quota_rows.append(
                        {
                            "quota": quota_name,
                            "resource": resource_name,
                            "used": used.get(resource_name),
                            "hard": hard.get(resource_name),
                        }
                    )

            output = {
                "success": True,
                "namespace": namespace,
                "summary": {
                    "quota_count": len(resource_quotas),
                    "row_count": len(quota_rows),
                },
                "resource_quotas": resource_quotas,
                "quota_rows": quota_rows,
                "execution_id": 
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=output)
            return json.dumps(output, ensure_ascii=False)
        except Exception as e:
            output = {
                "success": False,
                "error": str(e)
                "exec_id": exec_id
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
            return json.dumps(output, ensure_ascii=False)


@register_tool("kubernetes-get-namespace-events")
class KubernetesGetNamespaceEvents(BaseTool):
    """Get Kubernetes events for a namespace, sorted by lastTimestamp, truncated to last 20."""
    tool_name = "kubernetes-get-namespace-events"

    description = (
        "Fetch namespace events with compact, tabular-friendly output. "
        "Always sorted by lastTimestamp, returning only the last 20 events."
    )

    parameters = [
        {
            "name": "namespace",
            "type": "string",
            "description": "Target namespace",
            "required": True,
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            namespace = args.get("namespace")

            if not namespace:
                return _tool_response(
                    {"success": False, "error": "namespace is required"},
                    execution_id,
                )

            ok, stdout, stderr = _run_kubectl(
                [
                    "get", "events",
                    "-n", namespace,
                    "--sort-by=.lastTimestamp",
                    "-o", "json"
                ],
                timeout_sec=30,
            )
            if not ok:
                output = {
                    "success": False,
                    "namespace": namespace,
                    "error": stderr or "kubectl failed",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            parsed = json.loads(stdout) if stdout else {"items": []}
            items = parsed.get("items", [])

            # Only keep the last 20 events
            items = items[-10:]

            event_rows: List[Dict[str, Any]] = []
            for item in items:
                metadata = item.get("metadata", {})
                involved = item.get("involvedObject", {})
                reason = item.get("reason")
                message = item.get("message")
                last_ts = item.get("lastTimestamp")
                type_ = item.get("type")

                event_rows.append(
                    {
                        "resource": f'{involved.get("kind")}/{involved.get("name")}',
                        "reason": reason,
                        "message": message,
                        "type": type_,
                        "lastTimestamp": last_ts,
                    }
                )

            output = {
                "success": True,
                "namespace": namespace,
                "event_count": len(event_rows),
                "events": event_rows,
                "exec_id": exec_id
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=output)
            return json.dumps(output, ensure_ascii=False)
        except Exception as e:
            output = {
                "success": False,
                "error": str(e)
                "exec_id": exec_id
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
            return json.dumps(output, ensure_ascii=False)


@register_tool("kubernetes-apply-resource-update")
class KubernetesApplyResourceUpdate(BaseTool):
    """Apply resource and replica updates to common workload kinds."""
    tool_name = "kubernetes-apply-resource-update"

    description = (
        "Apply CPU/memory request/limit updates and optional replicas to pods, deployments, "
        "statefulsets, jobs, daemonsets, and cronjobs using kubectl apply with compact output."
    )

    parameters = [
        {
            "name": "kind",
            "type": "string",
            "description": "Resource kind: pod|deployment|statefulset|job|daemonset|cronjob",
            "required": True,
        },
        {
            "name": "name",
            "type": "string",
            "description": "Resource name",
            "required": True,
        },
        {
            "name": "namespace",
            "type": "string",
            "description": "Target namespace",
            "required": True,
        },
        {
            "name": "container",
            "type": "string",
            "description": "Optional container name. If omitted, updates all containers.",
            "required": False,
        },
        {
            "name": "cpu_request",
            "type": "string",
            "description": "CPU request in millicores, e.g. 50m",
            "required": False,
        },
        {
            "name": "cpu_limit",
            "type": "string",
            "description": "CPU limit in millicores, e.g. 200m",
            "required": False,
        },
        {
            "name": "memory_request",
            "type": "string",
            "description": "Memory request in Mi/Gi, e.g. 256Mi",
            "required": False,
        },
        {
            "name": "memory_limit",
            "type": "string",
            "description": "Memory limit in Mi/Gi, e.g. 512Mi",
            "required": False,
        },
        {
            "name": "replicas",
            "type": "integer",
            "description": "Optional replica count (deployment/statefulset only)",
            "required": False,
        },
        {
            "name": "dry_run",
            "type": "boolean",
            "description": "If true, validates without applying changes",
            "required": False,
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            kind = str(args["kind"]).strip().lower()
            name = str(args["name"]).strip()
            namespace = str(args["namespace"]).strip()

            supported = {"pod", "deployment", "statefulset", "job", "daemonset", "cronjob"}
            if kind not in supported:
                output = {
                    "success": False,
                    "error": f"Unsupported kind '{kind}'. Supported: {sorted(supported)}",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            cpu_request = args.get("cpu_request")
            cpu_limit = args.get("cpu_limit")
            memory_request = args.get("memory_request")
            memory_limit = args.get("memory_limit")
            container = args.get("container")
            dry_run = bool(args.get("dry_run", False))

            replicas = args.get("replicas")
            if replicas is not None:
                replicas = int(replicas)
                if replicas < 1:
                    output = {
                        "success": False,
                        "error": "replicas must be a positive integer",
                        "exec_id": exec_id
                    }
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                    return json.dumps(output, ensure_ascii=False)

            if cpu_request and not _validate_cpu_unit(str(cpu_request)):
                output = {
                    "success": False,
                    "error": "cpu_request must use millicores format like 50m",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)
            if cpu_limit and not _validate_cpu_unit(str(cpu_limit)):
                output = {
                    "success": False,
                    "error": "cpu_limit must use millicores format like 200m",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)
            if memory_request and not _validate_memory_unit(str(memory_request)):
                output = {
                    "success": False,
                    "error": "memory_request must use Mi/Gi format like 256Mi or 1Gi",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)
            if memory_limit and not _validate_memory_unit(str(memory_limit)):
                output = {
                    "success": False,
                    "error": "memory_limit must use Mi/Gi format like 512Mi or 2Gi",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            if not any([cpu_request, cpu_limit, memory_request, memory_limit, replicas]):
                output = {
                    "success": False,
                    "error": "No updates provided. Set at least one resource field or replicas.",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            ok, stdout, stderr = _run_kubectl(
                ["get", kind, name, "-n", namespace, "-o", "json"],
                timeout_sec=30,
            )
            if not ok:
                output = {
                    "success": False,
                    "error": stderr or "Failed to fetch current resource",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            obj = json.loads(stdout)
            updated = _merge_resource_updates(
                obj=obj,
                kind=kind,
                target_container=container,
                cpu_request=cpu_request,
                cpu_limit=cpu_limit,
                memory_request=memory_request,
                memory_limit=memory_limit,
                replicas=replicas,
            )

            manifest = json.dumps(updated, separators=(",", ":"))
            apply_args = ["apply", "-f", "-"]
            if dry_run:
                apply_args.extend(["--dry-run=server"])

            proc = subprocess.run(
                ["kubectl", *apply_args],
                input=manifest,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=45,
                check=False,
            )

            if proc.returncode != 0:
                output = {
                    "success": False,
                    "error": proc.stderr.strip() or proc.stdout.strip() or "kubectl apply failed",
                    "exec_id": exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

            output = {
                "success": True,
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "dry_run": dry_run,
                "updated_fields": {
                    "container": container or "*",
                    "cpu_request": cpu_request,
                    "cpu_limit": cpu_limit,
                    "memory_request": memory_request,
                    "memory_limit": memory_limit,
                    "replicas": replicas,
                },
                "result": proc.stdout.strip(),
                "exec_id": exec_id
            }
            return json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            return _tool_response(
                {
                    "success": False,
                    "error": str(exc),
                },
                args.get("execution_id"),
            )
