from typing import Dict, Type, Callable, Any, Optional
import importlib
import pkgutil
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Base Agent class
class BaseA2AAgent(ABC):
    @abstractmethod
    async def analyze(self, agent_id: str, skill_id: str, parameters: Dict[str, Any], 
                     request_context: Dict[str, Any], task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform analysis and return results"""
        pass

# Registry to store agent implementations
_agent_registry: Dict[str, Dict[str, Type[BaseA2AAgent]]] = {}

def register_agent(agent_id: str, skill_id: str = "analyze") -> Callable:
    """Decorator to register an agent implementation"""
    def decorator(cls):
        if not issubclass(cls, BaseA2AAgent):
            raise TypeError(f"Class {cls.__name__} must inherit from BaseA2AAgent")
        
        if agent_id not in _agent_registry:
            _agent_registry[agent_id] = {}
            
        _agent_registry[agent_id][skill_id] = cls
        logger.info(f"Registered A2A agent '{cls.__name__}' for agent_id '{agent_id}', skill_id '{skill_id}'")
        return cls
    return decorator

def get_agent(agent_id: str, skill_id: str = "analyze") -> Optional[Type[BaseA2AAgent]]:
    """Get agent implementation by agent_id and skill_id"""
    if agent_id in _agent_registry and skill_id in _agent_registry[agent_id]:
        return _agent_registry[agent_id][skill_id]
    return None

def load_agents() -> None:
    """Dynamically load all agent implementations"""
    agents_package = 'agents'
    try:
        # Import the agents package
        agents_module = importlib.import_module(agents_package)
        agents_path = agents_module.__path__
        
        # Discover and import all modules in the agents package
        for _, name, is_pkg in pkgutil.iter_modules(agents_path):
            try:
                importlib.import_module(f'{agents_package}.{name}')
                logger.debug(f"Loaded agent module: {name}")
            except ImportError as e:
                logger.error(f"Failed to import agent {name}: {str(e)}")
                
        logger.info(f"Loaded {len(_agent_registry)} A2A agents")
    except ImportError as e:
        logger.error(f"Failed to load agents package: {str(e)}") 