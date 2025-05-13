import asyncio
import json
import uuid
import httpx
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_registry import load_agents, get_agent, _agent_registry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_hello_agent():
    """
    Test function to call the A2A hello agent directly.
    """
    print("\nTesting Hello A2A Agent...")
    
    # Update to match the endpoint in agents.json
    a2a_endpoint = "http://localhost:8002/a2a/execute"
    
    # Create a unique task ID and request ID
    task_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    # Create the A2A request payload
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "task": {
                "task_id": task_id,
                "messages": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": "Please greet the user with the provided name."},
                            {
                                "json": {
                                    "agent_id": "hello-a2a-analyzer-001",
                                    "skill_id": "greet",
                                    "parameters": {
                                        "name": "Test User",
                                        "message": "This is a test message from the client."
                                    },
                                    "context": {
                                        "workflow_id": "test-workflow-id",
                                        "node_id": "test-node-id",
                                        "deployment_id": "test-deployment-id",
                                        "activity_key": "test-activity-key"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        },
        "id": request_id
    }
    
    try:
        print(f"Sending request to {a2a_endpoint}...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(a2a_endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
            
        print(f"Response status code: {response.status_code}")
        print(f"Response JSON: {json.dumps(result, indent=2)}")
        
        # Extract the greeting from the response
        if "result" in result and "task" in result["result"]:
            task = result["result"]["task"]
            agent_messages = [msg for msg in task["messages"] if msg.get("role") == "agent"]
            if agent_messages:
                for part in agent_messages[0].get("parts", []):
                    if "json" in part:
                        print("\nExtracted greeting:")
                        print(f"Greeting: {part['json'].get('greeting')}")
                        print(f"Message: {part['json'].get('message')}")
                        print(f"Status: {part['json'].get('status')}")
        
        return result
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}")
    except Exception as e:
        print(f"Error: {e}")

async def test_aws_account_analysis():
    """
    Test function to call the AWS Account Analysis A2A agent.
    """
    print("\nTesting AWS Account Analysis A2A Agent...")
    
    # Update to match the endpoint in agents.json
    a2a_endpoint = "http://localhost:8002/a2a/analyzer/aws_account_analysis-a2a"
    
    # Create a unique task ID and request ID
    task_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    # Create the A2A request payload
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "task": {
                "task_id": task_id,
                "messages": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": "Please analyze AWS external access."},
                            {
                                "json": {
                                    "agent_id": "aws_account_analysis-a2a",
                                    "skill_id": "analyze",
                                    "parameters": {
                                        "trusted_accounts_file": "trusted_accounts.yaml"
                                    },
                                    "context": {
                                        "workflow_id": "test-workflow-id",
                                        "node_id": "test-node-id",
                                        "deployment_id": "test-deployment-id",
                                        "activity_key": "test-activity-key"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        },
        "id": request_id
    }
    
    try:
        print(f"Sending request to {a2a_endpoint}...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(a2a_endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
            
        print(f"Response status code: {response.status_code}")
        print(f"Response summary: {result.get('result', {}).get('task', {}).get('status', {}).get('state', 'unknown')}")
        
        return result
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}")
    except Exception as e:
        print(f"Error: {e}")

async def test_aws_ec2_eye():
    """
    Test function to call the AWS EC2 Eye A2A agent.
    """
    print("\nTesting AWS EC2 Eye A2A Agent...")
    
    # Update to match the endpoint in agents.json
    a2a_endpoint = "http://localhost:8002/a2a/analyzer/aws_ec2_eye-a2a"
    
    # Create a unique task ID and request ID
    task_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    # Create the A2A request payload
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "task": {
                "task_id": task_id,
                "messages": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": "Please analyze AWS EC2 images."},
                            {
                                "json": {
                                    "agent_id": "aws_ec2_eye-a2a",
                                    "skill_id": "analyze",
                                    "parameters": {
                                        "AWS Access Key": {
                                            "value": "test-access-key",
                                            "is_encrypted": True
                                        },
                                        "AWS Secret Key": {
                                            "value": "test-secret-key",
                                            "is_encrypted": True
                                        },
                                        "regions": ["us-east-1", "us-west-2"],
                                        "trusted_accounts": ["123456789012"]
                                    },
                                    "context": {
                                        "workflow_id": "test-workflow-id",
                                        "node_id": "test-node-id",
                                        "deployment_id": "test-deployment-id",
                                        "activity_key": "test-activity-key"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        },
        "id": request_id
    }
    
    try:
        print(f"Sending request to {a2a_endpoint}...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(a2a_endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
            
        print(f"Response status code: {response.status_code}")
        print(f"Response summary: {result.get('result', {}).get('task', {}).get('status', {}).get('state', 'unknown')}")
        
        return result
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}")
    except Exception as e:
        print(f"Error: {e}")

def list_registered_agents():
    """
    List all registered agents in the registry.
    """
    print("\nLoading agent registry...")
    try:
        # Load all agent implementations
        load_agents()
        
        print(f"\nRegistered agents ({len(_agent_registry)}):")
        for agent_id, skills in _agent_registry.items():
            print(f"  Agent: {agent_id}")
            for skill_id, agent_class in skills.items():
                print(f"    Skill: {skill_id} - Class: {agent_class.__name__}")
    except Exception as e:
        print(f"Error loading agents: {e}")

if __name__ == "__main__":
    # First, list all registered agents
    list_registered_agents()
    
    # Check if we should run the tests
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\nRunning tests...")
        asyncio.run(test_hello_agent())
        asyncio.run(test_aws_account_analysis())
        asyncio.run(test_aws_ec2_eye()) 