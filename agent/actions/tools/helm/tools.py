"""
Helm Agentic Tools - Registered tools for Helm operations in Qwen Agent.
This module provides multiple registered tools for repository and release management.
"""
import json
import asyncio
import json5
import os
from typing import Optional, Callable, Any
from qwen_agent.tools.base import register_tool
from .helm_client import HelmClient
from ..utils.traceability import TRACEABILITY_PARAMS_ADD_ONS, MemoryTraceableTool, ToolExecStatus


# EXECUTION_ID_PARAMETER = {
#     'name': 'execution_id',
#     'type': 'string',
#     'description': 'Optional execution ID supplied by the orchestrator for attestation',
#     'required': False,
# }


def run_async(async_func: Callable) -> Any:
    """
    Helper to run async functions from sync context.
    Handles cases where event loop is already running.
    """
    try:
        asyncio.get_running_loop()
        # Event loop already running in this thread; execute coroutine in a
        # separate worker thread and wait for completion synchronously.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(async_func())).result()
    except RuntimeError:
        # No running event loop in this thread, run directly.
        return asyncio.run(async_func())


def parse_params(params) -> dict:
    """
    Safely parse params which can be either a JSON string or a dict.
    This handles the case where params might come in as a string or 
    as an already-parsed dictionary.
    """
    if isinstance(params, dict):
        return params
    
    if not params:
        return {}
    
    try:
        parsed = json5.loads(params) if isinstance(params, str) else params
        # Ensure result is a dict
        if isinstance(parsed, dict):
            return parsed
        else:
            # If parsing a string returned something that's not a dict,
            # wrap it or return empty dict
            return {}
    except Exception:
        # If parsing fails, return empty dict
        return {}


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse a bool from native booleans or common string values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    return bool(value)


# ============================================================================
# Repository Management Tools
# ============================================================================

