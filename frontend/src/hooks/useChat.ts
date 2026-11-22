import { useState, useCallback } from 'react';
import api, { API_BASE_URL, getCsrfToken, refreshSession } from '../services/api';

export interface Source {
  ref?: number;
  cited?: boolean;
  section?: string | null;
  document_id: number;
  filename: string;
  chunk_index: number;
  page_number: number;
  similarity_score: number;
  text_content: string;
}

export type GlossStatus = 'supported' | 'partial' | 'unsupported' | 'phantom' | 'traceable' | 'uncited';

export interface GlossClaim {
  text: string;
  status: GlossStatus;
  support: number;
  citations: { ref?: number; filename: string | null; page: number | null; found: boolean }[];
  notes: string[];
}

export interface GlossReport {
  claims: GlossClaim[];
  summary: { total: number; grounding: number | null; retrieved_passages: number } & Record<GlossStatus, number>;
  method: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
  created_at: string;
  gloss?: GlossReport | null;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
}

export const useChat = () => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSources, setActiveSources] = useState<Source[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await api.get('/api/history');
      setSessions(response.data);
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    setLoading(true);
    try {
      const response = await api.get(`/api/history/${sessionId}`);
      setMessages(response.data);
      setActiveSessionId(sessionId);
      setActiveSources([]);
    } catch (error) {
      console.error('Failed to load session messages:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const startNewChat = useCallback(() => {
    setMessages([]);
    setActiveSessionId(null);
    setActiveSources([]);
  }, []);

  const sendMessage = useCallback(async (
    messageText: string,
    searchMode: string = 'hybrid',
    documentIds: number[] | null = null,
    k: number = 5
  ) => {
    if (!messageText.trim()) return;

    // Add user message to local state immediately
    const userMsgId = Math.random().toString();
    const userMessage: Message = {
      id: userMsgId,
      role: 'user',
      content: messageText,
      sources: [],
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);
    setIsStreaming(true);

    // Prepare assistant temporary state message
    const assistantMsgId = 'assistant-streaming';
    const tempAssistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      sources: [],
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempAssistantMsg]);

    const body = JSON.stringify({
      message: messageText,
      session_id: activeSessionId,
      search_mode: searchMode,
      document_ids: documentIds,
      k: k
    });
    // Cookies carry the session (HttpOnly); the CSRF token is sent as a header.
    const post = () => fetch(`${API_BASE_URL}/api/query`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() || '' },
      body
    });
    let sessionForRefresh: string | null = activeSessionId;

    try {
      let response = await post();
      if (response.status === 401 && await refreshSession()) {
        response = await post();
      }

      if (!response.ok) {
        let detail = `Server returned HTTP ${response.status}`;
        try {
          const err = await response.json();
          if (typeof err.detail === 'string') detail = err.detail;
          else if (Array.isArray(err.detail)) detail = err.detail.map((d: { msg?: string }) => d.msg).join('; ');
        } catch { /* non-JSON error body */ }
        if (response.status === 429) detail = 'Too many questions in a short time. Please wait a moment.';
        throw new Error(detail);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Readable stream not supported.');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let currentReplyContent = '';
      let currentEvent = 'message';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Save the last partial line back to the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          // SSE format parsing: event or data
          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.substring(6).trim();
          } else if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.substring(5).trim();
            if (dataStr === '[DONE]') continue;
            
            const eventType = currentEvent;
            currentEvent = 'message';
            try {
              const dataObj = JSON.parse(dataStr);

              if (eventType === 'error') {
                currentReplyContent += `

*${dataObj.detail || 'The answer could not be completed.'}*`;
                setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, content: currentReplyContent } : m));
              } else if (eventType === 'meta') {
                // timings / token usage / grounding signals: not rendered
              }
              // Handle custom session initialization
              else if (dataObj.session_id) {
                sessionForRefresh = dataObj.session_id;
                setActiveSessionId(dataObj.session_id);
                fetchSessions(); // Refresh sessions list
              } 
              // Handle citations list
              else if (Array.isArray(dataObj)) {
                setActiveSources(dataObj);
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantMsgId
                      ? { ...m, sources: dataObj }
                      : m
                  )
                );
              } 
              // Handle the citation check that follows the finished answer
              else if (dataObj.gloss) {
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantMsgId
                      ? { ...m, gloss: dataObj.gloss }
                      : m
                  )
                );
              }
              // Handle regular text chunk
              else if (dataObj.content !== undefined) {
                currentReplyContent += dataObj.content;
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantMsgId
                      ? { ...m, content: currentReplyContent }
                      : m
                  )
                );
              }
            } catch (e) {
              // Ignore line if not valid JSON
            }
          }
        }
      }
      
      // When streaming is completed, replace temporary ID with permanent state sync
      // (Wait briefly for backend database writes)
      // Reload the persisted thread (also marks which sources were actually cited).
      setTimeout(() => {
        if (sessionForRefresh) {
          loadSessionMessages(sessionForRefresh);
        }
      }, 500);

    } catch (error: any) {
      console.error('Streaming error:', error);
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, content: `*(Error streaming response: ${error.message})*` }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
    }
  }, [activeSessionId, fetchSessions, loadSessionMessages]);

  return {
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
  };
};

