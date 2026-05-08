'use client';

import React, { useEffect, useRef } from 'react';
import styles from './workspace-info-modal.module.css';

interface WorkspaceInfoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CAPABILITIES = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    title: 'Upload & edit documents',
    desc: 'DOCX, XLSX, PPTX, PDF — upload, review, and edit with tracked changes.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
    title: 'Legal research',
    desc: 'Search across 80+ jurisdictions and the open web with sourced citations.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
      </svg>
    ),
    title: 'Draft contracts',
    desc: 'Generate documents shaped by your playbook and organizational context.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 3h5v5" />
        <line x1="21" y1="3" x2="14" y2="10" />
        <path d="M8 21H3v-5" />
        <line x1="3" y1="21" x2="10" y2="14" />
      </svg>
    ),
    title: 'Compare & redline',
    desc: 'Diff two documents side by side and generate DOCX with track changes.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
      </svg>
    ),
    title: 'Review & flag risks',
    desc: 'AI reviews your contract against your playbook, flags risks, and suggests edits.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    ),
    title: 'Run code & analyze data',
    desc: 'Execute Python in a sandbox to process spreadsheets and generate charts.',
  },
];

const COMMANDS = [
  { cmd: '/setup', label: 'Configure your workspace, role, and playbook' },
  { cmd: '/review', label: 'Review the open document against your playbook' },
  { cmd: '/research', label: 'Research a legal question with citations' },
  { cmd: '/compare', label: 'Compare two documents and generate a redline' },
  { cmd: '/draft', label: 'Draft a new contract from a template' },
];

export default function WorkspaceInfoModal({ isOpen, onClose }: WorkspaceInfoModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      className={styles.overlay}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className={styles.modal} role="dialog" aria-label="Workspace guide">
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
              </svg>
            </div>
            <h2 className={styles.title}>Workspace Guide</h2>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className={styles.body}>
          {/* Capabilities grid */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>What you can do</h3>
            <div className={styles.grid}>
              {CAPABILITIES.map((cap) => (
                <div key={cap.title} className={styles.card}>
                  <div className={styles.cardIcon}>{cap.icon}</div>
                  <div className={styles.cardText}>
                    <div className={styles.cardTitle}>{cap.title}</div>
                    <div className={styles.cardDesc}>{cap.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Slash commands */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Slash commands</h3>
            <p className={styles.sectionHint}>Type <kbd className={styles.kbd}>/</kbd> in the chat to see available commands</p>
            <div className={styles.commandList}>
              {COMMANDS.map((c) => (
                <div key={c.cmd} className={styles.commandRow}>
                  <code className={styles.commandCode}>{c.cmd}</code>
                  <span className={styles.commandLabel}>{c.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Tips */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Tips</h3>
            <ul className={styles.tipsList}>
              <li>Attach files using the paperclip icon in the chat input</li>
              <li>Set up a <strong>playbook</strong> to customize how the agent reviews your contracts</li>
              <li>Add <strong>folder-level instructions</strong> (click + on any folder) to give the AI context for all documents in that folder — instructions cascade into subfolders too</li>
              <li>All workspace data is encrypted at rest with AES-256</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
