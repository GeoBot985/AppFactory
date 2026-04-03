import duckdb

def get_connection(db_path="rag.db"):
    return duckdb.connect(db_path)

def init_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT,
        chunk_index INTEGER,
        text TEXT,
        embedding BLOB
    );
    """)

def insert_chunk(conn, doc_id, chunk_index, text, embedding):
    import struct
    # Convert list of floats to binary format for BLOB storage
    # Assuming embeddings are stored as list of floats
    blob_data = struct.pack(f'{len(embedding)}f', *embedding)
    conn.execute(
        "INSERT INTO documents (id, chunk_index, text, embedding) VALUES (?, ?, ?, ?)",
        [doc_id, chunk_index, text, blob_data]
    )

def get_all_embeddings(conn):
    import struct
    results = conn.execute("SELECT text, embedding FROM documents").fetchall()

    parsed_results = []
    for text, blob in results:
        # Convert blob back to list of floats
        num_floats = len(blob) // 4 # 4 bytes per float32
        embedding = list(struct.unpack(f'{num_floats}f', blob))
        parsed_results.append((text, embedding))

    return parsed_results
