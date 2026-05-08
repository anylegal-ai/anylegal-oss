'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import styles from './DocumentManager.module.css';

interface Document {
  id: string;
  title: string;
  preview: string;
  document_type: string;
  word_count: number;
  created_at: string;
  updated_at: string;
}

interface DocumentManagerProps {
  onSelectDocument: (content: string, title: string, documentId?: string) => void;
  currentDocumentContent?: string;
  currentDocumentId?: string;
  onClose?: () => void;
  onDocumentSaved?: (documentId: string, title: string) => void;
}

export default function DocumentManager({
  onSelectDocument,
  currentDocumentContent,
  currentDocumentId,
  onClose,
  onDocumentSaved,
}: DocumentManagerProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveTitle, setSaveTitle] = useState('');
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [deleteConfirmDoc, setDeleteConfirmDoc] = useState<Document | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleting, setDeleting] = useState(false);

  const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';

  const hasContentToSave = useMemo(() => {
    if (!currentDocumentContent) return false;
    const textContent = currentDocumentContent.replace(/<[^>]*>/g, '').trim();
    return textContent.length > 10;
  }, [currentDocumentContent]);

  const filteredDocuments = useMemo(() => {
    if (!searchQuery.trim()) return documents;
    const query = searchQuery.toLowerCase();
    return documents.filter(doc => 
      doc.title.toLowerCase().includes(query) ||
      doc.preview.toLowerCase().includes(query)
    );
  }, [documents, searchQuery]);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      setError(null);

      const token = localStorage.getItem('auth_token');
      const response = await fetch(`${BASE_URL}/api/v1/documents`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error('Failed to load documents');
      }

      const data = await response.json();
      setDocuments(data.documents || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDocument = async (docId: string) => {
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token');

      const response = await fetch(`${BASE_URL}/api/v1/documents/${docId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load document');
      }

      const doc = await response.json();
      onSelectDocument(doc.content, doc.title, docId);
      onClose?.();
    } catch (err: any) {
      setError(err.message || 'Failed to open document');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDocument = async () => {
    if (!currentDocumentContent || !saveTitle.trim()) return;

    try {
      setSaving(true);
      setError(null);

      const token = localStorage.getItem('auth_token');

      const response = await fetch(`${BASE_URL}/api/v1/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: saveTitle.trim(),
          content: currentDocumentContent,
          document_type: 'general',
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to save document');
      }

      const data = await response.json();
      const newDocId = data.id || data.document_id;

      setShowSaveDialog(false);
      setSaveTitle('');
      loadDocuments();

      if (newDocId && onDocumentSaved) {
        onDocumentSaved(newDocId, saveTitle.trim());
      }
    } catch (err: any) {
      setError(err.message || 'Failed to save document');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteDocument = async () => {
    if (!deleteConfirmDoc) return;

    try {
      setDeleting(true);
      const token = localStorage.getItem('auth_token');

      const response = await fetch(`${BASE_URL}/api/v1/documents/${deleteConfirmDoc.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to delete document');
      }

      setDeleteConfirmDoc(null);
      loadDocuments();
    } catch (err: any) {
      setError(err.message || 'Failed to delete document');
    } finally {
      setDeleting(false);
    }
  };

  const formatRelativeTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const diffWeeks = Math.floor(diffDays / 7);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffWeeks < 4) return `${diffWeeks}w ago`;

    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
          </svg>
          My Documents
        </h2>
        <div className={styles.headerActions}>
          {hasContentToSave && (
            <button 
              className={styles.saveBtn}
              onClick={() => setShowSaveDialog(true)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
              Save Current
            </button>
          )}
          {onClose && (
            <button className={styles.closeBtn} onClick={onClose}>
              ×
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className={styles.error}>
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Save Dialog */}
      {showSaveDialog && (
        <div className={styles.saveDialog}>
          <h3>Save Document</h3>
          <input
            type="text"
            placeholder="Document title..."
            value={saveTitle}
            onChange={(e) => setSaveTitle(e.target.value)}
            className={styles.saveInput}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && saveTitle.trim()) {
                handleSaveDocument();
              }
            }}
          />
          <div className={styles.saveActions}>
            <button 
              className={styles.saveCancelBtn}
              onClick={() => {
                setShowSaveDialog(false);
                setSaveTitle('');
              }}
            >
              Cancel
            </button>
            <button 
              className={styles.saveConfirmBtn}
              onClick={handleSaveDocument}
              disabled={!saveTitle.trim() || saving}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {/* Search Bar */}
      {!loading && documents.length > 0 && (
        <div className={styles.searchBar}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={styles.searchInput}
          />
          {searchQuery && (
            <button 
              className={styles.searchClear}
              onClick={() => setSearchQuery('')}
            >
              ×
            </button>
          )}
        </div>
      )}

      {/* Documents List */}
      <div className={styles.documentsList}>
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner}></div>
            <p>Loading documents...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className={styles.empty}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className={styles.emptyIcon}>
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            <p className={styles.emptyText}>No saved documents yet</p>
            <p className={styles.emptyHint}>
              Documents you save will appear here for easy access.
            </p>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className={styles.empty}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className={styles.emptyIcon}>
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <p className={styles.emptyText}>No documents found</p>
            <p className={styles.emptyHint}>
              Try a different search term.
            </p>
          </div>
        ) : (
          filteredDocuments.map((doc) => (
            <div key={doc.id} className={styles.documentCard}>
              <div className={styles.docIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
              </div>
              <div className={styles.docInfo}>
                <h4 className={styles.docTitle}>{doc.title}</h4>
                <p className={styles.docPreview}>{doc.preview}</p>
                <div className={styles.docMeta}>
                  <span>{doc.word_count} words</span>
                  <span>•</span>
                  <span>{formatRelativeTime(doc.updated_at)}</span>
                </div>
              </div>
              <div className={styles.docActions}>
                <button 
                  className={styles.openBtn}
                  onClick={() => handleOpenDocument(doc.id)}
                >
                  Open
                </button>
                <button 
                  className={styles.deleteBtn}
                  onClick={() => setDeleteConfirmDoc(doc)}
                  title="Delete document"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Privacy Notice */}
      <div className={styles.privacyNotice}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0110 0v4"/>
        </svg>
        <span>Your documents are encrypted at rest</span>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmDoc && (
        <div className={styles.deleteModalOverlay} onClick={() => !deleting && setDeleteConfirmDoc(null)}>
          <div className={styles.deleteModal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.deleteModalIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
              </svg>
            </div>
            <h3 className={styles.deleteModalTitle}>Delete Document?</h3>
            <p className={styles.deleteModalText}>
              Are you sure you want to delete "<strong>{deleteConfirmDoc.title}</strong>"? 
              This action cannot be undone.
            </p>
            <div className={styles.deleteModalActions}>
              <button 
                className={styles.deleteModalCancel}
                onClick={() => setDeleteConfirmDoc(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button 
                className={styles.deleteModalConfirm}
                onClick={handleDeleteDocument}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
