# REST API Specification & Integration Guides

All endpoints require JWT authorization bearer header (except register and login).

```text
Authorization: Bearer <your_jwt_access_token>
```

---

## 1. Authentication Endpoints

### POST `/api/auth/register`
Creates a user account.
- **Request Body (JSON)**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword123",
    "full_name": "John Doe"
  }
  ```
- **Response (JSON - 201 Created)**:
  ```json
  {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "user"
  }
  ```

### POST `/api/auth/login`
Authenticates user and returns JWT access token.
- **Request Body (JSON)**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword123"
  }
  ```
- **Response (JSON - 200 OK)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "bearer",
    "user": {
      "id": 1,
      "email": "user@example.com",
      "full_name": "John Doe",
      "role": "user"
    }
  }
  ```

---

## 2. Ingestion Endpoints

### POST `/api/upload`
Uploads a document.
- **Request Headers**: `Content-Type: multipart/form-data`
- **Request Body (Multipart)**:
  - `file`: Binary file data (PDF, DOCX, TXT, MD)
- **Response (JSON - 201 Created)**:
  ```json
  {
    "id": 15,
    "filename": "annual_report.pdf",
    "file_type": "pdf",
    "file_size": 1048576,
    "status": "processing",
    "total_chunks": 0,
    "created_at": "2026-07-08T03:10:00Z"
  }
  ```

### GET `/api/documents`
Lists uploaded documents.
- **Response (JSON - 200 OK)**:
  ```json
  [
    {
      "id": 15,
      "filename": "annual_report.pdf",
      "file_type": "pdf",
      "file_size": 1048576,
      "status": "indexed",
      "total_chunks": 54,
      "created_at": "2026-07-08T03:10:00Z"
    }
  ]
  ```

### DELETE `/api/document/{id}`
Deletes a document and its associated vectors.
- **Response (JSON - 200 OK)**:
  ```json
  {
    "message": "Document deleted and index updated successfully."
  }
  ```

---

## 3. Conversational QA Endpoints

### POST `/api/query`
Streams an LLM answer back.
- **Request Body (JSON)**:
  ```json
  {
    "message": "What was the total revenue in 2025?",
    "session_id": "optional-uuid-session-string",
    "search_mode": "hybrid",
    "k": 5
  }
  ```
- **Response (Server-Sent Events Stream)**:
  - Event: `session` with session ID details.
  - Event: `sources` with list of citing document chunks.
  - Data: JSON objects containing text reply tokens: `{"content": "..."}`.
  - Event: `close` with token `[DONE]` signifying stream termination.

### GET `/api/history`
Lists all active chat threads of the logged-in user.
- **Response (JSON - 200 OK)**:
  ```json
  [
    {
      "id": "a5e8f810-7212-421f-8181-a3fcf118cd99",
      "title": "What was the total revenue in 2025?",
      "created_at": "2026-07-08T03:15:00Z"
    }
  ]
  ```
