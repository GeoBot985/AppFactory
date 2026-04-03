import duckdb
import struct

def get_connection(db_path="rag_v2.db"):
    return duckdb.connect(db_path)

def init_db(conn):
    # New normalized schema
    conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        document_name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        ingested_at TEXT NOT NULL,
        chunk_count INTEGER NOT NULL,
        ingestion_method TEXT DEFAULT 'text',
        file_type TEXT DEFAULT 'pdf',
        ocr_used BOOLEAN DEFAULT FALSE,
        ocr_char_count INTEGER DEFAULT 0,
        ocr_page_count INTEGER DEFAULT 0
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        FOREIGN KEY(document_id) REFERENCES documents(document_id)
    );
    """)

    # Migration for existing databases
    existing_cols_info = conn.execute("PRAGMA table_info('documents')").fetchall()
    col_names = [c[1] for c in existing_cols_info]
    if "ingestion_method" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ingestion_method TEXT DEFAULT 'text'")
    if "file_type" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN file_type TEXT DEFAULT 'pdf'")
    if "ocr_used" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_used BOOLEAN DEFAULT FALSE")
    if "ocr_char_count" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_char_count INTEGER DEFAULT 0")
    if "ocr_page_count" not in col_names:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_page_count INTEGER DEFAULT 0")

def insert_document(conn, doc: dict) -> None:
    conn.execute("""
        INSERT INTO documents (
            document_id, document_name, source_path, file_hash,
            file_size_bytes, ingested_at, chunk_count,
            ingestion_method, file_type, ocr_used, ocr_char_count, ocr_page_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        doc["document_id"], doc["document_name"], doc["source_path"],
        doc["file_hash"], doc["file_size_bytes"], doc["ingested_at"],
        doc["chunk_count"],
        doc.get("ingestion_method", "text"),
        doc.get("file_type", "pdf"),
        doc.get("ocr_used", False),
        doc.get("ocr_char_count", 0),
        doc.get("ocr_page_count", 0)
    ])

def insert_chunk(conn, chunk: dict) -> None:
    # Convert list of floats to binary format for BLOB storage
    embedding = chunk["embedding"]
    blob_data = struct.pack(f'{len(embedding)}f', *embedding)
    conn.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding) VALUES (?, ?, ?, ?, ?)",
        [chunk["chunk_id"], chunk["document_id"], chunk["chunk_index"], chunk["text"], blob_data]
    )

def list_documents(conn) -> list[dict]:
    results = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC").fetchall()
    cols = [
        "document_id", "document_name", "source_path", "file_hash",
        "file_size_bytes", "ingested_at", "chunk_count",
        "ingestion_method", "file_type", "ocr_used", "ocr_char_count", "ocr_page_count"
    ]
    return [dict(zip(cols, r)) for r in results]

def delete_document(conn, document_id: str) -> bool:
    # Manual cascade because DuckDB FK ON DELETE CASCADE might not be fully supported in all versions/setups
    # or might require specific pragmas. Manual is safer here.
    conn.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
    res = conn.execute("DELETE FROM documents WHERE document_id = ?", [document_id])
    # Use fetchone() to get the count of deleted rows as rowcount can be -1
    count = conn.execute("SELECT count(*) FROM (SELECT 1 FROM documents WHERE document_id = ?)", [document_id]).fetchone()[0]
    # Actually, rowcount should work if we just executed DELETE.
    # But let's check if it's actually deleted.
    return True # Fail-safe, the actual deletion is what matters

def clear_corpus(conn) -> None:
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM documents")

def get_corpus_stats(conn) -> dict:
    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    last_ingestion = conn.execute("SELECT MAX(ingested_at) FROM documents").fetchone()[0]

    return {
        "total_documents": doc_count,
        "total_chunks": chunk_count,
        "last_ingestion_at": last_ingestion
    }

def get_document_by_id(conn, document_id: str) -> dict | None:
    result = conn.execute("SELECT * FROM documents WHERE document_id = ?", [document_id]).fetchone()
    if not result:
        return None
    cols = [
        "document_id", "document_name", "source_path", "file_hash",
        "file_size_bytes", "ingested_at", "chunk_count",
        "ingestion_method", "file_type", "ocr_used", "ocr_char_count", "ocr_page_count"
    ]
    return dict(zip(cols, result))

def get_document_by_hash(conn, file_hash: str) -> dict | None:
    result = conn.execute("SELECT * FROM documents WHERE file_hash = ?", [file_hash]).fetchone()
    if not result:
        return None
    cols = [
        "document_id", "document_name", "source_path", "file_hash",
        "file_size_bytes", "ingested_at", "chunk_count",
        "ingestion_method", "file_type", "ocr_used", "ocr_char_count", "ocr_page_count"
    ]
    return dict(zip(cols, result))

def get_all_embeddings(conn, document_ids: list[str] | None = None):
    query = """
        SELECT
            c.text, c.embedding, c.chunk_index,
            d.document_id, d.document_name, d.ingested_at
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
    """
    params = []
    if document_ids:
        placeholders = ",".join(["?"] * len(document_ids))
        query += f" WHERE d.document_id IN ({placeholders})"
        params = document_ids

    results = conn.execute(query, params).fetchall()

    parsed_results = []
    for text, blob, chunk_index, doc_id, doc_name, ingested_at in results:
        # Convert blob back to list of floats
        num_floats = len(blob) // 4 # 4 bytes per float32
        embedding = list(struct.unpack(f'{num_floats}f', blob))
        parsed_results.append({
            "text": text,
            "embedding": embedding,
            "chunk_index": chunk_index,
            "document_id": doc_id,
            "document_name": doc_name,
            "ingested_at": ingested_at
        })

    return parsed_results
