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
python main.py
```

4. **Access the web application:**
Open your browser and navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Manual Testing for RAG Integration
1. Start Ollama and ensure `nomic-embed-text` is available.
2. Launch app: `python main.py`
3. Click **Browse PDF** in the ingest panel and select a valid PDF file.
4. Click **Ingest PDF** and confirm:
   - Success status appears in the ingest panel.
   - Chunk count appears in the success message.
   - Debug panel logs ingestion details.
   - The document ID appears in the "Indexed docs" list.
5. Ask a question related to the PDF and confirm:
   - App responds using retrieved context,
   - Debug panel shows retrieved chunks in the RAG section.
6. Click **Ingest PDF** with no file selected (or cancel the browse dialog) and confirm it shows a clean message like "No PDF selected".
7. (Optional) Try ingesting an invalid or broken file and confirm the UI handles the failure gracefully.

## Features Included in Phase 1
- FastAPI backend serving a lightweight single-page HTML frontend.
- Ollama local model discovery.
- Chat UI.
- Passive watcher intercepting `pre_ollama` and `post_ollama` stages, logging them to a structured trace context.
- Verbose structural debug output visible in the UI side panel.
