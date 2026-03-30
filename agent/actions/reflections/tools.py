import json
import asyncio
import json5
import os
from typing import Optional, Callable, Any
from qwen_agent.tools.base import BaseTool, register_tool

# ============================================================================
# Prompt Update Tools
# ============================================================================

class ReflectivePromptOptimzer():
    def __init__(self, goal_config_path):
        self.config_path = config_path

    def update_user_prompt_template():
        pass

    

@register_tool('update-user-prompt')
class OptimizerUpdateUserPromptTemplate(BaseTool):
    
    description = 'Update current agent user prompt template.'
    parameters = [
        {
            'name': 'updated prompt',
            'type': 'string',
            'description': 'Updated prompt',
            'required': True
        },
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