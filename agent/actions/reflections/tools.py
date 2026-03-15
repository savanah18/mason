import json
import asyncio
import json5
import os
from typing import Optional, Callable, Any
from qwen_agent.tools.base import BaseTool, register_tool

# ============================================================================
# Prompt Update Tools
# ============================================================================

@register_tool('update-base-prompt')
class OptimizerUpdatePrompt(BaseTool):
    
    description = 'Update current agent base prompt.'
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
    ]

    def call(self, params: str, **kwargs) -> str:
        async def _async_call():
            try:
                args = parse_params(params)
                client = HelmClient()
                
                success = await client.add_repository(
                    name=args['repo_name'],
                    url=args['repo_url'],
                    username=args.get('username'),
                    password=args.get('password'),
                    force_update=True
                )
                
                if success:
                    return json5.dumps({
                        'success': True,
                        'message': f"Repository '{args['repo_name']}' added/updated successfully"
                    }, ensure_ascii=False)
                else:
                    return json5.dumps({
                        'success': False,
                        'message': f"Failed to add repository '{args['repo_name']}'"
                    }, ensure_ascii=False)
            except Exception as e:
                return json5.dumps({
                    'success': False,
                    'error': str(e)
                }, ensure_ascii=False)
        
        return run_async(_async_call)