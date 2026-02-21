"""
Helm Tools - Usage Examples and Demonstration

This module shows practical examples of how to use the Helm tools
directly and with Qwen Agent.
"""

import asyncio
import json
from helm_client import HelmClient


# ============================================================================
# Example 1: Direct HelmClient Usage (Async)
# ============================================================================

async def example_direct_usage():
    """Example 1: Using HelmClient directly for Helm operations."""
    print("\n" + "="*70)
    print("Example 1: Direct HelmClient Usage")
    print("="*70)
    
    client = HelmClient(timeout=30)
    
    try:
        # 1. Add Bitnami repository
        print("\n[1] Adding Bitnami repository...")
        success = await client.add_repository(
            name="bitnami",
            url="https://charts.bitnami.com/bitnami"
        )
        print(f"    Success: {success}")
        
        # 2. List repositories
        print("\n[2] Listing repositories...")
        repos = await client.list_repositories()
        print(f"    Found {len(repos)} repositories:")
        for repo in repos:
            print(f"      - {repo.get('name')}: {repo.get('url')}")
        
        # 3. List releases
        print("\n[3] Listing releases in all namespaces...")
        releases = await client.list_releases(all_namespaces=True)
        print(f"    Found {len(releases)} releases:")
        for release in releases:
            print(f"      - {release.name} ({release.status.value}) in {release.namespace}")
        
        # 4. Template a chart
        print("\n[4] Templating a chart...")
        manifests = await client.template(
            release_name="test-release",
            chart="bitnami/nginx",
            namespace="default",
            values={"replicas": 2}
        )
        print(f"    Generated {len(manifests)} characters of manifests")
        print(f"    First 200 chars:\n{manifests[:200]}...")
        
        # 5. Lint a chart
        print("\n[5] Linting chart...")
        lint_result = await client.lint("bitnami/nginx")
        print(f"    Lint result: {lint_result}")
        
    except Exception as e:
        print(f"    Error: {e}")


# ============================================================================
# Example 2: Full Release Lifecycle
# ============================================================================

async def example_release_lifecycle():
    """Example 2: Install, upgrade, and rollback a release."""
    print("\n" + "="*70)
    print("Example 2: Full Release Lifecycle")
    print("="*70)
    
    client = HelmClient(timeout=30)
    release_name = "example-release"
    namespace = "example-ns"
    
    try:
        # 1. Install
        print(f"\n[1] Installing release '{release_name}'...")
        success = await client.install(
            release_name=release_name,
            chart="bitnami/nginx",
            namespace=namespace,
            values={"replicas": 1},
            create_namespace=True,
            wait=False  # Skip wait for example
        )
        print(f"    Install success: {success}")
        
        # 2. List releases
        print(f"\n[2] Listing releases...")
        releases = await client.list_releases(namespace=namespace)
        print(f"    Found {len(releases)} releases in {namespace}")
        
        # 3. Get values
        print(f"\n[3] Getting release values...")
        values = await client.get_values(release_name, namespace=namespace)
        print(f"    Current values: {json.dumps(values, indent=2)[:200]}...")
        
        # 4. Upgrade
        print(f"\n[4] Upgrading release...")
        success = await client.upgrade(
            release_name=release_name,
            chart="bitnami/nginx",
            namespace=namespace,
            values={"replicas": 3},
            wait=False  # Skip wait for example
        )
        print(f"    Upgrade success: {success}")
        
        # 5. Get history
        print(f"\n[5] Getting release history...")
        history = await client.get_history(release_name, namespace=namespace)
        print(f"    Found {len(history)} revisions:")
        for rev in history:
            print(f"      - Revision {rev.revision}: {rev.status.value}")
        
        # 6. Rollback (if history exists)
        if len(history) > 1:
            print(f"\n[6] Rolling back to revision 1...")
            success = await client.rollback(
                release_name=release_name,
                revision=1,
                namespace=namespace,
                wait=False  # Skip wait for example
            )
            print(f"    Rollback success: {success}")
        
        # 7. Uninstall
        print(f"\n[7] Uninstalling release...")
        success = await client.uninstall(release_name, namespace, wait=False)
        print(f"    Uninstall success: {success}")
        
    except Exception as e:
        print(f"    Error: {e}")


# ============================================================================
# Example 3: Integration with Qwen Agent
# ============================================================================

