'use client';

import React, { useRef, useMemo, useCallback, useState, useEffect } from 'react';
import {
  useExternalStoreRuntime,
  type ThreadMessageLike,
} from '@assistant-ui/react';
import {
  useAgenticChat,
  flagsForMode,
  initialModeFromUrl,
  detectModeFromText,
  type AgenticMode,
  type ToolCall,
  type DocumentCreatedEvent,
} from '@/app/workspace/hooks/useAgenticChat';
import type { SlashCommand } from '@/app/workspace/components/SlashCommandMenu';

interface ToolCallWithUid extends ToolCall {
  __uid: string;
}

function makeToolCallPart(tc: ToolCallWithUid) {
  return {
    type: 'tool-call' as const,
    toolCallId: tc.__uid,
    toolName: tc.tool_name,
    args: tc.arguments || {},
    argsText: JSON.stringify(tc.arguments || {}),
    result: tc.result?.result,
    isError: tc.result ? !tc.result.success : false,
  };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  toolCalls?: ToolCallWithUid[];
  thinking?: string;
}

export interface AttachedFile {
  file: File;
  id: string;
  preview?: string; // data URL for image thumbnails
}

export interface UseAgenticRuntimeOptions {
  documentText?: string;
  selectedText?: string;
  sessionContext?: string;
  documentId?: string;
  documentName?: string;
  workspaceSessionId?: string;

  onAgenticSessionCreated?: (sessionId: string) => void;
  onDocumentUpdate?: (path: string, content: string, docType?: string, replacementText?: string) => void;
  onDocumentCreated?: (event: DocumentCreatedEvent) => void;
  onDocumentDeleted?: (path: string) => void;
  onOpenDocument?: (sessionId: string, documentPath: string) => void;

  onCreditsExhausted?: () => void;

  suggestions?: string[];

  initialThreadId?: string | null;
  onThreadIdChanged?: (threadId: string | null) => void;

  attachedFilesRef?: React.RefObject<AttachedFile[]>;
  clearAttachments?: () => void;
  slashCommands?: SlashCommand[];
}

