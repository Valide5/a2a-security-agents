from typing import Dict, Any, Optional
from datetime import datetime
import logging
from agent_registry import BaseA2AAgent, register_agent

logger = logging.getLogger(__name__)

@register_agent('hello-a2a-analyzer-001', 'greet')
class HelloAgentAnalyzer(BaseA2AAgent):
    """
    A simple Hello Agent that demonstrates A2A integration.
    """
    
    async def analyze(self, agent_id: str, skill_id: str, parameters: Dict[str, Any], 
                     request_context: Dict[str, Any], task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simple hello test analyzer that greets the user with the provided name.
        """
        logger.info(f"Performing hello analysis with parameters: {parameters}")
        
        try:
            # Extract name from parameters or use default
            name = parameters.get("name", "World")
            message = parameters.get("message", "Hello from A2A!")
            
            # Return greeting response
            return {
                "status": "success",
                "greeting": f"Hello, {name}!",
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "request_context": request_context,
                "input_parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error performing hello analysis: {str(e)}")
            return {
                "status": "error",
                "error_message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            } 