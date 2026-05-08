'use client';

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ActionBarPrimitive,
  useMessage,
  useComposerRuntime,
  useComposer,
} from '@assistant-ui/react';
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import type { DocumentCreatedEvent } from '@/app/workspace/hooks/useAgenticChat';
import { useAgenticRuntime, type AttachedFile } from './useAgenticRuntime';
import SlashCommandMenu, { useSlashCommands, type SlashCommand } from '@/app/workspace/components/SlashCommandMenu';
import ThreadSelectorDropdown from './ThreadSelectorDropdown';
import WorkspaceInfoModal from './WorkspaceInfoModal';
import styles from './workspace-chat.module.css';

const ThinkingContext = React.createContext<Map<string, string>>(new Map());

interface ChatActionsContextType {
  onOpenDocument?: (sessionId: string, documentPath: string) => void;
  onDownloadDocument?: (sessionId: string, documentPath: string) => void;
  sessionId?: string;
  awaitingApproval?: boolean;
  approvePlan?: () => void;
  cancelPlan?: () => void;
  pendingEnterPlan?: { reason: string } | null;
  pendingExitPlan?: { planText: string } | null;
  approveEnterPlan?: () => void;
  rejectEnterPlan?: () => void;
  approveExitPlan?: () => void;
  rejectExitPlan?: () => void;
}
const ChatActionsContext = createContext<ChatActionsContextType>({});

const TOOL_ICONS: Record<string, string> = {
  list_documents: '📄',
  read_document: '📖',
  create_document: '✍️',
  write_document: '✍️',
  edit_document: '✏️',
  web_search: '🔍',
  web_fetch: '🌐',
  compare: '⚖️',
  accept_all_changes: '✅',
  reject_all_changes: '↩️',
  accept_changes: '✅',
  reject_changes: '↩️',
  add_comment: '💬',
  get_revision_stats: '📊',
  export_docx: '📤',
  delete_document: '🗑️',
  clone_document: '📋',
  revert_edit: '↩️',
  instantiate_template: '📑',
  produce_redline: '📝',
};