@register_tool('helm-add-repository')
class HelmAddRepository(MemoryTraceableTool):
    """Add or update a Helm chart repository."""
    tool_name = "helm-add-repository"
    
    description = 'Add a new Helm chart repository or update existing one. Supports public and private repositories with authentication.'
    parameters = [
        {
            'name': 'repo_name',
            'type': 'string',
            'description': 'Name for the repository (e.g., "stable", "bitnami")',
            'required': True
        },
        {
            'name': 'repo_url',
            'type': 'string',
            'description': 'Repository URL (e.g., "https://charts.bitnami.com/bitnami")',
            'required': True
        },
        {
            'name': 'username',
            'type': 'string',
            'description': 'Optional: Username for authentication',
            'required': False
        },
        {
            'name': 'password',
            'type': 'string',
            'description': 'Optional: Password for authentication',
            'required': False
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.add_repository(
                    name=args['repo_name'],
                    url=args['repo_url'],
                    username=args.get('username'),
                    password=args.get('password'),
                    force_update=True
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    "success": False,
                    "error": str(e),
                    "exec_id": exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-registry-login')
class HelmRegistryLogin(MemoryTraceableTool):
    """Login to an OCI registry for Helm charts."""
    tool_name = "helm-registry-login"
    description = 'Login to an OCI registry (e.g., ghcr.io) for Helm chart pulls.'
    parameters = [
        {
            'name': 'registry',
            'type': 'string',
            'description': 'Registry hostname (e.g., "ghcr.io")',
            'required': True
        },
        {
            'name': 'username',
            'type': 'string',
            'description': 'Optional: Registry username. Falls back to REGISTRY_USERNAME env var',
            'required': False
        },
        {
            'name': 'password',
            'type': 'string',
            'description': 'Optional: Registry password/token. Falls back to REGISTRY_PASSWORD env var',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()

                username = args.get('username') or os.getenv('REGISTRY_USERNAME')
                password = args.get('password') or os.getenv('REGISTRY_PASSWORD')

                if not username or not password:
                    result = {
                        'success': False,
                        'error': 'Missing registry credentials: set REGISTRY_USERNAME and REGISTRY_PASSWORD or pass username/password',
                        'exec_id': exec_id
                    }
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                    return json.dumps(result, ensure_ascii=False)
                
                result = await client.registry_login(
                    registry=args['registry'],
                    username=username,
                    password=password
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-update-repositories')
class HelmUpdateRepositories(MemoryTraceableTool):
    """Update Helm chart repositories."""
    tool_name = "helm-update-repositories"
    
    description = 'Update one or all Helm chart repositories to get the latest chart versions.'
    parameters = [
        {
            'name': 'repo_name',
            'type': 'string',
            'description': 'Optional: Specific repository to update. If empty, updates all repositories',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.update_repository(args.get('repo_name'))
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-list-repositories')
class HelmListRepositories(MemoryTraceableTool):
    """List all configured Helm repositories."""
    tool_name = "helm-list-repositories"
    
    description = 'List all Helm chart repositories currently configured.'
    parameters = TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                repos = await client.list_repositories()
                
                result = {
                    'success': True,
                    'repositories': repos,
                    'count': len(repos),
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-remove-repository')
class HelmRemoveRepository(MemoryTraceableTool):
    """Remove a Helm chart repository."""
    tool_name = "helm-remove-repository"
    
    description = 'Remove a Helm chart repository from the system.'
    parameters = [
        {
            'name': 'repo_name',
            'type': 'string',
            'description': 'Name of the repository to remove',
            'required': True
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.remove_repository(args['repo_name'])
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


# ============================================================================
# Chart Validation Tools
# ============================================================================

@register_tool('helm-template')
class HelmTemplate(MemoryTraceableTool):
    """Render Helm chart templates without installing."""
    tool_name = "helm-template"
    
    description = 'Render Helm chart templates to preview manifests without installing. Useful for validation and review.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Release name to use in template rendering',
            'required': True
        },
        {
            'name': 'chart',
            'type': 'string',
            'description': 'Chart reference (chart name, path, or OCI URL)',
            'required': True
        },
        {
            'name': 'version',
            'type': 'string',
            'description': 'Optional chart version for repo or OCI charts',
            'required': False
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Target namespace for rendering (default: "default")',
            'required': False
        },
        {
            'name': 'values',
            'type': 'string',
            'description': 'JSON string of values to override (e.g., \'{"replicas": 3, "image": {"tag": "1.2.0"}}\')',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                values = None
                if args.get('values'):
                    values = json5.loads(args['values'])
                
                manifests = await client.template(
                    release_name=args['release_name'],
                    chart=args['chart'],
                    namespace=args.get('namespace', 'default'),
                    values=values,
                    version=args.get('version')
                )
                
                result = {
                    'success': True,
                    'manifests': manifests,
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-lint')
class HelmLint(MemoryTraceableTool):
    """Lint a Helm chart for issues."""
    tool_name = "helm-lint"
    
    description = 'Lint a Helm chart to find issues with structure, values, and templates.'
    parameters = [
        {
            'name': 'chart',
            'type': 'string',
            'description': 'Path to chart directory or chart reference',
            'required': True
        },
        {
            'name': 'version',
            'type': 'string',
            'description': 'Optional chart version for repo or OCI charts',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.lint(
                    args['chart'],
                    version=args.get('version')
                )
                
                output = {
                    'success': result.get('success', False),
                    'errors': result.get('errors', []),
                    'warnings': result.get('warnings', []),
                    'output': result.get('raw_output', ''),
                    'exec_id': exec_id
                }
                status = ToolExecStatus.COMPLETED if output['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=output)
                return json.dumps(output, ensure_ascii=False)
            except Exception as e:
                output = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)
        
        return run_async(_async_call)


# ============================================================================
# Release Management Tools
# ============================================================================

@register_tool('helm-install')
class HelmInstall(MemoryTraceableTool):
    """Install a Helm chart as a release."""
    tool_name = "helm-install"
    
    description = 'Install a Helm chart in a Kubernetes cluster as a new release.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name for the release',
            'required': True
        },
        {
            'name': 'chart',
            'type': 'string',
            'description': 'Chart reference (e.g., "bitnami/nginx")',
            'required': True
        },
        {
            'name': 'version',
            'type': 'string',
            'description': 'Optional chart version for repo or OCI charts',
            'required': False
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Target namespace (default: "default")',
            'required': False
        },
        {
            'name': 'values',
            'type': 'string',
            'description': 'JSON string of custom values (e.g., \'{"replicas": 3, "resources": {"limits": {"cpu": "500m"}}}\')',
            'required': False
        },
        {
            'name': 'create_namespace',
            'type': 'string',
            'description': 'Create namespace if it does not exist (true/false, default: true)',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                values = None
                if args.get('values'):
                    values = json5.loads(args['values'])
                
                create_ns = args.get('create_namespace', 'true').lower() == 'true'
                
                result = await client.install(
                    release_name=args['release_name'],
                    chart=args['chart'],
                    namespace=args.get('namespace', 'default'),
                    values=values,
                    create_namespace=create_ns,
                    wait=True,
                    version=args.get('version')
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-upgrade')
class HelmUpgrade(MemoryTraceableTool):
    """Upgrade an existing Helm release."""
    tool_name = "helm-upgrade"
    
    description = 'Upgrade an existing Helm release or install it if it does not exist.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release to upgrade',
            'required': True
        },
        {
            'name': 'chart',
            'type': 'string',
            'description': 'Chart reference (e.g., "bitnami/nginx")',
            'required': True
        },
        {
            'name': 'version',
            'type': 'string',
            'description': 'Optional chart version for repo or OCI charts',
            'required': False
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
        {
            'name': 'values',
            'type': 'string',
            'description': 'JSON string of new values to set',
            'required': False
        },
        {
            'name': 'install',
            'type': 'string',
            'description': 'Install if release does not exist (true/false, default: true)',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                values = None
                if args.get('values'):
                    values = json5.loads(args['values'])
                
                install_flag = args.get('install', 'true').lower() == 'true'
                
                result = await client.upgrade(
                    release_name=args['release_name'],
                    chart=args['chart'],
                    namespace=args.get('namespace', 'default'),
                    values=values,
                    wait=True,
                    install=install_flag,
                    version=args.get('version')
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


# ============================================================================
# Release Information Tools
# ============================================================================

@register_tool('helm-list-releases')
class HelmListReleases(MemoryTraceableTool):
    """List Helm releases."""
    tool_name = "helm-list-releases"
    
    description = 'List Helm releases in a namespace or across all namespaces.'
    parameters = [
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Specific namespace (default: current context)',
            'required': False
        },
        {
            'name': 'all_namespaces',
            'type': 'string',
            'description': 'List releases from all namespaces (true/false, default: false)',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                all_ns = args.get('all_namespaces', 'false').lower() == 'true'
                
                releases = await client.list_releases(
                    namespace=args.get('namespace'),
                    all_namespaces=all_ns
                )
                
                releases_data = [
                    {
                        'name': r.name,
                        'namespace': r.namespace,
                        'revision': r.revision,
                        'status': r.status.value,
                        'chart': r.chart,
                        'app_version': r.app_version,
                        'updated': r.updated
                    }
                    for r in releases
                ]
                
                result = {
                    'success': True,
                    'releases': releases_data,
                    'count': len(releases_data),
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-get-history')
class HelmGetHistory(MemoryTraceableTool):
    """Get release history and revisions."""
    tool_name = "helm-get-history"
    
    description = 'Get the history of revisions for a Helm release, showing all deployments and changes.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release',
            'required': True
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                revisions = await client.get_history(
                    release_name=args['release_name'],
                    namespace=args.get('namespace', 'default')
                )
                
                revisions_data = [
                    {
                        'revision': r.revision,
                        'status': r.status.value,
                        'chart': r.chart,
                        'app_version': r.app_version,
                        'updated': r.updated,
                        'description': r.description
                    }
                    for r in revisions
                ]
                
                result = {
                    'success': True,
                    'revisions': revisions_data,
                    'count': len(revisions_data),
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-get-values')
class HelmGetValues(MemoryTraceableTool):
    """Get the values for a Helm release."""
    tool_name = "helm-get-values"
    
    description = 'Get the current values (merged user and default values) for a deployed Helm release.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release',
            'required': True
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                values = await client.get_values(
                    release_name=args['release_name'],
                    namespace=args.get('namespace', 'default')
                )
                
                result = {
                    'success': True,
                    'values': values,
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


# ============================================================================
# Release Rollback Tools
# ============================================================================

@register_tool('helm-rollback')
class HelmRollback(MemoryTraceableTool):
    """Rollback a Helm release to a previous revision."""
    tool_name = "helm-rollback"
    
    description = 'Rollback a Helm release to a specific previous revision.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release',
            'required': True
        },
        {
            'name': 'revision',
            'type': 'string',
            'description': 'Revision number to rollback to',
            'required': True
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.rollback(
                    release_name=args['release_name'],
                    revision=int(args['revision']),
                    namespace=args.get('namespace', 'default'),
                    wait=True
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-uninstall')
class HelmUninstall(MemoryTraceableTool):
    """Uninstall a Helm release."""
    tool_name = "helm-uninstall"
    
    description = 'Uninstall and delete a Helm release from the cluster.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release to uninstall',
            'required': True
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()
                
                result = await client.uninstall(
                    release_name=args['release_name'],
                    namespace=args.get('namespace', 'default'),
                    wait=True
                )
                result['exec_id'] = exec_id
                status = ToolExecStatus.COMPLETED if result['success'] else ToolExecStatus.FAILED
                self._post_call(exec_id, self.tool_name, args, status, result=result)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
                return json.dumps(result, ensure_ascii=False)
        
        return run_async(_async_call)


@register_tool('helm-test')
class HelmTest(MemoryTraceableTool):
    """Run Helm test hooks for a release."""
    tool_name = "helm-test"

    description = 'Run Helm tests for a deployed release and optionally include test logs.'
    parameters = [
        {
            'name': 'release_name',
            'type': 'string',
            'description': 'Name of the release to test',
            'required': True
        },
        {
            'name': 'namespace',
            'type': 'string',
            'description': 'Release namespace (default: "default")',
            'required': False
        },
        {
            'name': 'logs',
            'type': 'string',
            'description': 'Include test pod logs in output (true/false, default: true)',
            'required': False
        },
        {
            'name': 'filter',
            'type': 'string',
            'description': 'Optional regex filter for selecting specific test hooks',
            'required': False
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            args = {}
            exec_id = None
            try:
                args = parse_params(params)
                exec_id = self._pre_call(self.tool_name, args)
                client = HelmClient()

                include_logs = parse_bool(args.get('logs'), default=True)
                result = await client.test(
                    release_name=args['release_name'],
                    namespace=args.get('namespace', 'default'),
                    logs=include_logs,
                    filter_pattern=args.get('filter'),
                    timeout='120s'
                )

                if result.get('success'):
                    output = {
                        'success': True,
                        'message': f"Helm tests passed for release '{args['release_name']}'",
                        'output': result.get('raw_output', ''),
                        'exec_id': exec_id
                    }
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=output)
                    return json.dumps(output, ensure_ascii=False)

                output = {
                    'success': False,
                    'message': f"Helm tests failed for release '{args['release_name']}'",
                    'error': result.get('error', ''),
                    'output': result.get('raw_output', ''),
                    'exec_id': exec_id
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)
            except Exception as e:
                output = {
                    'success': False,
                    'error': str(e),
                    'exec_id': exec_id
                }
                if exec_id is not None:
                    self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=output)
                return json.dumps(output, ensure_ascii=False)

        return run_async(_async_call)
