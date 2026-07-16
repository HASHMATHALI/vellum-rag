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
  HardDrive,
  Calendar,
  Layers,
  FileCode,
  FileCheck
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
      alert('Vector database rebuilt successfully.');
      fetchDocuments();
    } catch (err) {
      alert('Failed to rebuild vector database.');
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  // Helper to format file sizes
  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  // Helper to get formatted date
  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString(undefined, { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  const renderFileTypeIcon = (ext: string) => {
    const cleanExt = ext.toLowerCase().replace('.', '');
    return (
      <span className="w-10 h-10 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 flex items-center justify-center font-bold text-[10px] shrink-0 border border-zinc-200/60 dark:border-zinc-700/60 uppercase tracking-wider font-display">
        {cleanExt}
      </span>
    );
  };

  const totalFiles = documents.length;
  const totalSize = documents.reduce((acc, d) => acc + d.file_size, 0);
  const totalChunksCount = documents.reduce((acc, d) => acc + d.total_chunks, 0);

  return (
    <div className="space-y-8 animate-fade-in">
      
      {/* 1. Quick Stats Header Area */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Total Documents Card */}
        <Card className="p-6 relative overflow-hidden bg-white dark:bg-dark-card border border-gray-200/50 dark:border-white/5 hover:border-zinc-950 dark:hover:border-white/40 shadow-sm hover:shadow-md transition-all duration-300">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-dark-muted">Total Documents</span>
              <h3 className="text-3xl font-black font-display text-gray-900 dark:text-white mt-1">{totalFiles}</h3>
            </div>
            <div className="w-12 h-12 rounded-2xl bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 flex items-center justify-center shadow-inner">
              <FileText className="w-6 h-6" />
            </div>
          </div>
        </Card>
        
        {/* Vector DB Size Card */}
        <Card className="p-6 relative overflow-hidden bg-white dark:bg-dark-card border border-gray-200/50 dark:border-white/5 hover:border-zinc-950 dark:hover:border-white/40 shadow-sm hover:shadow-md transition-all duration-300">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-dark-muted">pgvector Chunks</span>
              <h3 className="text-3xl font-black font-display text-gray-900 dark:text-white mt-1">{totalChunksCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-2xl bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 flex items-center justify-center shadow-inner">
              <Database className="w-6 h-6" />
            </div>
          </div>
        </Card>

        {/* Database Storage Card */}
        <Card className="p-6 relative overflow-hidden bg-white dark:bg-dark-card border border-gray-200/50 dark:border-white/5 hover:border-zinc-950 dark:hover:border-white/40 shadow-sm hover:shadow-md transition-all duration-300">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-dark-muted">Storage Consumed</span>
              <h3 className="text-3xl font-black font-display text-gray-900 dark:text-white mt-1">{formatSize(totalSize)}</h3>
            </div>
            <div className="w-12 h-12 rounded-2xl bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 flex items-center justify-center shadow-inner">
              <HardDrive className="w-6 h-6" />
            </div>
          </div>
        </Card>
      </div>

      {/* 2. Main Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        
        {/* Left column: Upload panel & administration options */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white/60 dark:bg-dark-card/45 backdrop-blur-md shadow-xl rounded-3xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-zinc-300 dark:bg-zinc-800" />
            <h3 className="font-display font-black text-xl text-gray-900 dark:text-white mb-2">Ingest Assets</h3>
            <p className="text-xs text-gray-500 dark:text-dark-muted mb-6 leading-relaxed">
              Upload local business docs, reports, or research sheets to parse into vector representations.
            </p>
            
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`
                border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-200 relative overflow-hidden group
                ${dragOver ? 'border-zinc-900 bg-zinc-100 dark:border-white dark:bg-zinc-800/40 scale-98' : 'border-gray-200 dark:border-dark-border'}
                ${uploading ? 'pointer-events-none opacity-60' : 'hover:border-zinc-950 dark:hover:border-white hover:bg-zinc-50 dark:hover:bg-zinc-800/20'}
              `}
            >
              <input 
                type="file" 
                id="file-upload" 
                className="hidden" 
                accept=".pdf,.docx,.txt,.md"
                onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
              />
              <label htmlFor="file-upload" className="cursor-pointer block space-y-3">
                {uploading ? (
                  <div className="flex flex-col items-center justify-center gap-3 py-4">
                    <Loader2 className="w-12 h-12 animate-spin text-brand-500" />
                    <span className="text-sm font-bold text-gray-700 dark:text-gray-200">Processing & Vectorizing...</span>
                    <span className="text-xs text-gray-400 dark:text-dark-muted">Extracting text & running embeddings</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center gap-3 py-2">
                    <div className="w-14 h-14 rounded-full bg-brand-500/5 group-hover:bg-brand-500/10 text-brand-500 flex items-center justify-center transition-colors shadow-sm">
                      <FileUp className="w-7 h-7" />
                    </div>
                    <div>
                      <span className="text-sm font-bold text-gray-800 dark:text-gray-200 block group-hover:text-brand-500 transition-colors">Drag & Drop document</span>
                      <span className="text-xs text-gray-400 dark:text-dark-muted block mt-1">or browse files from system</span>
                    </div>
                    <span className="inline-block text-[10px] font-semibold bg-gray-100 dark:bg-dark-bg/80 text-gray-500 dark:text-dark-muted px-2.5 py-1 rounded-md">
                      PDF, DOCX, TXT, MD up to 20MB
                    </span>
                  </div>
                )}
              </label>
            </div>

            {statusMessage && (
              <div className={`mt-5 p-3.5 rounded-xl text-xs font-bold border transition-all duration-200 animate-fade-in ${
                statusMessage.toLowerCase().includes('failed')
                  ? 'bg-zinc-100 dark:bg-zinc-800 text-red-500 dark:text-red-400 border-zinc-200/80 dark:border-zinc-700/80'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 border-zinc-200/80 dark:border-zinc-700/80'
              }`}>
                {statusMessage}
              </div>
            )}
          </Card>
          
          {/* Admin Index rebuilding panel */}
          {user?.role === 'admin' && (
            <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white/60 dark:bg-dark-card/45 backdrop-blur-md rounded-3xl space-y-4">
              <h4 className="font-display font-black text-xs uppercase tracking-wider text-red-500 flex items-center gap-2">
                <Layers className="w-4 h-4" />
                <span>Admin Maintenance</span>
              </h4>
              <p className="text-xs text-gray-500 dark:text-dark-muted leading-relaxed">
                Force a full database scan to rebuild the dense vector embeddings table from scratch.
              </p>
              <Button 
                variant="secondary" 
                loading={loading} 
                onClick={handleRebuildIndex} 
                className="w-full flex items-center justify-center gap-2 border-red-500/20 hover:border-red-500 hover:text-red-500 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>Force Rebuild pgvector Columns</span>
              </Button>
            </Card>
          )}
        </div>

        {/* Right column: Documents Registry Table */}
        <div className="lg:col-span-2">
          <Card className="border-gray-200/50 dark:border-white/5 bg-white/60 dark:bg-dark-card/45 backdrop-blur-md shadow-xl rounded-3xl overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-200/50 dark:border-white/5 flex items-center justify-between">
              <div>
                <h3 className="font-display font-black text-xl text-gray-900 dark:text-white">Document Registry</h3>
                <p className="text-xs text-gray-400 dark:text-dark-muted mt-1">List of indexed document assets in the database</p>
              </div>
              <button 
                onClick={fetchDocuments}
                className="p-2.5 rounded-xl border border-gray-200 dark:border-dark-border text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all active:scale-95 shadow-sm"
                title="Refresh Documents"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-x-auto">
              {documents.length === 0 ? (
                <div className="p-20 text-center">
                  <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-dark-bg/60 text-gray-400 dark:text-dark-muted flex items-center justify-center mx-auto mb-5 shadow-inner">
                    <FileText className="w-8 h-8 opacity-60" />
                  </div>
                  <h4 className="font-bold text-gray-800 dark:text-gray-200 text-sm">No documents found</h4>
                  <p className="text-xs text-gray-400 dark:text-dark-muted max-w-xs mx-auto mt-1 leading-relaxed">
                    Upload your document using the ingest panel to begin vector queries.
                  </p>
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-dark-border text-gray-400 dark:text-dark-muted font-bold text-xs uppercase tracking-wider bg-gray-50/50 dark:bg-dark-bg/20">
                      <th className="px-6 py-4 font-bold">Filename</th>
                      <th className="px-6 py-4 font-bold">Size</th>
                      <th className="px-6 py-4 font-bold">Status</th>
                      <th className="px-6 py-4 font-bold">Chunks</th>
                      <th className="px-6 py-4 font-bold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-dark-border">
                    {documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-brand-500/5 dark:hover:bg-brand-400/5 transition-colors group">
                        {/* Filename with custom extensions */}
                        <td className="px-6 py-4 font-semibold text-gray-900 dark:text-white flex items-center gap-3">
                          {renderFileTypeIcon(doc.file_type)}
                          <div className="min-w-0">
                            <span className="truncate block font-bold max-w-[260px] text-xs md:text-sm hover:text-brand-500 transition-colors cursor-default" title={doc.filename}>{doc.filename}</span>
                            <span className="text-[10px] text-gray-400 dark:text-dark-muted flex items-center gap-1 mt-0.5">
                              <Calendar className="w-3.5 h-3.5 shrink-0" />
                              <span>{formatDate(doc.created_at)}</span>
                            </span>
                          </div>
                        </td>
                        
                        {/* File Size */}
                        <td className="px-6 py-4 text-xs font-semibold text-gray-500 dark:text-dark-muted font-mono">
                          {formatSize(doc.file_size)}
                        </td>
                        
                        {/* Custom Status badge */}
                        <td className="px-6 py-4">
                          {doc.status === 'indexed' && (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-bold uppercase tracking-wider bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 border border-zinc-200/60 dark:border-zinc-700/60">
                              <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                              </span>
                              <span>Indexed</span>
                            </span>
                          )}
                          {doc.status === 'processing' && (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-bold uppercase tracking-wider bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 border border-zinc-200/60 dark:border-zinc-700/60">
                              <Loader2 className="w-3 h-3 animate-spin text-zinc-500" />
                              <span>Indexing</span>
                            </span>
                          )}
                          {doc.status === 'failed' && (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-bold uppercase tracking-wider bg-zinc-100 dark:bg-zinc-800 text-red-500 dark:text-red-400 border border-zinc-200/60 dark:border-zinc-700/60">
                              <AlertCircle className="w-3 h-3" />
                              <span>Failed</span>
                            </span>
                          )}
                        </td>
                        
                        {/* Chunks Count */}
                        <td className="px-6 py-4 text-gray-500 dark:text-dark-muted font-mono text-xs font-bold">
                          {doc.total_chunks}
                        </td>
                        
                        {/* Actions */}
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => handleDelete(doc.id)}
                            className="p-2 rounded-xl text-red-500 hover:bg-red-500/10 transition-colors opacity-80 md:opacity-0 group-hover:opacity-100"
                            title="Delete Document"
                          >
                            <Trash2 className="w-4.5 h-4.5" />
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