function getToolLabel(name: string | undefined | null): string {
  if (!name) return 'Tool';
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const DOC_CREATION_TOOLS = new Set([
  'write_document',
  'create_document',
  'clone_document',
  'instantiate_template',
  'produce_redline',
]);

// ── Todo / plan checklist ──
interface PlanStepPayload {
  id?: string;
  step_number?: number;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  result?: string | null;
  error?: string | null;
}
interface PlanPayload {
  plan_id?: string;
  goal?: string;
  status?: 'pending' | 'in_progress' | 'completed' | 'failed';
  current_step?: number;
  steps: PlanStepPayload[];
  reasoning?: string | null;
}

interface TodoWriteItem {
  content: string;
  active_form?: string;
  status: 'pending' | 'in_progress' | 'completed';
}

function todoWritePayloadToPlan(payload: unknown): PlanPayload | null {
  if (!payload || typeof payload !== 'object') return null;
  const obj = payload as Record<string, unknown>;
  const todos = Array.isArray(obj.todos) ? (obj.todos as TodoWriteItem[]) : null;
  if (!todos) return null;
  return {
    steps: todos.map((t, i) => ({
      id: `todo-${i}`,
      step_number: i + 1,
      description: t.active_form && t.status === 'in_progress' ? t.active_form : t.content,
      status: t.status,
    })),
  };
}

function PlanChecklist({
  plan,
  kind = 'plan',
  awaitingApproval = false,
  onApprove,
  onCancel,
}: {
  plan: PlanPayload;
  kind?: 'plan' | 'todos';
  awaitingApproval?: boolean;
  onApprove?: () => void;
  onCancel?: () => void;
}) {
  const steps = plan.steps || [];
  const doneCount = steps.filter(s => s.status === 'completed').length;
  const failCount = steps.filter(s => s.status === 'failed').length;
  const totalCount = steps.length;
  const headerLabel = kind === 'todos' ? 'Progress' : 'Plan';

  return (
    <div
      style={{
        margin: '8px 0',
        padding: '10px 12px',
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, fontWeight: 500 }}>
        <span>📋</span>
        <span>{headerLabel}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#64748b', fontVariantNumeric: 'tabular-nums' }}>
          {doneCount}/{totalCount}{failCount > 0 ? ` · ${failCount} failed` : ''}
        </span>
      </div>
      {plan.reasoning && (
        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8, fontStyle: 'italic' }}>
          {plan.reasoning}
        </div>
      )}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {steps.map((step, i) => {
          const key = step.id || `step-${step.step_number ?? i}`;
          const icon =
            step.status === 'completed' ? '✓' :
            step.status === 'failed' ? '✗' :
            step.status === 'in_progress' ? '◐' : '☐';
          const color =
            step.status === 'completed' ? '#16a34a' :
            step.status === 'failed' ? '#dc2626' :
            step.status === 'in_progress' ? '#2563eb' : '#94a3b8';
          const hasDetail = Boolean(step.result || step.error);
          const summary = (
            <>
              <span
                style={{
                  color,
                  fontWeight: 600,
                  minWidth: 16,
                  textAlign: 'center',
                  lineHeight: '20px',
                  display: 'inline-block',
                }}
              >
                {icon}
              </span>
              <span
                style={{
                  marginLeft: 8,
                  color: step.status === 'failed' ? '#94a3b8' : '#1e293b',
                  textDecoration: step.status === 'failed' ? 'line-through' : 'none',
                }}
              >
                {step.description}
              </span>
            </>
          );
          return (
            <li key={key} style={{ padding: '3px 0' }}>
              {hasDetail ? (
                <details>
                  <summary style={{ cursor: 'pointer', listStyle: 'revert' }}>
                    {summary}
                  </summary>
                  <div
                    style={{
                      marginTop: 6,
                      marginLeft: 24,
                      padding: '6px 10px',
                      background: '#ffffff',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 12,
                      color: '#334155',
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.55,
                    }}
                  >
                    {step.result && <div>{step.result}</div>}
                    {step.error && (
                      <div style={{ color: '#dc2626', marginTop: step.result ? 6 : 0 }}>
                        {step.error}
                      </div>
                    )}
                  </div>
                </details>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-start' }}>{summary}</div>
              )}
            </li>
          );
        })}
      </ul>
      {awaitingApproval && (
        <div
          style={{
            marginTop: 10,
            paddingTop: 8,
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            onClick={onApprove}
            style={{
              padding: '4px 12px',
              fontSize: 12,
              fontWeight: 500,
              color: '#fff',
              background: '#2563eb',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Approve &amp; Execute
          </button>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '4px 10px',
              fontSize: 12,
              color: '#475569',
              background: 'transparent',
              border: '1px solid #cbd5e1',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            Or send a message to refine the plan.
          </span>
        </div>
      )}
    </div>
  );
}

function EnterPlanModeInlineCard({ reason, resolved }: { reason: string; resolved: boolean }) {
  const { pendingEnterPlan, approveEnterPlan, rejectEnterPlan } = useContext(ChatActionsContext);
  const awaiting = !resolved && Boolean(pendingEnterPlan);
  return (
    <div
      style={{
        margin: '6px 0',
        padding: '10px 14px',
        background: awaiting ? '#eff6ff' : '#f8fafc',
        border: `1px solid ${awaiting ? '#bfdbfe' : '#e2e8f0'}`,
        borderRadius: 10,
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: reason ? 6 : 0, fontWeight: 500, color: '#1e40af' }}>
        <span>📋</span>
        <span>Enter plan mode?</span>
      </div>
      {reason && (
        <div style={{ fontSize: 13, color: '#334155', marginBottom: awaiting ? 10 : 0 }}>
          {reason}
        </div>
      )}
      {awaiting ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={approveEnterPlan}
            style={{ padding: '4px 12px', fontSize: 12, fontWeight: 500, color: '#fff', background: '#2563eb', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Enter plan mode
          </button>
          <button
            type="button"
            onClick={rejectEnterPlan}
            style={{ padding: '4px 10px', fontSize: 12, color: '#475569', background: 'transparent', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer' }}
          >
            Stay reactive
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
          {resolved ? 'Resolved.' : ''}
        </div>
      )}
    </div>
  );
}

function ExitPlanModeInlineCard({ planText, resolved }: { planText: string; resolved: boolean }) {
  const { pendingExitPlan, approveExitPlan, rejectExitPlan } = useContext(ChatActionsContext);
  const awaiting = !resolved && Boolean(pendingExitPlan);
  return (
    <div
      style={{
        margin: '6px 0',
        padding: '10px 14px',
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, fontWeight: 500, color: '#1e293b' }}>
        <span>📋</span>
        <span>Review plan</span>
      </div>
      <div
        style={{
          maxHeight: 320,
          overflowY: 'auto',
          padding: '8px 10px',
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 6,
          fontSize: 12,
          color: '#334155',
          whiteSpace: 'pre-wrap',
          lineHeight: 1.55,
          marginBottom: awaiting ? 10 : 0,
        }}
      >
        {planText || '(no plan text provided)'}
      </div>
      {awaiting && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            type="button"
            onClick={approveExitPlan}
            style={{ padding: '4px 12px', fontSize: 12, fontWeight: 500, color: '#fff', background: '#2563eb', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Approve &amp; Execute
          </button>
          <button
            type="button"
            onClick={rejectExitPlan}
            style={{ padding: '4px 10px', fontSize: 12, color: '#475569', background: 'transparent', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer' }}
          >
            Reject
          </button>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            Or send a message to refine the plan.
          </span>
        </div>
      )}
    </div>
  );
}

type SuggestInstructionResult = {
  ok?: boolean;
  proposed_text?: string;
  target_path?: string;
  rationale?: string;
};

function SuggestInstructionCard({ result }: { result: SuggestInstructionResult }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'dismissed' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const proposed = (result?.proposed_text || '').trim();
  const target = result?.target_path || 'anylegal.md';
  const rationale = result?.rationale || '';

  const handleAdd = useCallback(async () => {
    if (state === 'saving' || state === 'saved') return;
    setState('saving');
    setError(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:8000';
      const token = typeof window !== 'undefined'
        ? window.localStorage.getItem('auth_token')
        : null;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const getRes = await fetch(
        `${baseUrl}/api/v1/editor/chat/agentic/workspace/file?path=${encodeURIComponent(target)}`,
        { headers },
      );
      let existing = '';
      if (getRes.ok) {
        const body = await getRes.json();
        existing = (body?.content as string) || '';
      }
      const merged = existing.trim()
        ? `${existing.trimEnd()}\n\n${proposed}\n`
        : `${proposed}\n`;

      const putRes = await fetch(
        `${baseUrl}/api/v1/editor/chat/agentic/workspace/file`,
        {
          method: 'PUT',
          headers,
          body: JSON.stringify({ path: target, content: merged }),
        },
      );
      if (!putRes.ok) {
        const errBody = await putRes.json().catch(() => ({}));
        throw new Error(errBody.error || `HTTP ${putRes.status}`);
      }
      setState('saved');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
      setState('error');
    }
  }, [state, proposed, target]);

  const handleDismiss = useCallback(() => setState('dismissed'), []);

  if (!proposed) return null;

  return (
    <div className={styles.suggestInstructionCard}>
      <div className={styles.suggestInstructionHeader}>
        <span className={styles.suggestInstructionIcon}>📝</span>
        <span className={styles.suggestInstructionLabel}>Suggested instruction</span>
        <span className={styles.suggestInstructionTarget}>→ {target}</span>
      </div>
      {rationale ? (
        <p className={styles.suggestInstructionRationale}>{rationale}</p>
      ) : null}
      <blockquote className={styles.suggestInstructionText}>{proposed}</blockquote>
      {state === 'saved' ? (
        <p className={styles.suggestInstructionStatus}>
          ✓ Added to {target}
        </p>
      ) : state === 'dismissed' ? (
        <p className={styles.suggestInstructionStatus}>Dismissed</p>
      ) : state === 'error' ? (
        <p className={styles.suggestInstructionError}>{error || 'Failed to save'}</p>
      ) : (
        <div className={styles.suggestInstructionActions}>
          <button
            type="button"
            className={styles.suggestInstructionPrimary}
            onClick={handleAdd}
            disabled={state === 'saving'}
          >
            {state === 'saving' ? 'Saving…' : 'Add to instructions'}
          </button>
          <button
            type="button"
            className={styles.suggestInstructionSecondary}
            onClick={handleDismiss}
            disabled={state === 'saving'}
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

function PlanChecklistWithApproval({ plan }: { plan: PlanPayload }) {
  const { awaitingApproval, approvePlan, cancelPlan } = useContext(ChatActionsContext);
  const allPending = (plan.steps || []).length > 0
    && (plan.steps || []).every(s => (s.status || 'pending') === 'pending');
  const showButtons = Boolean(awaitingApproval && allPending);
  return (
    <PlanChecklist
      plan={plan}
      awaitingApproval={showButtons}
      onApprove={showButtons ? approvePlan : undefined}
      onCancel={showButtons ? cancelPlan : undefined}
    />
  );
}

function ToolCallFallback({ toolName, args, result, isError }: {
  toolName: string;
  args: Record<string, unknown>;
  result?: unknown;
  isError?: boolean;
}) {
  if (toolName === 'update_plan') {
    const payload = (result as PlanPayload | undefined) || (args as unknown as PlanPayload);
    if (payload && Array.isArray(payload.steps)) {
      return <PlanChecklistWithApproval plan={payload} />;
    }
  }

  if (toolName === 'todo_write') {
    const normalized = todoWritePayloadToPlan(result) || todoWritePayloadToPlan(args);
    if (normalized) {
      return <PlanChecklist plan={normalized} kind="todos" />;
    }
  }

  if (toolName === 'enter_plan_mode') {
    const reason = (args?.reason as string | undefined) || '';
    return <EnterPlanModeInlineCard reason={reason} resolved={result !== undefined} />;
  }
  if (toolName === 'exit_plan_mode') {
    const plan = (args?.plan as string | undefined) || '';
    return <ExitPlanModeInlineCard planText={plan} resolved={result !== undefined} />;
  }

  if (toolName === 'suggest_instruction' && result !== undefined && !isError) {
    return <SuggestInstructionCard result={result as SuggestInstructionResult} />;
  }

  const safeToolName = toolName || 'tool';
  const icon = TOOL_ICONS[safeToolName] || '🔧';
  const label = getToolLabel(toolName);
  const isDone = result !== undefined;
  const { onOpenDocument, sessionId } = useContext(ChatActionsContext);

  const isDocCreation = DOC_CREATION_TOOLS.has(safeToolName) && isDone && !isError;
  const docResult = isDocCreation ? (result as Record<string, unknown> | null) : null;
  let docPath = docResult?.path as string | undefined;
  let isDocx = docResult?.has_docx === true || (docPath ? /\.docx?$/i.test(docPath) : false);

  if (!docPath && toolName === 'run_python' && isDone && !isError) {
    const r = result as Record<string, unknown> | null;
    const files = r?.files_created as Array<Record<string, unknown>> | undefined;
    const created = files?.find(f => f.added_to_workspace);
    if (created?.path) {
      docPath = String(created.path);
      isDocx = created.type === 'docx' || /\.docx?$/i.test(docPath);
    }
  }

  let summary = '';
  if (isDone) {
    const r = result as Record<string, unknown> | null;
    if (isError) {
      summary = String(r?.error || 'Failed');
    } else if (toolName === 'read_document' && r?.content) {
      summary = `Read ${(r.content as string).length} characters`;
    } else if (toolName === 'web_search' && r?.count) {
      summary = `Found ${r.count} results`;
    } else if (toolName === 'compare' && r?.similarity_pct !== undefined) {
      summary = `${r.similarity_pct}% similar`;
    } else if (toolName === 'list_documents' && r?.documents) {
      summary = `${(r.documents as unknown[]).length} documents`;
    } else if (toolName === 'create_redlined_docx' && r?.success) {
      summary = 'Redline created';
    } else if (docPath) {
      summary = '';
    } else if (r?.success) {
      summary = 'Done';
    } else {
      summary = 'Completed';
    }
  }

  let argSummary = '';
  if (toolName === 'read_document' && args?.path) {
    argSummary = String(args.path).slice(0, 30);
  } else if (toolName === 'web_search' && args?.query) {
    argSummary = `"${String(args.query).slice(0, 50)}"`;
  } else if (toolName === 'web_fetch' && args?.url) {
    argSummary = String(args.url).slice(0, 50);
  } else if (toolName === 'edit_document' && args?.explanation) {
    argSummary = String(args.explanation).slice(0, 60);
  }

  return (
    <div className={`${styles.toolCall} ${isDone ? (isError ? styles.toolError : styles.toolDone) : styles.toolRunning}`}>
      <div className={styles.toolHeader}>
        <span className={styles.toolStatus}>
          {isDone ? (isError ? '✗' : '✓') : <span className={styles.toolSpinner} />}
        </span>
        <span className={styles.toolIcon}>{icon}</span>
        <span className={styles.toolName}>{label}</span>
        {argSummary && <span className={styles.toolArgs}>{argSummary}</span>}
      </div>
      {summary && <div className={styles.toolSummary}>{summary}</div>}
      {docPath && (
        <div className={styles.docCard}>
          <span className={styles.docCardIcon}>{isDocx ? '📄' : '📝'}</span>
          <span className={styles.docCardPath}>{docPath}</span>
          {isDocx && <span className={styles.docCardBadge}>DOCX</span>}
        </div>
      )}
    </div>
  );
}

export interface WorkspaceChatProps {
  documentText?: string;
  selectedText?: string;
  sessionContext?: string;
  documentId?: string;
  documentName?: string;
  hasDocument?: boolean;
  hasUserContent?: boolean;
  workspaceSessionId?: string;
  onAgenticSessionCreated?: (sessionId: string) => void;
  onDocumentUpdate?: (path: string, content: string, docType?: string, replacementText?: string) => void;
  onDocumentCreated?: (event: DocumentCreatedEvent) => void;
  onDocumentDeleted?: (path: string) => void;
  onOpenDocument?: (sessionId: string, documentPath: string) => void;
  onDownloadDocument?: (sessionId: string, documentPath: string) => void;
  newChatTrigger?: number;
  showHeader?: boolean;
  variant?: 'sidebar' | 'sheet' | 'fullscreen';
  initialThreadId?: string | null;
  onThreadIdChanged?: (threadId: string | null) => void;
  onSelectThread?: (threadId: string) => void;
  onCreditsExhausted?: () => void;
}

export function WorkspaceChat({
  documentText,
  selectedText,
  sessionContext,
  documentId,
  documentName,
  hasDocument,
  hasUserContent = true,
  workspaceSessionId,
  onAgenticSessionCreated,
  onDocumentUpdate,
  onDocumentCreated,
  onDocumentDeleted,
  onOpenDocument,
  onDownloadDocument,
  newChatTrigger,
  showHeader = true,
  variant = 'sidebar',
  initialThreadId,
  onThreadIdChanged,
  onSelectThread,
  onCreditsExhausted,
}: WorkspaceChatProps) {

  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const attachedFilesRef = useRef<AttachedFile[]>([]);
  useEffect(() => { attachedFilesRef.current = attachedFiles; }, [attachedFiles]);
  const clearAttachments = useCallback(() => {
    for (const af of attachedFilesRef.current) {
      if (af.preview) URL.revokeObjectURL(af.preview);
    }
    setAttachedFiles([]);
    attachedFilesRef.current = [];
  }, []);

  const defaultSuggestions = hasDocument
    ? ['Review document', 'Compare & redline', 'Research']
    : hasUserContent
      ? ['Draft a document', 'Research', 'Review & edit a document']
      : ['Set up workspace', 'Draft a document', 'Research'];

  const [slashCommands, setSlashCommands] = useState<SlashCommand[] | undefined>(undefined);

  const {
    runtime, resetChat, isRunning, thinkingText, thinkingMap, messages, threadTitle, session, mode, setMode,
    awaitingApproval, approvePlan, cancelPlan,
    pendingEnterPlan, pendingExitPlan, approveEnterPlan, rejectEnterPlan, approveExitPlan, rejectExitPlan,
  } = useAgenticRuntime({
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
    suggestions: defaultSuggestions,
    initialThreadId,
    onThreadIdChanged,
    attachedFilesRef,
    clearAttachments,
    onCreditsExhausted,
    slashCommands,
  });

  const lastTriggerRef = useRef(newChatTrigger ?? 0);
  useEffect(() => {
    const trigger = newChatTrigger ?? 0;
    if (trigger > 0 && trigger !== lastTriggerRef.current) {
      lastTriggerRef.current = trigger;
      resetChat();
    }
  }, [newChatTrigger, resetChat]);

  const derivedTitle = React.useMemo(() => {
    if (documentName) return documentName;
    if (threadTitle) {
      const t = threadTitle.trim();
      if (t.length > 40) return t.slice(0, 40) + '…';
      if (t.length > 0) return t;
    }
    const firstUserMsg = messages.find((m) => m.role === 'user');
    if (firstUserMsg?.content) {
      const text = typeof firstUserMsg.content === 'string'
        ? firstUserMsg.content
        : String(firstUserMsg.content);
      const trimmed = text.trim();
      if (trimmed.length > 40) return trimmed.slice(0, 40) + '…';
      if (trimmed.length > 0) return trimmed;
    }
    return 'New Task';
  }, [documentName, threadTitle, messages]);

  const chatActions = React.useMemo(() => ({
    onOpenDocument,
    onDownloadDocument,
    sessionId: workspaceSessionId,
    awaitingApproval,
    approvePlan,
    cancelPlan,
    pendingEnterPlan,
    pendingExitPlan,
    approveEnterPlan,
    rejectEnterPlan,
    approveExitPlan,
    rejectExitPlan,
  }), [
    onOpenDocument, onDownloadDocument, workspaceSessionId,
    awaitingApproval, approvePlan, cancelPlan,
    pendingEnterPlan, pendingExitPlan,
    approveEnterPlan, rejectEnterPlan, approveExitPlan, rejectExitPlan,
  ]);

  const [infoModalOpen, setInfoModalOpen] = useState(false);

  return (
    <ThinkingContext.Provider value={thinkingMap}>
    <ChatActionsContext.Provider value={chatActions}>
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={styles.container} data-variant={variant}>
        {/* Thread selector header */}
        {showHeader && (
          <ThreadSelectorDropdown
            currentTitle={derivedTitle}
            onSelectThread={(threadId) => onSelectThread?.(threadId)}
            onNewThread={resetChat}
            onInfoClick={() => setInfoModalOpen(true)}
          />
        )}

        {/* Mode pill (non-clickable label + discrete × to exit). */}
        {mode !== 'default' && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, margin: '4px 12px 0', alignItems: 'center' }}>
            <span
              title={
                mode === 'plan'
                  ? 'Plan mode — the agent writes a plan and waits for your approval before executing.'
                  : 'Coordinator mode — multi-agent with workers.'
              }
              style={{
                padding: '2px 8px',
                fontSize: 11,
                color: '#1e40af',
                background: '#dbeafe',
                border: '1px solid #bfdbfe',
                borderRadius: 999,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                userSelect: 'none',
              }}
            >
              {mode === 'plan' ? '📋 Plan' : '👥 Coordinator'}
            </span>
            <button
              type="button"
              onClick={() => setMode('default')}
              aria-label="Exit plan mode"
              title="Exit plan mode"
              style={{
                width: 18,
                height: 18,
                padding: 0,
                fontSize: 12,
                lineHeight: 1,
                color: '#64748b',
                background: 'transparent',
                border: 'none',
                borderRadius: 999,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              ×
            </button>
          </div>
        )}

        {/* Workspace info modal */}
        <WorkspaceInfoModal isOpen={infoModalOpen} onClose={() => setInfoModalOpen(false)} />

        {/* Plan-mode approvals now render inline via EnterPlanModeInlineCard
            and ExitPlanModeInlineCard — right where the tool call was made,
            so the user can't miss them in the conversation flow. */}

        {/* Messages */}
        <ThreadPrimitive.Root className={styles.thread}>
          <ThreadPrimitive.Viewport className={styles.viewport} autoScroll={false}>
            <ThreadPrimitive.Empty>
              <div className={styles.emptyState}>
                {!hasDocument && (
                  <>
                    <h2 className={styles.emptyStateHeading}>What would you like to work on?</h2>
                    <div className={styles.emptyStateFormats}>
                      <span className={styles.formatBadgeDocx}>DOCX</span>
                      <span className={styles.formatBadgePptx}>PPTX</span>
                      <span className={styles.formatBadgeXlsx}>XLSX</span>
                      <span className={styles.formatBadgePdf}>PDF</span>
                    </div>
                  </>
                )}
                <div className={styles.emptyStateChips}>
                  {hasDocument ? (
                    <>
                      <ThreadPrimitive.Suggestion prompt="/review" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Review document</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/compare" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Compare &amp; redline</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/research" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Research</span>
                      </ThreadPrimitive.Suggestion>
                    </>
                  ) : hasUserContent ? (
                    <>
                      <ThreadPrimitive.Suggestion prompt="/draft" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Draft a document</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/research" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Research</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/review" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Review &amp; edit a document</span>
                      </ThreadPrimitive.Suggestion>
                    </>
                  ) : (
                    <>
                      <ThreadPrimitive.Suggestion prompt="/setup" method="replace" autoSend>
                        <span className={`${styles.suggestionChip} ${styles.suggestionChipPrimary}`}>Set up workspace</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/draft" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Draft a document</span>
                      </ThreadPrimitive.Suggestion>
                      <ThreadPrimitive.Suggestion prompt="/research" method="replace" autoSend>
                        <span className={styles.suggestionChip}>Research</span>
                      </ThreadPrimitive.Suggestion>
                    </>
                  )}
                </div>
              </div>
            </ThreadPrimitive.Empty>

            <ThreadPrimitive.Messages
              components={{
                UserMessage,
                AssistantMessage,
              }}
            />

            {/* Thinking indicator (live, always shown while agent is running) */}
            {isRunning && (
              <ThinkingDisclosure text={thinkingText} live />
            )}
          </ThreadPrimitive.Viewport>

          {/* Composer with slash command support */}
          <ChatComposer
            isRunning={isRunning}
            attachedFiles={attachedFiles}
            setAttachedFiles={setAttachedFiles}
            onSlashCommandsChange={setSlashCommands}
          />
          <div className={styles.encryptionFooter}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            <span>Encrypted at rest with AES-256</span>
          </div>
        </ThreadPrimitive.Root>
      </div>
    </AssistantRuntimeProvider>
    </ChatActionsContext.Provider>
    </ThinkingContext.Provider>
  );
}

function ChatComposer({
  isRunning,
  attachedFiles,
  setAttachedFiles,
  onSlashCommandsChange,
}: {
  isRunning: boolean;
  attachedFiles: AttachedFile[];
  setAttachedFiles: React.Dispatch<React.SetStateAction<AttachedFile[]>>;
  onSlashCommandsChange?: (cmds: SlashCommand[]) => void;
}) {
  const composerRuntime = useComposerRuntime();
  const composerText = useComposer((s) => s.text);
  const { commands: slashCommands } = useSlashCommands();
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { pendingEnterPlan, pendingExitPlan } = useContext(ChatActionsContext);
  const approvalPending = Boolean(pendingEnterPlan);
  const approvalPlaceholder = pendingExitPlan
    ? 'Approve the plan above, or type to refine it.'
    : 'Use the buttons above to enter plan mode or stay reactive.';

  useEffect(() => {
    onSlashCommandsChange?.(slashCommands);
  }, [slashCommands, onSlashCommandsChange]);

  useEffect(() => {
    if (composerText.startsWith('/')) {
      setSlashMenuOpen(true);
      setSlashFilter(composerText.slice(1));
    } else {
      if (slashMenuOpen) {
        setSlashMenuOpen(false);
        setSlashFilter('');
      }
    }
  }, [composerText]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSlashSelect = useCallback((cmd: SlashCommand) => {
    setSlashMenuOpen(false);
    setSlashFilter('');
    composerRuntime.setText(cmd.name);
    composerRuntime.send();
  }, [composerRuntime]);

  const handleSlashClose = useCallback(() => {
    setSlashMenuOpen(false);
    setSlashFilter('');
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (slashMenuOpen && (e.key === 'Enter' || e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'Tab')) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, [slashMenuOpen]);

  const handleAttachClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFilesSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newAttachments: AttachedFile[] = Array.from(files).map((file) => {
      const id = `attach-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const isImage = file.type.startsWith('image/');
      const preview = isImage ? URL.createObjectURL(file) : undefined;
      return { file, id, preview };
    });

    setAttachedFiles((prev) => [...prev,...newAttachments]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [setAttachedFiles]);

  const handleRemoveFile = useCallback((id: string) => {
    setAttachedFiles((prev) => {
      const removed = prev.find((f) => f.id === id);
      if (removed?.preview) URL.revokeObjectURL(removed.preview);
      return prev.filter((f) => f.id !== id);
    });
  }, [setAttachedFiles]);

  return (
    <div className={styles.composerArea} style={{ position: 'relative' }}>
      {slashMenuOpen && (
        <SlashCommandMenu
          isOpen={slashMenuOpen}
          filter={slashFilter}
          onSelect={handleSlashSelect}
          onClose={handleSlashClose}
          commands={slashCommands}
        />
      )}

      {/* Attached files bar */}
      {attachedFiles.length > 0 && (
        <div className={styles.attachedFilesBar}>
          {attachedFiles.map((af) => (
            <div key={af.id} className={styles.attachedFileChip}>
              {af.preview && (
                <img src={af.preview} alt="" className={styles.attachedFilePreview} />
              )}
              <span className={styles.attachedFileName}>
                {af.file.name.length > 24 ? af.file.name.slice(0, 21) + '...' : af.file.name}
              </span>
              <button
                type="button"
                className={styles.attachedFileRemove}
                onClick={() => handleRemoveFile(af.id)}
                aria-label={`Remove ${af.file.name}`}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <ComposerPrimitive.Root className={styles.composer}>
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={handleFilesSelected}
        />

        {/* Attach button (paperclip) */}
        <button
          type="button"
          className={styles.attachButton}
          onClick={handleAttachClick}
          title="Attach files"
          aria-label="Attach files"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
          </svg>
        </button>

        <ComposerPrimitive.Input
          className={styles.composerInput}
          placeholder={pendingExitPlan ? approvalPlaceholder : approvalPending ? approvalPlaceholder : 'What do you need to do?'}
          onKeyDown={handleKeyDown}
          onPaste={(e) => {
            const el = e.currentTarget;
            requestAnimationFrame(() => {
              el.scrollTop = 0;
            });
          }}
          maxRows={8}
          disabled={approvalPending}
        />
        <div className={styles.composerActions}>
          {isRunning ? (
            <ComposerPrimitive.Cancel className={styles.composerCancel}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </ComposerPrimitive.Cancel>
          ) : (
            <ComposerPrimitive.Send className={styles.composerSend}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </ComposerPrimitive.Send>
          )}
        </div>
      </ComposerPrimitive.Root>
    </div>
  );
}

function ThinkingDisclosure({ text, live = false }: { text: string; live?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = text.length > 0;

  return (
    <div className={styles.thinkingWrapper}>
      <button
        className={styles.thinkingToggle}
        onClick={hasContent ? () => setExpanded((v) => !v) : undefined}
        style={hasContent ? undefined : { cursor: 'default' }}
      >
        {live ? (
          <span className={styles.thinkingDots}>
            <span /><span /><span />
          </span>
        ) : (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="10" /><path d="M12 8v4m0 4h.01" />
          </svg>
        )}
        <span>{live ? 'Thinking' : 'View reasoning'}</span>
        {hasContent && (
          <svg
            className={`${styles.thinkingChevron} ${expanded ? styles.thinkingChevronOpen : ''}`}
            width="12" height="12" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </button>
      {expanded && hasContent && (
        <div className={styles.thinkingContent}>
          {text}
        </div>
      )}
    </div>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className={styles.userMessage}>
      <div className={styles.userText}>
        <MessagePrimitive.Content
          components={{
            Text: ({ text }) => <p>{text}</p>,
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const thinkingMap = useContext(ThinkingContext);
  const message = useMessage();
  const thinking = thinkingMap.get(message.id);
  const { onOpenDocument, onDownloadDocument, sessionId } = useContext(ChatActionsContext);

  const createdDocs = React.useMemo(() => {
    if (message.role !== 'assistant') return [];
    const docs: { path: string; isDocx: boolean }[] = [];
    const seen = new Set<string>();
    for (const part of message.content) {
      if (part.type !== 'tool-call' || !part.result || part.isError) continue;

      let r = part.result as Record<string, unknown>;
      if (Array.isArray(r)) {
        const textPart = (r as Array<Record<string, unknown>>).find(p => p.type === 'text');
        if (textPart?.text) {
          try { r = JSON.parse(textPart.text as string); } catch { continue; }
        } else continue;
      }

      if (DOC_CREATION_TOOLS.has(part.toolName)) {
        const path = (r?.path ?? r?.document_path) as string | undefined;
        if (path && !seen.has(path)) {
          seen.add(path);
          docs.push({
            path,
            isDocx: r?.has_docx === true || /\.docx?$/i.test(path),
          });
        }
      } else if (part.toolName === 'run_python') {
        const files = r?.files_created as Array<Record<string, unknown>> | undefined;
        if (files) {
          for (const f of files) {
            if (f.added_to_workspace && f.path && !seen.has(String(f.path))) {
              const fpath = String(f.path);
              seen.add(fpath);
              docs.push({
                path: fpath,
                isDocx: f.type === 'docx' || /\.docx?$/i.test(fpath),
              });
            }
          }
        }
      }
    }
    return docs;
  }, [message]);

  return (
    <MessagePrimitive.Root className={styles.assistantMessage}>
      {thinking && <ThinkingDisclosure text={thinking} />}
      <div className={styles.answerContent}>
        <MessagePrimitive.Content
          components={{
            Text: AssistantText,
            tools: { Override: ToolCallComponent },
          }}
        />
      </div>
      {createdDocs.length > 0 && (!message.status || message.status.type !== 'running') && (
        <div className={styles.createdDocsBar}>
          {createdDocs.map((doc) => (
            <div key={doc.path} className={styles.createdDocCard}>
              <button
                className={styles.createdDocMain}
                onClick={() => sessionId && onOpenDocument?.(sessionId, doc.path)}
                title={`Open ${doc.path}`}
              >
                <span className={styles.createdDocIcon}>{doc.isDocx ? '📄' : '📝'}</span>
                <span className={styles.createdDocInfo}>
                  <span className={styles.createdDocPath}>{doc.path}</span>
                  <span className={styles.createdDocHint}>Click to open</span>
                </span>
                {doc.isDocx && <span className={styles.createdDocBadge}>DOCX</span>}
              </button>
              {onDownloadDocument && sessionId && (
                <button
                  className={styles.createdDocDownload}
                  onClick={(e) => { e.stopPropagation(); onDownloadDocument(sessionId, doc.path); }}
                  title={`Download ${doc.path}`}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <AssistantActions />
    </MessagePrimitive.Root>
  );
}

function AssistantActions() {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className={styles.actionBar}
    >
      <ActionBarPrimitive.Copy className={styles.actionBtn}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Reload className={styles.actionBtn}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="23 4 23 10 17 10" />
          <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
        </svg>
      </ActionBarPrimitive.Reload>
    </ActionBarPrimitive.Root>
  );
}

const remarkPlugins = [remarkGfm, remarkBreaks];

function preprocessMarkdown(text: string): string {
  let cleaned = text.replace(
    /<\|?tool_calls?_section_begin\|?>[\s\S]*?(<\|?tool_calls?_section_end\|?>|$)/g,
    ''
  );
  cleaned = cleaned.replace(
    /<\|?tool_call(?:s_section)?_?(?:begin|end|argument_begin)\|?>/g,
    ''
  );
  cleaned = cleaned.replace(/functions\.\w+:\d+/g, '');

  cleaned = cleaned.replace(/<think>[\s\S]*?<\/think>/gi, '');

  cleaned = cleaned.replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2');

  return cleaned;
}

const markdownComponents = {
  a: ({ href, children,...rest }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  ),
};

function AssistantText() {
  return <MarkdownTextPrimitive className={styles.markdownContent} remarkPlugins={remarkPlugins} components={markdownComponents} preprocess={preprocessMarkdown} />;
}

function ToolCallComponent(props: {
  toolName: string;
  args: Record<string, unknown>;
  argsText: string;
  result?: unknown;
  isError?: boolean;
  toolCallId: string;
  addResult: (result: unknown) => void;
  resume: (payload: unknown) => void;
}) {
  return (
    <ToolCallFallback
      toolName={props.toolName}
      args={props.args}
      result={props.result}
      isError={props.isError}
    />
  );
}

export default WorkspaceChat;
