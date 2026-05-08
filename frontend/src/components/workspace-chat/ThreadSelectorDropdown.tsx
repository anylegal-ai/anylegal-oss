'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useThreadList, type ThreadListItem } from './useThreadList';
import styles from './workspace-chat.module.css';

interface ThreadSelectorDropdownProps {
  currentTitle: string;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
  onInfoClick?: () => void;
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
    }).format(date);
  } catch {
    return '';
  }
}

export default function ThreadSelectorDropdown({
  currentTitle,
  onSelectThread,
  onNewThread,
  onInfoClick,
}: ThreadSelectorDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { threads, loading, fetchThreads, deleteThread } = useThreadList();
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      fetchThreads();
    }
  }, [isOpen, fetchThreads]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKey);
      return () => document.removeEventListener('keydown', handleKey);
    }
  }, [isOpen]);

  const handleDelete = async (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();
    await deleteThread(threadId);
  };

  return (
    <div className={styles.threadSelector} ref={wrapperRef}>
      <button
        className={styles.threadSelectorTrigger}
        onClick={() => setIsOpen(!isOpen)}
        title="Switch thread"
      >
        <span className={styles.threadSelectorTitle}>{currentTitle}</span>
        <svg
          className={`${styles.threadSelectorChevron} ${isOpen ? styles.threadSelectorChevronOpen : ''}`}
          width="12" height="12" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div className={styles.headerSpacer} />

      {onInfoClick && (
        <button
          className={styles.infoBtn}
          onClick={onInfoClick}
          title="Workspace guide"
          aria-label="Workspace guide"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4" />
            <path d="M12 8h.01" />
          </svg>
        </button>
      )}

      <button
        className={styles.newThreadBtn}
        onClick={() => { onNewThread(); setIsOpen(false); }}
        title="New thread"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {isOpen && (
        <div className={styles.threadDropdown}>
          {loading ? (
            <div className={styles.threadDropdownEmpty}>Loading...</div>
          ) : threads.length === 0 ? (
            <div className={styles.threadDropdownEmpty}>No previous threads</div>
          ) : (
            threads.map((thread: ThreadListItem) => (
              <div
                key={thread.id}
                className={styles.threadItem}
                role="button"
                tabIndex={0}
                onClick={() => {
                  onSelectThread(thread.id);
                  setIsOpen(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    onSelectThread(thread.id);
                    setIsOpen(false);
                  }
                }}
              >
                <span className={styles.threadItemTitle}>
                  {thread.title || 'Untitled'}
                </span>
                <span className={styles.threadItemDate}>
                  {formatDate(thread.updated_at || thread.created_at)}
                </span>
                <button
                  className={styles.threadItemDelete}
                  onClick={(e) => handleDelete(e, thread.id)}
                  title="Delete thread"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
