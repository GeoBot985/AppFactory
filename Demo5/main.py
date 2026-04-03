from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
import time

from models import ChatRequest, ChatResponse, TurnContext
from ollama_client import get_models, chat as ollama_chat
from watcher import PassiveWatcher
from app.services.rag_service import get_rag_context

RAG_ENABLED = True

app = FastAPI(title="Demo5 Passive Watcher Chat")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

watcher = PassiveWatcher()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

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
    rag_debug = {"enabled": False}
    final_prompt = request.message
    if RAG_ENABLED:
        rag_result = get_rag_context(request.message, top_k=3)
        rag_debug = {
            "enabled": True,
            "query": request.message,
            "chunks_returned": len(rag_result.get("chunks", [])),
            "error": rag_result.get("error"),
            "chunks": [chunk[:300] for chunk in rag_result.get("chunks", [])]
        }

        if rag_result.get("chunks"):
            context_blocks = "\n\n".join([f"[Chunk {i+1}]\n{chunk}" for i, chunk in enumerate(rag_result["chunks"])])
            final_prompt = f"You are a helpful assistant.\n\nUse the following retrieved context if it is relevant to the user's question.\nIf it is not relevant, ignore it.\n\nRetrieved context:\n{context_blocks}\n\nUser question:\n{request.message}"

    # 3. Call Ollama
    ollama_response, request_summary, error = await ollama_chat(request.model, final_prompt)
    context.ollama_request_summary = request_summary

    reply_text = ""
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
    preview = request.message[:50] + ("..." if len(request.message) > 50 else "")

    debug_trace = {
        "selected_model": request.model,
        "user_message_preview": preview,
        "watcher_pre_result": [e.model_dump() for e in context.watcher_events if e.stage == "pre_ollama"][0] if any(e.stage == "pre_ollama" for e in context.watcher_events) else None,
        "rag": rag_debug,
        "ollama_request_summary": context.ollama_request_summary,
        "ollama_response_summary": context.ollama_response_summary,
        "watcher_post_result": [e.model_dump() for e in context.watcher_events if e.stage == "post_ollama"][0] if any(e.stage == "post_ollama" for e in context.watcher_events) else None,
        "elapsed_time_ms": elapsed_ms,
        "error": context.error
    }

    return ChatResponse(
        reply=reply_text,
        debug=debug_trace
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
