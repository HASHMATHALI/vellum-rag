import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Sparkles, Shield, Zap, Search, MessageSquare, ArrowRight } from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="relative overflow-hidden animate-fade-in">
      
      {/* Sleek Vercel Grid & Floating Orbs Overlay */}
      <div className="absolute inset-0 bg-grid-pattern -z-10 pointer-events-none opacity-80" />
      <div className="absolute top-[-10%] left-[-10%] w-[35rem] h-[35rem] rounded-full bg-gradient-to-br from-zinc-500/10 to-transparent blur-[8rem] animate-orb-1 -z-10 pointer-events-none" />
      <div className="absolute bottom-[10%] right-[-10%] w-[30rem] h-[30rem] rounded-full bg-gradient-to-br from-zinc-700/10 to-transparent blur-[8rem] animate-orb-2 -z-10 pointer-events-none" />

      {/* Hero Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-brand-200 bg-brand-50/50 text-brand-700 dark:border-brand-900/30 dark:bg-brand-900/10 dark:text-brand-300 font-bold text-xs tracking-wider uppercase mb-8 shadow-sm">
          <Zap className="w-4 h-4 text-brand-500" />
          <span>Semantic Document RAG Chat Platform</span>
        </div>

        <h1 className="font-display text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight mb-8 max-w-4xl mx-auto leading-[1.1] text-gray-900 dark:text-white">
          Decentralized Search. <br />
          <span className="gradient-text">Instant Answers.</span>
        </h1>

        <p className="text-lg md:text-xl text-gray-600 dark:text-dark-muted max-w-2xl mx-auto mb-10 leading-relaxed font-semibold">
          Upload PDFs, Word docs, and Markdown files. Query them using advanced semantic vector search and generate accurate responses with precise source citations.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4.5 mb-24 max-w-md mx-auto">
          <button 
            onClick={() => navigate('/dashboard')}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-3.5 rounded-2xl bg-zinc-950 hover:bg-zinc-800 dark:bg-white dark:hover:bg-zinc-100 text-white dark:text-black font-bold border border-zinc-900 dark:border-white hover:scale-[1.01] active:scale-98 transition-all duration-300 shadow-lg shadow-zinc-900/10 dark:shadow-zinc-100/5 text-sm"
          >
            <span>Launch Console</span>
            <ArrowRight className="w-4 h-4 shrink-0" />
          </button>
          <button 
            onClick={() => navigate('/docs')}
            className="w-full sm:w-auto px-8 py-3.5 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-transparent hover:bg-zinc-100/50 dark:hover:bg-zinc-900/40 text-zinc-600 dark:text-zinc-300 font-bold transition-all duration-300 text-sm hover:text-zinc-900 dark:hover:text-white"
          >
            Explore API Docs
          </button>
        </div>

        {/* Feature Grid Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          
          <Card spotlight hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm shadow-lg hover:shadow-xl rounded-3xl transition-all duration-300">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500/10 to-brand-600/10 text-brand-500 flex items-center justify-center mb-6 shadow-inner">
              <Search className="w-6 h-6" />
            </div>
            <h3 className="font-display font-black text-xl mb-3 text-gray-900 dark:text-white">Semantic Search</h3>
            <p className="text-gray-500 dark:text-dark-muted text-xs font-semibold leading-relaxed">
              Find content by concept and context rather than just keyword matches using the all-MiniLM-L6-v2 embeddings model.
            </p>
          </Card>

          <Card spotlight hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm shadow-lg hover:shadow-xl rounded-3xl transition-all duration-300">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500/10 to-indigo-600/10 text-indigo-500 flex items-center justify-center mb-6 shadow-inner">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="font-display font-black text-xl mb-3 text-gray-900 dark:text-white">Hybrid QA Chat</h3>
            <p className="text-gray-500 dark:text-dark-muted text-xs font-semibold leading-relaxed">
              Conversational QA driven by the Llama-3.3-70B model via Groq, complete with citation tags linking back to source pages.
            </p>
          </Card>

          <Card spotlight hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm shadow-lg hover:shadow-xl rounded-3xl transition-all duration-300">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500/10 to-purple-600/10 text-purple-500 flex items-center justify-center mb-6 shadow-inner">
              <Zap className="w-6 h-6" />
            </div>
            <h3 className="font-display font-black text-xl mb-3 text-gray-900 dark:text-white">Lightning Fast</h3>
            <p className="text-gray-500 dark:text-dark-muted text-xs font-semibold leading-relaxed">
              Sub-100ms retrieval times backed by pgvector SQL index. Fast streaming text chunks using Server-Sent Events.
            </p>
          </Card>
          
        </div>
      </section>


    </div>
  );
};
