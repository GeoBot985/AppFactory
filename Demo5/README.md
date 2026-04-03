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

### Manual Testing for Batch Ingestion (Spec 010)

**Case A — Multiple valid PDFs**
1. Select 3 PDFs.
2. Click **Ingest Selected Files**.
3. Confirm:
   - All succeed.
   - Individual chunk counts are displayed in the results area.
   - Documents appear in the corpus panel.
   - Debug panel shows `[INGEST BATCH]` with all 3 files.

**Case B — Mixed valid + invalid**
1. Select 2 valid + 1 corrupted/non-PDF file.
2. Click **Ingest Selected Files**.
3. Confirm:
   - Valid files succeed.
   - Invalid file fails cleanly with a red ✖ and error message.
   - Batch continues after the failure.
   - Results area shows all 3 statuses.

**Case C — Empty selection**
1. Click **Ingest Selected Files** with no files selected.
2. Confirm:
   - Button is disabled until files are selected.
   - If forced, clear message shown, no crash.

**Case D — Duplicate file**
1. Ingest a file.
2. Select the same file again and ingest.
3. Confirm:
   - Result shows "Skipped (duplicate)" with an orange ℹ.
   - Debug panel logs the reason as `duplicate`.
   - No new document is added to the corpus.

**Case E — Corpus refresh**
1. Ingest multiple files in one batch.
2. Confirm the corpus panel updates immediately after the batch completes.
3. Confirm any previous working set selection is preserved (if IDs still exist).

### Manual Testing for Corpus Panel + Working Set (Spec 009)

**Case A — Empty corpus**
1. Start app with no indexed documents.
2. Confirm corpus panel says "No indexed documents."
3. Confirm retrieval scope shows "Full corpus".
4. Normal chat still works.

**Case B — Single document**
1. Ingest one PDF.
2. Confirm one document card appears in the Corpus panel.
3. Select it (card should highlight).
4. Ask a related question.
5. Confirm retrieval scope in UI shows "Working set (1 documents)".
6. Confirm debug output shows `retrieval_scope: working_set` and `selected_documents_count: 1`.
7. Confirm results come from that document.

**Case C — Multiple documents, no selection**
1. Ingest multiple PDFs.
2. Leave all unselected.
3. Ask a question.
4. Confirm retrieval uses full corpus (check debug `retrieval_scope: full_corpus`).

**Case D — Multiple documents, subset selected**
1. Ingest 3+ PDFs.
2. Select only two cards.
3. Ask a question.
4. Confirm retrieval scope shows "Working set (2 documents)".
5. Confirm debug output names selected docs and returned source docs.

**Case E — Clear selection**
1. Select multiple documents.
2. Click **Clear Selection**.
3. Confirm working set empties (cards unhighlight).
4. Confirm retrieval scope returns to "Full corpus".

**Case F — Select All**
1. Click **Select All**.
2. Confirm all document cards are highlighted.
3. Confirm retrieval scope updates to "Working set (N documents)".

### Manual Testing for Chat Debug Panel

**Case A — Plain chat, empty DB**
1. Launch app with no indexed PDFs.
2. Ask a normal question.
3. Confirm:
   - App responds,
   - Debug panel shows RAG state as enabled but retrieved chunks count is 0,
   - Final prompt is visible.

**Case B — RAG chat**
1. Ingest a PDF.
2. Ask a related question.
3. Confirm:
   - Retrieved chunks are shown with their lengths,
   - Final prompt includes the retrieved context,
   - Model response preview is shown,
   - Selected model is shown.

**Case C — Retrieval failure**
1. Temporarily break the RAG logic (e.g. point to a missing DB or rename `rag.db`).
2. Ask a question.
3. Confirm:
   - Chat still works gracefully (without context),
   - Debug panel clearly shows `retrieval: <error message>` under Errors.

**Case D — Ollama failure**
1. Stop the Ollama server.
2. Submit a message.
3. Confirm:
   - No app crash,
   - Debug panel shows `ollama: <error message>` under Errors.

### Manual Test Path for Watcher (Spec 006)

**Case A — watcher enabled, plain chat**
1. Start app and ensure `WATCHER_ENABLED = True`.
2. Ask a normal question.
3. Confirm response works, debug shows watcher enabled, allowed = true, modified = false, and notes includes `pass_through`.

**Case B — watcher enabled, RAG chat**
1. Ingest a PDF.
2. Ask a question related to the PDF.
3. Confirm retrieval works, watcher sees assembled prompt, watcher section appears in debug, response still works normally.

**Case C — watcher disabled**
1. Set `WATCHER_ENABLED = False`.
2. Ask a question.
3. Confirm app still works, debug shows watcher skipped.

**Case D — simulated watcher failure**
1. Temporarily force an exception inside watcher.
2. Confirm app does not crash, watcher fails open, request reaches Ollama, and debug shows watcher error and fail-open note.

## Features Included in Phase 1
- FastAPI backend serving a lightweight single-page HTML frontend.
- Ollama local model discovery.
- Chat UI.
- Passive watcher intercepting `pre_ollama` and `post_ollama` stages, logging them to a structured trace context.
- Verbose structural debug output visible in the UI side panel.
