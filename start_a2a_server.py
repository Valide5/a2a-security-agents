import uvicorn
import logging
import os
import sys

# Ensure the current directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Make sure the agents directory exists
    agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agents')
    if not os.path.exists(agents_dir):
        logger.warning(f"Creating agents directory: {agents_dir}")
        os.makedirs(agents_dir, exist_ok=True)
    
    # Check if agent_cards directory exists
    agent_cards_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_cards')
    if not os.path.exists(agent_cards_dir):
        logger.warning(f"Creating agent_cards directory: {agent_cards_dir}")
        os.makedirs(agent_cards_dir, exist_ok=True)
    
    print("Starting A2A server on http://localhost:8002")
    print("Available endpoints:")
    print("- Agent endpoints: http://localhost:8002/a2a/analyzer/{agent_id}")
    print("- Agent card: http://localhost:8002/.well-known/agent.json")
    print("- Agent-specific cards: http://localhost:8002/.well-known/agent-cards/{card_name}")
    
    # Start the server
    uvicorn.run("a2a_server:app", host="0.0.0.0", port=8002, reload=True) 