def example_with_qwen_agent():
    """Example 3: Using Helm tools with Qwen Agent."""
    print("\n" + "="*70)
    print("Example 3: Integration with Qwen Agent")
    print("="*70)
    
    try:
        from qwen_agent.agents import Assistant
        from tools import *  # Import all registered Helm tools
        
        print("\n[1] Creating Qwen Agent with Helm tools...")
        
        llm_config = {
            'model': 'Qwen3-4B-Instruct',
            'model_server': 'http://localhost:8001/v1',
            'generate_cfg': {
                'temperature': 0.8,
                'top_p': 0.9,
            }
        }
        
        helm_tools = [
            'helm-add-repository',
            'helm-list-repositories',
            'helm-update-repositories',
            'helm-list-releases',
            'helm-template',
            'helm-lint',
            'helm-install',
            'helm-upgrade',
            'helm-get-history',
            'helm-get-values',
            'helm-rollback',
            'helm-uninstall',
        ]
        
        agent = Assistant(
            llm=llm_config,
            system_message="You are a Helm operations specialist. Help users manage Kubernetes deployments using Helm.",
            function_list=helm_tools
        )
        
        print(f"    Agent created with {len(helm_tools)} Helm tools")
        
        # Example interaction
        print("\n[2] Example interaction:")
        messages = [
            {
                'role': 'user',
                'content': 'List all Helm releases in all namespaces'
            }
        ]
        
        print(f"    User: {messages[0]['content']}")
        print("    Agent: [Processing with helm-list-releases tool...]")
        
    except ImportError:
        print("    Note: qwen-agent not installed. Install with: pip install qwen-agent")
    except Exception as e:
        print(f"    Error: {e}")


# ============================================================================
# Example 4: Error Handling
# ============================================================================

async def example_error_handling():
    """Example 4: Proper error handling with Helm tools."""
    print("\n" + "="*70)
    print("Example 4: Error Handling")
    print("="*70)
    
    client = HelmClient(timeout=10)
    
    try:
        # Try to get history for non-existent release
        print("\n[1] Attempting to get history for non-existent release...")
        history = await client.get_history("non-existent", "default")
        print(f"    Success (shouldn't happen): {history}")
        
    except RuntimeError as e:
        print(f"    Caught expected error: {e}")
    
    try:
        # Try to lint non-existent chart
        print("\n[2] Attempting to lint non-existent chart...")
        result = await client.lint("/non/existent/chart")
        print(f"    Lint result: {result['success']}")
        if not result['success']:
            print(f"    Error details: {result.get('raw_output', 'No output')[:100]}")
        
    except Exception as e:
        print(f"    Error: {e}")


# ============================================================================
# Example 5: Batch Operations
# ============================================================================

async def example_batch_operations():
    """Example 5: Performing batch operations on multiple releases."""
    print("\n" + "="*70)
    print("Example 5: Batch Operations")
    print("="*70)
    
    client = HelmClient()
    
    try:
        # List all releases
        print("\n[1] Listing all releases...")
        releases = await client.list_releases(all_namespaces=True)
        print(f"    Found {len(releases)} total releases")
        
        # Group by namespace
        by_namespace = {}
        for release in releases:
            ns = release.namespace
            if ns not in by_namespace:
                by_namespace[ns] = []
            by_namespace[ns].append(release)
        
        # Show summary
        print(f"\n[2] Summary by namespace:")
        for ns, rels in sorted(by_namespace.items()):
            statuses = {}
            for rel in rels:
                status = rel.status.value
                statuses[status] = statuses.get(status, 0) + 1
            print(f"    {ns}: {len(rels)} releases")
            for status, count in sorted(statuses.items()):
                print(f"      - {status}: {count}")
        
    except Exception as e:
        print(f"    Error: {e}")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("HELM TOOLS - USAGE EXAMPLES")
    print("="*70)
    
    # Run async examples
    await example_direct_usage()
    await example_release_lifecycle()
    await example_error_handling()
    await example_batch_operations()
    
    # Run synchronous examples
    example_with_qwen_agent()
    
    print("\n" + "="*70)
    print("Examples completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    print("""
    Helm Tools Examples
    ===================
    
    This script demonstrates:
    1. Direct HelmClient usage
    2. Complete release lifecycle (install, upgrade, rollback)
    3. Integration with Qwen Agent
    4. Error handling
    5. Batch operations
    
    Note: These examples show how the tools work.
    Some operations require:
    - Helm 3.x installed
    - Kubernetes cluster access
    - Proper kubeconfig configured
    """)
    
    # Run examples
    asyncio.run(main())
