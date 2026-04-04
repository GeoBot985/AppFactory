from fastapi import FastAPI, Request, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
import time
import os
import shutil
import uuid

from models import ChatRequest, ChatResponse, TurnContext
from ollama_client import get_models, chat as ollama_chat
from watcher import PassiveWatcher
from app.services.rag_service import (
    get_rag_context, list_indexed_documents, delete_document_service,
    clear_corpus_service, get_corpus_stats_service
)
from app.services.ingest_service import ingest_file
from app.services.watcher import inspect_chat_request, ChatRequestPayload
from app.services.prompt_builder import build_grounded_prompt
from app.services.session_grounding import build_session_grounding, get_session_grounding

RAG_ENABLED = True
WATCHER_ENABLED = True

app = FastAPI(title="Demo5 Passive Watcher Chat")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

watcher = PassiveWatcher()

@app.on_event("startup")
async def startup_event():
    await build_session_grounding()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/grounding")
async def api_grounding():
    grounding = get_session_grounding()
    return grounding

@app.post("/api/ingest")
async def api_ingest(file: UploadFile = File(...)):
    # Save the uploaded file temporarily
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    filename = file.filename or "upload.pdf"
    safe_name = os.path.basename(filename)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")

    # Extension validation
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in [".pdf", ".docx"]:
        return JSONResponse(content={
            "ok": False,
            "status": "failed",
            "error": "Unsupported file type. Supported types: PDF, DOCX."
        })

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = ingest_file(temp_path, document_name=safe_name)
    finally:
        await file.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return JSONResponse(content=result)

@app.get("/api/docs")
async def api_docs():
    result = list_indexed_documents()
    return result

@app.delete("/api/docs/{document_id}")
async def api_delete_doc(document_id: str):
    result = delete_document_service(document_id)
    return result

@app.post("/api/docs/clear")
async def api_clear_corpus():
    result = clear_corpus_service()
    return result

@app.get("/api/stats")
async def api_stats():
    result = get_corpus_stats_service()
    return result

@app.get("/api/models")
async def api_models():
    models, error = await get_models()
    if error:
        # We don't crash, we just return the error gracefully.
        return JSONResponse(content={"models": [], "error": error}, status_code=200)
    return {"models": models}

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest):
    start_time = time.time()

    # 1. Create TurnContext
    context = TurnContext(
        model=request.model,
        user_message=request.message,
        request_started_at=datetime.now(timezone.utc).isoformat()
    )

    # 2. Watcher Pre-check
    watcher.pre_check(context)

    # RAG Integration
    retrieval_query = None
    retrieval_chunks = []
    retrieval_metrics = None
    retrieval_error = None
    final_prompt = request.message
    skip_llm = False
    reply_text = ""

    if RAG_ENABLED:
        rag_result = get_rag_context(request.message, top_k=3, document_ids=request.document_ids)
        retrieval_query = request.message
        retrieval_error = rag_result.get("error")
        retrieval_chunks = rag_result.get("chunks", [])
        retrieval_metrics = rag_result.get("metrics")

        if not retrieval_chunks and not retrieval_error:
            # Fallback if corpus is empty or nothing retrieved
            skip_llm = True
            reply_text = "Insufficient information. No relevant information found in the selected documents."
            final_prompt = "No context provided."
        elif retrieval_chunks:
            final_prompt = build_grounded_prompt(request.message, retrieval_chunks)

    # 2.5 Watcher Module
    watcher_allowed = None
    watcher_modified = None
    watcher_notes = []
    watcher_error = None
    watcher_rule_results = []

    if WATCHER_ENABLED:
        payload: ChatRequestPayload = {
            "user_message": request.message,
            "selected_model": request.model,
            "rag_enabled": RAG_ENABLED,
            "retrieval_query": retrieval_query,
            "retrieval_chunks": retrieval_chunks,
            "retrieval_error": retrieval_error,
            "final_prompt": final_prompt
        }

        watcher_result = inspect_chat_request(payload)

        watcher_allowed = watcher_result.get("allowed")
        watcher_modified = watcher_result.get("modified")
        watcher_notes = watcher_result.get("watcher_notes", [])
        watcher_error = watcher_result.get("watcher_error")
        watcher_rule_results = watcher_result.get("rule_results", [])

        final_prompt = watcher_result.get("payload", payload).get("final_prompt", final_prompt)

    # 3. Call Ollama
    if not skip_llm:
        ollama_response, request_summary, error = await ollama_chat(request.model, final_prompt, temperature=0.1)
        context.ollama_request_summary = request_summary

        if error:
            context.error = error
            reply_text = f"Error: {error}"
        else:
            # Simplify response summary to keep it clean
            context.ollama_response_summary = {
                "model": ollama_response.get("model"),
                "created_at": ollama_response.get("created_at"),
                "done": ollama_response.get("done"),
                "total_duration": ollama_response.get("total_duration")
            }
            reply_text = ollama_response.get("message", {}).get("content", "")

    # 4. Watcher Post-check
    watcher.post_check(context)

    end_time = time.time()
    elapsed_ms = round((end_time - start_time) * 1000, 2)

    # 5. Build structured debug trace
    response_preview = reply_text[:100] + ("..." if len(reply_text) > 100 else "") if reply_text else None

    # Handle RAG scope for debug
    retrieval_scope = "full_corpus"
    selected_documents_count = 0
    selected_documents_names = []

    if request.document_ids:
        retrieval_scope = "working_set"
        selected_documents_count = len(request.document_ids)

        # Try to resolve document names from chunks or recent docs
        # We can map ID -> Name from the retrieval_chunks if any matched
        # Or from a quick lookup if needed. For now, let's use the chunks metadata.
        id_to_name = {chunk['document_id']: chunk['document_name'] for chunk in retrieval_chunks}

        selected_documents_names = []
        for doc_id in request.document_ids:
            name = id_to_name.get(doc_id, doc_id) # Fallback to ID if not in retrieved chunks
            selected_documents_names.append(name)

    debug_payload = {
        "grounding": get_session_grounding(),
        "user_message": request.message,
        "selected_model": request.model,
        "rag_enabled": RAG_ENABLED,
        "retrieval_scope": retrieval_scope,
        "selected_documents_count": selected_documents_count,
        "selected_documents_names": selected_documents_names,
        "retrieval_query": retrieval_query,
        "retrieval_chunks": retrieval_chunks,
        "retrieval_metrics": retrieval_metrics,
        "retrieval_error": retrieval_error,
        "watcher_enabled": WATCHER_ENABLED,
        "watcher_allowed": watcher_allowed,
        "watcher_modified": watcher_modified,
        "watcher_notes": watcher_notes,
        "watcher_error": watcher_error,
        "watcher_rule_results": watcher_rule_results,
        "final_prompt": final_prompt,
        "ollama_error": context.error,
        "response_preview": response_preview
    }

    return ChatResponse(
        reply=reply_text,
        evidence=retrieval_chunks if RAG_ENABLED else None,
        debug=debug_payload
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
