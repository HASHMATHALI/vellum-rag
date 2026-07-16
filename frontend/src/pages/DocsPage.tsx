import React, { useState } from 'react';
import { Card } from '../components/ui/Card';

export const DocsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'auth' | 'upload' | 'query'>('auth');

  const curlCode = {
    auth: `# 1. Register User Account
curl -X POST "http://localhost/api/auth/register" \\
     -H "Content-Type: application/json" \\
     -d '{
       "email": "user@example.com",
       "password": "securepassword123",
       "full_name": "John Doe"
     }'

# 2. Authenticate & Obtain Bearer Token
curl -X POST "http://localhost/api/auth/login" \\
     -H "Content-Type: application/json" \\
     -d '{
       "email": "user@example.com",
       "password": "securepassword123"
     }'`,

    upload: `# Upload Document for Semantic Indexing
curl -X POST "http://localhost/api/upload" \\
     -H "Authorization: Bearer <your_jwt_access_token>" \\
     -H "Content-Type: multipart/form-data" \\
     -F "file=@/path/to/your/document.pdf"`,

    query: `# Run Semantic RAG Query (SSE Stream)
curl -X POST "http://localhost/api/query" \\
     -H "Authorization: Bearer <your_jwt_access_token>" \\
     -H "Content-Type: application/json" \\
     -d '{
       "message": "What are the core features of the system?",
       "search_mode": "hybrid",
       "k": 5
     }'`
  };

  const responseJson = {
    auth: `{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "user"
  }
}`,
    upload: `{
  "id": 12,
  "filename": "document.pdf",
  "file_type": "pdf",
  "file_size": 204857,
  "status": "processing",
  "total_chunks": 0,
  "created_at": "2026-07-08T03:00:00Z"
}`,
    query: `event: session
data: {"session_id": "a5e8f810-7212-421f-8181-a3fcf118cd99"}

event: sources
data: [{"document_id": 12, "filename": "document.pdf", "chunk_index": 2, "page_number": 1, "similarity_score": 0.854, "text_content": "..."}]

data: {"content": "Based "}
data: {"content": "on the "}
data: {"content": "uploaded "}
data: {"content": "document, ..."}

event: close
data: [DONE]`
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        
        {/* Sidebar Guide Menu */}
        <aside className="space-y-6 lg:col-span-1">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">API Guidelines</h3>
            <ul className="space-y-2 text-sm">
              <li><a href="#quickstart" className="hover:text-brand-500 transition-colors">Developer Quickstart</a></li>
              <li><a href="#authentication" className="hover:text-brand-500 transition-colors">Authentication</a></li>
              <li><a href="#uploads" className="hover:text-brand-500 transition-colors">File Ingestion</a></li>
              <li><a href="#retrieval" className="hover:text-brand-500 transition-colors">Semantic Retrieval</a></li>
            </ul>
          </div>
          <div className="h-px bg-gray-200 dark:bg-dark-border" />
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Swagger Docs</h3>
            <p className="text-xs text-gray-500 dark:text-dark-muted mb-2 leading-relaxed">
              FastAPI auto-generates live interactive Swagger docs.
            </p>
            <a 
              href="http://localhost:8000/docs" 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center text-xs font-bold text-brand-500 hover:underline"
            >
              Open API Playground &rarr;
            </a>
          </div>
        </aside>

        {/* Documentation Content */}
        <main className="lg:col-span-3 space-y-12">
          
          {/* Quickstart */}
          <section id="quickstart" className="space-y-4">
            <h1 className="font-display text-3xl font-extrabold tracking-tight">Developer Integration Guide</h1>
            <p className="text-gray-600 dark:text-dark-muted leading-relaxed text-sm">
              The Vellum RAG platform exposes simple REST APIs, allowing external applications, mobile apps, or backend worker jobs to upload documents and query vector indexes. All requests require standard Authorization bearer headers.
            </p>
          </section>

          {/* Interactive Code Switcher Section */}
          <section className="space-y-6">
            <div className="flex border-b border-gray-200 dark:border-dark-border">
              <button 
                onClick={() => setActiveTab('auth')}
                className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                  activeTab === 'auth' ? 'border-brand-500 text-brand-500' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                1. Authenticate
              </button>
              <button 
                onClick={() => setActiveTab('upload')}
                className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                  activeTab === 'upload' ? 'border-brand-500 text-brand-500' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                2. Upload File
              </button>
              <button 
                onClick={() => setActiveTab('query')}
                className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                  activeTab === 'query' ? 'border-brand-500 text-brand-500' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                3. Semantic Chat
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Request Code Block */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-gray-500">cURL Example Request</span>
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-xl text-xs overflow-auto font-mono max-h-[300px] border border-white/5">
                  <code>{curlCode[activeTab]}</code>
                </pre>
              </div>

              {/* Response Code Block */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-gray-500">JSON API Response</span>
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-xl text-xs overflow-auto font-mono max-h-[300px] border border-white/5">
                  <code>{responseJson[activeTab]}</code>
                </pre>
              </div>
            </div>
          </section>

          {/* Advanced Explanations */}
          <section id="retrieval" className="space-y-4">
            <h2 className="font-display text-2xl font-bold">Query Parameters Details</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-dark-border text-gray-500">
                    <th className="py-2.5 font-semibold">Parameter</th>
                    <th className="py-2.5 font-semibold">Type</th>
                    <th className="py-2.5 font-semibold">Default</th>
                    <th className="py-2.5 font-semibold">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-dark-border">
                  <tr>
                    <td className="py-3 font-mono font-bold text-xs text-brand-500">message</td>
                    <td className="py-3 font-mono text-xs">string</td>
                    <td className="py-3 font-mono text-xs">Required</td>
                    <td className="py-3 text-gray-500 dark:text-dark-muted">The main prompt query text.</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-mono font-bold text-xs text-brand-500">search_mode</td>
                    <td className="py-3 font-mono text-xs">string</td>
                    <td className="py-3 font-mono text-xs">"semantic"</td>
                    <td className="py-3 text-gray-500 dark:text-dark-muted">Method: "semantic", "mmr", "hybrid".</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-mono font-bold text-xs text-brand-500">document_ids</td>
                    <td className="py-3 font-mono text-xs">array[int]</td>
                    <td className="py-3 font-mono text-xs">null</td>
                    <td className="py-3 text-gray-500 dark:text-dark-muted">Restrict search context to specific documents.</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-mono font-bold text-xs text-brand-500">k</td>
                    <td className="py-3 font-mono text-xs">int</td>
                    <td className="py-3 font-mono text-xs">5</td>
                    <td className="py-3 text-gray-500 dark:text-dark-muted">Number of chunks to feed into LLM prompt (max 20).</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

        </main>
      </div>
    </div>
  );
};


