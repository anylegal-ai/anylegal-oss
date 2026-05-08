
'use client';

import React, { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgenticStatus as AgenticStatusType, ToolCall, AgenticSession } from '@/app/workspace/hooks/useAgenticChat';
import styles from './AgenticStatus.module.css';

const TOOL_ICONS: Record<string, string> = {
  list_documents: '📄',
  read_document: '📖',
  create_document: '✍️',
  write_document: '✍️',
  edit_document: '✏️',
  web_search: '🔍',
  web_fetch: '🌐',
  compare: '⚖️',
  create_redlined_docx: '📝',
  accept_revisions: '✅',
  reject_revisions: '↩️',
  get_revision_stats: '📊',
  export_docx: '📤',
  search_workspace: '🔎',
  read_wiki_page: '🧠',
  list_wiki_pages: '🧠',
  append_wiki_note: '📌',
  update_wiki_page: '🧠',
  set_wiki_metadata: '🏷️',
  delete_wiki_page: '🗑️',
  suggest_instruction: '📝',
  analyze_clause: '🔬',
  generate_redline: '📝',
  compare_documents: '⚖️',
  summarize_changes: '📊',
};

const TOOL_CATEGORIES: Record<string, string> = {
  list_documents: 'Document',
  read_document: 'Document',
  create_document: 'Document',
  write_document: 'Document',
  edit_document: 'Document',
  clone_document: 'Document',
  delete_document: 'Document',
  web_search: 'Research',
  web_fetch: 'Research',
  compare: 'Comparison',
  produce_redline: 'Redline',
  accept_all_changes: 'Revisions',
  reject_all_changes: 'Revisions',
  accept_changes: 'Revisions',
  reject_changes: 'Revisions',
  revert_edit: 'Revisions',
  get_revision_stats: 'Revisions',
  add_comment: 'Revisions',
  instantiate_template: 'Template',
  export_docx: 'Export',
  search_workspace: 'Memory',
  read_wiki_page: 'Memory',
  list_wiki_pages: 'Memory',
  append_wiki_note: 'Memory',
  update_wiki_page: 'Memory',
  set_wiki_metadata: 'Memory',
  delete_wiki_page: 'Memory',
  suggest_instruction: 'Instructions',
  analyze_clause: 'Analysis',
  generate_redline: 'Analysis',
  summarize_changes: 'Analysis',
};

