# Vellum RAG — document question answering that checks its own citations

> **Identity.** The interface is styled after its name: calfskin parchment, iron-gall ink and
> rubric red, with a faint ruled-manuscript texture, Young Serif headings and square corners.
> The whole palette is defined once in `frontend/tailwind.config.js` by replacing Tailwind's
> zinc/gray scales, so every screen follows it in light and dark mode.


Vellum RAG is a Retrieval-Augmented Generation (RAG) platform with accounts and per-user document libraries. It answers questions over PDF, DOCX, TXT and Markdown files, cites the file and page for each fact, and then checks those citations. It runs as a website or as a REST API.

## Gloss: the citation check

A model that is told to cite can still cite the wrong page, cite a file it was never shown, or state a figure that is not in the passage. After every answer Vellum runs a **gloss** (the margin note a reader writes beside a manuscript line) and shows the result under the reply:

| Verdict | Meaning |
|---|---|
| Found in cited passage | the cited passage contains most of the sentence's terms |
| Partly found | some of the terms, or a figure in the sentence is missing from the passage |
| Not found in cited passage | the citation resolves, but the passage does not say this |
| Cites a passage that was not retrieved | the file/page was never given to the model |
| No citation, but found in a passage | uncited, and the checker names the passage it matches |
| No citation, not found | uncited and not in any retrieved passage |

The check is `backend/app/retrieval/gloss.py`: plain Python, no model call, so it is repeatable and adds no API cost. It is streamed as a `gloss` event after the answer and recomputed when a conversation is reopened, so it needs no database change.

**Limits.** It compares wording (stop-words removed, light stemming) and figures. It cannot judge whether a paraphrase is faithful or whether reasoning across passages is sound, so a "found" verdict means the words are there, not that the claim is true. Run its tests with `pytest tests/test_gloss.py`.

---

## Technical Architecture

- **Backend**: FastAPI (Python 3.12), SQLAlchemy (Async), Uvicorn, PostgreSQL, Redis (Caching and Rate Limiting).
- **Frontend**: React (TypeScript), Tailwind CSS, Vite, Axios, Lucide React (Icons).
- **AI Core**: Sentence Transformers (`all-MiniLM-L6-v2`, 384-dimension vectors), pgvector in PostgreSQL for similarity search, Groq API (`Llama-3.3-70B-Versatile`).
- **Gateway**: Nginx Reverse Proxy (EventSource chunk streaming, WebSocket routing).

---

## Directory Layout

```text
rag-platform/
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
│   │   ├── retrieval/    # Semantic, MMR and Hybrid search, plus the gloss citation check
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
1. Clone or navigate to the workspace directory the repository root.
2. Copy `.env.example` to `.env` and fill in `GROQ_API_KEY`, `JWT_SECRET_KEY` (`openssl rand -hex 32`), `POSTGRES_PASSWORD` and `ADMIN_PASSWORD`. Docker Compose refuses to start without them.
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
4. **Vectors**: each chunk row carries its 384-dimension embedding in a pgvector column (`DocumentChunk.embedding`); retrieval orders by cosine distance in SQL.

---

## Project Documentation
Detailed specifications are available in the `/docs` directory:
- [System Architecture Flow](docs/architecture.md)
- [REST API Specifications](docs/api_documentation.md)
- [Database Metadata Layout](docs/db_diagram.md)
- [Multi-Cloud Deployment Guide](docs/deployment_guide.md)
