"""
Helm Client Wrapper - Provides async interface to helm CLI operations.
This module wraps helm CLI commands for chart repository and release management.
"""
import asyncio
import json
import subprocess
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class HelmStatus(str, Enum):
    """Enum for helm release status."""
    DEPLOYED = "deployed"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    PENDING_INSTALL = "pending-install"
    PENDING_UPGRADE = "pending-upgrade"
    PENDING_ROLLBACK = "pending-rollback"
    UNINSTALLED = "uninstalled"


@dataclass
class HelmRelease:
    """Represents a Helm release."""
    name: str
    namespace: str
    revision: int
    updated: str
    status: HelmStatus
    chart: str
    app_version: str

    def __str__(self):
        return f"{self.name} ({self.status}) in {self.namespace} - {self.chart}"


@dataclass
class HelmRevision:
    """Represents a Helm release revision."""
    revision: int
    updated: str
    status: HelmStatus
    chart: str
    app_version: str
    description: str


class HelmClient:
    """Async wrapper around helm CLI commands."""

    def __init__(self, timeout: int = 120):
        """Initialize HelmClient.
        
        Args:
            timeout: Command execution timeout in seconds
        """
        self.timeout = timeout

    async def _run_helm(
        self, 
        command_args: List[str],
        check_error: bool = True,
        stdin_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run helm command and return parsed output.
        
        Args:
            command_args: List of arguments for helm command
            check_error: Whether to raise exception on non-zero exit code
            
        Returns:
            Dictionary with 'success', 'output', 'error', and 'raw_output' keys
        """
        try:
            cmd = ["helm"] + command_args # + ["--output", "json"]
            print(f"Running {cmd}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdin_bytes = None
            if stdin_data is not None:
                stdin_bytes = stdin_data.encode('utf-8')

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=stdin_bytes),
                timeout=self.timeout
            )
            
            output = stdout.decode('utf-8', errors='ignore').strip()
            error = stderr.decode('utf-8', errors='ignore').strip()
            
            if process.returncode != 0 and check_error:
                return {
                    "success": False,
                    "output": None,
                    "error": error or output,
                    "raw_output": output
                }
            
            # Try to parse JSON output
            try:
                parsed = json.loads(output) if output else None
            except json.JSONDecodeError:
                parsed = output
            
            return {
                "success": process.returncode == 0,
                "output": parsed,
                "error": error,
                "raw_output": output
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "output": None,
                "error": f"Command timed out after {self.timeout} seconds",
                "raw_output": ""
            }

    def _build_command_result(
        self,
        command_args: List[str],
        result: Dict[str, Any],
        success_message: str,
        failure_message: str,
    ) -> Dict[str, Any]:
        try:
            return {
                "success": result.get("success", False),
                "message": success_message if result.get("success", False) else failure_message,
                "command": ["helm"] + command_args,
                "output": result.get("output"),
                "error": result.get("error"),
                "raw_output": result.get("raw_output", ""),
            }
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "raw_output": ""
            }

    async def list_releases(
        self,
        namespace: Optional[str] = None,
        all_namespaces: bool = False
    ) -> List[HelmRelease]:
        """List Helm releases.
        
        Args:
            namespace: Specific namespace (default: current context)
            all_namespaces: List releases from all namespaces
            
        Returns:
            List of HelmRelease objects
        """
        args = ["list"]
        if all_namespaces:
            args.append("--all-namespaces")
        elif namespace:
            args.extend(["-n", namespace])
        
        args.extend(["--output", "json"])
        result = await self._run_helm(args)
        
        if not result["success"]:
            raise RuntimeError(f"Failed to list releases: {result['error']}")
        
        releases = []
        if result["output"]:
            for item in result["output"]:
                releases.append(HelmRelease(
                    name=item.get("name"),
                    namespace=item.get("namespace"),
                    revision=int(item.get("revision", 0)),
                    updated=item.get("updated"),
                    status=HelmStatus(item.get("status", "").lower()),
                    chart=item.get("chart"),
                    app_version=item.get("app_version", "")
                ))
        
        return releases

    async def template(
        self,
        release_name: str,
        chart: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None
    ) -> str:
        """Render Helm chart templates.
        
        Args:
            release_name: Release name
            chart: Chart reference (name, path, or OCI URL)
            namespace: Target namespace
            values: Values overrides as dict
            version: Optional chart version (for repo or OCI charts)
            
        Returns:
            Rendered manifests as string
        """
        args = ["template", release_name, chart]
        args.extend(["-n", namespace])
        
        if version:
            args.extend(["--version", version])

        if values:
            # Create a temporary values file or use --set
            for key, value in values.items():
                if isinstance(value, dict):
                    # Handle nested values
                    for subkey, subvalue in value.items():
                        args.extend(["--set", f"{key}.{subkey}={subvalue}"])
                else:
                    args.extend(["--set", f"{key}={value}"])
        
        result = await self._run_helm(args, check_error=False)
        
        if not result["success"]:
            # Template doesn't return JSON, return raw output
            if result["raw_output"]:
                return result["raw_output"]
            raise RuntimeError(f"Failed to render template: {result['error']}")
        
        return result["raw_output"]

    async def lint(
        self,
        chart: str,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lint a Helm chart.
        
        Args:
            chart: Chart path or reference
            version: Optional chart version (for repo or OCI charts)
            
        Returns:
            Linting results with warnings/errors
        """
        args = ["lint", chart]
        if version:
            args.extend(["--version", version])
        
        result = await self._run_helm(args)
        
        if not result["success"]:
            return {
                "success": False,
                "errors": [result["error"]],
                "warnings": [],
                "raw_output": result["raw_output"]
            }
        
        return {
            "success": True,
            "errors": [],
            "warnings": [],
            "raw_output": result["raw_output"]
        }

    async def add_repository(
        self,
        name: str,
        url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        force_update: bool = True
    ) -> Dict[str, Any]:
        """Add Helm repository.
        
        Args:
            name: Repository name
            url: Repository URL
            username: Optional username for authentication
            password: Optional password for authentication
            force_update: Force update if repo exists
            
        Returns:
            True if successful
        """
        args = ["repo", "add", name, url]
        
        if force_update:
            args.append("--force-update")
        
        if username and password:
            args.extend(["--username", username])
            args.extend(["--password", password])
        
        result = await self._run_helm(args, check_error=False)
        return self._build_command_result(
            args,
            result,
            success_message=f"Repository '{name}' added/updated successfully",
            failure_message=f"Failed to add repository '{name}'",
        )

    async def registry_login(
        self,
        registry: str,
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """Login to an OCI registry for Helm charts.
        
        Args:
            registry: Registry hostname (e.g., "ghcr.io")
            username: Registry username
            password: Registry password or token
            
        Returns:
            True if successful
        """
        args = ["registry", "login", registry, "--username", username, "--password-stdin"]
        stdin_data = f"{password}\n"
        result = await self._run_helm(args, check_error=False, stdin_data=stdin_data)
        return self._build_command_result(
            args,
            result,
            success_message=f"Registry '{registry}' login succeeded",
            failure_message=f"Registry '{registry}' login failed",
        )

    async def update_repository(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Update Helm repository.
        
        Args:
            name: Repository name (updates all if None)
            
        Returns:
            True if successful
        """
        args = ["repo", "update"]
        if name:
            args.append(name)
        
        result = await self._run_helm(args, check_error=False)
        target = name or "all repositories"
        return self._build_command_result(
            args,
            result,
            success_message=f"{target} updated successfully",
            failure_message="Failed to update repositories",
        )

    async def remove_repository(self, name: str) -> Dict[str, Any]:
        """Remove Helm repository.
        
        Args:
            name: Repository name
            
        Returns:
            True if successful
        """
        args = ["repo", "remove", name]
        result = await self._run_helm(args, check_error=False)
        return self._build_command_result(
            args,
            result,
            success_message=f"Repository '{name}' removed successfully",
            failure_message=f"Failed to remove repository '{name}'",
        )

    async def list_repositories(self) -> List[Dict[str, str]]:
        """List Helm repositories.
        
        Returns:
            List of repository dicts with name, url, etc.
        """
        args = ["repo", "list"]
        result = await self._run_helm(args)
        
        if not result["success"]:
            raise RuntimeError(f"Failed to list repositories: {result['error']}")
        
        return result["output"] or []

    async def install(
        self,
        release_name: str,
        chart: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        create_namespace: bool = True,
        wait: bool = True,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Install Helm chart.
        
        Args:
            release_name: Release name
            chart: Chart reference
            namespace: Target namespace
            values: Values overrides
            create_namespace: Create namespace if doesn't exist
            wait: Wait for resources to be ready
            version: Optional chart version (for repo or OCI charts)
            
        Returns:
            True if successful
        """
        args = ["install", release_name, chart]
        args.extend(["-n", namespace])
        
        if create_namespace:
            args.append("--create-namespace")
        
        if wait:
            args.append("--wait")

        if version:
            args.extend(["--version", version])
        
        if values:
            for key, value in values.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        args.extend(["--set", f"{key}.{subkey}={subvalue}"])
                else:
                    args.extend(["--set", f"{key}={value}"])
        
        result = await self._run_helm(args, check_error=False)
        return self._build_command_result(
            args,
            result,
            success_message=f"Release '{release_name}' installed successfully",
            failure_message=f"Failed to install release '{release_name}'",
        )

    async def upgrade(
        self,
        release_name: str,
        chart: str,
        namespace: str = "default",
        values: Optional[Dict[str, Any]] = None,
        wait: bool = True,
        install: bool = False,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upgrade Helm release.
        
        Args:
            release_name: Release name
            chart: Chart reference
            namespace: Target namespace
            values: Values overrides
            wait: Wait for resources to be ready
            install: Install if release doesn't exist
            version: Optional chart version (for repo or OCI charts)
            
        Returns:
            True if successful
        """
        args = ["upgrade", release_name, chart]
        args.extend(["-n", namespace])
        
        if wait:
            args.append("--wait")
        
        if install:
            args.append("--install")

        if version:
            args.extend(["--version", version])
        
        if values:
            for key, value in values.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        args.extend(["--set", f"{key}.{subkey}={subvalue}"])
                else:
                    args.extend(["--set", f"{key}={value}"])
        
        result = await self._run_helm(args, check_error=True)
        return self._build_command_result(
            args,
            result,
            success_message=f"Release '{release_name}' upgraded successfully",
            failure_message=f"Failed to upgrade release '{release_name}'",
        )

    async def get_history(
        self,
        release_name: str,
        namespace: str = "default"
    ) -> List[HelmRevision]:
        """Get release history/revisions.
        
        Args:
            release_name: Release name
            namespace: Release namespace
            
        Returns:
            List of HelmRevision objects
        """
        args = ["history", release_name, "-n", namespace]
        args.extend(["--output", "json"])
        
        result = await self._run_helm(args)
        
        if not result["success"]:
            raise RuntimeError(f"Failed to get history: {result['error']}")
        
        revisions = []
        if result["output"]:
            for item in result["output"]:
                revisions.append(HelmRevision(
                    revision=int(item.get("revision", 0)),
                    updated=item.get("updated"),
                    status=HelmStatus(item.get("status", "").lower()),
                    chart=item.get("chart"),
                    app_version=item.get("app_version", ""),
                    description=item.get("description", "")
                ))
        
        return revisions

    async def rollback(
        self,
        release_name: str,
        revision: int,
        namespace: str = "default",
        wait: bool = True
    ) -> Dict[str, Any]:
        """Rollback to a previous release revision.
        
        Args:
            release_name: Release name
            revision: Revision number to rollback to
            namespace: Release namespace
            wait: Wait for rollback to complete
            
        Returns:
            True if successful
        """
        args = ["rollback", release_name, str(revision)]
        args.extend(["-n", namespace])
        
        if wait:
            args.append("--wait")
        
        result = await self._run_helm(args, check_error=False)
        return self._build_command_result(
            args,
            result,
            success_message=f"Release '{release_name}' rolled back to revision {revision}",
            failure_message=f"Failed to rollback release '{release_name}'",
        )

    async def uninstall(
        self,
        release_name: str,
        namespace: str = "default",
        wait: bool = True
    ) -> Dict[str, Any]:
        """Uninstall Helm release.
        
        Args:
            release_name: Release name
            namespace: Release namespace
            wait: Wait for uninstall to complete
            
        Returns:
            True if successful
        """
        args = ["uninstall", release_name, "-n", namespace]
        
        if wait:
            args.append("--wait")
        
        result = await self._run_helm(args, check_error=False)
        return self._build_command_result(
            args,
            result,
            success_message=f"Release '{release_name}' uninstalled successfully",
            failure_message=f"Failed to uninstall release '{release_name}'",
        )

    async def test(
        self,
        release_name: str,
        namespace: str = "default",
        logs: bool = True,
        filter_pattern: Optional[str] = None,
        timeout: str = "120s"
    ) -> Dict[str, Any]:
        """Run Helm tests for a release.

        Args:
            release_name: Release name
            namespace: Release namespace
            logs: Include test pod logs in output
            filter_pattern: Optional regex filter for test hooks
            timeout: Helm command timeout (default: "120s")

        Returns:
            Dict with success status and command output
        """
        args = ["test", release_name, "-n", namespace]

        if logs:
            args.append("--logs")

        if filter_pattern:
            args.extend(["--filter", filter_pattern])

        args.extend(["--timeout", timeout])

        result = await self._run_helm(args, check_error=False)
        return {
            "success": result["success"],
            "error": result["error"],
            "raw_output": result["raw_output"]
        }

    async def get_values(
        self,
        release_name: str,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Get release values.
        
        Args:
            release_name: Release name
            namespace: Release namespace
            
        Returns:
            Values dict
        """
        args = ["get", "values", release_name,"-a", "-n", namespace]
        args.extend(["--output", "json"])
        
        result = await self._run_helm(args)
        
        if not result["success"]:
            raise RuntimeError(f"Failed to get values: {result['error']}")
        
        return result["output"] or {}
