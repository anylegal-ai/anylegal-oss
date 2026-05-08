import React from 'react';
import styles from './DocumentCard.module.css';

interface DocumentCardProps {
  document: {
    path: string;
    description: string;
    format: 'html' | 'docx';
    hasDocx: boolean;
    isSynced: boolean;
    modifiedAt: string;
    content?: string;
  };
  sessionId: string;
  onOpen: (documentPath: string, content?: string) => void;
  onExport?: (documentPath: string) => void;
  isActive?: boolean;
}

const DocxIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <polyline points="14,2 14,8 20,8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <text x="7" y="17" fontSize="6" fontWeight="bold" fill="currentColor">W</text>
  </svg>
);

const HtmlIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <polyline points="14,2 14,8 20,8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9 13l-2 2 2 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15 13l2 2-2 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const ExportIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <polyline points="7,10 12,15 17,10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function getFileName(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

export function DocumentCard({
  document,
  sessionId,
  onOpen,
  onExport,
  isActive = false,
}: DocumentCardProps) {
  const fileName = getFileName(document.path);
  const isDocx = document.format === 'docx' || document.hasDocx;

  const handleClick = () => {
    onOpen(document.path, document.content);
  };

  const handleExport = (e: React.MouseEvent) => {
    e.stopPropagation();
    onExport?.(document.path);
  };

  return (
    <div 
      className={`${styles.card} ${isActive ? styles.cardActive : ''}`}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && handleClick()}
    >
      {/* Format Icon */}
      <div className={`${styles.formatIcon} ${isDocx ? styles.docxIcon : styles.htmlIcon}`}>
        {isDocx ? <DocxIcon /> : <HtmlIcon />}
      </div>

      {/* Content */}
      <div className={styles.content}>
        <div className={styles.header}>
          <span className={styles.fileName}>{fileName}</span>
          {document.hasDocx && !document.isSynced && (
            <span className={styles.syncBadge} title="HTML and DOCX are out of sync">
              Out of sync
            </span>
          )}
          {document.hasDocx && document.isSynced && (
            <span className={styles.syncBadgeSynced} title="HTML and DOCX are synced">
              Synced
            </span>
          )}
        </div>

        {document.description && (
          <p className={styles.description}>{document.description}</p>
        )}

        <div className={styles.meta}>
          <span className={styles.format}>
            {isDocx ? 'DOCX' : 'HTML'}
          </span>
          <span className={styles.modified}>
            {formatRelativeTime(document.modifiedAt)}
          </span>
        </div>
      </div>

      {/* Actions */}
      {onExport && document.hasDocx && (
        <button 
          className={styles.exportBtn}
          onClick={handleExport}
          title="Export as DOCX"
        >
          <ExportIcon />
        </button>
      )}
    </div>
  );
}

export default DocumentCard;
