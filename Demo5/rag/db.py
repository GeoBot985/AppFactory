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
        chunk_count INTEGER NOT NULL
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

def insert_document(conn, doc: dict) -> None:
    conn.execute("""
        INSERT INTO documents (
            document_id, document_name, source_path, file_hash,
            file_size_bytes, ingested_at, chunk_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        doc["document_id"], doc["document_name"], doc["source_path"],
        doc["file_hash"], doc["file_size_bytes"], doc["ingested_at"],
        doc["chunk_count"]
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
        "file_size_bytes", "ingested_at", "chunk_count"
    ]
    return [dict(zip(cols, r)) for r in results]

def get_document_by_id(conn, document_id: str) -> dict | None:
    result = conn.execute("SELECT * FROM documents WHERE document_id = ?", [document_id]).fetchone()
    if not result:
        return None
    cols = [
        "document_id", "document_name", "source_path", "file_hash",
        "file_size_bytes", "ingested_at", "chunk_count"
    ]
    return dict(zip(cols, result))

def get_document_by_hash(conn, file_hash: str) -> dict | None:
    result = conn.execute("SELECT * FROM documents WHERE file_hash = ?", [file_hash]).fetchone()
    if not result:
        return None
    cols = [
        "document_id", "document_name", "source_path", "file_hash",
        "file_size_bytes", "ingested_at", "chunk_count"
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
