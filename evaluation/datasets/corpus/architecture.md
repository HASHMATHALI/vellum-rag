# Platform Architecture & Core Pipelines

This document outlines the software engineering architecture of the RAG platform.

```mermaid
graph TD
    User([User UI / Client]) -->|Web / API Requests| Gateway[Nginx Gateway]
    Gateway -->|/api/*| Backend[FastAPI Backend]
    Gateway -->|/*| Frontend[React SPA]
    
    Backend -->|JWT Auth & Metadata| DB[(PostgreSQL + pgvector)]
    Backend -->|Request Count Check| RedisCache[(Redis Cache)]
    
    Backend -->|Local Inference| Embedder[all-MiniLM-L6-v2]
    
    Backend -->|Streaming Prompt| Groq[Groq Llama-3.3]
```

## 1. Document Processing Ingestion Pipeline
When a user uploads a document (PDF, DOCX, TXT, MD):
1. **Physical Write**: The file is stored either remotely in Supabase Storage or locally inside `uploads/` directory.
2. **Text Parsing**: `FileParser` extracts page-by-page string characters based on file extension.
3. **Overlapping Chunker**: `TextChunker` segments text into sliding chunks of 1500 characters with 200 characters overlap (or custom config boundaries) to ensure contextual boundaries are not severed.
4. **Relational Sync**: Chunks are inserted into the PostgreSQL database under the `document_chunks` table, securing incrementing primary keys (`chunk.id`).
5. **Local Vector Embeddings**: `Embedder` (Sentence Transformers `all-MiniLM-L6-v2`) converts text chunks into a series of 384-dimension floating-point arrays.
6. **Vector Sync**: The generated embeddings are saved directly inside the `document_chunks` table in the `embedding` vector column, where PostgreSQL creates/updates vector index structures.

## 2. Conversational RAG Completions Pipeline
When a user sends a query inside a chat session:
1. **Query Reformulation**: The backend fetches the last few messages of history. If history exists, it queries the Groq API to rewrite the follow-up prompt into a standalone vector search query.
2. **Dense Vector Search**: The standalone query is embedded using `all-MiniLM-L6-v2`. A native pgvector cosine similarity lookup is executed directly over the database to retrieve the top `k` matching chunk IDs and their textual content.
3. **Context Construction**: Chunks are compiled into the `SYSTEM_RAG_PROMPT` along with page numbers and document names.
4. **SSE Stream completions**: Groq API is called asynchronously, and the response is streamed chunk-by-chunk using Server-Sent Events (SSE).
5. **Persistence logging**: The complete aggregated assistant response and list of citations are committed to the PostgreSQL `chat_messages` table at the end of the stream.
