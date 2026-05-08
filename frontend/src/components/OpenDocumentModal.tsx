'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './OpenDocumentModal.module.css';

interface Document {
  id: string;
  title: string;
  preview: string;
  document_type: string;
  word_count: number;
  created_at: string;
  updated_at: string;
}

interface OpenDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCloudDocument: (content: string, title: string, documentId: string) => void;
  onUploadClick: () => void;
}

export default function OpenDocumentModal({
  isOpen,
  onClose,
  onSelectCloudDocument,
  onUploadClick,
}: OpenDocumentModalProps) {
  const [activeTab, setActiveTab] = useState<'upload' | 'cloud'>('upload');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    setIsAuthenticated(!!token);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && activeTab === 'cloud' && isAuthenticated) {
      loadDocuments();
    }
  }, [isOpen, activeTab, isAuthenticated]);

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
      onSelectCloudDocument(doc.content, doc.title, docId);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to open document');
    } finally {
      setLoading(false);
    }
  };

  const handleUploadClick = () => {
    onUploadClick();
    onClose();
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Open Document</h2>
          <button className={styles.closeBtn} onClick={onClose}>×</button>
        </div>

        <div className={styles.tabs}>
          <button 
            className={`${styles.tab} ${activeTab === 'upload' ? styles.tabActive : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Upload from Device
          </button>
          <button 
            className={`${styles.tab} ${activeTab === 'cloud' ? styles.tabActive : ''}`}
            onClick={() => setActiveTab('cloud')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            Encrypted Cloud
          </button>
        </div>

        <div className={styles.content}>
          {activeTab === 'upload' ? (
            <div className={styles.uploadTab}>
              <div className={styles.uploadArea} onClick={handleUploadClick}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <p className={styles.uploadText}>Click to select a file</p>
                <p className={styles.uploadHint}>Supports .docx, .doc, .pdf, .xlsx, .pptx, .txt</p>
              </div>
              <p className={styles.privacyNote}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="16" x2="12" y2="12"/>
                  <line x1="12" y1="8" x2="12.01" y2="8"/>
                </svg>
                Files from device are processed locally and not stored on our servers
              </p>
            </div>
          ) : (
            <div className={styles.cloudTab}>
              {!isAuthenticated ? (
                <div className={styles.signInPrompt}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                  <p>Sign in to access your encrypted documents</p>
                </div>
              ) : loading ? (
                <div className={styles.loading}>
                  <div className={styles.spinner} />
                  <span>Loading documents...</span>
                </div>
              ) : error ? (
                <div className={styles.error}>
                  <p>{error}</p>
                  <button onClick={loadDocuments}>Retry</button>
                </div>
              ) : documents.length === 0 ? (
                <div className={styles.emptyState}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <p>No saved documents yet</p>
                  <span>Save a document to access it from any device</span>
                </div>
              ) : (
                <>
                  <div className={styles.documentList}>
                    {documents.map(doc => (
                      <button
                        key={doc.id}
                        className={styles.documentItem}
                        onClick={() => handleOpenDocument(doc.id)}
                      >
                        <div className={styles.documentIcon}>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                            <line x1="16" y1="13" x2="8" y2="13"/>
                            <line x1="16" y1="17" x2="8" y2="17"/>
                          </svg>
                        </div>
                        <div className={styles.documentInfo}>
                          <span className={styles.documentTitle}>{doc.title}</span>
                          <span className={styles.documentMeta}>
                            {doc.word_count} words • {formatDate(doc.updated_at)}
                          </span>
                        </div>
                        <svg className={styles.openIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="9 18 15 12 9 6"/>
                        </svg>
                      </button>
                    ))}
                  </div>
                  <p className={styles.encryptionNote}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                    </svg>
                    All documents are encrypted at rest
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
