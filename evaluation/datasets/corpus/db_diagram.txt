# Database Schemas & Vector Models

Vellum RAG stores system metadata and chunk embeddings in a single relational database (PostgreSQL) using the `pgvector` extension.

---

## 1. Relational Entity Relationship (PostgreSQL)

```text
  +------------------+          +------------------+
  |      users       |          |    documents     |
  +------------------+          +------------------+
  | id (PK, Serial)  |--------->| id (PK, Serial)  |
  | email (Unique)   |          | filename         |
  | hashed_password  |          | filepath         |
  | full_name        |          | file_type        |
  | role             |          | file_size        |
  | is_active        |          | user_id (FK)     |
  | created_at       |          | status           |
  +------------------+          | total_chunks     |
           |                    | created_at       |
           |                    +------------------+
           |                             |
           |                             |
           v                             v
  +------------------+          +------------------+
  |  chat_sessions   |          | document_chunks  |
  +------------------+          +------------------+
  | id (PK, UUID)    |          | id (PK, Serial)  |<---+
  | title            |          | document_id (FK) |    |
  | user_id (FK)     |          | chunk_index      |    |
  | created_at       |          | text_content     |    |
  +------------------+          | page_number      |    |
           |                    | embedding        |    | (Vector(384) in-row)
           |                    +------------------+    |
           v                                            |
  +------------------+                                  |
  |  chat_messages   |                                  |
  +------------------+                                  |
  | id (PK, UUID)    |                                  |
  | session_id (FK)  |                                  |
  | role             |                                  |
  | content          |                                  |
  | sources (JSON)   |== (JSON array of cited ids) =====+
  | created_at       |
  +------------------+
```

---

## 2. pgvector Vector Database Mappings

Instead of syncing relational rows with a separate local binary index, Vellum RAG stores dense vector representations directly inside the PostgreSQL database using pgvector's `Vector(384)` type.

```text
  PostgreSQL document_chunks Table
  +----+-------------+----------------------+--------------------------+
  | id | document_id | text_content         | embedding (Vector(384))  |
  +----+-------------+----------------------+--------------------------+
  | 102|          15 | "Rockets are fast..."| [0.012, -0.450, 0.98, ...] |
  | 103|          15 | "History of space..."| [0.141,  0.032, 0.11, ...] |
  +----+-------------+----------------------+--------------------------+
```

### Search Process Flow
1. Query embedding yields vector: `[q_0, q_1, ...]`.
2. The backend executes a direct SQL query comparing query embeddings to chunk embeddings using the `<=>` cosine distance operator:
   ```sql
   SELECT id, text_content, page_number
   FROM document_chunks
   WHERE document_id = :doc_id
   ORDER BY embedding <=> :query_vector
   LIMIT :k;
   ```
3. PostgreSQL performs the calculation on-the-fly (accelerated by an optional HNSW or IVFFlat index on the `embedding` column) and returns matching database text rows directly.
4. Context is compiled using matching database text rows and served to the LLM.
5. Deleting a document from PostgreSQL executes a simple SQL cascading delete (deleting the parent `documents` row automatically removes all child `document_chunks` rows and their vector embeddings).