function getToolResultSummary(toolName: string, args: Record<string, unknown>, result: unknown): string {
  if (!result || typeof result !== 'object') return 'Completed';
  const r = result as Record<string, unknown>;

  switch (toolName) {
    case 'read_document':
      if (r.success) {
        const content = r.content as string;
        return `Read ${content?.length || 0} characters`;
      }
      return r.error as string || 'Document not found';

    case 'edit_document':
      if (r.success) {
        const docType = r.doc_type as string;
        if (docType === 'docx') return 'DOCX updated (tracked changes)';
        return 'Document updated successfully';
      }
      return r.error as string || 'Edit failed';

    case 'write_document':
      if (r.success) {
        const path = r.path as string || args.path as string;
        const action = r.action as string || 'saved';
        return `Document ${action}: ${path}`;
      }
      return r.error as string || 'Write failed';

    case 'web_search':
      if (r.success) {
        const count = r.count as number || (r.results as unknown[])?.length || 0;
        return `Found ${count} result${count !== 1 ? 's' : ''}`;
      }
      return 'Search failed';

    case 'compare':
      if (r.success) {
        const similarity = r.similarity_pct as number;
        return similarity !== undefined ? `Compared — ${similarity}% similar` : 'Comparison complete';
      }
      return 'Comparison failed';

    case 'accept_all_changes':
      if (r.success) return 'All tracked changes accepted';
      return r.error as string || 'Accept all failed';

    case 'reject_all_changes':
      if (r.success) return 'All tracked changes rejected';
      return r.error as string || 'Reject all failed';

    case 'accept_changes': {
      if (r.success) {
        const accepted = (r.accepted_ids as number[]) || [];
        const notFound = (r.not_found_ids as number[]) || [];
        const accCount = accepted.length;
        let msg = `Accepted ${accCount} change${accCount !== 1 ? 's' : ''}`;
        if (notFound.length) msg += ` (${notFound.length} not found)`;
        return msg;
      }
      return r.error as string || 'Accept failed';
    }

    case 'reject_changes': {
      if (r.success) {
        const rejected = (r.rejected_ids as number[]) || [];
        const notFound = (r.not_found_ids as number[]) || [];
        const rejCount = rejected.length;
        let msg = `Rejected ${rejCount} change${rejCount !== 1 ? 's' : ''}`;
        if (notFound.length) msg += ` (${notFound.length} not found)`;
        return msg;
      }
      return r.error as string || 'Reject failed';
    }

    case 'instantiate_template': {
      if (r.success) {
        const applied = (r.applied as string[]) || [];
        const notFound = (r.not_found as string[]) || [];
        const path = r.output_path as string || args.output_path as string;
        let msg = `Created from template: ${path}`;
        if (applied.length) msg += ` (${applied.length} placeholder${applied.length !== 1 ? 's' : ''} filled)`;
        if (notFound.length) msg += `, ${notFound.length} not found`;
        return msg;
      }
      return r.error as string || 'Template fill failed';
    }

    case 'produce_redline': {
      if (r.success) {
        const path = r.output_path as string || args.output_path as string;
        return `Redline DOCX created: ${path}`;
      }
      return r.error as string || 'Redline failed';
    }

    case 'add_comment':
      if (r.success) return 'Comment added';
      return r.error as string || 'Comment failed';

    case 'revert_edit':
      if (r.success) {
        const reverted = (r.reverted_ids as number[]) || [];
        return `Reverted ${reverted.length} edit${reverted.length !== 1 ? 's' : ''}`;
      }
      return r.error as string || 'Revert failed';

    case 'get_revision_stats': {
      if (r.success) {
        const ins = r.insertions as number || 0;
        const del = r.deletions as number || 0;
        const revisions = r.revisions as unknown[];
        if (Array.isArray(revisions) && revisions.length > 0) {
          return `${ins} insertions, ${del} deletions (${revisions.length} with snippets)`;
        }
        return `${ins} insertions, ${del} deletions`;
      }
      return 'Stats unavailable';
    }

    case 'export_docx':
      if (r.success) return 'DOCX exported';
      return 'Export failed';

    case 'search_workspace': {
      const count = r.result_count as number;
      if (typeof count === 'number') return `Found ${count} match${count !== 1 ? 'es' : ''}`;
      return 'Searched workspace';
    }

    case 'read_wiki_page':
      if (r.error) return r.error as string;
      return `Read AI Memory of ${args.slug || 'page'}`;

    case 'list_wiki_pages': {
      const cats = r.categories as Record<string, unknown[]> | undefined;
      const total = cats ? Object.values(cats).reduce((n, v) => n + (Array.isArray(v) ? v.length : 0), 0) : 0;
      return `Listed ${total} memory page${total !== 1 ? 's' : ''}`;
    }

    case 'append_wiki_note':
      if (r.ok) {
        const slug = (args.slug as string) || '';
        const last = slug.split('/').pop() || slug;
        return `Added note to AI Memory of ${last}`;
      }
      return (r.error as string) || 'Note failed';

    case 'update_wiki_page':
      if (r.ok) {
        const slug = (args.slug as string) || '';
        const last = slug.split('/').pop() || slug;
        return `Rewrote AI Memory of ${last}`;
      }
      return (r.error as string) || 'Update failed';

    case 'set_wiki_metadata':
      if (r.ok) {
        const key = (args.key as string) || 'metadata';
        return `Updated ${key} in AI Memory`;
      }
      return (r.error as string) || 'Metadata update failed';

    case 'delete_wiki_page':
      if (r.ok) return 'Removed from AI Memory';
      return (r.error as string) || 'Delete failed';

    case 'suggest_instruction':
      if (r.ok) {
        const target = (r.target_path as string) || 'anylegal.md';
        return `Proposed an addition to ${target}`;
      }
      return (r.error as string) || 'Suggestion failed';

    case 'create_document':
      if (r.success) {
        const path = r.path as string || args.path as string;
        return `Created: ${path}`;
      }
      return r.error as string || 'Creation failed';

    case 'web_fetch':
      if (r.success) {
        const chars = (r.content as string)?.length || 0;
        return `Fetched ${chars} characters`;
      }
      return 'Fetch failed';

    case 'list_documents':
      if (r.success) {
        const docs = r.documents as unknown[];
        return `Found ${docs?.length || 0} document${(docs?.length || 0) !== 1 ? 's' : ''}`;
      }
      return 'No documents found';

    default:
      if (r.success) return 'Completed successfully';
      if (r.error) return String(r.error).slice(0, 100);
      return 'Completed';
  }
}

