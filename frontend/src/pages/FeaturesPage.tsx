import React from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useNavigate } from 'react-router-dom';
import { 
  FileSearch, 
  Layers, 
  GitBranch, 
  FileText, 
  HelpCircle 
} from 'lucide-react';

export const FeaturesPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="text-center max-w-3xl mx-auto mb-16">
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold mb-4">
          Advanced Retrieval & <span className="gradient-text">Search Architecture</span>
        </h1>
        <p className="text-gray-600 dark:text-dark-muted leading-relaxed">
          Discover the high-performance retrieval and processing layers that power Vellum, allowing sub-100ms answers over large collections.
        </p>
      </div>

      {/* Main Algorithm breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 mb-16 items-center">
        <div className="space-y-6">
          <h2 className="font-display text-3xl font-bold tracking-tight">Flexible Retrieval Strategies</h2>
          <p className="text-gray-600 dark:text-dark-muted leading-relaxed text-sm">
            Configure how your document context is selected. Our platform supports three advanced search algorithms suited for different RAG use cases.
          </p>

          <div className="space-y-4">
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-500 flex items-center justify-center shrink-0">
                <FileSearch className="w-4 h-4" />
              </div>
              <div>
                <h4 className="font-bold text-base mb-1">Standard Semantic Search</h4>
                <p className="text-xs text-gray-500 dark:text-dark-muted">
                  Performs a cosine-similarity check between user queries and text chunks. Ideal for retrieving conceptually matching segments.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center shrink-0">
                <GitBranch className="w-4 h-4" />
              </div>
              <div>
                <h4 className="font-bold text-base mb-1">Maximal Marginal Relevance (MMR)</h4>
                <p className="text-xs text-gray-500 dark:text-dark-muted">
                  Balances keyword/context relevance with structural diversity, preventing redundant chunks from dominating the LLM prompt.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-500 flex items-center justify-center shrink-0">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h4 className="font-bold text-base mb-1">Hybrid (Keyword + Vector) Search</h4>
                <p className="text-xs text-gray-500 dark:text-dark-muted">
                  Fuses semantic vector scores with traditional database word matching (ILike/Keyword Index). Excellent for finding precise technical terms or serial numbers.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Algorithm Visualization Card */}
        <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card/50 shadow-xl space-y-6">
          <div className="flex items-center justify-between border-b border-gray-200/50 dark:border-white/5 pb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-500">Pipeline Visualization</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-100 text-brand-800 dark:bg-brand-950/40 dark:text-brand-400">pgvector Indexer</span>
          </div>

          <div className="space-y-4">
            <div className="p-3 bg-gray-50 dark:bg-dark-bg rounded-xl border border-gray-200/30 dark:border-white/5 text-xs">
              <span className="font-bold block mb-1">Step 1: Document Upload</span>
              User uploads PDF/DOCX. Parser extracts text page-by-page.
            </div>
            <div className="p-3 bg-gray-50 dark:bg-dark-bg rounded-xl border border-gray-200/30 dark:border-white/5 text-xs">
              <span className="font-bold block mb-1">Step 2: Recursive Chunking</span>
              Text is chunked into 500-char intervals with 50-char overlap.
            </div>
            <div className="p-3 bg-gray-50 dark:bg-dark-bg rounded-xl border border-gray-200/30 dark:border-white/5 text-xs">
              <span className="font-bold block mb-1">Step 3: Vector Embeddings Generation</span>
              all-MiniLM-L6-v2 maps each chunk to a 384-dimensional dense float vector.
            </div>
            <div className="p-3 bg-gray-50 dark:bg-dark-bg rounded-xl border border-gray-200/30 dark:border-white/5 text-xs">
              <span className="font-bold block mb-1">Step 4: Vector Storage (pgvector)</span>
              Vectors are written directly to PostgreSQL pgvector columns.
            </div>
          </div>
        </Card>
      </div>

      {/* Dynamic CTA */}
      <div className="text-center py-8">
        <Button size="lg" onClick={() => navigate('/dashboard')}>
          Launch Vellum Console
        </Button>
      </div>
    </div>
  );
};


