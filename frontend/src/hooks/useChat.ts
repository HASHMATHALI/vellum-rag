import { useState, useCallback } from 'react';
import api from '../services/api';

export interface Source {
  document_id: number;
  filename: string;
  chunk_index: number;
  page_number: number;
  similarity_score: number;
  text_content: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
  created_at: string;
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
    searchMode: string = 'semantic',
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

    const token = localStorage.getItem('token');
    
    const backendUrl = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? ''
      : 'https://rag-backend-8pv0.onrender.com';

    try {
      // Use vanilla fetch for custom POST streaming headers - call backend directly to bypass static site buffering proxies
      const response = await fetch(`${backendUrl}/api/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: messageText,
          session_id: activeSessionId,
          search_mode: searchMode,
          document_ids: documentIds,
          k: k
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP status ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Readable stream not supported.');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let currentReplyContent = '';
      let sourcesList: Source[] = [];

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
            const eventType = trimmed.substring(6).trim();
            // We can read next line if needed, but in our backend, each packet is single-lined
            // We search for type events
            if (eventType === 'close') {
              // Done streaming
            }
          } else if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.substring(5).trim();
            if (dataStr === '[DONE]') continue;
            
            try {
              const dataObj = JSON.parse(dataStr);
              
              // Handle custom session initialization
              if (dataObj.session_id) {
                setActiveSessionId(dataObj.session_id);
                fetchSessions(); // Refresh sessions list
              } 
              // Handle citations list
              else if (Array.isArray(dataObj)) {
                sourcesList = dataObj;
                setActiveSources(dataObj);
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantMsgId
                      ? { ...m, sources: dataObj }
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
      setTimeout(() => {
        if (activeSessionId) {
          loadSessionMessages(activeSessionId);
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

