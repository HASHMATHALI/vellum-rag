import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChat } from '../hooks/useChat';
import { Card } from './ui/Card';
import { Button } from './ui/Button';
import { 
  MessageSquare, 
  Plus, 
  Send, 
  BookOpen, 
  Copy, 
  Check, 
  Sliders, 
  Sparkles,
  HelpCircle,
  FileText,
  FileSpreadsheet
} from 'lucide-react';

export const ChatInterface: React.FC = () => {
  const {
    sessions,
    messages,
    activeSessionId,
    activeSources,
    isStreaming,
    loading,
    fetchSessions,
    loadSessionMessages,
    startNewChat,
    sendMessage
  } = useChat();

  const [input, setInput] = useState('');
  const [searchMode, setSearchMode] = useState<string>(() => localStorage.getItem('searchMode') || 'semantic');
  const [k, setK] = useState<number>(() => parseInt(localStorage.getItem('k') || '5'));
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize
  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    
    // Read current settings
    const currentLambda = parseFloat(localStorage.getItem('lambda') || '0.5');
    const currentSemWeight = parseFloat(localStorage.getItem('semanticWeight') || '0.7');
    
    sendMessage(input, searchMode, null, k);
    setInput('');
  };

  const handleCopy = (text: string, msgId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(msgId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const suggestedQuestions = [
    "What information is contained in the uploaded files?",
    "Can you summarize the core themes of the document?",
    "Give me the key takeaways with exact page numbers."
  ];

  return (
    <div className="h-[calc(100vh-8rem)] flex rounded-2xl border border-gray-200/50 dark:border-white/5 overflow-hidden bg-white dark:bg-dark-card shadow-lg">
      
      {/* Sidebar - Conversation History threads */}
      <aside className="w-64 border-r border-gray-200/50 dark:border-white/5 bg-gray-50/50 dark:bg-dark-bg/25 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200/50 dark:border-white/5">
          <Button 
            onClick={startNewChat}
            className="w-full flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>New Session</span>
          </Button>
        </div>
        
        {/* Threads List */}
        <div className="flex-grow overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-400 dark:text-dark-muted">
              No recent conversations.
            </div>
          ) : (
            sessions.map((sess) => (
              <button
                key={sess.id}
                onClick={() => loadSessionMessages(sess.id)}
                className={`
                  w-full text-left px-3 py-2.5 rounded-xl text-xs font-semibold truncate transition-colors flex items-center gap-2.5 ${
                    activeSessionId === sess.id
                      ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/20 dark:text-brand-400'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800/50 text-gray-600 dark:text-gray-400'
                  }
                `}
              >
                <MessageSquare className="w-4 h-4 shrink-0" />
                <span className="truncate">{sess.title}</span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main Chat Panel */}
      <div className="flex-grow flex flex-col min-w-0 bg-white dark:bg-dark-card">
        
        {/* Thread header control settings */}
        <header className="px-6 py-3 border-b border-gray-200/50 dark:border-white/5 flex items-center justify-between bg-gray-50/50 dark:bg-dark-bg/25">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Retrieval Method:</span>
            <select
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-300 dark:border-dark-border bg-white dark:bg-dark-bg focus:outline-none focus:ring-2 focus:ring-brand-500/20 capitalize font-medium"
            >
              <option value="semantic">Semantic Search</option>
              <option value="mmr">MMR (Diverse)</option>
              <option value="hybrid">Hybrid Search</option>
            </select>
          </div>

          <button 
            onClick={() => setShowConfig(!showConfig)}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-500"
            title="Tuning Configs"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </header>

        {/* Configuration settings overlay box */}
        {showConfig && (
          <div className="px-6 py-4 bg-gray-50 dark:bg-dark-bg border-b border-gray-200/50 dark:border-white/5 text-xs grid grid-cols-2 gap-4 animate-fade-in">
            <div className="space-y-1">
              <label className="font-semibold text-gray-500">Retrieval Chunks Count (k)</label>
              <div className="flex items-center gap-3">
                <input 
                  type="range" min="1" max="15" value={k} 
                  onChange={(e) => setK(parseInt(e.target.value))}
                  className="w-full accent-brand-500 h-1.5 bg-gray-200 dark:bg-dark-border rounded-lg"
                />
                <span className="font-mono font-bold text-brand-500 shrink-0">{k} chunks</span>
              </div>
            </div>
            <div className="text-gray-500 dark:text-dark-muted flex items-center justify-end">
              Adjust configurations for real-time prompt search.
            </div>
          </div>
        )}

        {/* Messages Stream Container */}
        <div className="flex-grow overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto">
              <Sparkles className="w-12 h-12 text-brand-500 mb-4 animate-pulse" />
              <h3 className="font-display font-bold text-xl mb-2">AuraRAG Assistant</h3>
              <p className="text-sm text-gray-500 dark:text-dark-muted mb-8 leading-relaxed">
                Query uploaded documents using AI. Your questions will be answered with exact document sources and page references.
              </p>
              
              <div className="w-full space-y-2">
                {suggestedQuestions.map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 dark:border-dark-border hover:border-brand-500 dark:hover:border-brand-500 hover:bg-brand-50/10 hover:text-brand-600 dark:hover:text-brand-400 text-xs font-semibold transition-all duration-150 flex items-center gap-2"
                  >
                    <HelpCircle className="w-4 h-4 text-brand-500 shrink-0" />
                    <span>{q}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div 
                  key={msg.id} 
                  className={`flex flex-col gap-2 max-w-[85%] ${
                    isUser ? 'ml-auto items-end' : 'mr-auto items-start'
                  }`}
                >
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-dark-muted font-semibold">
                    <span>{isUser ? 'You' : 'AuraRAG Assistant'}</span>
                  </div>

                  <div className={`p-4 rounded-2xl relative group ${
                    isUser 
                      ? 'bg-brand-500 text-white rounded-br-none' 
                      : 'bg-gray-100 dark:bg-dark-bg rounded-bl-none text-gray-800 dark:text-gray-100 border border-gray-200/50 dark:border-white/5'
                  }`}>
                    {/* Copy Button */}
                    <button
                      onClick={() => handleCopy(msg.content, msg.id)}
                      className={`
                        absolute top-2 right-2 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity bg-white dark:bg-dark-card border border-gray-200/50 dark:border-white/5 text-gray-500 hover:text-gray-700
                      `}
                      title="Copy response"
                    >
                      {copiedId === msg.id ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>

                    {/* Markdown responses */}
                    <div className={`prose dark:prose-invert prose-xs text-sm leading-relaxed max-w-none break-words ${
                      isUser ? 'prose-headings:text-white prose-strong:text-white prose-a:text-white' : ''
                    }`}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {/* Sources Preview Drawer Cards */}
                  {!isUser && msg.sources && msg.sources.length > 0 && !msg.content.toLowerCase().includes('general knowledge') && (
                    <div className="mt-2 space-y-1.5 w-full">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-dark-muted flex items-center gap-1.5">
                        <BookOpen className="w-3.5 h-3.5 text-brand-500" />
                        <span>Sources Cited ({msg.sources.length})</span>
                      </span>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full">
                        {msg.sources.map((src, sIdx) => (
                          <Card 
                            key={sIdx} 
                            className="p-3 border border-gray-200/30 dark:border-white/5 bg-gray-50/50 dark:bg-dark-bg/25 text-[11px] leading-relaxed flex flex-col justify-between"
                          >
                            <div>
                              <div className="flex items-center gap-1 font-bold text-gray-700 dark:text-gray-300 mb-1 truncate" title={src.filename}>
                                <FileText className="w-3.5 h-3.5 text-brand-500 shrink-0" />
                                <span className="truncate">{src.filename}</span>
                              </div>
                              <p className="text-gray-500 dark:text-dark-muted line-clamp-2 italic mb-2">
                                "{src.text_content}"
                              </p>
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-gray-400 dark:text-dark-muted border-t border-gray-200/20 dark:border-white/5 pt-1.5">
                              <span>Page: {src.page_number}</span>
                              <span className="font-mono text-brand-400">Score: {(src.similarity_score * 100).toFixed(0)}%</span>
                            </div>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}

                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Form Panel */}
        <footer className="p-4 border-t border-gray-200/50 dark:border-white/5 bg-gray-50/50 dark:bg-dark-bg/25">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              placeholder="Ask a question about your files..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isStreaming}
              className="flex-grow px-4 py-3 rounded-xl border border-gray-300 dark:border-dark-border bg-white dark:bg-dark-bg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-sm"
            />
            <Button 
              type="submit" 
              disabled={!input.trim() || isStreaming}
              className="px-5"
            >
              <Send className="w-4 h-4" />
            </Button>
          </form>
        </footer>

      </div>
    </div>
  );
};


