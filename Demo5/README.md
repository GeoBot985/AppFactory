# Demo5: Passive Watcher Chat Shell

This is Phase 1 of the Demo5 application. It provides a minimal working local web app that connects to a local Ollama instance, discovers available models, allows a user to send chat messages, and routes requests through a passive watcher layer before interacting with the LLM. It includes a side panel for structured debug tracing.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally on the default port (`http://localhost:11434`)
- At least one model pulled in Ollama (e.g. `ollama run qwen2.5-coder:7b`)

## Setup Instructions

1. **Create and activate a virtual environment:**

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

2. **Install requirements:**

```bash
pip install -r requirements.txt
```

3. **Run the application:**

```bash
python app.py
```

4. **Access the web application:**
Open your browser and navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Features Included in Phase 1
- FastAPI backend serving a lightweight single-page HTML frontend.
- Ollama local model discovery.
- Chat UI.
- Passive watcher intercepting `pre_ollama` and `post_ollama` stages, logging them to a structured trace context.
- Verbose structural debug output visible in the UI side panel.
