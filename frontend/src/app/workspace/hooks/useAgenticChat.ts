
import { useState, useCallback, useRef, useEffect } from 'react';
import { isTokenExpired, refreshAccessToken } from '@/utils/auth';

const AGENTIC_LOCK_KEY = '__agenticChatLockTime';
const LOCK_TIMEOUT_MS = 120_000; // 2 minutes
function isAgenticLocked(): boolean {
  if (typeof window === 'undefined') return false;
  const lockTime = (window as any)[AGENTIC_LOCK_KEY] as number | undefined;
  if (!lockTime) return false;
  if (Date.now() - lockTime > LOCK_TIMEOUT_MS) return false;
  return true;
}
function setAgenticLock(locked: boolean): void {
  if (typeof window !== 'undefined') {
    (window as any)[AGENTIC_LOCK_KEY] = locked ? Date.now() : 0;
  }
}

export type AgenticEventType =
  | 'start'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'text_chunk'
  | 'document_created'  // Hybrid DOCX Architecture: document creation event
  | 'system_message'    // Context compaction or other system notifications
  | 'error'
  | 'end';

export type AgenticStatus =
  | 'idle'
  | 'connecting'
  | 'running'
  | 'executing_tool'
  | 'completed'
  | 'error';

export interface ToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, any>;
  timestamp: string;
  result?: ToolResult;
}

export interface ToolResult {
  success: boolean;
  result: Record<string, any>;
  error?: string;
  execution_time_ms: number;
}

export interface AgenticEvent {
  type: AgenticEventType;
  data: Record<string, any>;
  timestamp: string;
}

export interface AgenticSession {
  sessionId: string;
  workspaceId?: string;
  model: string;
  iterations: number;
  toolCallCount: number;
  documentsModified: string[];
  totalCostUsd?: number;
  totalPromptTokens?: number;
  totalCompletionTokens?: number;
}

export interface DocumentState {
  path: string;
  content: string;
  description?: string;
  format?: 'html' | 'docx';
  hasDocx?: boolean;
  isSynced?: boolean;
}

export interface DocumentCreatedEvent {
  path: string;
  description?: string;
  sessionId: string;
  format?: string;
  hasDocx?: boolean;
}

interface UseAgenticChatOptions {
  apiBaseUrl?: string;
  endpoint?: string;
  onToolCall?: (toolCall: ToolCall) => void;
  onToolResult?: (toolCall: ToolCall, result: ToolResult) => void;
  onTextChunk?: (content: string) => void;
  onThinking?: (content: string) => void;
  onDocumentUpdate?: (path: string, content: string, docType?: string, replacementText?: string) => void;
  onDocumentCreated?: (event: DocumentCreatedEvent) => void;  // Hybrid DOCX: new document created
  onDocumentDeleted?: (path: string) => void;
  onSystemMessage?: (content: string) => void;
  onComplete?: (session: AgenticSession) => void;
  onError?: (error: string) => void;
  onCreditsExhausted?: () => void;
}

export function resolveAgenticEndpoint(
  override?: string,
  _requestBody?: { planner_mode?: boolean; coordinator_mode?: boolean }
): string {
  if (override) return override;
  return '/api/v1/agentic/chat';
}

export type AgenticMode = 'default' | 'plan' | 'coordinator';

export function flagsForMode(mode: AgenticMode): {
  planner_mode?: boolean;
  coordinator_mode?: boolean;
} {
  switch (mode) {
    case 'plan':
      return { planner_mode: true };
    case 'coordinator':
      return { coordinator_mode: true };
    case 'default':
    default:
      return {};
  }
}

export function initialModeFromUrl(): AgenticMode {
  if (typeof window === 'undefined') return 'default';
  try {
    const params = new URLSearchParams(window.location.search);
    const ls = window.localStorage;
    const on = (q: string, k: string) => params.get(q) === '1' || ls?.getItem(k) === '1';
    if (on('coord', 'agentic_coord')) return 'coordinator';
    if (on('plan', 'agentic_plan')) return 'plan';
  } catch {
  }
  return 'default';
}

export function detectModeFromText(_text: string): AgenticMode | null {
  return null;
}

interface AgenticChatRequest {
  message: string;
  documents: Record<string, { content: string; description?: string }>;
  active_document?: string;
  session_id?: string;
  thread_id?: string;
  playbook?: string;
  context?: Record<string, string>;
  history?: Array<{ role: string; content: string }>;
  attached_files?: string[];

