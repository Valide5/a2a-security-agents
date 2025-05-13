import asyncio
import json
import uuid
import httpx

async def test_hello_agent():
    """
    Test function to call the A2A hello agent directly.
    """
    print("Testing A2A hello agent...")
    
    # Update to match the endpoint in agents.json
    a2a_endpoint = "http://localhost:8002/a2a/analyzer/hello-a2a-analyzer-001"
    
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

if __name__ == "__main__":
    asyncio.run(test_hello_agent()) 