function getToolArgsSummary(toolName: string, args: Record<string, unknown>): string {
  switch (toolName) {
    case 'read_document':
      return args.path ? `Document: ${String(args.path).slice(0, 30)}` : '';
    case 'edit_document':
      return args.explanation ? String(args.explanation).slice(0, 60) : 'Replacing text in document';
    case 'create_document':
    case 'write_document':
      return args.path ? `Creating: ${String(args.path).slice(0, 40)}` : '';
    case 'web_search':
      return args.query ? `"${String(args.query).slice(0, 50)}"` : '';
    case 'web_fetch':
      return args.url ? `${String(args.url).slice(0, 50)}` : '';
    case 'compare':
      return 'Comparing document versions';
    case 'create_redlined_docx':
      return args.output_path ? `Output: ${String(args.output_path)}` : 'Creating tracked-changes DOCX';
    case 'list_documents':
      return 'Listing workspace documents';

    case 'search_workspace':
      return args.query ? `Searching memory: "${String(args.query).slice(0, 50)}"` : '';
    case 'read_wiki_page':
      return args.slug ? `Reading AI Memory: ${String(args.slug)}` : '';
    case 'list_wiki_pages':
      return args.category ? `Listing ${args.category}` : 'Listing memory pages';
    case 'append_wiki_note': {
      const slug = (args.slug as string) || '';
      const last = slug.split('/').pop() || slug;
      const note = (args.note as string) || '';
      return note ? `${last} — "${note.slice(0, 80)}${note.length > 80 ? '…' : ''}"` : `Note for ${last}`;
    }
    case 'update_wiki_page': {
      const slug = (args.slug as string) || '';
      const last = slug.split('/').pop() || slug;
      return `Rewriting summary for ${last}`;
    }
    case 'set_wiki_metadata': {
      const slug = (args.slug as string) || '';
      const last = slug.split('/').pop() || slug;
      const key = (args.key as string) || '';
      return key ? `${last} · ${key}` : last;
    }
    case 'delete_wiki_page':
      return args.slug ? `Removing ${String(args.slug)}` : '';
    case 'suggest_instruction': {
      const text = (args.text as string) || '';
      return text ? `"${text.slice(0, 80)}${text.length > 80 ? '…' : ''}"` : 'Proposing instruction';
    }

    default:
      return '';
  }
}

interface AgenticStatusProps {
  status: AgenticStatusType;
  toolCalls: ToolCall[];
  currentTool: string | null;
  responseText: string;
  thinking?: string;
  error: string | null;
  session: AgenticSession | null;
  onCancel?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onOpenDocument?: (sessionId: string, documentPath: string) => void;
}

