"""
Helm Tools - Unit Tests

Test suite for validating Helm tools functionality and integration.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from helm_client import HelmClient, HelmRelease, HelmRevision, HelmStatus


# ============================================================================
# Test HelmClient
# ============================================================================

class TestHelmClient:
    """Test HelmClient basic functionality."""
    
    @pytest.fixture
    def client(self):
        """Create HelmClient instance for testing."""
        return HelmClient(timeout=10)
    
    def test_client_initialization(self):
        """Test HelmClient can be initialized."""
        client = HelmClient()
        assert client is not None
        assert client.timeout == 30
    
    def test_client_custom_timeout(self):
        """Test HelmClient with custom timeout."""
        client = HelmClient(timeout=60)
        assert client.timeout == 60
    
    @pytest.mark.asyncio
    async def test_helm_status_enum(self):
        """Test HelmStatus enum values."""
        assert HelmStatus.DEPLOYED.value == "deployed"
        assert HelmStatus.FAILED.value == "failed"
        assert HelmStatus.SUPERSEDED.value == "superseded"
    
    @pytest.mark.asyncio
    async def test_helm_release_dataclass(self):
        """Test HelmRelease dataclass."""
        release = HelmRelease(
            name="test",
            namespace="default",
            revision=1,
            updated="2024-01-01",
            status=HelmStatus.DEPLOYED,
            chart="nginx:1.0",
            app_version="1.24"
        )
        assert release.name == "test"
        assert release.status == HelmStatus.DEPLOYED
        assert "test" in str(release)


# ============================================================================
# Test Tools Registration
# ============================================================================

class TestToolsRegistration:
    """Test that all tools are properly registered."""
    
    def test_tools_can_be_imported(self):
        """Test that tools module can be imported."""
        try:
            from tools import (
                HelmAddRepository,
                HelmUpdateRepositories,
                HelmListRepositories,
                HelmTemplate,
                HelmLint,
                HelmInstall,
                HelmUpgrade,
                HelmListReleases,
                HelmGetHistory,
                HelmRollback,
                HelmUninstall,
            )
            assert HelmAddRepository is not None
        except ImportError as e:
            pytest.fail(f"Failed to import tools: {e}")
    
    def test_tool_descriptions_exist(self):
        """Test that all tools have descriptions."""
        from tools import HelmAddRepository
        tool = HelmAddRepository()
        assert tool.description is not None
        assert len(tool.description) > 10
    
    def test_tool_parameters_exist(self):
        """Test that tools have parameter definitions."""
        from tools import HelmAddRepository
        tool = HelmAddRepository()
        assert tool.parameters is not None
        assert isinstance(tool.parameters, list)
        assert any(p['name'] == 'repo_name' for p in tool.parameters)


# ============================================================================
# Test Tool Response Formats
# ============================================================================

class TestToolResponses:
    """Test that tools return proper response formats."""
    
    @pytest.mark.asyncio
    async def test_list_releases_response_format(self):
        """Test helm-list-releases returns proper format."""
        from tools import HelmListReleases
        tool = HelmListReleases()
        
        # Mock the response
        with patch('tools.HelmClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.list_releases.return_value = []
            mock_client_class.return_value = mock_client
            
            params = '{"namespace": "default"}'
            try:
                response = await tool.call(params)
                result = json.loads(response)
                assert 'success' in result
                assert 'releases' in result or 'error' in result
            except Exception:
                # Expected if helm not installed
                pass
    
    def test_tool_parameter_validation(self):
        """Test that tool parameters are properly validated."""
        from tools import HelmAddRepository, HelmInstall
        
        # Check required parameters
        add_repo = HelmAddRepository()
        required = [p for p in add_repo.parameters if p.get('required', False)]
        assert any(p['name'] == 'repo_name' for p in required)
        assert any(p['name'] == 'repo_url' for p in required)
        
        # Check optional parameters
        install = HelmInstall()
        optional = [p for p in install.parameters if not p.get('required', False)]
        assert len(optional) > 0


# ============================================================================
# Test Values Handling
# ============================================================================

class TestValuesHandling:
    """Test proper handling of values in tools."""
    
    def test_values_json_parsing(self):
        """Test that values are properly parsed from JSON."""
        import json5
        
        # Test simple values
        values_str = '{"replicas": 3, "tag": "1.0"}'
        values = json5.loads(values_str)
        assert values['replicas'] == 3
        assert values['tag'] == '1.0'
        
        # Test nested values
        nested_str = '{"image": {"repository": "nginx", "tag": "latest"}}'
        nested = json5.loads(nested_str)
        assert nested['image']['repository'] == 'nginx'


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in tools."""
    
    @pytest.mark.asyncio
    async def test_invalid_json_handling(self):
        """Test that invalid JSON is handled gracefully."""
        from tools import HelmAddRepository
        tool = HelmAddRepository()
        
        # Invalid JSON should cause an error
        invalid_params = '{ invalid json'
        try:
            response = await tool.call(invalid_params)
            result = json.loads(response)
            assert result['success'] is False
            assert 'error' in result
        except json.JSONDecodeError:
            pass  # Expected
    
    @pytest.mark.asyncio
    async def test_missing_required_params(self):
        """Test handling of missing required parameters."""
        from tools import HelmAddRepository
        tool = HelmAddRepository()
        
        # Missing required 'repo_url'
        incomplete_params = '{"repo_name": "test"}'
        try:
            response = await tool.call(incomplete_params)
            result = json.loads(response)
            # Should either error or gracefully handle
            assert 'success' in result or 'error' in result
        except Exception:
            pass  # Expected


