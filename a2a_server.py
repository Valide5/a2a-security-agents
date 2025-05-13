from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import os
import logging
import asyncio
import glob
from datetime import datetime
from typing import Any, Dict, Optional, List, Set
from agent_registry import load_agents, get_agent, BaseA2AAgent

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app with the correct path prefix
app = FastAPI()

# Load all agent implementations
try:
    load_agents()
    logger.info("Successfully loaded A2A agents")
except Exception as e:
    logger.error(f"Error loading A2A agents: {str(e)}")

# Load the Agent Cards
AGENT_CARDS_DIR = "agent_cards"
AGENT_CARDS = {}
AGENT_TO_CARD_MAP = {}

def load_agent_cards():
    """
    Load all agent cards from the agent_cards directory.
    """
    try:
        # Ensure the directory exists
        if not os.path.exists(AGENT_CARDS_DIR):
            os.makedirs(AGENT_CARDS_DIR, exist_ok=True)
            logger.warning(f"Created agent_cards directory: {AGENT_CARDS_DIR}")
            return
            
        # Find all JSON files in the agent_cards directory
        card_files = glob.glob(os.path.join(AGENT_CARDS_DIR, "*.json"))
        if not card_files:
            logger.warning(f"No agent card files found in {AGENT_CARDS_DIR}")
            return
            
        for card_file in card_files:
            try:
                with open(card_file, "r") as f:
                    card_data = json.load(f)
                    card_name = os.path.basename(card_file)
                    AGENT_CARDS[card_name] = card_data
                    
                    # Map each agent_id to its card
                    for agent_id in card_data.get("agent_ids", []):
                        AGENT_TO_CARD_MAP[agent_id] = card_name
                        
                    logger.info(f"Loaded agent card: {card_name}")
            except Exception as e:
                logger.error(f"Error loading agent card {card_file}: {str(e)}")
                
        logger.info(f"Successfully loaded {len(AGENT_CARDS)} agent cards")
    except Exception as e:
        logger.error(f"Error loading agent cards: {str(e)}")

# Load agent cards at startup
load_agent_cards()

# Cross-validate agent IDs between registry and cards
def validate_agents_and_cards():
    """
    Validates agent cards and registered implementations, logging warnings for mismatches.
    """
    # Get all agent_ids from cards
    card_agent_ids = set()
    for card_name, card_data in AGENT_CARDS.items():
        for agent_id in card_data.get("agent_ids", []):
            if not agent_id.endswith("_coming_soon"):
                card_agent_ids.add(agent_id)
    
    # Get all agent_ids from registry
    from agent_registry import _agent_registry
    registry_agent_ids = set(_agent_registry.keys())
    
    # Find mismatches
    missing_implementations = card_agent_ids - registry_agent_ids
    if missing_implementations:
        logger.warning(f"Agent cards reference {len(missing_implementations)} agent IDs with no implementations: {missing_implementations}")
    
    missing_cards = registry_agent_ids - card_agent_ids
    if missing_cards:
        logger.warning(f"Agent registry contains {len(missing_cards)} agent IDs not included in any card: {missing_cards}")
        
    logger.info(f"Agent validation complete: {len(registry_agent_ids)} implementations, {len(card_agent_ids)} references in cards")

# Run validation
validate_agents_and_cards()

# --- A2A Server Endpoints ---

@app.get("/.well-known/agent.json")
async def get_agent_card():
    """
    Exposes the default Agent Card at the /.well-known/agent.json path.
    This aggregates all agent cards into one for backward compatibility.
    """
    logger.info("Default Agent Card requested")
    if not AGENT_CARDS:
        logger.error("No agent cards loaded, returning 500 error")
        raise HTTPException(status_code=500, detail="No agent cards loaded.")
        
    # Create an aggregated agent card
    aggregated_card = {
        "name": "Valide5 A2A Agent Hub",
        "description": "Provides multiple security analysis capabilities via A2A protocol",
        "url": "YOUR_SERVER_BASE_URL",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False
        },
        "authentication": None,
        "defaultInputModes": ["text", "json"],
        "defaultOutputModes": ["json"],
        "skills": []
    }
    
    # Keep track of skills by a compound key of card name + skill ID
    # This prevents skills with the same ID from different agents from being merged
    seen_skills = {}
    
    # Combine skills from all agent cards
    for card_name, card_data in AGENT_CARDS.items():
        for skill in card_data.get("skills", []):
            skill_id = skill.get("id")
            # Create a unique identifier for each skill by combining card name and skill ID
            unique_skill_key = f"{card_name}:{skill_id}"
            
            # If this is a new skill, add it to the aggregated card
            if unique_skill_key not in seen_skills:
                # Create a copy of the skill to avoid modifying the original
                skill_copy = skill.copy()
                
                # Prepend the card name to the skill name for clarity in the aggregated view
                card_prefix = card_data.get("name", "").split(" Agent")[0]
                if card_prefix and not skill_copy.get("name", "").startswith(card_prefix):
                    skill_copy["name"] = f"{card_prefix} - {skill_copy.get('name', skill_id)}"
                
                aggregated_card["skills"].append(skill_copy)
                seen_skills[unique_skill_key] = True
                logger.debug(f"Added skill '{skill_copy.get('name')}' from card '{card_name}'")
    
    # Log the total count of skills added to the aggregated card
    logger.info(f"Created aggregated agent card with {len(aggregated_card['skills'])} skills")
    return JSONResponse(content=aggregated_card)

