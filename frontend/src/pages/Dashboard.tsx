import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { 
  FileUp, 
  Trash2, 
  RefreshCw, 
  FileText, 
  CheckCircle, 
  AlertCircle, 
  Loader2, 
  Database,
  BarChart3,
  HardDrive
} from 'lucide-react';

interface Document {
  id: number;
  filename: string;
  file_type: string;
  file_size: number;
  status: 'processing' | 'indexed' | 'failed';
  total_chunks: number;
  created_at: string;
}

export const Dashboard: React.FC = () => {
  const { user } = useAuth();
  
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      const response = await api.get('/api/documents');
      setDocuments(response.data);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, []);

  // Poll for document status updates while files are in 'processing' status
  useEffect(() => {
    fetchDocuments();
    
    const interval = setInterval(() => {
      const hasProcessing = documents.some(d => d.status === 'processing');
      if (hasProcessing) {
        fetchDocuments();
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [documents, fetchDocuments]);

  const handleFileUpload = async (files: FileList) => {
    if (files.length === 0) return;
    
    setUploading(true);
    setStatusMessage(null);
    
    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      await api.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setStatusMessage('File uploaded successfully. Indexing started in background...');
      fetchDocuments();
    } catch (err: any) {
      setStatusMessage(`Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this document? All vector indexes and parsed content will be deleted.')) return;
    
    try {
      await api.delete(`/api/document/${id}`);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const handleRebuildIndex = async () => {
    if (!window.confirm('Trigger vector store index rebuild? This will re-embed all uploaded files from scratch.')) return;
    setLoading(true);
    try {
      await api.post('/api/build-index');
      alert('FAISS vector index rebuilt successfully.');
      fetchDocuments();
    } catch (err) {
      alert('Failed to rebuild vector index.');
    } finally {
      setLoading(false);
    }
  };

  // Drag and Drop helpers
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  // Stats calculation
  const totalFiles = documents.length;
  const totalSizeMB = (documents.reduce((acc, d) => acc + d.file_size, 0) / (1024 * 1024)).toFixed(2);
  const totalChunksCount = documents.reduce((acc, d) => acc + d.total_chunks, 0);

  return (
    <div className="space-y-8">
      
      {/* Quick Dashboard Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-6 flex items-center justify-between border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Total Files</span>
            <h3 className="text-3xl font-extrabold font-display mt-1">{totalFiles}</h3>
          </div>
          <div className="w-12 h-12 rounded-xl bg-brand-100 dark:bg-brand-950/40 text-brand-500 flex items-center justify-center">
            <FileText className="w-6 h-6" />
          </div>
        </Card>
        
        <Card className="p-6 flex items-center justify-between border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Index Vectors Size</span>
            <h3 className="text-3xl font-extrabold font-display mt-1">{totalChunksCount} Chunks</h3>
          </div>
          <div className="w-12 h-12 rounded-xl bg-indigo-100 dark:bg-indigo-950/40 text-indigo-500 flex items-center justify-center">
            <Database className="w-6 h-6" />
          </div>
        </Card>

        <Card className="p-6 flex items-center justify-between border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Storage Size</span>
            <h3 className="text-3xl font-extrabold font-display mt-1">{totalSizeMB} MB</h3>
          </div>
          <div className="w-12 h-12 rounded-xl bg-purple-100 dark:bg-purple-950/40 text-purple-500 flex items-center justify-center">
            <HardDrive className="w-6 h-6" />
          </div>
        </Card>
      </div>

      {/* Main Row: Upload and Document Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        
        {/* Upload Container Panel */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg">
            <h3 className="font-display font-bold text-lg mb-4">Ingest Document</h3>
            
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`
                border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-150 
                ${dragOver ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-950/10' : 'border-gray-200 dark:border-dark-border'}
                ${uploading ? 'pointer-events-none opacity-50' : 'hover:border-brand-500 hover:bg-gray-50/50 dark:hover:bg-dark-bg/50'}
              `}
            >
              <input 
                type="file" 
                id="file-upload" 
                className="hidden" 
                accept=".pdf,.docx,.txt,.md"
                onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
              />
              <label htmlFor="file-upload" className="cursor-pointer block">
                {uploading ? (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="w-10 h-10 animate-spin text-brand-500" />
                    <span className="text-sm font-semibold">Uploading and Processing...</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <FileUp className="w-10 h-10 text-gray-400" />
                    <span className="text-sm font-semibold">Drag & Drop file here</span>
                    <span className="text-xs text-gray-400 dark:text-dark-muted">Supports PDF, DOCX, TXT, MD (Max 20MB)</span>
                  </div>
                )}
              </label>
            </div>

            {statusMessage && (
              <div className="mt-4 p-3 rounded-xl bg-gray-100 text-gray-700 dark:bg-dark-bg dark:text-gray-300 text-xs font-semibold border border-gray-200 dark:border-white/5">
                {statusMessage}
              </div>
            )}
          </Card>
          
          {/* Admin Rebuild Store triggers */}
          {user?.role === 'admin' && (
            <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card space-y-4">
              <h4 className="font-display font-bold text-sm uppercase tracking-wider text-red-500">Vector Store Utilities</h4>
              <p className="text-xs text-gray-500 dark:text-dark-muted leading-relaxed">
                Rebuild the FAISS index database in case of inconsistencies between SQLite/Postgres records and binary file vectors.
              </p>
              <Button variant="danger" loading={loading} onClick={handleRebuildIndex} className="w-full">
                <RefreshCw className="w-4 h-4 mr-2" />
                <span>Rebuild FAISS Index</span>
              </Button>
            </Card>
          )}
        </div>

        {/* Documents Table */}
        <div className="lg:col-span-2">
          <Card className="border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-200/50 dark:border-white/5 flex items-center justify-between">
              <h3 className="font-display font-bold text-lg">Document Registry</h3>
              <button 
                onClick={fetchDocuments}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                title="Refresh Documents"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-x-auto">
              {documents.length === 0 ? (
                <div className="p-12 text-center text-gray-400 dark:text-dark-muted">
                  <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p className="font-semibold text-sm">No documents found.</p>
                  <p className="text-xs mt-1">Upload a PDF or TXT file on the left panel to begin.</p>
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-dark-border text-gray-500">
                      <th className="px-6 py-4 font-semibold">Filename</th>
                      <th className="px-6 py-4 font-semibold">Size</th>
                      <th className="px-6 py-4 font-semibold">Status</th>
                      <th className="px-6 py-4 font-semibold">Chunks</th>
                      <th className="px-6 py-4 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-dark-border">
                    {documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-gray-50/50 dark:hover:bg-dark-bg/25 transition-colors">
                        <td className="px-6 py-4 font-medium flex items-center gap-3">
                          <FileText className="w-5 h-5 text-brand-500 shrink-0" />
                          <span className="truncate max-w-[200px]" title={doc.filename}>{doc.filename}</span>
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-dark-muted">
                          {(doc.file_size / 1024).toFixed(1)} KB
                        </td>
                        <td className="px-6 py-4">
                          {doc.status === 'indexed' && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-400">
                              <CheckCircle className="w-3.5 h-3.5" />
                              <span>Indexed</span>
                            </span>
                          )}
                          {doc.status === 'processing' && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-400">
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              <span>Indexing</span>
                            </span>
                          )}
                          {doc.status === 'failed' && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-400">
                              <AlertCircle className="w-3.5 h-3.5" />
                              <span>Failed</span>
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-dark-muted font-mono text-xs">
                          {doc.total_chunks}
                        </td>
                        <td className="px-6 py-4">
                          <button
                            onClick={() => handleDelete(doc.id)}
                            className="p-2 rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/20 transition-colors"
                            title="Delete Document"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
        </div>

      </div>
    </div>
  );
};