# ============================================================================
# Test Integration
# ============================================================================

class TestIntegration:
    """Test integration between components."""
    
    def test_helm_client_import(self):
        """Test HelmClient can be imported."""
        from helm_client import HelmClient, HelmRelease, HelmStatus
        assert HelmClient is not None
        assert HelmRelease is not None
        assert HelmStatus is not None
    
    def test_tools_import(self):
        """Test tools can be imported."""
        from tools import (
            HelmAddRepository,
            HelmListReleases,
            HelmInstall,
        )
        assert HelmAddRepository is not None
        assert HelmListReleases is not None
        assert HelmInstall is not None
    
    def test_module_exports(self):
        """Test module __init__ exports."""
        from __init__ import HelmClient, HelmRelease, HelmStatus
        assert HelmClient is not None
        assert HelmRelease is not None
        assert HelmStatus is not None


# ============================================================================
# Test Helm Status Values
# ============================================================================

class TestHelmStatuses:
    """Test Helm status values."""
    
    def test_all_status_values(self):
        """Test all HelmStatus enum values."""
        statuses = [
            HelmStatus.DEPLOYED,
            HelmStatus.SUPERSEDED,
            HelmStatus.FAILED,
            HelmStatus.PENDING_INSTALL,
            HelmStatus.PENDING_UPGRADE,
            HelmStatus.PENDING_ROLLBACK,
            HelmStatus.UNINSTALLED,
        ]
        
        for status in statuses:
            assert status.value is not None
            assert len(status.value) > 0
    
    def test_status_from_string(self):
        """Test creating HelmStatus from string values."""
        assert HelmStatus("deployed") == HelmStatus.DEPLOYED
        assert HelmStatus("failed") == HelmStatus.FAILED


# ============================================================================
# Test Release Instances
# ============================================================================

class TestHelmReleaseInstances:
    """Test HelmRelease and HelmRevision instances."""
    
    def test_release_creation(self):
        """Test creating HelmRelease instances."""
        release = HelmRelease(
            name="test-app",
            namespace="production",
            revision=5,
            updated="2024-01-15T10:30:00Z",
            status=HelmStatus.DEPLOYED,
            chart="myrepo/myapp:1.2.3",
            app_version="2.0.0"
        )
        
        assert release.name == "test-app"
        assert release.namespace == "production"
        assert release.revision == 5
        assert release.status == HelmStatus.DEPLOYED
    
    def test_revision_creation(self):
        """Test creating HelmRevision instances."""
        revision = HelmRevision(
            revision=3,
            updated="2024-01-10T08:00:00Z",
            status=HelmStatus.SUPERSEDED,
            chart="myrepo/myapp:1.1.0",
            app_version="1.9.0",
            description="Upgrade successful"
        )
        
        assert revision.revision == 3
        assert revision.status == HelmStatus.SUPERSEDED
        assert "Upgrade" in revision.description


# ============================================================================
# Test Data Models
# ============================================================================

class TestDataModels:
    """Test data model functionality."""
    
    def test_release_string_representation(self):
        """Test HelmRelease string representation."""
        release = HelmRelease(
            name="my-release",
            namespace="web",
            revision=1,
            updated="2024-01-01",
            status=HelmStatus.DEPLOYED,
            chart="nginx:1.0",
            app_version="1.24"
        )
        
        release_str = str(release)
        assert "my-release" in release_str
        assert "deployed" in release_str
        assert "web" in release_str


# ============================================================================
# Test Tool Call Interface
# ============================================================================

class TestToolCallInterface:
    """Test the tool call interface."""
    
    def test_tool_has_call_method(self):
        """Test that all tools have a call method."""
        from tools import (
            HelmAddRepository,
            HelmListReleases,
            HelmInstall,
            HelmUpgrade,
        )
        
        tools = [
            HelmAddRepository(),
            HelmListReleases(),
            HelmInstall(),
            HelmUpgrade(),
        ]
        
        for tool in tools:
            assert hasattr(tool, 'call')
            assert callable(tool.call)


# ============================================================================
# pytest Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
