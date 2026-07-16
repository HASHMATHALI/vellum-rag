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
  Zap,
  HelpCircle,
  FileText
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
    <div className="h-[calc(100vh-8rem)] flex rounded-3xl border border-gray-200/50 dark:border-white/5 overflow-hidden bg-white/80 dark:bg-dark-card/45 backdrop-blur-md shadow-2xl animate-fade-in">
      
      {/* Sidebar - Conversation History threads */}
      <aside className="w-64 border-r border-gray-200/50 dark:border-white/5 bg-gray-50/20 dark:bg-dark-bg/10 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200/50 dark:border-white/5">
          <button 
            onClick={startNewChat}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-2xl bg-zinc-950 hover:bg-zinc-800 dark:bg-white dark:hover:bg-zinc-100 text-white dark:text-black font-bold text-xs border border-zinc-950 dark:border-white transition-all duration-300 active:scale-98"
          >
            <Plus className="w-4 h-4" />
            <span>New Session</span>
          </button>
        </div>
        
        {/* Threads List */}
        <div className="flex-grow overflow-y-auto p-2.5 space-y-1.5">
          {sessions.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-400 dark:text-dark-muted font-medium">
              No recent conversations.
            </div>
          ) : (
            sessions.map((sess) => (
              <button
                key={sess.id}
                onClick={() => loadSessionMessages(sess.id)}
                className={`
                  w-full text-left px-4 py-3 rounded-2xl text-xs font-bold truncate transition-all duration-200 flex items-center gap-3 hover:-translate-x-0.5 active:scale-98 ${
                    activeSessionId === sess.id
                      ? 'bg-zinc-100 dark:bg-zinc-800/80 text-zinc-950 dark:text-white border-l-4 border-zinc-900 dark:border-white'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800/40 text-gray-600 dark:text-gray-400 border-l-4 border-transparent'
                  }
                `}
              >
                <MessageSquare className="w-4 h-4 shrink-0 text-brand-500/60" />
                <span className="truncate">{sess.title}</span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main Chat Panel */}
      <div className="flex-grow flex flex-col min-w-0 bg-white/40 dark:bg-dark-card/10">
        
        {/* Thread header control settings */}
        <header className="px-6 py-4 border-b border-gray-200/50 dark:border-white/5 flex items-center justify-between bg-gray-50/30 dark:bg-dark-bg/5">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-gray-500 dark:text-dark-muted uppercase tracking-wider">Retrieval Engine:</span>
            <select
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value)}
              className="text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all font-bold cursor-pointer"
            >
              <option value="semantic">Semantic Search</option>
              <option value="mmr">MMR (Diverse Rerank)</option>
              <option value="hybrid">Hybrid (Semantic + Keyword)</option>
            </select>
          </div>

          <button 
            onClick={() => setShowConfig(!showConfig)}
            className="p-2.5 rounded-xl border border-gray-200 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-gray-800 transition-all text-gray-500 active:scale-95 shadow-sm"
            title="Tuning Configs"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </header>

        {/* Configuration settings overlay box */}
        {showConfig && (
          <div className="px-6 py-4 bg-gray-50 dark:bg-dark-bg/60 border-b border-gray-200/50 dark:border-white/5 text-xs grid grid-cols-2 gap-6 animate-fade-in">
            <div className="space-y-2">
              <label className="font-bold text-gray-500 dark:text-dark-muted">Retrieval Chunks Count (k)</label>
              <div className="flex items-center gap-4">
                <input 
                  type="range" min="1" max="15" value={k} 
                  onChange={(e) => setK(parseInt(e.target.value))}
                  className="w-full accent-brand-500 h-1.5 bg-gray-200 dark:bg-dark-border rounded-lg cursor-pointer"
                />
                <span className="font-mono font-bold text-brand-500 shrink-0 bg-brand-500/10 px-2.5 py-1 rounded-md">{k} chunks</span>
              </div>
            </div>
            <div className="text-gray-400 dark:text-dark-muted flex items-center justify-end font-semibold">
              Adjust configurations to tune prompt source context size.
            </div>
          </div>
        )}

        {/* Messages Stream Container */}
        <div className="flex-grow overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center p-4">
              <Card spotlight hoverEffect className="p-8 max-w-lg w-full text-center border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-2xl rounded-3xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-zinc-300 dark:bg-zinc-800" />
                <div className="w-16 h-16 rounded-2xl bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 flex items-center justify-center mx-auto mb-6 shadow-inner animate-float border border-zinc-200/50 dark:border-zinc-700/50">
                  <Zap className="w-8 h-8" />
                </div>
                <h3 className="font-display font-black text-2xl mb-3 text-gray-900 dark:text-white">Vellum Assistant</h3>
                <p className="text-xs text-gray-500 dark:text-dark-muted mb-8 leading-relaxed max-w-sm mx-auto">
                  Ask questions about your uploaded documents. Responses are generated in real-time with document citations and similarity metrics.
                </p>
                
                <div className="w-full space-y-3">
                  {suggestedQuestions.map((q) => (
                    <div 
                      key={q}
                      onClick={() => setInput(q)}
                      className="w-full text-left p-3.5 rounded-2xl border border-gray-200/80 dark:border-dark-border/80 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-brand-500/5 cursor-pointer flex items-center gap-3.5 group transition-all duration-300 bg-white/40 dark:bg-dark-bg/20"
                    >
                      <div className="w-8 h-8 rounded-xl bg-brand-500/10 text-brand-500 flex items-center justify-center group-hover:scale-110 transition-all shadow-sm shrink-0">
                        <HelpCircle className="w-4.5 h-4.5" />
                      </div>
                      <span className="text-xs font-bold text-gray-700 dark:text-gray-200">{q}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div 
                  key={msg.id} 
                  className={`flex flex-col gap-2.5 max-w-[85%] ${
                    isUser ? 'ml-auto items-end animate-fade-in' : 'mr-auto items-start'
                  }`}
                >
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-gray-400 dark:text-dark-muted font-bold px-1">
                    <span>{isUser ? 'You' : 'Vellum Assistant'}</span>
                  </div>

                  <div className={`p-4.5 rounded-3xl relative group shadow-sm border ${
                    isUser 
                      ? 'bg-zinc-950 dark:bg-zinc-900 text-white rounded-br-none border-zinc-900 dark:border-zinc-800' 
                      : 'bg-zinc-50 dark:bg-zinc-950/40 rounded-bl-none text-zinc-900 dark:text-zinc-100 border-zinc-200/60 dark:border-zinc-800/80'
                  }`}>
                    {/* Copy Button */}
                    <button
                      onClick={() => handleCopy(msg.content, msg.id)}
                      className={`
                        absolute top-2 right-2 p-1.5 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity bg-white dark:bg-dark-card border border-gray-200/50 dark:border-white/5 text-gray-500 hover:text-gray-700 active:scale-95 shadow-sm
                      `}
                      title="Copy response"
                    >
                      {copiedId === msg.id ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>

                    {/* Markdown responses */}
                    <div className={`markdown-body text-sm max-w-none break-words ${
                      isUser ? 'text-white' : ''
                    }`}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {/* Sources Cited Preview Tiles */}
                  {!isUser && msg.sources && msg.sources.length > 0 && !msg.content.toLowerCase().includes('general knowledge') && (
                    <div className="mt-2.5 space-y-2 w-full animate-fade-in">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 dark:text-dark-muted flex items-center gap-1.5 px-1">
                        <BookOpen className="w-4 h-4 text-brand-500" />
                        <span>Sources Cited ({msg.sources.length})</span>
                      </span>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4.5 w-full">
                        {msg.sources.map((src, sIdx) => (
                          <Card 
                            key={sIdx} 
                            spotlight
                            hoverEffect
                            className="p-4 border border-gray-200/50 dark:border-white/5 bg-gray-50/50 dark:bg-dark-bg/25 text-[11px] leading-relaxed flex flex-col justify-between rounded-2xl shadow-sm"
                          >
                            <div>
                              <div className="flex items-center gap-1.5 font-bold text-gray-700 dark:text-gray-200 mb-2 truncate" title={src.filename}>
                                <FileText className="w-4 h-4 text-brand-500 shrink-0" />
                                <span className="truncate text-xs font-bold">{src.filename}</span>
                              </div>
                              <p className="text-gray-500 dark:text-dark-muted line-clamp-3 italic mb-3 leading-relaxed">
                                "{src.text_content}"
                              </p>
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-gray-400 dark:text-dark-muted border-t border-gray-200/20 dark:border-white/5 pt-2">
                              <span className="font-bold">Page: {src.page_number}</span>
                              <span className="font-mono font-black text-brand-500">Score: {(src.similarity_score * 100).toFixed(0)}%</span>
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
        <footer className="p-4 border-t border-gray-200/50 dark:border-white/5 bg-gray-50/20 dark:bg-dark-bg/5">
          <form onSubmit={handleSubmit} className="flex gap-3 max-w-4xl mx-auto w-full">
            <input
              type="text"
              placeholder="Ask a question about your files..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isStreaming}
              className="flex-grow px-4.5 py-3 rounded-2xl border border-gray-300 dark:border-dark-border bg-white dark:bg-dark-bg focus:outline-none focus:ring-4 focus:ring-brand-500/10 focus:border-brand-500 text-sm transition-all shadow-sm"
            />
            <button 
              type="submit" 
              disabled={!input.trim() || isStreaming}
              className="px-5 rounded-2xl bg-zinc-950 hover:bg-zinc-800 dark:bg-white dark:hover:bg-zinc-100 text-white dark:text-black border border-zinc-950 dark:border-white transition-all duration-300 flex items-center justify-center active:scale-97 disabled:opacity-40 disabled:pointer-events-none"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </footer>

      </div>
    </div>
  );
};
