'use client';

import React, { useEffect, useState, useCallback } from 'react';
import styles from './HistoryModal.module.css';
import { getAuthHeaders, isTokenExpired, refreshAccessToken } from '@/utils/auth';

interface Thread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface HistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onThreadSelect: (threadId: string) => void;
  privacyMode?: 'private' | 'cloud';
}

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';
const THREADS_PER_PAGE = 15;

export default function HistoryModal({ 
  isOpen, 
  onClose, 
  onThreadSelect,
  privacyMode = 'cloud'
}: HistoryModalProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  const fetchThreads = useCallback(async (page: number = 1) => {
    if (isTokenExpired()) {
      const refreshed = await refreshAccessToken();
      if (!refreshed) {
        setError('Session expired. Please sign in again.');
        setLoading(false);
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const url = `${BASE_URL}/api/v1/threads?page=${page}&limit=${THREADS_PER_PAGE}`;

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          ...getAuthHeaders()
        } as HeadersInit
      });

      if (!response.ok) {
        if (response.status === 401) {
          const refreshed = await refreshAccessToken();
          if (refreshed) {
            return fetchThreads(page);
          }
          setError('Session expired. Please sign in again.');
          setThreads([]);
          return;
        }
        throw new Error(`Failed to load threads: ${response.status}`);
      }

      const data = await response.json();
      const fetchedThreads = Array.isArray(data.threads) ? data.threads : [];
      setThreads(fetchedThreads);

      const totalCount = data.total_count;
      if (typeof totalCount === 'number') {
        setTotalPages(Math.ceil(totalCount / THREADS_PER_PAGE));
      } else {
        setTotalPages(fetchedThreads.length < THREADS_PER_PAGE ? 1 : page + 1);
      }
      setCurrentPage(page);
    } catch (err: any) {
      console.error('Error fetching threads:', err);
      setError(err.message || 'Failed to load history');
      setThreads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen && privacyMode === 'cloud') {
      fetchThreads(1);
    }
  }, [isOpen, privacyMode, fetchThreads]);

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      }).format(date);
    } catch {
      return dateString;
    }
  };

  const handleThreadClick = (threadId: string) => {
    onThreadSelect(threadId);
    onClose();
  };

  const handleDelete = async (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();

    if (!confirm('Delete this conversation? This cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`${BASE_URL}/api/v1/threads/${threadId}`, {
        method: 'DELETE',
        headers: {
          ...getAuthHeaders()
        } as HeadersInit
      });

      if (response.ok) {
        setThreads(threads.filter(t => t.id !== threadId));
      } else {
        alert('Failed to delete conversation');
      }
    } catch (err) {
      console.error('Error deleting thread:', err);
      alert('Failed to delete conversation');
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Conversation History</h2>
          <button className={styles.closeBtn} onClick={onClose}>×</button>
        </div>

        <div className={styles.content}>
          {privacyMode === 'private' ? (
            <div className={styles.privateMessage}>
              <span className={styles.privateIcon}>🔒</span>
              <h3>Private Mode Active</h3>
              <p>History is disabled in Private Mode. Switch to Secure Cloud mode to save and access your conversations.</p>
            </div>
          ) : loading ? (
            <div className={styles.loading}>Loading conversations...</div>
          ) : error ? (
            <div className={styles.error}>{error}</div>
          ) : threads.length === 0 ? (
            <div className={styles.empty}>
              <p>No conversations yet</p>
              <span>Your research conversations will appear here</span>
            </div>
          ) : (
            <>
              <div className={styles.threadList}>
                {threads.map(thread => (
                  <div 
                    key={thread.id}
                    className={styles.threadItem}
                    onClick={() => handleThreadClick(thread.id)}
                  >
                    <div className={styles.threadInfo}>
                      <div className={styles.threadTitleRow}>
                        <span className={styles.threadTypeIcon}>🔍</span>
                        <h3 className={styles.threadTitle}>
                          {thread.title || 'Untitled Conversation'}
                        </h3>
                      </div>
                      <span className={styles.threadDate}>
                        {formatDate(thread.updated_at || thread.created_at)}
                      </span>
                    </div>
                    <div className={styles.threadActions}>
                      <button 
                        className={styles.deleteBtn}
                        onClick={(e) => handleDelete(e, thread.id)}
                        title="Delete conversation"
                      >
                        🗑️
                      </button>
                      <span className={styles.arrow}>›</span>
                    </div>
                  </div>
                ))}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button
                    onClick={() => fetchThreads(currentPage - 1)}
                    disabled={currentPage === 1 || loading}
                    className={styles.pageBtn}
                  >
                    ← Prev
                  </button>
                  <span className={styles.pageInfo}>
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    onClick={() => fetchThreads(currentPage + 1)}
                    disabled={currentPage === totalPages || loading}
                    className={styles.pageBtn}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