  coordinator_mode?: boolean;
  planner_mode?: boolean;
  approved_plan?: Record<string, unknown>;
  approved_mode_change?: Record<string, unknown>;
  max_budget_usd?: number;
  model?: string;
}

export function useAgenticChat(options: UseAgenticChatOptions = {}) {
  const {
    apiBaseUrl = process.env.NEXT_PUBLIC_BASE_URL || '',
    endpoint,
    onToolCall,
    onToolResult,
    onTextChunk,
    onThinking,
    onDocumentUpdate,
    onDocumentCreated,
    onDocumentDeleted,
    onSystemMessage,
    onComplete,
    onError,
    onCreditsExhausted,
  } = options;

  const [status, setStatus] = useState<AgenticStatus>('idle');
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [currentTool, setCurrentTool] = useState<string | null>(null);
  const [responseText, setResponseText] = useState<string>('');
  const [thinking, setThinking] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<AgenticSession | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const toolCallsRef = useRef<ToolCall[]>([]);

  const processEventRef = useRef<((event: AgenticEvent) => void) | null>(null);

  const completedRef = useRef(false);

  const sessionRef = useRef<AgenticSession | null>(null);

  const requestIdRef = useRef(0);

  const callbackRefs = useRef({
    onToolCall,
    onToolResult,
    onTextChunk,
    onThinking,
    onDocumentUpdate,
    onDocumentCreated,
    onDocumentDeleted,
    onSystemMessage,
    onComplete,
    onError,
  });
  callbackRefs.current = {
    onToolCall,
    onToolResult,
    onTextChunk,
    onThinking,
    onDocumentUpdate,
    onDocumentCreated,
    onDocumentDeleted,
    onSystemMessage,
    onComplete,
    onError,
  };

  const sendMessage = useCallback(async (request: AgenticChatRequest) => {
    if (isAgenticLocked()) {
      console.log('[SSE] Blocked by global lock: another hook instance has a request in flight');
      return;
    }
    setAgenticLock(true);

    const myRequestId = ++requestIdRef.current;

    setStatus('connecting');
    setToolCalls([]);
    toolCallsRef.current = [];
    setCurrentTool(null);
    setResponseText('');
    setThinking('');
    setError(null);
    setSession(null);
    completedRef.current = false;
    sessionRef.current = null;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      let token = localStorage.getItem('auth_token');
      if (!token || isTokenExpired()) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
          throw new Error('Session expired. Please sign in again.');
        }
        token = localStorage.getItem('auth_token');
      }

      const chatEndpoint = resolveAgenticEndpoint(endpoint, request);
      const baseUrl = process.env.NEXT_PUBLIC_BASE_URL
        || (process.env.NODE_ENV === 'development'
            ? (process.env.NEXT_PUBLIC_FASTAPI_DEV_URL || 'http://localhost:8000')
            : '');
      const fullUrl = `${baseUrl}${chatEndpoint}`;
      console.log('[AGENTIC]', fullUrl, {
        planner_mode: request.planner_mode,
        coordinator_mode: request.coordinator_mode,
      });
      const makeRequest = (authToken: string) => fetch(fullUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: abortControllerRef.current!.signal,
      });

      let response = await makeRequest(token!);

      if (response.status === 401) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
          throw new Error('Session expired. Please sign in again.');
        }
        token = localStorage.getItem('auth_token');
        response = await makeRequest(token!);
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({})) as { error?: string; message?: string; detail?: string };
        if (response.status === 401) {
          throw new Error('Session expired. Please sign in again.');
        }
        if (response.status === 402) {
          onCreditsExhausted?.();
        }
        if (response.status === 403) {
          const detail = errorData.detail || errorData.error || 'This feature is not enabled for your account.';
          throw new Error(detail);
        }
        if (response.status === 503) {
          const detail = errorData.detail || 'Service temporarily unavailable. Please try again shortly.';
          throw new Error(detail);
        }
        const message = response.status === 402 && errorData.message
          ? errorData.message
          : (errorData.error || errorData.detail || `HTTP ${response.status}`);
        throw new Error(message);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      setStatus('running');
      console.log('[SSE] Stream started, reading events... (request #' + myRequestId + ')');
      const decoder = new TextDecoder();
      let buffer = '';

      let currentEventType = '';
      let currentEventData = '';

      let firstEventReceived = false;
      const noResponseTimeoutId = setTimeout(() => {
        if (!firstEventReceived) {
          console.warn('[SSE] No response within 30s, cancelling stream');
          reader.cancel('No response timeout');
        }
      }, 30_000);

      while (true) {
        if (requestIdRef.current !== myRequestId) {
          console.log('[SSE] Request #' + myRequestId + ' superseded by #' + requestIdRef.current + ', stopping');
          clearTimeout(noResponseTimeoutId);
          reader.cancel();
          return;
        }

        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') || line.startsWith('data:')) {
            currentEventData = line.startsWith('data: ') ? line.slice(6).trim() : line.slice(5).trim();

            if (currentEventType && currentEventData) {
              try {
                const event: AgenticEvent = {
                  type: currentEventType as AgenticEventType,
                  data: JSON.parse(currentEventData),
                  timestamp: new Date().toISOString(),
                };

                if (!firstEventReceived) {
                  firstEventReceived = true;
                  clearTimeout(noResponseTimeoutId);
                }

                if (processEventRef.current) {
                  processEventRef.current(event);
                } else {
                  console.warn('[SSE] processEventRef not yet set, dropping event:', event.type);
                }
              } catch (e) {
                console.error('[SSE] Error parsing event:', e, 'raw data:', currentEventData?.slice(0, 200));
              }

              currentEventType = '';
              currentEventData = '';
            }
          } else if (line.trim() === '') {
            currentEventType = '';
            currentEventData = '';
          }
        }
      }

      clearTimeout(noResponseTimeoutId); // Defensive cleanup if loop exits normally

      if (!completedRef.current) {
        console.warn('[SSE] Stream closed without end event (model timeout or network drop)');
        setToolCalls(prev => prev.map(tc => tc.result ? tc : {...tc,
          result: { success: false, result: { skipped: true }, execution_time_ms: 0 },
        }));
        setAgenticLock(false);
        const errorMsg = 'The model did not respond. The connection may have timed out — please try again.';
        setError(errorMsg);
        setStatus('error');
        onError?.(errorMsg);
      }

    } catch (err: any) {
      if (err.name === 'AbortError') {
        setAgenticLock(false);
        setStatus('idle');
        return;
      }

      setAgenticLock(false); // Release global lock only on genuine errors
      const errorMessage = err.message || 'Unknown error';
      setError(errorMessage);
      setStatus('error');
      onError?.(errorMessage);
    }
  }, [apiBaseUrl, onError]);

  const processEvent = useCallback((event: AgenticEvent) => {
    const cbs = callbackRefs.current;

    switch (event.type) {
      case 'start':
        const startSession: AgenticSession = {
          sessionId: event.data.workspace_id || event.data.session_id,
          workspaceId: event.data.workspace_id || event.data.session_id,
          model: event.data.model,
          iterations: 0,
          toolCallCount: 0,
          documentsModified: [],
        };
        sessionRef.current = startSession;
        setSession(startSession);
        break;

      case 'thinking':
        setResponseText('');
        setThinking(event.data.content || '');
        cbs.onThinking?.(event.data.content || '');
        break;

      case 'tool_call': {
        setStatus('executing_tool');
        setCurrentTool(event.data.tool_name);

        const tcId = event.data.tool_call_id || `call_${Date.now()}`;
        const toolCall: ToolCall = {
          id: tcId,
          tool_name: event.data.tool_name,
          arguments: event.data.arguments,
          timestamp: event.data.timestamp || new Date().toISOString(),
        };

        setToolCalls(prev => {
          const existingIdx = prev.findIndex(tc => tc.id === tcId);
          if (existingIdx !== -1) {
            const updated = [...prev];
            updated[existingIdx] = {...updated[existingIdx],...toolCall };
            toolCallsRef.current = updated;
            return updated;
          }
          const updated = [...prev, toolCall];
          toolCallsRef.current = updated;
          return updated;
        });
        cbs.onToolCall?.(toolCall);
        break;
      }

      case 'tool_result': {
        setStatus('running');
        setCurrentTool(null);

        const result: ToolResult = {
          success: event.data.success,
          result: event.data.result,
          error: event.data.error,
          execution_time_ms: event.data.execution_time_ms,
        };

        const resultTcId = event.data.tool_call_id;

        setToolCalls(prev => {
          const matchIdx = resultTcId
            ? prev.findIndex(tc => tc.id === resultTcId)
            : prev.findIndex(tc => tc.tool_name === event.data.tool_name && !tc.result);
          if (matchIdx === -1) {
            toolCallsRef.current = prev;
            return prev;
          }
          const updated = prev.map((tc, i) =>
            i === matchIdx ? {...tc, result } : tc
          );
          toolCallsRef.current = updated;
          return updated;
        });

        const DOCX_MODIFYING_TOOLS = [
          'edit_document',
          'accept_revisions',
          'reject_revisions',
          'revert_edit',
          'edit_xml',
          'add_comment',
          'accept_all_changes',
          'reject_all_changes',
        ];
        if (result.success && DOCX_MODIFYING_TOOLS.includes(event.data.tool_name)) {
          const path = event.data.result?.path;
          const content = event.data.result?.content;
          const docType = event.data.result?.doc_type as string | undefined;
          const replacementText = event.data.result?.replacement_text as string | undefined;
          console.log(`[SSE] ${event.data.tool_name} result:`, { path, docType, hasReplacementText: !!replacementText, replacementTextPreview: replacementText?.substring(0, 80) });
          if (path) {
            cbs.onDocumentUpdate?.(path, content || '', docType, replacementText);
          }
        }

        if (result.success && event.data.tool_name === 'delete_document') {
          const path = event.data.result?.path as string | undefined;
          if (path) {
            cbs.onDocumentDeleted?.(path);
          }
        }

        const matchingCall = toolCallsRef.current.find(tc =>
          tc.id === resultTcId || (tc.tool_name === event.data.tool_name && !tc.result)
        );
        if (matchingCall) {
          cbs.onToolResult?.(matchingCall, result);
        }
        break;
      }

      case 'text_chunk':
        setResponseText(prev => prev + (event.data.content || ''));
        cbs.onTextChunk?.(event.data.content || '');
        break;

      case 'document_created':
        const docEvent: DocumentCreatedEvent = {
          path: event.data.path,
          description: event.data.description,
          sessionId: event.data.workspace_id || event.data.session_id,
          format: event.data.format,
          hasDocx: event.data.has_docx,
        };
        cbs.onDocumentCreated?.(docEvent);

        setSession(prev => prev ? {...prev,
          documentsModified: [...prev.documentsModified, event.data.path],
        } : null);
        break;

      case 'system_message':
        cbs.onSystemMessage?.(event.data.content || '');
        break;

      case 'error':
        setAgenticLock(false); // Release global lock
        setError(event.data.error);
        setStatus('error');
        cbs.onError?.(event.data.error);
        break;

      case 'end':
        if (completedRef.current) return;
        completedRef.current = true;

        setToolCalls(prev => {
          const hasUnresolved = prev.some(tc => !tc.result);
          if (!hasUnresolved) return prev;
          return prev.map(tc => {
            if (tc.result) return tc;
            if (tc.tool_name === 'enter_plan_mode' || tc.tool_name === 'exit_plan_mode') return tc;
            return {...tc,
              result: { success: true, result: { skipped: true }, execution_time_ms: 0 },
            };
          });
        });

        setAgenticLock(false); // Release global lock
        setStatus('completed');
        const finalSession: AgenticSession = {
          sessionId: event.data.workspace_id || event.data.session_id,
          workspaceId: event.data.workspace_id || event.data.session_id,
          model: sessionRef.current?.model || '',
          iterations: event.data.iterations || 0,
          toolCallCount: event.data.tool_calls || toolCallsRef.current.length,
          documentsModified: event.data.documents_modified || [],
          totalCostUsd: typeof event.data.total_cost_usd === 'number'
            ? event.data.total_cost_usd
            : undefined,
          totalPromptTokens: typeof event.data.total_prompt_tokens === 'number'
            ? event.data.total_prompt_tokens
            : undefined,
          totalCompletionTokens: typeof event.data.total_completion_tokens === 'number'
            ? event.data.total_completion_tokens
            : undefined,
        };
        sessionRef.current = finalSession;
        setSession(finalSession);
        cbs.onComplete?.(finalSession);
        break;
    }
  }, []); // No dependencies — all callbacks accessed via callbackRefs

  processEventRef.current = processEvent;

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const cancel = useCallback(() => {
    setAgenticLock(false); // Release global lock
    abortControllerRef.current?.abort();
    eventSourceRef.current?.close();
    setStatus('idle');
    setCurrentTool(null);
  }, []);

  const reset = useCallback(() => {
    cancel();
    setToolCalls([]);
    toolCallsRef.current = [];
    setResponseText('');
    setThinking('');
    setError(null);
    setSession(null);
  }, [cancel]);

  return {
    status,
    toolCalls,
    currentTool,
    responseText,
    thinking,
    error,
    session,

    isRunning: status === 'connecting' || status === 'running' || status === 'executing_tool',
    isCompleted: status === 'completed',
    hasError: status === 'error',

    sendMessage,
    cancel,
    reset,
  };
}

export default useAgenticChat;
