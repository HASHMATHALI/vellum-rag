import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Sparkles, Shield, Zap, Search, MessageSquare, ArrowRight } from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="relative overflow-hidden">
      
      {/* Background Gradients */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(45rem_50rem_at_50%_-10rem,#eef2ff,transparent)] dark:bg-[radial-gradient(45rem_50rem_at_50%_-10rem,#1e293b,transparent)] opacity-70" />
      <div className="absolute top-[20%] left-[10%] w-[30rem] h-[30rem] -z-10 bg-brand-500/10 rounded-full blur-[10rem] animate-pulse" />
      <div className="absolute top-[40%] right-[10%] w-[25rem] h-[25rem] -z-10 bg-indigo-500/10 rounded-full blur-[8rem] animate-pulse" />

      {/* Hero Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-brand-200 bg-brand-50/50 text-brand-700 dark:border-brand-900/30 dark:bg-brand-900/10 dark:text-brand-300 font-semibold text-xs tracking-wider uppercase mb-8 shadow-sm">
          <Sparkles className="w-4 h-4 text-brand-500" />
          <span>Semantic Document RAG Chat Platform</span>
        </div>

        <h1 className="font-display text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight mb-8 max-w-4xl mx-auto leading-[1.1]">
          Decentralized Search. <br />
          <span className="gradient-text">Instant Answers.</span>
        </h1>

        <p className="text-lg md:text-xl text-gray-600 dark:text-dark-muted max-w-2xl mx-auto mb-10 leading-relaxed">
          Upload PDFs, Word docs, and Markdown files. Query them using advanced semantic vector search and generate accurate responses with precise source citations.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-20">
          <Button 
            size="lg" 
            onClick={() => navigate('/dashboard')}
            className="w-full sm:w-auto flex items-center gap-2 px-8"
          >
            <span>Get Started Free</span>
            <ArrowRight className="w-4 h-4" />
          </Button>
          <Button 
            size="lg" 
            variant="secondary"
            onClick={() => navigate('/docs')}
            className="w-full sm:w-auto"
          >
            Explore API Documentation
          </Button>
        </div>

        {/* Feature Grid Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <Card hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-brand-100 dark:bg-brand-950/40 text-brand-500 flex items-center justify-center mb-6">
              <Search className="w-6 h-6" />
            </div>
            <h3 className="font-display font-bold text-xl mb-3">Semantic Search</h3>
            <p className="text-gray-500 dark:text-dark-muted text-sm leading-relaxed">
              Find content by concept and context rather than just keyword matches using the all-MiniLM-L6-v2 embeddings model.
            </p>
          </Card>

          <Card hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-indigo-100 dark:bg-indigo-950/40 text-indigo-500 flex items-center justify-center mb-6">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="font-display font-bold text-xl mb-3">Hybrid QA Chat</h3>
            <p className="text-gray-500 dark:text-dark-muted text-sm leading-relaxed">
              Conversational QA driven by the Llama-3.3-70B model via Groq, complete with citation tags linking back to source pages.
            </p>
          </Card>

          <Card hoverEffect className="p-8 text-left border-gray-200/50 dark:border-white/5 bg-white/50 dark:bg-dark-card/50 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-purple-100 dark:bg-purple-950/40 text-purple-500 flex items-center justify-center mb-6">
              <Zap className="w-6 h-6" />
            </div>
            <h3 className="font-display font-bold text-xl mb-3">Lightning Fast</h3>
            <p className="text-gray-500 dark:text-dark-muted text-sm leading-relaxed">
              Sub-100ms retrieval times backed by FAISS local indexes. Fast streaming text chunks using Server-Sent Events.
            </p>
          </Card>
        </div>
      </section>

      {/* Security & Scale Banner */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 border-t border-gray-200/50 dark:border-white/5 text-center">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8 bg-brand-500/5 rounded-3xl p-10 border border-brand-500/10">
          <div className="text-left max-w-lg">
            <h2 className="font-display text-2xl font-bold mb-2 flex items-center gap-2">
              <Shield className="w-6 h-6 text-brand-500" />
              <span>Enterprise-Ready Security</span>
            </h2>
            <p className="text-sm text-gray-500 dark:text-dark-muted leading-relaxed">
              All documents are stored locally on isolated network folders. Access is secured by industry standard JWT authentication and fine-grained roles.
            </p>
          </div>
          <Button onClick={() => navigate('/login')} className="px-6 py-3 shrink-0">
            Sign Up and Try
          </Button>
        </div>
      </section>
    </div>
  );
};