@app.get("/.well-known/agent-cards/{card_name}")
async def get_specific_agent_card(card_name: str):
    """
    Exposes a specific Agent Card by name.
    """
    if card_name not in AGENT_CARDS:
        raise HTTPException(status_code=404, detail=f"Agent card {card_name} not found")
    
    return JSONResponse(content=AGENT_CARDS[card_name])

@app.get("/.well-known/agent-cards")
async def list_agent_cards():
    """
    Lists all available agent cards.
    """
    return JSONResponse(content={
        "agent_cards": list(AGENT_CARDS.keys()),
        "agent_mappings": AGENT_TO_CARD_MAP
    })

@app.post("/a2a/analyzer/{agent_id}")
async def handle_agent_specific_request(agent_id: str, request: Request):
    """
    Handles incoming A2A JSON-RPC requests at agent-specific endpoints.
    The agent_id is extracted from the URL path.
    """
    logger.info(f"Received request for agent_id: {agent_id}")
    
    # Check if agent_id is registered but marked as "coming soon"
    if agent_id.endswith("_coming_soon"):
        return JSONResponse(
            status_code=503,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32001, 
                    "message": f"Agent {agent_id} is coming soon and not yet implemented"
                },
                "id": None
            }
        )
    
    try:
        payload = await request.json()
        logger.info(f"Received A2A request payload: {json.dumps(payload, indent=2)}")

        # Validate JSON-RPC 2.0 structure
        if payload.get("jsonrpc") != "2.0":
            logger.error("Invalid JSON-RPC version")
            raise ValueError("Invalid JSON-RPC version")

        method = payload.get("method")
        params = payload.get("params")
        request_id = payload.get("id") # Can be null for notifications, but A2A tasks typically have an id

        logger.info(f"JSON-RPC method: {method}, request_id: {request_id}")

        if not method:
            logger.error("Method field is missing")
            raise ValueError("Method field is missing")

        # Handle A2A methods
        if method == "tasks/send":
            logger.info("Processing tasks/send method")
            
            # Use the agent_id from the path to override the agent_id in the payload
            task = params.get("task", {})
            messages = task.get("messages", [])
            if messages and len(messages) > 0:
                user_message = messages[0]
                if user_message.get("role") == "user" and user_message.get("parts"):
                    for part in user_message.get("parts", []):
                        if part.get("json"):
                            json_part = part.get("json", {})
                            # Log if there's a mismatch between path and payload agent_id
                            payload_agent_id = json_part.get("agent_id")
                            if payload_agent_id and payload_agent_id != agent_id:
                                logger.warning(f"Agent ID mismatch: path={agent_id}, payload={payload_agent_id}")
                            # Always use the agent_id from the path
                            json_part["agent_id"] = agent_id
            
            response_payload = await handle_send_task(params, request_id)
        # Add handlers for other A2A methods if needed (e.g., tasks/get, tasks/cancel)
        # elif method == "tasks/get":
        #     response_payload = await handle_get_task(params, request_id)
        else:
            # Method not found
            logger.error(f"Method not found: {method}")
            response_payload = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
                "id": request_id
            }

        logger.info(f"Sending response: {json.dumps(response_payload, indent=2)}")
        return JSONResponse(content=response_payload)

    except json.JSONDecodeError:
        logger.error("JSON parse error")
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }
        )
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": f"Invalid Request: {e}"},
                "id": payload.get("id") if isinstance(payload, dict) else None
            }
        )
    except Exception as e:
        logger.error(f"An error occurred while processing A2A request: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {e}"},
                "id": payload.get("id") if isinstance(payload, dict) else None
            }
        )

