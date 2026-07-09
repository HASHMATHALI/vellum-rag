# Database Schemas & Vector Models

AuraRAG stores system metadata in a relational database (PostgreSQL) and chunk embeddings in a flat local vector index (FAISS).

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
           |                    +------------------+    |
           |                                            |
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

## 2. FAISS Vector Database Mappings

FAISS indices do not natively hold document fields (like filename or text_content) in standard implementations. To prevent duplicate storage and syncing overhead, AuraRAG configures FAISS using `IndexIDMap`:

```text
  FAISS Vector Store (faiss_index.bin)
  +-------------------------------------+
  | label: chunk_id | vector (float[384])|
  +-------------------------------------+
  |            102  | [0.012, -0.45,...]| ---> Match: document_chunks.id = 102
  |            103  | [0.141,  0.03,...]| ---> Match: document_chunks.id = 103
  +-------------------------------------+
```

### Search Process Flow
1. Query embedding yields vector: `[q_0, q_1, ...]`.
2. FAISS similarity matching yields top ID labels: `[102, 103]`.
3. Backend performs SQL lookup over PostgreSQL:
   ```sql
   SELECT * FROM document_chunks WHERE id IN (102, 103);
   ```
4. Context is compiled using matching database text rows and served to the LLM.
5. Deleting a document from PostgreSQL executes a vector delete call:
   ```python
   # FAISS Index ID Removal
   vector_store.delete_vectors([102, 103])
   ```
