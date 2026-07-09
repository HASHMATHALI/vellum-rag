import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Settings, Sliders, ToggleLeft } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [searchMode, setSearchMode] = useState<string>(() => localStorage.getItem('searchMode') || 'semantic');
  const [k, setK] = useState<number>(() => parseInt(localStorage.getItem('k') || '5'));
  const [lambda, setLambda] = useState<number>(() => parseFloat(localStorage.getItem('lambda') || '0.5'));
  const [semanticWeight, setSemanticWeight] = useState<number>(() => parseFloat(localStorage.getItem('semanticWeight') || '0.7'));
  const [status, setStatus] = useState<string | null>(null);

  const handleSave = () => {
    localStorage.setItem('searchMode', searchMode);
    localStorage.setItem('k', k.toString());
    localStorage.setItem('lambda', lambda.toString());
    localStorage.setItem('semanticWeight', semanticWeight.toString());
    setStatus('Preferences updated successfully.');
    setTimeout(() => setStatus(null), 3000);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold flex items-center gap-2">
          <Settings className="w-6 h-6 text-brand-500" />
          <span>Search & Retrieval Settings</span>
        </h2>
        <p className="text-sm text-gray-500 dark:text-dark-muted">Configure default parameters for prompt context retrieval and indexing matching.</p>
      </div>

      <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg space-y-6">
        {status && (
          <div className="p-3.5 rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400 text-xs font-semibold border border-emerald-500/10">
            {status}
          </div>
        )}

        {/* 1. Retrieval Algorithm */}
        <div className="space-y-3">
          <h3 className="font-semibold text-base flex items-center gap-2">
            <ToggleLeft className="w-5 h-5 text-brand-500" />
            <span>Default Retrieval Algorithm</span>
          </h3>
          <p className="text-xs text-gray-500 dark:text-dark-muted leading-relaxed">
            Select the default algorithm used to search document collections. Can be overridden inside individual chat threads.
          </p>
          <div className="grid grid-cols-3 gap-4">
            {['semantic', 'mmr', 'hybrid'].map((mode) => (
              <button
                key={mode}
                onClick={() => setSearchMode(mode)}
                className={`
                  p-4 rounded-xl border text-center capitalize font-semibold transition-all duration-150 ${
                    searchMode === mode 
                      ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-950/10 dark:text-brand-400'
                      : 'border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-gray-800'
                  }
                `}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        <div className="h-px bg-gray-200 dark:bg-dark-border" />

        {/* 2. Knobs / Weights */}
        <div className="space-y-6">
          <h3 className="font-semibold text-base flex items-center gap-2">
            <Sliders className="w-5 h-5 text-brand-500" />
            <span>Retrieval Fine-Tuning</span>
          </h3>

          {/* Top-K slider */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="font-semibold">Top-K Documents (k)</span>
              <span className="font-mono text-brand-500 font-bold">{k} chunks</span>
            </div>
            <p className="text-xs text-gray-500 dark:text-dark-muted">
              The maximum number of matching document chunks retrieved and added to the LLM system prompt context window.
            </p>
            <input 
              type="range" 
              min="1" 
              max="15" 
              value={k} 
              onChange={(e) => setK(parseInt(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-dark-border accent-brand-500"
            />
          </div>

          {/* MMR Lambda */}
          {searchMode === 'mmr' && (
            <div className="space-y-2 animate-fade-in">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">MMR Diversity Factor (λ)</span>
                <span className="font-mono text-brand-500 font-bold">{lambda}</span>
              </div>
              <p className="text-xs text-gray-500 dark:text-dark-muted">
                Controls the balance between document relevance (1.0) and chunk content uniqueness (0.0). Higher values yield closer semantic links; lower values yield more unique viewpoints.
              </p>
              <input 
                type="range" 
                min="0.0" 
                max="1.0" 
                step="0.05"
                value={lambda} 
                onChange={(e) => setLambda(parseFloat(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-dark-border accent-brand-500"
              />
            </div>
          )}

          {/* Hybrid semantic weight */}
          {searchMode === 'hybrid' && (
            <div className="space-y-2 animate-fade-in">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">Hybrid Search Semantic Weight</span>
                <span className="font-mono text-brand-500 font-bold">{(semanticWeight * 100).toFixed(0)}% Vector / {((1 - semanticWeight) * 100).toFixed(0)}% Keyword</span>
              </div>
              <p className="text-xs text-gray-500 dark:text-dark-muted">
                Weight assigned to semantic vector similarity score versus direct SQL pattern text match scores.
              </p>
              <input 
                type="range" 
                min="0.0" 
                max="1.0" 
                step="0.05"
                value={semanticWeight} 
                onChange={(e) => setSemanticWeight(parseFloat(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-dark-border accent-brand-500"
              />
            </div>
          )}
        </div>

        <div className="h-px bg-gray-200 dark:bg-dark-border" />

        <Button onClick={handleSave} className="px-6 py-2.5">
          Save Settings
        </Button>
      </Card>
    </div>
  );
};


