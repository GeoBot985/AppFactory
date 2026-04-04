import os
import sys

# Ensure rag can be imported from Demo5 root if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.personal_db import (
    get_connection, init_personal_db, insert_personal_memory,
    resolve_personal_entities, retrieve_personal_memories,
    bootstrap_personal_data
)
from app.config import DB_PATH

def initialize_personal_service():
    conn = get_connection(DB_PATH)
    try:
        init_personal_db(conn)
        bootstrap_personal_data(conn)
    finally:
        conn.close()

def persist_user_input(text: str, session_id: str = None):
    conn = get_connection(DB_PATH)
    try:
        insert_personal_memory(conn, {
            "raw_user_input": text,
            "session_id": session_id,
            "mode": "personal"
        })
    finally:
        conn.close()

def get_personal_context(query: str, top_k: int = 5):
    conn = get_connection(DB_PATH)
    try:
        resolved_entities = resolve_personal_entities(conn, query)
        memories = retrieve_personal_memories(conn, query, top_k=top_k)
        return {
            "resolved_entities": resolved_entities,
            "memories": memories
        }
    finally:
        conn.close()
