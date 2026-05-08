import React, { useState, useEffect } from 'react';
import styles from '../workspace.module.css';

interface FileUploadModalProps {
  open: boolean;
  fileName?: string;
  folders?: string[];
  defaultFolder?: string;
  onConfirm: (folderPath?: string) => void;
  onCancel: () => void;
}

type FileCategory = 'docx' | 'pdf' | 'image' | 'spreadsheet' | 'presentation' | 'other';

function detectFileCategory(fileName: string): FileCategory {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  if (ext === 'docx' || ext === 'doc') return 'docx';
  if (ext === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return 'image';
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'spreadsheet';
  if (['pptx', 'ppt'].includes(ext)) return 'presentation';
  return 'other';
}

const CATEGORY_CONFIG: Record<FileCategory, {
  gradient: string;
  iconColor: string;
  label: string;
  iconContent: React.ReactNode;
  features: { icon: React.ReactNode; text: React.ReactNode }[];
  buttonText: string;
}> = {
  docx: {
    gradient: 'linear-gradient(135deg, #2b579a 0%, #3b6fba 100%)',
    iconColor: '#fff',
    label: 'Word Document',
    iconContent: <text x="7" y="18" fontSize="8" fill="#fff" stroke="none" fontWeight="bold">W</text>,
    features: [
      { icon: <SparkleIcon color="#3b82f6" />, text: <>Edited by <strong>Anylegal.ai agent</strong> — original Word formatting preserved</> },
      { icon: <EyeIcon color="#3b82f6" />, text: 'Preview the document right here in the cloud editor' },
      { icon: <DownloadIcon color="#3b82f6" />, text: 'Download a redlined version anytime to continue in Microsoft Word' },
    ],
    buttonText: 'Open Preview',
  },
  pdf: {
    gradient: 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)',
    iconColor: '#fff',
    label: 'PDF Document',
    iconContent: <text x="5" y="18" fontSize="7" fill="#fff" stroke="none" fontWeight="bold">PDF</text>,
    features: [
      { icon: <EyeIcon color="#dc2626" />, text: 'The agent can read and reference this document' },
      { icon: <DownloadIcon color="#dc2626" />, text: 'Download the original file anytime' },
    ],
    buttonText: 'Upload File',
  },
  image: {
    gradient: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
    iconColor: '#fff',
    label: 'Image',
    iconContent: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
      </svg>
    ),
    features: [
      { icon: <EyeIcon color="#059669" />, text: 'View inline in the workspace' },
      { icon: <DownloadIcon color="#059669" />, text: 'Download the original file anytime' },
    ],
    buttonText: 'Upload File',
  },
  spreadsheet: {
    gradient: 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
    iconColor: '#fff',
    label: 'Spreadsheet',
    iconContent: <text x="7" y="18" fontSize="8" fill="#fff" stroke="none" fontWeight="bold">X</text>,
    features: [
      { icon: <DownloadIcon color="#16a34a" />, text: 'Stored in workspace — download anytime' },
    ],
    buttonText: 'Upload File',
  },
  presentation: {
    gradient: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
    iconColor: '#fff',
    label: 'Presentation',
    iconContent: <text x="7" y="18" fontSize="8" fill="#fff" stroke="none" fontWeight="bold">P</text>,
    features: [
      { icon: <DownloadIcon color="#d97706" />, text: 'Stored in workspace — download anytime' },
    ],
    buttonText: 'Upload File',
  },
  other: {
    gradient: 'linear-gradient(135deg, #6b7280 0%, #9ca3af 100%)',
    iconColor: '#fff',
    label: 'File',
    iconContent: null,
    features: [
      { icon: <DownloadIcon color="#6b7280" />, text: 'Stored in workspace — download anytime' },
    ],
    buttonText: 'Upload File',
  },
};

export function FileUploadModal({ open, fileName, folders, defaultFolder, onConfirm, onCancel }: FileUploadModalProps) {
  const [selectedFolder, setSelectedFolder] = useState(defaultFolder || '');

  useEffect(() => {
    if (defaultFolder !== undefined) setSelectedFolder(defaultFolder);
  }, [defaultFolder]);

  if (!open) return null;

  const category = detectFileCategory(fileName || '');
  const config = CATEGORY_CONFIG[category];

  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div
        className={styles.modalContent}
        onClick={e => e.stopPropagation()}
        style={{ maxWidth: 420, padding: '2rem' }}
      >
        {/* Hero area — file icon + file name */}
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          gap: 8, marginBottom: 20,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: config.gradient,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 4px 12px rgba(0, 0, 0, 0.15)`,
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke={config.iconColor} strokeWidth="1.5" />
              <polyline points="14 2 14 8 20 8" stroke={config.iconColor} strokeWidth="1.5" />
              {config.iconContent}
            </svg>
          </div>
          {fileName && (
            <span style={{
              fontSize: '0.82rem', color: '#64748b',
              maxWidth: '100%', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {fileName}
            </span>
          )}
        </div>

        {/* Feature list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 22 }}>
          {config.features.map((feat, i) => (
            <FeatureRow key={i} icon={feat.icon} text={feat.text} />
          ))}
        </div>

        {/* Folder selector (when folders available) */}
        {folders && folders.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginBottom: 4 }}>
              Upload to folder
            </label>
            <select
              value={selectedFolder}
              onChange={e => setSelectedFolder(e.target.value)}
              style={{
                width: '100%', padding: '6px 8px', fontSize: '0.82rem',
                border: '1px solid #d1d5db', borderRadius: 6,
                background: '#fff', color: '#1f2937',
              }}
            >
              <option value="">Workspace root</option>
              {folders.map(f => (
                <option key={f} value={f}>{f.replace(/\/$/, '')}</option>
              ))}
            </select>
          </div>
        )}

        {/* Single action */}
        <button
          className={styles.modalConfirmBtn}
          onClick={() => onConfirm(selectedFolder || undefined)}
          style={{
            width: '100%', padding: '0.65rem 1rem',
            fontSize: '0.9rem', borderRadius: 8,
          }}
        >
          {config.buttonText}
        </button>
      </div>
    </div>
  );
}

export const DocxUploadModal = FileUploadModal;

function FeatureRow({ icon, text }: { icon: React.ReactNode; text: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <span style={{
        flexShrink: 0, width: 22, height: 22, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        borderRadius: 6, background: '#f0f5ff', marginTop: 1,
      }}>
        {icon}
      </span>
      <span style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.45 }}>
        {text}
      </span>
    </div>
  );
}

function SparkleIcon({ color = '#3b82f6' }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
    </svg>
  );
}

function EyeIcon({ color = '#3b82f6' }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function DownloadIcon({ color = '#3b82f6' }: { color?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}
