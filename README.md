# a2a-security-agents

This repository houses a collection of security analyzer agents built using the Google Agent2Agent (A2A) protocol. These agents function as A2A Servers, exposing specialized security analysis capabilities for various platforms to A2A-compliant clients.

The goal of this project is to provide modular, interoperable security analysis tools that can be easily integrated into multi-agent systems and workflows via the open A2A standard.

## Key Features

* **A2A Protocol Compliance:** Agents adhere to the Google Agent2Agent protocol for communication and discovery.
* **Platform-Specific Analysis:** Includes specialized agents for analyzing security configurations and posture on different cloud platforms (AWS, Azure, GCP, etc.).
* **Agent Card Discovery:** Each agent exposes an A2A Agent Card for dynamic capability discovery.
* **JSON-RPC Communication:** Utilizes JSON-RPC 2.0 over HTTP(S) for task submission and response.
* **Modular Design:** Agents are designed as independent services.


## Repository Contents

* **/agent_cards/**: Contains the JSON files defining the Agent Card for each analyzer agent.
* **/agents/**: Contains the implementation of each security analyzer agent.
* **/tests/**: Contains test scripts for verifying agent functionality.
* **a2a_server.py**: Main server implementation that handles A2A protocol requests.
* **agent_registry.py**: Registry system for dynamically loading and managing agents.
* **start_a2a_server.py**: Utility script to start the A2A server.

## Setup and Installation

1. Ensure you have Python 3.12+ installed
2. Install required dependencies:
3. Configure any agent-specific settings in their respective configuration files

## Usage

### Starting the A2A Server

```bash
python start_a2a_server.py
```

The server will start on port 8002 by default and expose endpoints for each registered agent.

### Testing Agents

```bash
# Run all tests
python -m tests.test_a2a_registry

# Test a specific agent
python -m tests.test_a2a_hello
```

### Agent Discovery

Agent capabilities can be discovered by accessing:
```
GET http://localhost:8002/.well-known/agent.json
```
