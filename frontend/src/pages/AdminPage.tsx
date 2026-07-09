import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { 
  Users, 
  FileText, 
  MessageSquare, 
  HardDrive, 
  Terminal, 
  CheckCircle2, 
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  Cpu
} from 'lucide-react';

interface Stats {
  total_users: number;
  total_documents: number;
  storage_used_mb: number;
  queries_today: number;
  most_asked_questions: string[];
  api_usage: {
    auth_requests: number;
    indexing_jobs: number;
    llm_tokens_estimated: number;
  };
}

interface Health {
  status: string;
  vector_store_size: number;
  services: {
    database: string;
    vector_store: string;
  };
}

export const AdminPage: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAdminData = async () => {
    setLoading(true);
    try {
      const [statsRes, healthRes, logsRes] = await Promise.all([
        api.get('/api/stats'),
        api.get('/api/health'),
        api.get('/api/logs?limit=50')
      ]);
      setStats(statsRes.data);
      setHealth(healthRes.data);
      setLogs(logsRes.data.logs);
    } catch (error) {
      console.error('Failed to load admin stats:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, []);

  return (
    <div className="space-y-8">
      
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold">Admin Console</h2>
          <p className="text-sm text-gray-500 dark:text-dark-muted">Platform-wide statistics, service health, and application logs.</p>
        </div>
        <Button onClick={fetchAdminData} loading={loading}>
          <RefreshCw className="w-4 h-4 mr-2" />
          <span>Refresh Console</span>
        </Button>
      </div>

      {/* Aggregate Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Registered Users</span>
              <h3 className="text-3xl font-extrabold font-display mt-1">{stats.total_users}</h3>
            </div>
            <div className="w-10 h-10 rounded-xl bg-brand-100 dark:bg-brand-950/40 text-brand-500 flex items-center justify-center">
              <Users className="w-5 h-5" />
            </div>
          </Card>

          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Indexed Files</span>
              <h3 className="text-3xl font-extrabold font-display mt-1">{stats.total_documents}</h3>
            </div>
            <div className="w-10 h-10 rounded-xl bg-indigo-100 dark:bg-indigo-950/40 text-indigo-500 flex items-center justify-center">
              <FileText className="w-5 h-5" />
            </div>
          </Card>

          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Queries (24h)</span>
              <h3 className="text-3xl font-extrabold font-display mt-1">{stats.queries_today}</h3>
            </div>
            <div className="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-950/40 text-purple-500 flex items-center justify-center">
              <MessageSquare className="w-5 h-5" />
            </div>
          </Card>

          <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Storage Used</span>
              <h3 className="text-3xl font-extrabold font-display mt-1">{stats.storage_used_mb} MB</h3>
            </div>
            <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-950/40 text-emerald-500 flex items-center justify-center">
              <HardDrive className="w-5 h-5" />
            </div>
          </Card>
        </div>
      )}

      {/* Row 2: Service Health Diagnostic & API Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Health Probe Checklist */}
        <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg flex flex-col justify-between">
          <div>
            <h3 className="font-display font-bold text-base mb-4">Diagnostics Health Probe</h3>
            {health ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">PostgreSQL Link</span>
                  </div>
                  {health.services.database === 'healthy' ? (
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-500">
                      <CheckCircle2 className="w-4 h-4" /> Healthy
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-red-500">
                      <AlertTriangle className="w-4 h-4" /> Faulty
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">FAISS Vector store</span>
                  </div>
                  {health.services.vector_store === 'healthy' ? (
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-500">
                      <CheckCircle2 className="w-4 h-4" /> Healthy
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-red-500">
                      <AlertTriangle className="w-4 h-4" /> Down
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5">
                  <span className="text-sm font-semibold">Indexed Vectors</span>
                  <span className="font-mono text-xs font-bold text-brand-500">{health.vector_store_size} embeddings</span>
                </div>
              </div>
            ) : (
              <div className="p-6 text-center text-gray-500 text-xs">Awaiting diagnostics metrics...</div>
            )}
          </div>
          <div className="text-[10px] text-gray-400 dark:text-dark-muted border-t border-gray-200/20 dark:border-white/5 pt-4 mt-6">
            Probes execute asynchronously on background API intervals.
          </div>
        </Card>

        {/* API Usage limits panel */}
        <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg lg:col-span-2">
          <h3 className="font-display font-bold text-base mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-brand-500" />
            <span>Usage Metrics (Today)</span>
          </h3>
          {stats ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5 text-center">
                <span className="text-xs text-gray-500">Auth Actions</span>
                <p className="text-2xl font-bold font-mono mt-1">{stats.api_usage.auth_requests}</p>
              </div>

              <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5 text-center">
                <span className="text-xs text-gray-500">Indexing Workloads</span>
                <p className="text-2xl font-bold font-mono mt-1">{stats.api_usage.indexing_jobs}</p>
              </div>

              <div className="p-4 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200/30 dark:border-white/5 text-center">
                <span className="text-xs text-gray-500">Est. LLM Tokens</span>
                <p className="text-2xl font-bold font-mono mt-1">{stats.api_usage.llm_tokens_estimated}</p>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-gray-400 text-xs">Waiting for stats loading...</div>
          )}

          {stats && stats.most_asked_questions.length > 0 && (
            <div className="mt-6">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Recent Conversational Prompts</h4>
              <ul className="space-y-2 text-xs">
                {stats.most_asked_questions.map((q, idx) => (
                  <li key={idx} className="p-2.5 rounded-lg bg-gray-50/50 dark:bg-dark-bg/25 border border-gray-200/20 dark:border-white/5 truncate font-medium">
                    "{q}"
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>

      {/* Row 3: Application Console logs */}
      <Card className="p-6 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg">
        <h3 className="font-display font-bold text-base mb-4 flex items-center gap-2">
          <Terminal className="w-5 h-5 text-brand-500" />
          <span>System Console Logs</span>
        </h3>
        
        <pre className="bg-gray-900 text-emerald-400 p-5 rounded-2xl text-xs font-mono overflow-auto max-h-[300px] border border-white/5 flex flex-col gap-1.5 scroll-smooth">
          {logs.map((log, idx) => (
            <code key={idx} className="whitespace-pre-wrap">{log}</code>
          ))}
        </pre>
      </Card>

    </div>
  );
};