export function AgenticStatus({
  status,
  toolCalls,
  currentTool,
  responseText,
  thinking,
  error,
  session,
  onCancel,
  collapsed = false,
  onToggleCollapse,
  onOpenDocument,
}: AgenticStatusProps) {
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [thinkingExpanded, setThinkingExpanded] = useState(false); // Collapsed by default

  const statusMessage = useMemo(() => {
    switch (status) {
      case 'idle':
        return 'Ready';
      case 'connecting':
        return 'Connecting...';
      case 'running':
        return 'Thinking...';
      case 'executing_tool':
        const toolLabel = currentTool ? getToolLabel(currentTool) : 'tool';
        return `Executing ${toolLabel}...`;
      case 'completed':
        return 'Completed';
      case 'error':
        return 'Error';
      default:
        return 'Unknown';
    }
  }, [status, currentTool]);

  function getToolLabel(toolName: string): string {
    return toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  const toggleToolExpanded = (toolId: string) => {
    setExpandedTools(prev => {
      const next = new Set(prev);
      if (next.has(toolId)) {
        next.delete(toolId);
      } else {
        next.add(toolId);
      }
      return next;
    });
  };

  if (status === 'idle' && toolCalls.length === 0) {
    return null;
  }

  const isActive = status === 'running' || status === 'executing_tool' || status === 'connecting';

  return (
    <div className={`${styles.container} ${isActive ? styles.active : ''} ${collapsed ? styles.collapsed : ''}`}>
      {/* Header */}
      <div className={styles.header} onClick={onToggleCollapse}>
        <div className={styles.headerLeft}>
          <span className={`${styles.statusDot} ${styles[status]}`} />
          <span className={styles.statusText}>{statusMessage}</span>
          {isActive && <span className={styles.spinner} />}
        </div>
        <div className={styles.headerRight}>
          {toolCalls.length > 0 && (
            <span className={styles.toolCount}>
              {toolCalls.length} tool{toolCalls.length !== 1 ? 's' : ''} called
            </span>
          )}
          {isActive && onCancel && (
            <button 
              className={styles.cancelButton}
              onClick={(e) => {
                e.stopPropagation();
                onCancel();
              }}
            >
              Cancel
            </button>
          )}
          <span className={styles.collapseIcon}>
            {collapsed ? '▼' : '▲'}
          </span>
        </div>
      </div>

      {/* Content - hidden when collapsed */}
      {!collapsed && (
        <div className={styles.content}>
          {/* Error message */}
          {error && (
            <div className={styles.error}>
              <span className={styles.errorIcon}>⚠️</span>
              <span>{error}</span>
            </div>
          )}

          {/* Thinking/reasoning — internal LLM chain-of-thought, hidden from users */}

          {/* Tool calls list — numbered steps */}
          {toolCalls.length > 0 && (
            <div className={styles.toolCallsSection}>
              <div className={styles.sectionTitle}>Steps</div>
              <div className={styles.toolCalls}>
                {toolCalls.map((call, index) => {
                  const argsSummary = getToolArgsSummary(call.tool_name, call.arguments || {});
                  const resultSummary = call.result 
                    ? getToolResultSummary(call.tool_name, call.arguments || {}, call.result.result)
                    : '';

                  return (
                    <div 
                      key={`${call.tool_name}-${call.id || index}-${index}`}
                      className={`${styles.toolCall} ${call.result ? (call.result.success ? styles.success : styles.failed) : styles.pending}`}
                    >
                      <div 
                        className={styles.toolCallHeader}
                        onClick={() => toggleToolExpanded(call.id)}
                      >
                        {/* Step number or status indicator */}
                        <span className={styles.stepNumber}>
                          {call.result
                            ? (call.result.success ? '✓' : '✗')
                            : (!call.result && currentTool === call.tool_name)
                              ? '•'
                              : String(index + 1)
                          }
                        </span>
                        <span className={styles.toolIcon}>
                          {TOOL_ICONS[call.tool_name] || '🔧'}
                        </span>
                        <span className={styles.toolName}>
                          {getToolLabel(call.tool_name)}
                        </span>
                        <span className={styles.toolCategory}>
                          {TOOL_CATEGORIES[call.tool_name] || 'Tool'}
                        </span>
                        {!call.result && currentTool === call.tool_name && (
                          <span className={styles.toolSpinner} />
                        )}
                        <span className={styles.expandIcon}>
                          {expandedTools.has(call.id) ? '−' : '+'}
                        </span>
                      </div>

                      {/* Collapsed summary - always visible */}
                      {!expandedTools.has(call.id) && (argsSummary || resultSummary) && (
                        <div className={styles.toolSummary}>
                          {argsSummary && <span className={styles.argsSummary}>{argsSummary}</span>}
                          {resultSummary && <span className={styles.resultSummary}>{resultSummary}</span>}
                          {/* Open Document button for document creation results */}
                          {(call.tool_name === 'write_document' || call.tool_name === 'create_document' || call.tool_name === 'create_redlined_docx') &&
                           call.result?.success &&
                           onOpenDocument && (
                            <button
                              className={styles.openDocBtn}
                              onClick={(e) => {
                                e.stopPropagation();
                                const path = (call.result?.result as Record<string, unknown>)?.path as string ||
                                             (call.arguments as Record<string, unknown>)?.path as string;
                                console.log('[AgenticStatus] Opening document:', { sessionId: session?.sessionId, path });
                                if (path) {
                                  onOpenDocument(session?.sessionId || '', path);
                                }
                              }}
                              title="Open document in editor"
                            >
                              Open
                            </button>
                          )}
                          {/* Open in Memory button — for wiki edit tools that operate on a slug */}
                          {(call.tool_name === 'append_wiki_note' ||
                            call.tool_name === 'update_wiki_page' ||
                            call.tool_name === 'set_wiki_metadata' ||
                            call.tool_name === 'read_wiki_page') &&
                           call.result?.success &&
                           Boolean((call.arguments as Record<string, unknown>)?.slug) && (
                            <button
                              className={styles.openDocBtn}
                              onClick={(e) => {
                                e.stopPropagation();
                                const slug = (call.arguments as Record<string, unknown>).slug as string;
                                window.dispatchEvent(new CustomEvent('anylegal:openMemoryPage', { detail: { slug } }));
                              }}
                              title="Open this page in the Memory tab"
                            >
                              Open in Memory
                            </button>
                          )}
                        </div>
                      )}

                      {/* Expanded details - technical view for developers */}
                      {expandedTools.has(call.id) && (
                        <div className={styles.toolCallDetails}>
                          {/* User-friendly summary */}
                          {(argsSummary || resultSummary) && (
                            <div className={styles.friendlySummary}>
                              {argsSummary && <div>{argsSummary}</div>}
                              {resultSummary && <div className={styles.resultText}>{resultSummary}</div>}
                            </div>
                          )}

                          {/* Technical details (collapsed by default) */}
                          <details className={styles.technicalDetails}>
                            <summary className={styles.technicalSummary}>Technical Details</summary>
                            <div className={styles.detailSection}>
                              <div className={styles.detailLabel}>Arguments:</div>
                              <pre className={styles.detailCode}>
                                {JSON.stringify(call.arguments, null, 2)}
                              </pre>
                            </div>

                            {call.result && (
                              <div className={styles.detailSection}>
                                <div className={styles.detailLabel}>
                                  Result ({call.result.execution_time_ms.toFixed(0)}ms):
                                </div>
                                {call.result.error ? (
                                  <div className={styles.resultError}>
                                    {call.result.error}
                                  </div>
                                ) : (
                                  <pre className={styles.detailCode}>
                                    {JSON.stringify(call.result.result, null, 2).slice(0, 1000)}
                                    {JSON.stringify(call.result.result).length > 1000 && '...'}
                                  </pre>
                                )}
                              </div>
                            )}
                          </details>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Response text - shown during streaming and when completed */}
          {responseText && (
            <div className={`${styles.responseSection} ${status === 'running' ? styles.streaming : ''}`}>
              <div className={styles.sectionTitle}>
                {status === 'running' ? (
                  <>Response <span className={styles.streamingIndicator}>●</span></>
                ) : (
                  'Response'
                )}
              </div>
              <div className={styles.responseContent}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {responseText}
                </ReactMarkdown>
                {status === 'running' && (
                  <span className={styles.streamingCursor}>▋</span>
                )}
              </div>
            </div>
          )}

          {/* Session summary - shown when completed */}
          {status === 'completed' && session && (
            <div className={styles.sessionSummary}>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Iterations:</span>
                <span className={styles.summaryValue}>{session.iterations}</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Tool calls:</span>
                <span className={styles.summaryValue}>{session.toolCallCount}</span>
              </div>
              {session.documentsModified.length > 0 && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Modified:</span>
                  <span className={styles.summaryValue}>
                    {session.documentsModified.join(', ')}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AgenticStatus;
