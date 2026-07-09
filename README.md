# AuraRAG — Production-Ready AI Semantic Search Platform

AuraRAG is a secure, AI-powered Retrieval-Augmented Generation (RAG) platform. It provides instant concept-based answers over PDF, DOCX, TXT, and Markdown documents. The application can run as a standalone website or as a deployable REST API gateway for mobile/web client integrations.

---

## Technical Architecture

- **Backend**: FastAPI (Python 3.12), SQLAlchemy (Async), Uvicorn, PostgreSQL, Redis (Caching and Rate Limiting).
- **Frontend**: React (TypeScript), Tailwind CSS, Vite, Axios, Lucide React (Icons).
- **AI Core**: Sentence Transformers (`all-MiniLM-L6-v2` dense vectors), FAISS (`IndexIDMap` + `IndexFlatIP`), Groq API (`Llama-3.3-70B-Versatile`).
- **Gateway**: Nginx Reverse Proxy (EventSource chunk streaming, WebSocket routing).

---

## Directory Layout

```text
rag-platform/ (c:\RAG)
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI Routes (Auth, Documents, Chat, Admin)
│   │   ├── config/       # Pydantic environment configurations
│   │   ├── database/     # Async engines and get_db sessions
│   │   ├── models/       # Users, Chunks, Messages SQLAlchemy models
│   │   ├── auth/         # JWT encryption and role permissions
│   │   ├── middleware/   # Sliding window Rate Limiting (Redis)
│   │   ├── embeddings/   # Lazy-load Local SentenceTransformers
│   │   ├── vectorstore/  # FAISS database managers
│   │   ├── ingestion/    # Text Parsers and Sliding Chunks splitters
│   │   ├── retrieval/    # Semantic, MMR, and Hybrid search logic
│   │   ├── llm/          # Groq streaming completions wrappers
│   │   └── main.py       # App Startup & database synchronization
│   ├── requirements.txt  # Python packages
│   └── Dockerfile        # Cached model docker build
├── frontend/
│   ├── src/
│   │   ├── components/   # Chat interfaces, UI buttons, and Admin views
│   │   ├── pages/        # Login, Signup, Landing, Pricing, and Console
│   │   ├── context/      # Auth and Theme provider states
│   │   └── App.tsx       # TSX routing and protected guards
│   ├── index.html        # Main template
│   ├── package.json      # React dependencies
│   └── Dockerfile        # Multi-stage production Nginx serve
├── nginx/
│   ├── nginx.conf        # Gateway proxy & buffering disables
│   └── Dockerfile        # Alpine container setup
└── docker-compose.yml    # Full service orchestration
```

---

## Quickstart Guide

### Prerequisite
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Obtain a free Groq API key from the [Groq Console](https://console.groq.com/).

### Running the Platform
1. Clone or navigate to the workspace directory `c:\RAG`.
2. Edit the `docker-compose.yml` file and replace `gsk_your_groq_api_key_goes_here` with your actual Groq API key.
3. Start the containers using Docker Compose:
   ```bash
   docker-compose up --build
   ```
4. Access the platform services:
   - **Frontend UI Platform**: [http://localhost](http://localhost)
   - **Interactive API Swagger Playground**: [http://localhost/docs](http://localhost/docs)
   - **Backend Server Root**: [http://localhost:8000](http://localhost:8000)

---

## Database Schemas & Vector Stores

1. **User Table**: Manages profiles and authorization credentials (Admin, User).
2. **Document & Chunk Tables**: Keeps metadata of uploaded files and maps text segments.
3. **Conversations Tables**: Stores message threads and SSE streaming replies.
4. **Vector Store ID Mappings**: FAISS utilizes an `IndexIDMap` wrapper which maps the Postgres chunk primary keys (`DocumentChunk.id`) to dense 384-dimension vector coordinates inside `vector_store/faiss_index.bin` for sub-100ms similarity lookups.

---

## Project Documentation
Detailed specifications are available in the `/docs` directory:
- [System Architecture Flow](file:///c:/RAG/docs/architecture.md)
- [REST API Specifications](file:///c:/RAG/docs/api_documentation.md)
- [Database Metadata Layout](file:///c:/RAG/docs/db_diagram.md)
- [Multi-Cloud Deployment Guide](file:///c:/RAG/docs/deployment_guide.md)