# --- A2A Method Handlers ---

async def handle_send_task(params: Optional[Dict[str, Any]], request_id: Any) -> Dict[str, Any]:
    """
    Handles the 'tasks/send' A2A method.
    """
    logger.info("Processing tasks/send parameters")
    if not params or "task" not in params:
        logger.error("Missing 'task' in params for tasks/send")
        raise ValueError("Missing 'task' in params for tasks/send")

    task = params.get("task")
    task_id = task.get("task_id")
    messages = task.get("messages")
    task_context = task.get("context") # Optional task-level context

    logger.info(f"Task ID: {task_id}")
    logger.debug(f"Task context: {task_context}")

    if not task_id or not isinstance(messages, list) or not messages:
         logger.error("Invalid or missing fields in task object")
         raise ValueError("Invalid or missing fields in task object")

    # Assuming the relevant information is in the first user message's json part
    user_message = messages[0] # Get the initial user message
    if user_message.get("role") != "user" or not isinstance(user_message.get("parts"), list) or not user_message["parts"]:
         logger.error("Invalid initial user message format")
         raise ValueError("Invalid initial user message format")

    # Find the JSON part containing agent_id, skill_id, parameters, context
    task_details = None
    for part in user_message["parts"]:
        if part.get("json") is not None:
            task_details = part["json"]
            break

    if not task_details:
         logger.error("Missing JSON part with task details in user message")
         raise ValueError("Missing JSON part with task details in user message")

    agent_id = task_details.get("agent_id")
    skill_id = task_details.get("skill_id", "analyze")
    parameters = task_details.get("parameters", {})
    request_context = task_details.get("context", {}) # Context from the client request payload
    
    logger.info(f"Received task_id: {task_id}, agent_id: {agent_id}, skill_id: {skill_id}")
    logger.info(f"Parameters: {parameters}")
    logger.debug(f"Context: {request_context}")

    # Get agent implementation from registry
    agent_class = get_agent(agent_id, skill_id)
    
    if agent_class:
        # Use registered agent implementation
        logger.info(f"Using registered agent implementation for agent_id '{agent_id}', skill_id '{skill_id}'")
        agent = agent_class()
        analysis_results = await agent.analyze(agent_id, skill_id, parameters, request_context, task_context)
    else:
        # Fallback to default analysis
        logger.warning(f"No registered agent found for agent_id '{agent_id}', skill_id '{skill_id}'. Using fallback.")
        analysis_results = await perform_default_analysis(agent_id, skill_id, parameters, request_context, task_context)

    # Construct the A2A response payload
    # A successful tasks/send response typically returns the updated Task object
    response_task = {
        "task_id": task_id,
        "status": {
            "state": "completed" # Or "failed", "working", "input-required"
            # Add error details if state is "failed"
            # "error": { ... }
        },
        "messages": messages + [ # Include original messages + agent's reply
            {
                "role": "agent",
                "parts": [
                    {
                        "text": "Analysis completed.",
                        "json": analysis_results # Include the analysis results as a JSON part
                    }
                ]
            }
        ],
        "context": task_context # Include original task-level context
        # Add artifacts if the analysis generated files or other artifacts
        # "artifacts": [ ... ]
    }

    logger.info("Successfully created response task")
    logger.debug(f"Response task: {response_task}")

    return {
        "jsonrpc": "2.0",
        "result": {
            "task": response_task
        },
        "id": request_id
    }

# --- Default Analysis Fallback ---
async def perform_default_analysis(agent_id: str, skill_id: str, parameters: Dict[str, Any], 
                                 request_context: Dict[str, Any], task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fallback function when no specific agent implementation is found.
    Returns a generic response with error information.
    """
    logger.warning(f"Using default analysis fallback for agent_id '{agent_id}', skill_id '{skill_id}'")
    
    # Simulate some analysis work
    await asyncio.sleep(1)

    # Return dummy analysis results
    results = {
        "status": "warning",
        "message": f"No specific agent implementation found for agent_id '{agent_id}', skill_id '{skill_id}'",
        "timestamp": datetime.utcnow().isoformat(),
        "agent_id": agent_id,
        "skill_id": skill_id,
        "parameters_received": parameters
    }
    
    logger.info("Default analysis complete")
    return results

# --- To run the server ---
# Save the above code as a2a_server.py and the agent_cards directory in the same directory.
# Run from your terminal:
# uvicorn a2a_server:app --host 0.0.0.0 --port 8002
# The server will run on http://localhost:8002 with agent-specific endpoints.
