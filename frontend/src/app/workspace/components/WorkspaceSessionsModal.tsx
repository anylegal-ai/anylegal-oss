import React, { useState, useEffect, useCallback } from 'react';
import { DocumentCard } from './DocumentCard';
import {
  listWorkspaceSessions,
  getWorkspaceSession,
  deleteWorkspaceSession,
  downloadDocxExport,
  type SessionMetadata,
  type WorkspaceSession,
  type SessionDocument,
} from '../services/workspaceSessionService';
import styles from './WorkspaceSessionsModal.module.css';

interface WorkspaceSessionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadSession: (session: WorkspaceSession) => void;
  onOpenDocument: (sessionId: string, document: SessionDocument) => void;
  currentSessionId?: string | null;
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function WorkspaceSessionsModal({
  isOpen,
  onClose,
  onLoadSession,
  onOpenDocument,
  currentSessionId,
}: WorkspaceSessionsModalProps) {
  const [sessions, setSessions] = useState<SessionMetadata[]>([]);
  const [selectedSession, setSelectedSession] = useState<WorkspaceSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listWorkspaceSessions();
      setSessions(data);
    } catch (err) {
      console.error('Failed to load sessions:', err);
      setError('Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSessionDetails = useCallback(async (sessionId: string) => {
    try {
      setLoadingSession(true);
      setError(null);
      const session = await getWorkspaceSession(sessionId);
      if (session) {
        setSelectedSession(session);
      }
    } catch (err) {
      console.error('Failed to load session details:', err);
      setError('Failed to load session details');
    } finally {
      setLoadingSession(false);
    }
  }, []);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      const success = await deleteWorkspaceSession(sessionId);
      if (success) {
        setSessions(prev => prev.filter(s => s.id !== sessionId));
        if (selectedSession?.id === sessionId) {
          setSelectedSession(null);
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
      setError('Failed to delete session');
    }
    setConfirmDelete(null);
  }, [selectedSession]);

  const handleExportDocument = useCallback(async (documentPath: string) => {
    if (!selectedSession) return;
    try {
      await downloadDocxExport(selectedSession.id, documentPath);
    } catch (err) {
      console.error('Failed to export document:', err);
      setError('Failed to export document');
    }
  }, [selectedSession]);

  useEffect(() => {
    if (isOpen) {
      loadSessions();
      setSelectedSession(null);
      setSearchTerm('');
    }
  }, [isOpen, loadSessions]);

  const filteredSessions = sessions.filter(session => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      session.session_name?.toLowerCase().includes(term) ||
      session.document_name?.toLowerCase().includes(term)
    );
  });

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <h2 className={styles.title}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
            Workspace Sessions
          </h2>
          <button className={styles.closeBtn} onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className={styles.searchContainer}>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search sessions..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
          <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </div>

        {/* Content */}
        <div className={styles.content}>
          {/* Sessions List */}
          <div className={styles.sessionsList}>
            {loading ? (
              <div className={styles.loading}>
                <div className={styles.spinner} />
                Loading sessions...
              </div>
            ) : error ? (
              <div className={styles.error}>
                {error}
                <button onClick={loadSessions}>Retry</button>
              </div>
            ) : filteredSessions.length === 0 ? (
              <div className={styles.empty}>
                {searchTerm ? (
                  <>No sessions match your search.</>
                ) : (
                  <>
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                      <line x1="3" y1="9" x2="21" y2="9"/>
                      <line x1="9" y1="21" x2="9" y2="9"/>
                    </svg>
                    <p>No saved sessions yet</p>
                    <span>Sessions are automatically saved when you work with documents in the workspace.</span>
                  </>
                )}
              </div>
            ) : (
              filteredSessions.map(session => (
                <div
                  key={session.id}
                  className={`${styles.sessionItem} ${
                    selectedSession?.id === session.id ? styles.sessionItemActive : ''
                  } ${currentSessionId === session.id ? styles.sessionItemCurrent : ''}`}
                  onClick={() => loadSessionDetails(session.id)}
                >
                  <div className={styles.sessionInfo}>
                    <span className={styles.sessionName}>
                      {session.session_name || session.document_name || 'Untitled Session'}
                    </span>
                    <span className={styles.sessionMeta}>
                      {formatRelativeTime(session.updated_at)}
                      {currentSessionId === session.id && (
                        <span className={styles.currentBadge}>Current</span>
                      )}
                    </span>
                  </div>
                  <button
                    className={styles.deleteBtn}
                    onClick={e => {
                      e.stopPropagation();
                      setConfirmDelete(session.id);
                    }}
                    title="Delete session"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3,6 5,6 21,6"/>
                      <path d="M19,6v14a2,2,0,0,1-2,2H7a2,2,0,0,1-2-2V6m3,0V4a2,2,0,0,1,2-2h4a2,2,0,0,1,2,2v2"/>
                    </svg>
                  </button>
                </div>
              ))
            )}
          </div>

          {/* Session Details */}
          <div className={styles.sessionDetails}>
            {loadingSession ? (
              <div className={styles.loading}>
                <div className={styles.spinner} />
                Loading documents...
              </div>
            ) : selectedSession ? (
              <>
                <div className={styles.detailsHeader}>
                  <h3>{selectedSession.session_name || 'Session Documents'}</h3>
                  <button
                    className={styles.loadSessionBtn}
                    onClick={() => {
                      onLoadSession(selectedSession);
                      onClose();
                    }}
                  >
                    Load Session
                  </button>
                </div>

                <div className={styles.documentsList}>
                  {selectedSession.documents.length === 0 ? (
                    <div className={styles.emptyDocuments}>
                      No documents in this session
                    </div>
                  ) : (
                    selectedSession.documents.map(doc => (
                      <DocumentCard
                        key={doc.path}
                        document={{
                          path: doc.path,
                          description: doc.description || doc.path,
                          format: doc.format || 'html',
                          hasDocx: doc.has_docx ?? false,
                          isSynced: doc.is_synced ?? true,
                          modifiedAt: doc.modified_at || new Date().toISOString(),
                          content: doc.content,
                        }}
                        sessionId={selectedSession.id}
                        onOpen={(path, content) => {
                          console.log('[WorkspaceSessionsModal] Opening document:', { sessionId: selectedSession.id, path, hasContent: !!content });
                          onOpenDocument(selectedSession.id, doc);
                          onClose();
                        }}
                        onExport={doc.has_docx ? handleExportDocument : undefined}
                        isActive={false}
                      />
                    ))
                  )}
                </div>
              </>
            ) : (
              <div className={styles.noSelection}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                  <polyline points="14,2 14,8 20,8"/>
                </svg>
                <p>Select a session to view documents</p>
              </div>
            )}
          </div>
        </div>

        {/* Delete Confirmation */}
        {confirmDelete && (
          <div className={styles.confirmOverlay} onClick={() => setConfirmDelete(null)}>
            <div className={styles.confirmDialog} onClick={e => e.stopPropagation()}>
              <p>Are you sure you want to delete this session?</p>
              <p className={styles.confirmWarning}>This action cannot be undone.</p>
              <div className={styles.confirmActions}>
                <button
                  className={styles.cancelBtn}
                  onClick={() => setConfirmDelete(null)}
                >
                  Cancel
                </button>
                <button
                  className={styles.confirmDeleteBtn}
                  onClick={() => handleDeleteSession(confirmDelete)}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkspaceSessionsModal;