export function useAgenticRuntime(options: UseAgenticRuntimeOptions) {
  const {
    documentText,
    selectedText,
    sessionContext,
    documentId,
    documentName,
    workspaceSessionId,
    onAgenticSessionCreated,
    onDocumentUpdate,
    onDocumentCreated,
    onDocumentDeleted,
    onOpenDocument,
    onCreditsExhausted,
    suggestions,
    initialThreadId,
    onThreadIdChanged,
    attachedFilesRef,
    clearAttachments,
    slashCommands,
  } = options;

  const slashCommandsRef = useRef<SlashCommand[] | undefined>(slashCommands);
  useEffect(() => { slashCommandsRef.current = slashCommands; }, [slashCommands]);

  const apiBaseUrl = process.env.NEXT_PUBLIC_BASE_URL || '';
  const [threadId, setThreadId] = useState<string | null>(initialThreadId ?? null);
  const threadIdRef = useRef<string | null>(initialThreadId ?? null);

  const [mode, setMode] = useState<AgenticMode>(() => initialModeFromUrl());
  const modeRef = useRef<AgenticMode>(mode);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  const lastUserMessageRef = useRef<string>('');
  const pendingPersistRef = useRef<{ threadId: string; userMsg: string; backendPersisted: boolean } | null>(null);
  useEffect(() => { threadIdRef.current = threadId; }, [threadId]);

  const parentThreadIdRef = useRef<string | null>(initialThreadId ?? null);
  useEffect(() => { parentThreadIdRef.current = initialThreadId ?? null; }, [initialThreadId]);

  const createThread = useCallback(async (title: string): Promise<string | null> => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${apiBaseUrl}/api/v1/threads`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ title }),
      });
      if (res.ok) {
        const data = await res.json();
        return data.id || data.thread_id || null;
      }
    } catch (e) { console.error('[THREAD] Failed to create:', e); }
    return null;
  }, [apiBaseUrl]);

  const persistMessage = useCallback(async (tid: string, userMessage: string, assistantMessage: string) => {
    try {
      const token = localStorage.getItem('auth_token');
      await fetch(`${apiBaseUrl}/api/v1/threads/${tid}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ user_message: userMessage, assistant_message: assistantMessage }),
      });
    } catch (e) { console.error('[THREAD] Failed to persist message:', e); }
  }, [apiBaseUrl]);

  const loadThreadMessages = useCallback(async (tid: string): Promise<{ messages: Array<{ role: string; content: string }>; title?: string }> => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${apiBaseUrl}/api/v1/threads/${tid}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        const messages = (data.messages || [])
          .filter((m: Record<string, unknown>) => {
            const role = m.role as string | undefined;
            return role === 'user' || role === 'assistant' || role === 'system';
          })
          .map((m: Record<string, unknown>) => ({ role: m.role as string, content: m.content as string }));
        return { messages, title: data.title as string | undefined };
      }
    } catch (e) { console.error('[THREAD] Failed to load:', e); }
    return { messages: [] };
  }, [apiBaseUrl]);

  const runCompact = useCallback(async (sessionId: string, tid: string): Promise<boolean> => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${apiBaseUrl}/api/v1/agentic/compact`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ session_id: sessionId, thread_id: tid }),
      });
      return res.ok;
    } catch (e) {
      console.error('[COMPACT] Failed:', e);
      return false;
    }
  }, [apiBaseUrl]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadTitle, setThreadTitle] = useState<string | null>(null);
  const nextIdRef = useRef(1);
  const genId = () => `msg-${nextIdRef.current++}`;

  const [streamingText, setStreamingText] = useState('');
  const [streamingToolCalls, setStreamingToolCalls] = useState<ToolCallWithUid[]>([]);
  const [thinkingText, setThinkingText] = useState('');
  const streamingIdRef = useRef<string | null>(null);
  const toolCallUidRef = useRef(0);

  const streamingTextRef = useRef('');
  const streamingToolCallsRef = useRef<ToolCallWithUid[]>([]);
  const thinkingForMessageRef = useRef('');

  const pendingPlanRef = useRef<Record<string, unknown> | null>(null);
  const pendingEnterPlanRef = useRef<{
    reason: string;
    toolCallId: string;
  } | null>(null);
  const pendingExitPlanRef = useRef<{
    planText: string;
    toolCallId: string;
  } | null>(null);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [pendingEnterPlan, setPendingEnterPlan] = useState<{ reason: string } | null>(null);
  const [pendingExitPlan, setPendingExitPlan] = useState<{ planText: string } | null>(null);

  const approvalHandlersRef = useRef<{
    approveEnter?: () => Promise<void>;
    rejectEnter?: () => Promise<void>;
    approveExit?: () => Promise<void>;
    rejectExit?: () => void;
  }>({});

  const loadedThreadRef = useRef<string | null>(null);
  useEffect(() => {
    if (!initialThreadId || initialThreadId === loadedThreadRef.current) return;
    loadedThreadRef.current = initialThreadId;
    const tid = initialThreadId;

    setStreamingText('');
    setStreamingToolCalls([]);
    setThinkingText('');
    streamingTextRef.current = '';
    streamingToolCallsRef.current = [];
    streamingIdRef.current = null;

    threadIdRef.current = tid;
    setThreadId(tid);

    loadThreadMessages(tid).then((result) => {
      if (result.title) setThreadTitle(result.title);
      if (result.messages.length === 0) {
        setMessages([]);
        return;
      }
      const restored: ChatMessage[] = result.messages.map((m, i) => ({
        id: `restored-${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));
      setMessages(restored);
      nextIdRef.current = restored.length + 1;
    });
  }, [initialThreadId, loadThreadMessages]);

  const agenticChat = useAgenticChat({
    onThinking: (content) => {
      const text = content || 'Reasoning...';
      thinkingForMessageRef.current = text;
      setThinkingText(text);
    },
    onTextChunk: (content) => {
      setStreamingText((prev) => prev + content);
      streamingTextRef.current += content;
    },
    onToolCall: (toolCall) => {
      if (toolCall.tool_name === 'update_plan' && toolCall.arguments && typeof toolCall.arguments === 'object') {
        pendingPlanRef.current = toolCall.arguments as Record<string, unknown>;
      }

      if (toolCall.tool_name === 'enter_plan_mode' && toolCall.arguments) {
        const args = toolCall.arguments as Record<string, unknown>;
        pendingEnterPlanRef.current = {
          reason: typeof args.reason === 'string' ? args.reason : '',
          toolCallId: toolCall.id,
        };
      }
      if (toolCall.tool_name === 'exit_plan_mode' && toolCall.arguments) {
        const args = toolCall.arguments as Record<string, unknown>;
        pendingExitPlanRef.current = {
          planText: typeof args.plan === 'string' ? args.plan : '',
          toolCallId: toolCall.id,
        };
      }

      if (streamingTextRef.current) {
        const narration = streamingTextRef.current;
        const prior = thinkingForMessageRef.current;
        const merged = prior ? `${prior}\n\n${narration}` : narration;
        thinkingForMessageRef.current = merged;
        setThinkingText(merged);
        setStreamingText('');
        streamingTextRef.current = '';
      }

      const prev = streamingToolCallsRef.current;
      let nextToolCalls: ToolCallWithUid[];

      const existingIdx = prev.findIndex((tc) => tc.id === toolCall.id);
      if (existingIdx !== -1) {
        nextToolCalls = [...prev];
        nextToolCalls[existingIdx] = {...nextToolCalls[existingIdx],...toolCall };
      } else if (toolCall.tool_name === 'todo_write') {
        const existingTodoIdx = [...prev].reverse().findIndex(
          (tc) => tc.tool_name === 'todo_write'
        );
        if (existingTodoIdx !== -1) {
          const idx = prev.length - 1 - existingTodoIdx;
          nextToolCalls = [...prev];
          const existing = nextToolCalls[idx];
          nextToolCalls[idx] = {...existing,...toolCall,
            __uid: existing.__uid,  // keep the stable React key
          } as ToolCallWithUid;
        } else {
          const uid = `tc-${toolCallUidRef.current++}`;
          nextToolCalls = [...prev, {...toolCall, __uid: uid } as ToolCallWithUid];
        }
      } else {
        const uid = `tc-${toolCallUidRef.current++}`;
        nextToolCalls = [...prev, {...toolCall, __uid: uid } as ToolCallWithUid];
      }

      streamingToolCallsRef.current = nextToolCalls;
      setStreamingToolCalls(nextToolCalls);
    },
    onToolResult: (toolCall, result) => {
      if (
        toolCall.tool_name === 'update_plan'
        && result?.result
        && typeof result.result === 'object'
      ) {
        pendingPlanRef.current = result.result as Record<string, unknown>;
      }

      const applyResult = (list: ToolCallWithUid[]) => {
        const direct = list.findIndex((tc) => tc.id === toolCall.id);
        if (direct !== -1) {
          const next = [...list];
          next[direct] = {...next[direct], result };
          return next;
        }
        if (toolCall.tool_name === 'todo_write') {
          const lastTodoIdx = [...list].reverse().findIndex(
            (tc) => tc.tool_name === 'todo_write'
          );
          if (lastTodoIdx !== -1) {
            const idx = list.length - 1 - lastTodoIdx;
            const next = [...list];
            next[idx] = {...next[idx], result };
            return next;
          }
        }
        return list;
      };

      setStreamingToolCalls((prev) => applyResult(prev));
      streamingToolCallsRef.current = applyResult(streamingToolCallsRef.current);
    },
    onDocumentUpdate: onDocumentUpdate,
    onDocumentDeleted: onDocumentDeleted,
    onDocumentCreated: onDocumentCreated,
    onSystemMessage: (content) => {
      const id = `system-${nextIdRef.current++}`;
      setMessages((prev) => [...prev, { id, role: 'system', content }]);
    },
    onComplete: (session) => {
      const finalText = streamingTextRef.current;
      const finalToolCalls = streamingToolCallsRef.current.map(tc => {
        if (tc.result) return tc;
        if (tc.tool_name === 'enter_plan_mode' || tc.tool_name === 'exit_plan_mode') return tc;
        return {...tc, result: { success: true, result: { skipped: true }, execution_time_ms: 0 } };
      });
      const id = streamingIdRef.current || genId();
      const finalThinking = thinkingForMessageRef.current || undefined;

      if (pendingEnterPlanRef.current) {
        setPendingEnterPlan({ reason: pendingEnterPlanRef.current.reason });
      } else if (pendingExitPlanRef.current) {
        setPendingExitPlan({ planText: pendingExitPlanRef.current.planText });
      } else {
        const pendingPlan = pendingPlanRef.current;
        const stepsArr = Array.isArray((pendingPlan as { steps?: unknown })?.steps)
          ? (pendingPlan as { steps: Array<{ status?: string }> }).steps
          : null;
        const planIsAwaiting = Boolean(
          pendingPlan
          && stepsArr
          && stepsArr.length > 0
          && stepsArr.every((s) => (s?.status || 'pending') === 'pending')
        );
        setAwaitingApproval(planIsAwaiting);
      }

      setMessages((prev) => [...prev,
        {
          id,
          role: 'assistant',
          content: finalText,
          toolCalls: finalToolCalls.length > 0 ? finalToolCalls : undefined,
          thinking: finalThinking,
        },
      ]);

      setStreamingText('');
      setStreamingToolCalls([]);
      setThinkingText('');
      streamingTextRef.current = '';
      streamingToolCallsRef.current = [];
      streamingIdRef.current = null;
      thinkingForMessageRef.current = '';

      // but we keep this as a safety net for cases where thread_id wasn't sent
      const pending = pendingPersistRef.current;
      if (pending && finalText) {
        if (!pending.backendPersisted) {
          persistMessage(pending.threadId, pending.userMsg, finalText);
        }
        pendingPersistRef.current = null;
      }

      // Notify parent of session — triggers sidebar refresh as a safety net
      if (session?.sessionId && onAgenticSessionCreated) {
        onAgenticSessionCreated(session.sessionId);
      }
    },
    onError: (error) => {
      const id = streamingIdRef.current || genId();
      setMessages((prev) => [...prev,
        { id, role: 'assistant', content: `Error: ${error}` },
      ]);
      setStreamingText('');
      setStreamingToolCalls([]);
      setThinkingText('');
      streamingTextRef.current = '';
      streamingToolCallsRef.current = [];
      streamingIdRef.current = null;
      thinkingForMessageRef.current = '';

    },
    onCreditsExhausted,
  });

  const threadMessages = useMemo((): ThreadMessageLike[] => {
    const converted: ThreadMessageLike[] = messages.map((msg) => {
      if (msg.role === 'system') {
        return {
          id: msg.id,
          role: 'assistant' as const,
          content: [{ type: 'text' as const, text: `> ℹ️ ${msg.content}` }],
          status: { type: 'complete' as const, reason: 'stop' as const },
        };
      }
      if (msg.role === 'user') {
        return {
          id: msg.id,
          role: 'user' as const,
          content: [{ type: 'text' as const, text: msg.content }],
        };
      }
      const toolParts = (msg.toolCalls || []).map(makeToolCallPart);
      const textParts = msg.content
        ? [{ type: 'text' as const, text: msg.content }]
        : [];
      const content = [...toolParts,...textParts];

      return {
        id: msg.id,
        role: 'assistant' as const,
        content: content.length > 0 ? content : [{ type: 'text' as const, text: '' }],
        status: { type: 'complete' as const, reason: 'stop' as const },
      };
    });

    if (agenticChat.isRunning) {
      const toolParts = streamingToolCalls.map(makeToolCallPart);

      const textParts = streamingText
        ? [{ type: 'text' as const, text: streamingText }]
        : [];

      const content = [...toolParts,...textParts];

      converted.push({
        id: streamingIdRef.current || 'streaming',
        role: 'assistant' as const,
        content: content.length > 0 ? content : [{ type: 'text' as const, text: '' }],
        status: { type: 'running' as const },
      });
    }

    return converted;
  }, [messages, agenticChat.isRunning, streamingText, streamingToolCalls]);

  const handleNew = useCallback(
    async (appendMessage: { content: Array<{ type: string; text?: string }> }) => {
      const textPart = appendMessage.content?.find(
        (p) => p.type === 'text',
      );
      const userText = textPart?.text || '';
      if (!userText.trim()) return;

      const trimmed = userText.trim();
      const affirmative = /^(yes|y|ok|okay|sure|go|approve|approved|proceed|do it)\b[\s.!]*$/i.test(trimmed);
      const negative = /^(no|n|nope|cancel|skip|stop|reject|decline|stay reactive|abort)\b[\s.!]*$/i.test(trimmed);
      if (pendingEnterPlanRef.current) {
        if (affirmative) { await approvalHandlersRef.current.approveEnter?.(); return; }
        if (negative) { await approvalHandlersRef.current.rejectEnter?.(); return; }
      } else if (pendingExitPlanRef.current) {
        if (affirmative) { await approvalHandlersRef.current.approveExit?.(); return; }
        if (negative) { approvalHandlersRef.current.rejectExit?.(); return; }
        approvalHandlersRef.current.rejectExit?.();
      }

      if (trimmed === '/compact') {
        const tid = threadIdRef.current && threadIdRef.current !== 'creating'
          ? threadIdRef.current
          : null;
        if (!tid || !workspaceSessionId) {
          const sysId = `system-${nextIdRef.current++}`;
          setMessages((prev) => [...prev, { id: sysId, role: 'system', content: 'Nothing to compact yet — start a conversation first.' }]);
          return;
        }
        const userMsgId = `user-${nextIdRef.current++}`;
        setMessages((prev) => [...prev, { id: userMsgId, role: 'user', content: userText }]);
        const ok = await runCompact(workspaceSessionId, tid);
        if (!ok) {
          const errId = `system-${nextIdRef.current++}`;
          setMessages((prev) => [...prev, { id: errId, role: 'system', content: 'Compaction failed. Please try again.' }]);
        }
        return;
      }

      lastUserMessageRef.current = userText;

      if (!threadIdRef.current) {
        if (parentThreadIdRef.current) {
          console.log('[THREAD] Recovered thread from parent:', parentThreadIdRef.current);
          threadIdRef.current = parentThreadIdRef.current;
          setThreadId(parentThreadIdRef.current);
        } else if (loadedThreadRef.current) {
          console.log('[THREAD] Recovered thread from loadedThreadRef:', loadedThreadRef.current);
          threadIdRef.current = loadedThreadRef.current;
          setThreadId(loadedThreadRef.current);
        } else if (messages.length > 0) {
          console.warn('[THREAD] Lost thread ID mid-conversation, skipping thread creation');
        } else {
          threadIdRef.current = 'creating'; // Block concurrent calls
          const title = userText.length > 50 ? userText.substring(0, 50).trim() + '...' : userText;
          console.log('[THREAD] Creating new thread:', title);
          setThreadTitle(title);
          const newThreadId = await createThread(title);
          if (newThreadId) {
            console.log('[THREAD] Created:', newThreadId);
            threadIdRef.current = newThreadId;
            loadedThreadRef.current = newThreadId;
            setThreadId(newThreadId);
            onThreadIdChanged?.(newThreadId);
          } else {
            console.warn('[THREAD] Creation failed, resetting ref');
            threadIdRef.current = null; // Reset on failure
          }
        }
      }

      const tid = threadIdRef.current;
      if (tid && tid !== 'creating') {
        pendingPersistRef.current = { threadId: tid, userMsg: userText, backendPersisted: false };
      }

      const userId = genId();
      setMessages((prev) => [...prev, { id: userId, role: 'user', content: userText }]);

      const assistantId = genId();
      streamingIdRef.current = assistantId;
      setStreamingText('');
      setStreamingToolCalls([]);
      streamingTextRef.current = '';
      streamingToolCallsRef.current = [];

      const documents: Record<string, { content: string; description?: string }> = {};
      if (documentId && documentText) {
        documents[documentId] = {
          content: documentText,
          description: documentName || 'Current document',
        };
      }

      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const attachedFilePaths: string[] = [];
      const pendingFiles = attachedFilesRef?.current || [];
      if (pendingFiles.length > 0) {
        const token = localStorage.getItem('auth_token');
        if (token) {
          for (const af of pendingFiles) {
            try {
              const formData = new FormData();
              formData.append('file', af.file);
              if (workspaceSessionId) {
                formData.append('session_id', workspaceSessionId);
              }
              const uploadRes = await fetch(`${apiBaseUrl}/api/v1/editor/chat/agentic/workspace/upload`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
                body: formData,
              });
              if (uploadRes.ok) {
                const uploadData = await uploadRes.json();
                const docPath = uploadData.path || uploadData.document_path || af.file.name;
                attachedFilePaths.push(docPath);
              } else {
                console.error('[ATTACH] Upload failed for', af.file.name, uploadRes.status);
              }
            } catch (e) {
              console.error('[ATTACH] Upload error for', af.file.name, e);
            }
          }
        }
        clearAttachments?.();
      }

      const currentThreadId = threadIdRef.current;

      const isPureSlashCommand = /^\s*\/[a-z][\w-]*\s*$/i.test(userText);
      const detected: AgenticMode | null = isPureSlashCommand
        ? null
        : detectModeFromText(userText);

      if (detected && detected !== modeRef.current) {
        setMode(detected);
      }

      const effectiveMode: AgenticMode = isPureSlashCommand
        ? modeRef.current
        : (detected || modeRef.current);
      const flags = flagsForMode(effectiveMode);

      if (awaitingApproval) {
        pendingPlanRef.current = null;
        setAwaitingApproval(false);
      }

      await agenticChat.sendMessage({
        message: userText,
        documents,
        active_document: documentId || documentName,
        session_id: workspaceSessionId,
        thread_id: currentThreadId && currentThreadId !== 'creating' ? currentThreadId : undefined,
        context: {...(selectedText ? { selectedText } : {}),...(sessionContext ? { sessionContext } : {}),
        },
        history,...(attachedFilePaths.length > 0 ? { attached_files: attachedFilePaths } : {}),...(flags.planner_mode ? { planner_mode: true } : {}),...(flags.coordinator_mode ? { coordinator_mode: true } : {}),
      });
    },
    [messages, documentText, documentId, documentName, selectedText, sessionContext, workspaceSessionId, agenticChat, createThread, onThreadIdChanged, apiBaseUrl, attachedFilesRef, clearAttachments, runCompact],
  );

  const handleCancel = useCallback(async () => {
    agenticChat.cancel();
  }, [agenticChat]);

  const approvePlan = useCallback(async () => {
    const plan = pendingPlanRef.current;
    if (!plan) return;
    setAwaitingApproval(false);

    const currentThreadId = threadIdRef.current;
    const history = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    const documents: Record<string, { content: string; description?: string }> = {};
    if (documentId && documentText) {
      documents[documentId] = {
        content: documentText,
        description: documentName || 'Current document',
      };
    }

    const approvalText = '(Execute the plan above.)';
    const userId = genId();
    setMessages((prev) => [...prev, { id: userId, role: 'user', content: approvalText }]);

    const assistantId = genId();
    streamingIdRef.current = assistantId;
    setStreamingText('');
    setStreamingToolCalls([]);
    streamingTextRef.current = '';
    streamingToolCallsRef.current = [];

    await agenticChat.sendMessage({
      message: approvalText,
      documents,
      active_document: documentId || documentName,
      session_id: workspaceSessionId,
      thread_id: currentThreadId && currentThreadId !== 'creating' ? currentThreadId : undefined,
      context: {...(selectedText ? { selectedText } : {}),...(sessionContext ? { sessionContext } : {}),
      },
      history,
      planner_mode: true,
      approved_plan: plan,
    });
  }, [messages, documentText, documentId, documentName, selectedText, sessionContext, workspaceSessionId, agenticChat]);

  const cancelPlan = useCallback(() => {
    pendingPlanRef.current = null;
    setAwaitingApproval(false);
    setMode('default');
  }, []);

  const markApprovalToolResolved = useCallback((toolCallId: string, approved: boolean) => {
    setMessages((prev) => prev.map((msg) => {
      if (!msg.toolCalls) return msg;
      const idx = msg.toolCalls.findIndex((tc) => tc.id === toolCallId);
      if (idx === -1) return msg;
      const updated = [...msg.toolCalls];
      updated[idx] = {...updated[idx],
        result: { success: true, result: { approved }, execution_time_ms: 0 },
      };
      return {...msg, toolCalls: updated };
    }));
  }, []);

  const approveEnterPlan = useCallback(async () => {
    const pending = pendingEnterPlanRef.current;
    if (!pending) return;
    pendingEnterPlanRef.current = null;
    setPendingEnterPlan(null);
    markApprovalToolResolved(pending.toolCallId, true);
    setMode('plan');

    const currentThreadId = threadIdRef.current;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const documents: Record<string, { content: string; description?: string }> = {};
    if (documentId && documentText) {
      documents[documentId] = { content: documentText, description: documentName || 'Current document' };
    }
    const approvalText = '(Entering plan mode — explore and plan.)';
    const userId = genId();
    setMessages((prev) => [...prev, { id: userId, role: 'user', content: approvalText }]);
    const assistantId = genId();
    streamingIdRef.current = assistantId;

    await agenticChat.sendMessage({
      message: approvalText,
      documents,
      active_document: documentId || documentName,
      session_id: workspaceSessionId,
      thread_id: currentThreadId && currentThreadId !== 'creating' ? currentThreadId : undefined,
      context: {...(selectedText ? { selectedText } : {}),...(sessionContext ? { sessionContext } : {}),
      },
      history,
      approved_mode_change: {
        mode: 'plan',
        approved: true,
        tool_call_id: pending.toolCallId,
      },
    });
  }, [messages, documentText, documentId, documentName, selectedText, sessionContext, workspaceSessionId, agenticChat, markApprovalToolResolved]);

  const rejectEnterPlan = useCallback(async () => {
    const pending = pendingEnterPlanRef.current;
    if (!pending) return;
    pendingEnterPlanRef.current = null;
    setPendingEnterPlan(null);
    markApprovalToolResolved(pending.toolCallId, false);

    const currentThreadId = threadIdRef.current;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const documents: Record<string, { content: string; description?: string }> = {};
    if (documentId && documentText) {
      documents[documentId] = { content: documentText, description: documentName || 'Current document' };
    }
    const rejectionText = '(Stay in reactive mode — answer directly.)';
    const userId = genId();
    setMessages((prev) => [...prev, { id: userId, role: 'user', content: rejectionText }]);
    const assistantId = genId();
    streamingIdRef.current = assistantId;

    await agenticChat.sendMessage({
      message: rejectionText,
      documents,
      active_document: documentId || documentName,
      session_id: workspaceSessionId,
      thread_id: currentThreadId && currentThreadId !== 'creating' ? currentThreadId : undefined,
      context: {...(selectedText ? { selectedText } : {}),...(sessionContext ? { sessionContext } : {}),
      },
      history,
      approved_mode_change: {
        mode: 'plan',
        approved: false,
        tool_call_id: pending.toolCallId,
      },
    });
  }, [messages, documentText, documentId, documentName, selectedText, sessionContext, workspaceSessionId, agenticChat, markApprovalToolResolved]);

  const approveExitPlan = useCallback(async () => {
    const pending = pendingExitPlanRef.current;
    if (!pending) return;
    pendingExitPlanRef.current = null;
    setPendingExitPlan(null);
    markApprovalToolResolved(pending.toolCallId, true);
    setMode('default');

    const currentThreadId = threadIdRef.current;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const documents: Record<string, { content: string; description?: string }> = {};
    if (documentId && documentText) {
      documents[documentId] = { content: documentText, description: documentName || 'Current document' };
    }
    const approvalText = '(Plan approved — execute.)';
    const userId = genId();
    setMessages((prev) => [...prev, { id: userId, role: 'user', content: approvalText }]);
    const assistantId = genId();
    streamingIdRef.current = assistantId;

    await agenticChat.sendMessage({
      message: approvalText,
      documents,
      active_document: documentId || documentName,
      session_id: workspaceSessionId,
      thread_id: currentThreadId && currentThreadId !== 'creating' ? currentThreadId : undefined,
      context: {...(selectedText ? { selectedText } : {}),...(sessionContext ? { sessionContext } : {}),
      },
      history,
      approved_plan: {
        plan_text: pending.planText,
        tool_call_id: pending.toolCallId,
      },
    });
  }, [messages, documentText, documentId, documentName, selectedText, sessionContext, workspaceSessionId, agenticChat, markApprovalToolResolved]);

  const rejectExitPlan = useCallback(() => {
    const pending = pendingExitPlanRef.current;
    pendingExitPlanRef.current = null;
    setPendingExitPlan(null);
    if (pending) markApprovalToolResolved(pending.toolCallId, false);
  }, [markApprovalToolResolved]);

  useEffect(() => {
    approvalHandlersRef.current = {
      approveEnter: approveEnterPlan,
      rejectEnter: rejectEnterPlan,
      approveExit: approveExitPlan,
      rejectExit: rejectExitPlan,
    };
  }, [approveEnterPlan, rejectEnterPlan, approveExitPlan, rejectExitPlan]);

  const resetChat = useCallback(() => {
    console.log('[THREAD] resetChat called, clearing thread:', threadIdRef.current);
    setMessages([]);
    setThreadTitle(null);
    setStreamingText('');
    setStreamingToolCalls([]);
    setThinkingText('');
    streamingTextRef.current = '';
    streamingToolCallsRef.current = [];
    streamingIdRef.current = null;
    threadIdRef.current = null;
    loadedThreadRef.current = null;
    setMode(initialModeFromUrl());
    setThreadId(null);
    onThreadIdChanged?.(null);
    agenticChat.reset();
  }, [agenticChat, onThreadIdChanged]);

  const runtime = useExternalStoreRuntime({
    messages: threadMessages,
    convertMessage: (msg) => msg,
    isRunning: agenticChat.isRunning,
    onNew: handleNew as any, // AppendMessage type is complex; runtime validates at call time
    onCancel: handleCancel,
    suggestions: suggestions?.map((text) => ({
      prompt: text,
    })),
  });

  const thinkingMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of messages) {
      if (m.role === 'assistant' && m.thinking) {
        map.set(m.id, m.thinking);
      }
    }
    return map;
  }, [messages]);

  return {
    runtime,
    messages,
    threadTitle,
    resetChat,
    session: agenticChat.session,
    isRunning: agenticChat.isRunning,
    toolCalls: streamingToolCalls,
    thinkingText,
    thinkingMap,
    threadId,
    mode,
    setMode,
    awaitingApproval,
    approvePlan,
    cancelPlan,
    pendingEnterPlan,
    pendingExitPlan,
    approveEnterPlan,
    rejectEnterPlan,
    approveExitPlan,
    rejectExitPlan,
  };
}
