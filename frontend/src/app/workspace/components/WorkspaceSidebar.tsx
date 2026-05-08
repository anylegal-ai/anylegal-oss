import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
} from '@dnd-kit/core';
import { useOrganization } from '@/contexts/OrganizationContext';
import type { WorkspaceTab } from '../types/workspace';
import styles from '../workspace.module.css';

const MAX_INDENT_DEPTH = 5;
const treeIndent = (depth: number) => `${8 + Math.min(depth, MAX_INDENT_DEPTH) * 14}px`;

interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  editable?: boolean;
  format?: string;
  has_content?: boolean;
  has_docx?: boolean;
  has_binary?: boolean;
  is_active?: boolean;
  is_anylegal?: boolean;
  has_anylegal?: boolean;
  no_instructions?: boolean;
  mime_type?: string;
  modified_at?: string;
  readonly?: boolean;
  collapsed?: boolean;
  children?: TreeNode[];
  count?: number;
}

interface WorkspaceSidebarProps {
  activeTab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
  hasDocument?: boolean;
  onLogoClick?: () => void;
  onNeedDocument?: (targetTab: WorkspaceTab) => void;
  onOpenSessions?: () => void;
  onFileSelect?: (path: string, format?: string) => void;
  onUploadToFolder?: (folderPath: string) => void;
  onDeleteFile?: (filePath: string) => void;
  onConfirmAction?: (message: string, onConfirm: () => void) => void;
  onUploadClick?: () => void;
  sessionId?: string;
  refreshTrigger?: number;
  mobileDrawerOpen?: boolean;
  onToggleMobileDrawer?: () => void;
  onOpenModelSelector?: () => void;
  onSignOut?: () => void;
  isAuthenticated?: boolean;
}

const ANYLEGAL_NAMES = new Set(['anylegal.md', 'agents.md']);

function getFileTypeBadge(node: TreeNode) {
  if (node.has_docx) return <span className={styles.treeBadgeDocx}>DOCX</span>;
  if (node.mime_type?.includes('pdf')) return <span className={styles.treeBadgePdf}>PDF</span>;
  if (node.mime_type?.includes('presentation')) return <span className={styles.treeBadgePptx}>PPTX</span>;
  if (node.mime_type?.includes('spreadsheet')) return <span className={styles.treeBadgeXlsx}>XLSX</span>;
  if (node.mime_type?.includes('markdown')) return <span className={styles.treeBadgeMd}>MD</span>;
  if (node.has_binary && node.mime_type) {
    const ext = node.mime_type.split('/')[1]?.toUpperCase() || 'BIN';
    return <span className={styles.treeBadgeBinary}>{ext}</span>;
  }
  return null;
}

function getFileIcon(node: TreeNode) {
  const isAnylegal = ANYLEGAL_NAMES.has(node.name) || node.is_anylegal;
  const isReadonly = node.readonly || node.path.startsWith('Skills/');

  if (isAnylegal) {
    return <span className={styles.treeAnylegalIcon}>✦</span>;
  }
  if (isReadonly) {
    return <span className={styles.treeReadonlyIcon}>🔒</span>;
  }
  if (node.has_docx) {
    return (
      <svg className={styles.treeFileIconDocx} width="14" height="14" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#2b579a"/><polyline points="14 2 14 8 20 8" stroke="#2b579a"/>
        <text x="7" y="18" fontSize="8" fill="#2b579a" stroke="none" fontWeight="bold">W</text>
      </svg>
    );
  }
  if (node.mime_type?.includes('pdf')) {
    return (
      <svg className={styles.treeFileIconPdf} width="14" height="14" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#dc2626"/><polyline points="14 2 14 8 20 8" stroke="#dc2626"/>
        <text x="5" y="18" fontSize="7" fill="#dc2626" stroke="none" fontWeight="bold">PDF</text>
      </svg>
    );
  }
  if (node.mime_type?.includes('presentation')) {
    return (
      <svg className={styles.treeFileIconPptx} width="14" height="14" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#d24726"/><polyline points="14 2 14 8 20 8" stroke="#d24726"/>
        <text x="7" y="18" fontSize="8" fill="#d24726" stroke="none" fontWeight="bold">P</text>
      </svg>
    );
  }
  if (node.mime_type?.includes('spreadsheet')) {
    return (
      <svg className={styles.treeFileIconXlsx} width="14" height="14" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#217346"/><polyline points="14 2 14 8 20 8" stroke="#217346"/>
        <text x="7" y="18" fontSize="8" fill="#217346" stroke="none" fontWeight="bold">X</text>
      </svg>
    );
  }
  if (node.mime_type?.startsWith('image/')) {
    return (
      <svg className={styles.treeFileIconImage} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
      </svg>
    );
  }
  if (node.mime_type?.includes('markdown')) {
    return (
      <svg className={styles.treeFileIconMd} width="14" height="14" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#475569"/><polyline points="14 2 14 8 20 8" stroke="#475569"/>
        <text x="5" y="18" fontSize="7" fill="#475569" stroke="none" fontWeight="bold">MD</text>
      </svg>
    );
  }
  return (
    <svg className={styles.treeFileIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
    </svg>
  );
}

function getHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}

function getBaseUrl() {
  return process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:8000';
}

async function apiCreateFolder(folderPath: string) {
  const res = await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/folders`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ folder_path: folderPath }),
  });
  return res.ok;
}

async function apiDeleteFolder(folderPath: string) {
  const res = await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/folders`, {
    method: 'DELETE',
    headers: getHeaders(),
    body: JSON.stringify({ folder_path: folderPath }),
  });
  return res.ok;
}

async function apiMoveItem(oldPath: string, newPath: string) {
  const res = await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/move`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
  });
  return res.ok;
}

async function apiSaveFile(path: string, content: string) {
  const res = await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/file`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify({ path, content }),
  });
  return res.ok;
}

function DraggableFileItem({
  node,
  depth = 0,
  onSelect,
  onDelete,
  activePath,
}: {
  node: TreeNode;
  depth?: number;
  onSelect: (path: string, format?: string) => void;
  onDelete?: (filePath: string) => void;
  activePath?: string;
}) {
  const isAnylegal = ANYLEGAL_NAMES.has(node.name) || node.is_anylegal;
  const isReadonly = node.readonly || node.path.startsWith('Skills/');
  const isDraggable = !isAnylegal && !isReadonly;

  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `file:${node.path}`,
    data: { type: 'file', path: node.path, node },
    disabled: !isDraggable,
  });

  const isActive = activePath === node.path;

  return (
    <div
      className={`${styles.treeFileRow} ${isDragging ? styles.treeDragging : ''}`}
      ref={setNodeRef}
      {...(isDraggable ? { ...attributes, ...listeners } : {})}
    >
      <button
        className={`${styles.treeFile} ${isActive ? styles.treeFileActive : ''} ${isAnylegal ? styles.treeFileAnylegal : ''}`}
        onClick={() => onSelect(node.path, node.format)}
        style={{ paddingLeft: treeIndent(depth) }}
        title={isAnylegal ? 'Instructions — the agent reads these automatically' : node.path}
      >
        {getFileIcon(node)}
        <span className={styles.treeFileName}>{node.name}</span>
        {getFileTypeBadge(node)}
      </button>
      {onDelete && !isReadonly && !isAnylegal && (
        <button
          className={styles.treeActionBtn}
          onClick={(e) => { e.stopPropagation(); onDelete(node.path); }}
          title={`Remove ${node.name}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      )}
    </div>
  );
}

function FolderContextMenu({
  x,
  y,
  node,
  onClose,
  onRename,
  onDelete,
  onAddInstructions,
  onCreateSubfolder,
  onUpload,
  onCreatePlaybook,
}: {
  x: number;
  y: number;
  node: TreeNode;
  onClose: () => void;
  onRename?: () => void;
  onDelete?: () => void;
  onAddInstructions: () => void;
  onCreateSubfolder: () => void;
  onUpload: () => void;
  onCreatePlaybook?: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [onClose]);

  const isPlaybookFolder = node.path === 'Playbook/';

  const items = [
    ...(onCreatePlaybook && isPlaybookFolder ? [{ label: 'New playbook', action: onCreatePlaybook }] : []),
    { label: 'New subfolder', action: onCreateSubfolder },
    ...(!node.no_instructions ? (node.has_anylegal ? [{ label: 'Edit instructions', action: onAddInstructions }] : [{ label: 'Add instructions', action: onAddInstructions }]) : []),
    ...(!isPlaybookFolder ? [{ label: 'Upload file here', action: onUpload }] : []),
    ...(onRename ? [{ label: 'Rename', action: onRename }] : []),
    ...(onDelete ? [{ label: 'Delete', action: onDelete }] : []),
  ];

  return (
    <div
      ref={menuRef}
      className={styles.treeContextMenu}
      style={{ top: y, left: x }}
    >
      {items.map((item) => (
        <button
          key={item.label}
          className={styles.treeContextMenuItem}
          onClick={() => { item.action(); onClose(); }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function DroppableFolderItem({
  node,
  depth = 0,
  onSelect,
  onAdd,
  onDelete,
  onDeleteFolder,
  onAddInstructions,
  onCreateSubfolder,
  onRenameFolder,
  onCreatePlaybook,
  showNewPlaybookInput,
  onConfirmNewPlaybook,
  onCancelNewPlaybook,
  activePath,
  sessionId,
}: {
  node: TreeNode;
  depth?: number;
  onSelect: (path: string, format?: string) => void;
  onAdd?: (folderPath: string) => void;
  onDelete?: (filePath: string) => void;
  onDeleteFolder?: (folderPath: string) => void;
  onAddInstructions?: (folderPath: string) => void;
  onCreateSubfolder?: (parentPath: string) => void;
  onRenameFolder?: (folderPath: string, newName: string) => void;
  onCreatePlaybook?: () => void;
  showNewPlaybookInput?: boolean;
  onConfirmNewPlaybook?: (name: string) => void;
  onCancelNewPlaybook?: () => void;
  activePath?: string;
  sessionId?: string;
}) {
  const [expanded, setExpanded] = useState(
    node.collapsed ? false : ((node.count ?? 0) > 0 || depth === 0)
  );
  const [isHovered, setIsHovered] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(node.name);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const isReadonly = node.readonly || node.path.startsWith('Skills/');
  const isPlaybookFolder = node.path === 'Playbook/';
  const isSystemFolder = isPlaybookFolder || node.path === 'Templates/' || node.path.startsWith('Skills/');
  const isDraggable = !isReadonly && !isSystemFolder;
  const expandTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renameRef = useRef<HTMLInputElement>(null);

  const { isOver, setNodeRef: setDropRef } = useDroppable({
    id: `folder:${node.path}`,
    data: { type: 'folder', path: node.path },
    disabled: isReadonly,
  });

  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: `folder:${node.path}`,
    data: { type: 'folder', path: node.path, node },
    disabled: !isDraggable,
  });

  const combinedRef = useCallback((el: HTMLDivElement | null) => {
    setDropRef(el);
    setDragRef(el);
  }, [setDropRef, setDragRef]);

  useEffect(() => {
    if (isOver && !expanded) {
      expandTimerRef.current = setTimeout(() => setExpanded(true), 500);
    }
    return () => {
      if (expandTimerRef.current) clearTimeout(expandTimerRef.current);
    };
  }, [isOver, expanded]);

  useEffect(() => {
    if (isPlaybookFolder && showNewPlaybookInput && !expanded) {
      setExpanded(true);
    }
  }, [isPlaybookFolder, showNewPlaybookInput, expanded]);

  useEffect(() => {
    if (isRenaming) renameRef.current?.focus();
  }, [isRenaming]);

  const handleContextMenu = (e: React.MouseEvent) => {
    if (isReadonly) return;
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  const handleRenameSubmit = () => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== node.name && !trimmed.includes('/') && !trimmed.includes('..')) {
      onRenameFolder?.(node.path, trimmed);
    }
    setIsRenaming(false);
  };

  return (
    <div ref={combinedRef} {...(isDraggable ? { ...attributes, ...listeners } : {})}>
      <div
        className={`${styles.treeFileRow} ${isHovered ? styles.treeRowHovered : ''} ${isOver && !isDragging ? styles.treeDropZone : ''} ${isDragging ? styles.treeDragging : ''}`}
        onContextMenu={handleContextMenu}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <button
          className={styles.treeFolder}
          onClick={() => setExpanded(!expanded)}
          style={{ paddingLeft: treeIndent(depth) }}
        >
          <svg className={styles.treeFolderSvg} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {expanded
              ? <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v1M2 10h20"/>
              : <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            }
          </svg>
          {isRenaming ? (
            <input
              ref={renameRef}
              className={styles.treeInlineInput}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameSubmit();
                if (e.key === 'Escape') setIsRenaming(false);
                e.stopPropagation();
              }}
              onBlur={handleRenameSubmit}
              onClick={(e) => e.stopPropagation()}
              style={{ width: '100%', maxWidth: 120 }}
            />
          ) : (
            <span className={styles.treeFolderName}>{node.name}</span>
          )}
        </button>
        {/* Right-side overlay: count + star (always) + action buttons (hover) */}
        <div className={styles.treeRowActions}>
          {/* Star — always visible, opens folder instructions */}
          {!isRenaming && node.has_anylegal && !node.no_instructions && (
            <button
              className={styles.treeStarBtn}
              title="Edit instructions"
              onClick={(e) => {
                e.stopPropagation();
                const anylegalPath = `${node.path.replace(/\/$/, '')}/anylegal.md`;
                onSelect(anylegalPath, 'markdown');
              }}
            >✦</button>
          )}
          {/* Count badge — inside overlay so it doesn't overlap with star */}
          {!isRenaming && (node.count ?? 0) > 0 && (
            <span className={styles.treeCount}>{node.count}</span>
          )}
          {/* Add instructions affordance */}
          {!isReadonly && onAddInstructions && !node.has_anylegal && !node.no_instructions && (
            <button
              className={styles.treeAddInstructions}
              onClick={(e) => { e.stopPropagation(); onAddInstructions(node.path); }}
              title="Add instructions to this folder"
            >
              + instructions
            </button>
          )}
          {/* New subfolder (hidden for Playbook — use "New playbook" instead) */}
          {!isReadonly && !isPlaybookFolder && onCreateSubfolder && (
            <button
              className={styles.treeActionBtn}
              onClick={(e) => { e.stopPropagation(); onCreateSubfolder(node.path); }}
              title={`New subfolder in ${node.name}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
          )}
          {/* New playbook (Playbook folder only — replaces upload) */}
          {isPlaybookFolder && onCreatePlaybook && (
            <button
              className={styles.treeActionBtn}
              onClick={(e) => { e.stopPropagation(); onCreatePlaybook(); }}
              title="New playbook"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
          )}
          {/* Upload to folder (hidden for Playbook — markdown-only via "New playbook") */}
          {onAdd && !isReadonly && !isPlaybookFolder && (
            <button
              className={styles.treeActionBtn}
              onClick={(e) => { e.stopPropagation(); onAdd(node.path); }}
              title={`Upload to ${node.name}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </button>
          )}
          {/* Delete folder (hidden for system folders: Playbook, Templates, Skills) */}
          {onDeleteFolder && !isReadonly && !isSystemFolder && (
            <button
              className={styles.treeActionBtn}
              onClick={(e) => { e.stopPropagation(); onDeleteFolder(node.path); }}
              title={`Delete ${node.name}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          )}
        </div>
      </div>
      {/* Context menu */}
      {contextMenu && (
        <FolderContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          node={node}
          onClose={() => setContextMenu(null)}
          onRename={isSystemFolder ? undefined : () => { setIsRenaming(true); setRenameValue(node.name); }}
          onDelete={isSystemFolder ? undefined : () => onDeleteFolder?.(node.path)}
          onAddInstructions={() => onAddInstructions?.(node.path)}
          onCreateSubfolder={() => onCreateSubfolder?.(node.path)}
          onUpload={() => onAdd?.(node.path)}
          onCreatePlaybook={onCreatePlaybook}
        />
      )}
      {expanded && node.children && (
        <div>
          {node.children.length > 0 ? (
            node.children.map((child) => (
              child.type === 'folder' ? (
                <DroppableFolderItem
                  key={child.path}
                  node={child}
                  depth={depth + 1}
                  onSelect={onSelect}
                  onAdd={onAdd}
                  onDelete={onDelete}
                  onDeleteFolder={onDeleteFolder}
                  onAddInstructions={onAddInstructions}
                  onCreateSubfolder={onCreateSubfolder}
                  onRenameFolder={onRenameFolder}
                  onCreatePlaybook={onCreatePlaybook}
                  showNewPlaybookInput={showNewPlaybookInput}
                  onConfirmNewPlaybook={onConfirmNewPlaybook}
                  onCancelNewPlaybook={onCancelNewPlaybook}
                  activePath={activePath}
                  sessionId={sessionId}
                />
              ) : (
                <DraggableFileItem key={child.path} node={child} depth={depth + 1} onSelect={onSelect} onDelete={onDelete} activePath={activePath} />
              )
            ))
          ) : !showNewPlaybookInput ? (
            <div className={styles.treeEmpty} style={{ paddingLeft: treeIndent(depth + 1) }}>
              <span className={styles.treeEmptyText}>No files yet</span>
            </div>
          ) : null}
          {/* Inline input for new playbook file */}
          {isPlaybookFolder && showNewPlaybookInput && onConfirmNewPlaybook && (
            <InlinePlaybookInput
              depth={depth + 1}
              onConfirm={onConfirmNewPlaybook}
              onCancel={() => onCancelNewPlaybook?.()}
            />
          )}
        </div>
      )}
    </div>
  );
}

function InlinePlaybookInput({
  depth,
  onConfirm,
  onCancel,
}: {
  depth: number;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  const submit = () => {
    const trimmed = value.trim();
    if (trimmed && !trimmed.includes('/') && !trimmed.includes('..')) {
      onConfirm(trimmed);
    } else {
      onCancel();
    }
  };

  return (
    <div style={{ paddingLeft: treeIndent(depth), paddingRight: 8, paddingTop: 2, paddingBottom: 2 }}>
      <input
        ref={ref}
        className={styles.treeInlineInput}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submit();
          if (e.key === 'Escape') onCancel();
        }}
        onBlur={submit}
        placeholder="Playbook name..."
        style={{ width: '100%' }}
      />
    </div>
  );
}

function InlineFolderInput({
  parentPath,
  depth,
  onConfirm,
  onCancel,
}: {
  parentPath: string;
  depth: number;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  const submit = () => {
    const trimmed = value.trim();
    if (trimmed && !trimmed.includes('/') && !trimmed.includes('..')) {
      onConfirm(trimmed);
    } else {
      onCancel();
    }
  };

  return (
    <div style={{ paddingLeft: treeIndent(depth), paddingRight: 8, paddingTop: 2, paddingBottom: 2 }}>
      <input
        ref={ref}
        className={styles.treeInlineInput}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submit();
          if (e.key === 'Escape') onCancel();
        }}
        onBlur={submit}
        placeholder="Folder name..."
      />
    </div>
  );
}

function MemoryNavButton({
  active,
  onClick,
}: {
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={active ? styles.knowledgeNavButtonActive : styles.knowledgeNavButton}
      onClick={onClick}
      title="Memory — what the AI knows about your workspace"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
      </svg>
      <span>Memory</span>
    </button>
  );
}

export function WorkspaceSidebar({
  activeTab,
  onTabChange,
  hasDocument,
  onLogoClick,
  onOpenSessions,
  onFileSelect,
  onUploadToFolder,
  onDeleteFile,
  onConfirmAction,
  onUploadClick,
  sessionId,
  refreshTrigger = 0,
  mobileDrawerOpen,
  onToggleMobileDrawer,
  onOpenModelSelector,
  onSignOut,
  isAuthenticated,
}: WorkspaceSidebarProps) {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const { organization, isOrgUser } = useOrganization();
  const [activePath, setActivePath] = useState<string>('');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [newFolderParent, setNewFolderParent] = useState<string | null>(null);
  const [showNewPlaybookInput, setShowNewPlaybookInput] = useState(false);
  const [treeVersion, setTreeVersion] = useState(0);

  const storageKey = 'anylegal_sidebar_workspace';
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(storageKey);
      if (stored !== null) return stored === 'true';
    }
    return false; // expanded by default
  });

  const toggleCollapse = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev;
      localStorage.setItem(storageKey, String(next));
      return next;
    });
  }, []);

  const widthStorageKey = 'anylegal_sidebar_width';
  const MIN_WIDTH = 160;
  const MAX_WIDTH = 480;
  const DEFAULT_WIDTH = 200;
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(widthStorageKey);
      if (stored !== null) {
        const w = parseInt(stored, 10);
        if (!isNaN(w) && w >= MIN_WIDTH && w <= MAX_WIDTH) return w;
      }
    }
    return DEFAULT_WIDTH;
  });
  const isResizing = useRef(false);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (ev: MouseEvent) => {
      if (!isResizing.current) return;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, ev.clientX));
      setSidebarWidth(newWidth);
    };

    const onMouseUp = () => {
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      setSidebarWidth(w => {
        localStorage.setItem(widthStorageKey, String(w));
        return w;
      });
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, []);

  const fetchTree = useCallback(async () => {
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const baseUrl = getBaseUrl();
      const res = await fetch(`${baseUrl}/api/v1/editor/chat/agentic/workspace/tree`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setTree(data.tree || []);
      } else {
        setTree([]);
      }
    } catch {
      setTree([]);
    }
  }, [refreshTrigger, treeVersion]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  const prevDrawerOpenRef = useRef(mobileDrawerOpen);
  useEffect(() => {
    if (mobileDrawerOpen && !prevDrawerOpenRef.current) {
      fetchTree();
    }
    prevDrawerOpenRef.current = mobileDrawerOpen;
  }, [mobileDrawerOpen, fetchTree]);

  const refreshTree = useCallback(() => {
    setTreeVersion(v => v + 1);
  }, []);

  const handleFileSelect = useCallback((path: string, format?: string) => {
    setActivePath(path);
    onFileSelect?.(path, format);
  }, [onFileSelect]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setDraggingId(event.active.id as string);
  }, []);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setDraggingId(null);
    const { active, over } = event;
    if (!over) return;

    const activeData = active.data.current;
    const overData = over.data.current;

    if (!activeData || !overData || overData.type !== 'folder') return;

    const itemPath = activeData.path as string;
    const targetFolder = overData.path as string;
    const isFolder = itemPath.endsWith('/');

    if (isFolder && targetFolder.startsWith(itemPath)) return;

    let newPath: string;
    if (isFolder) {
      const folderName = itemPath.replace(/\/$/, '').split('/').pop() || '';
      newPath = targetFolder + folderName + '/';
    } else {
      const fileName = itemPath.split('/').pop() || '';
      newPath = targetFolder + fileName;
    }

    if (itemPath === newPath) return;

    const ok = await apiMoveItem(itemPath, newPath);
    if (ok) refreshTree();
  }, [refreshTree]);

  const handleCreateFolder = useCallback(async (parentPath: string, name: string) => {
    const folderPath = parentPath ? `${parentPath.replace(/\/$/, '')}/${name}/` : `${name}/`;
    const ok = await apiCreateFolder(folderPath);
    if (ok) refreshTree();
    setNewFolderParent(null);
  }, [refreshTree]);

  const handleDeleteFolder = useCallback(async (folderPath: string) => {
    const folderName = folderPath.replace(/\/$/, '').split('/').pop() || folderPath;
    const doDelete = async () => {
      const ok = await apiDeleteFolder(folderPath);
      if (ok) refreshTree();
    };
    if (onConfirmAction) {
      onConfirmAction(`Delete "${folderName}" and all its contents?`, doDelete);
    } else {
      doDelete();
    }
  }, [refreshTree, onConfirmAction]);

  const handleAddInstructions = useCallback(async (folderPath: string) => {
    const anylegalPath = `${folderPath.replace(/\/$/, '')}/anylegal.md`;
    const ok = await apiSaveFile(anylegalPath, '');
    if (ok) {
      refreshTree();
      handleFileSelect(anylegalPath, 'markdown');
    }
  }, [refreshTree, handleFileSelect]);

  const handleRenameFolder = useCallback(async (folderPath: string, newName: string) => {
    const parts = folderPath.replace(/\/$/, '').split('/');
    parts[parts.length - 1] = newName;
    const newPath = parts.join('/') + '/';
    const ok = await apiMoveItem(folderPath, newPath);
    if (ok) refreshTree();
  }, [refreshTree]);

  const handleCreateSubfolder = useCallback((parentPath: string) => {
    setNewFolderParent(parentPath);
  }, []);

  const handleCreatePlaybook = useCallback(() => {
    setShowNewPlaybookInput(true);
  }, []);

  const handleConfirmNewPlaybook = useCallback(async (name: string) => {
    setShowNewPlaybookInput(false);
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const filePath = `Playbook/${slug}.md`;
    const template = [
      `# ${name}`,
      '',
      `Describe what this playbook covers (e.g. "Standard positions for SaaS vendor agreements").`,
      'The AI agent reads this before reviewing or drafting matching contracts.',
      '',
      '## Indemnification',
      '',
      '- **Our position**: What you ideally want',
      '- **Red line**: What you will not accept',
      '- **Acceptable**: What you can live with',
      '',
      '## [Add More Clauses]',
      '',
      '- **Our position**: ',
      '- **Red line**: ',
      '- **Acceptable**: ',
      '',
      '---',
      '',
      '*Edit the sections above to match your needs. Add or remove clauses as needed.*',
    ].join('\n');
    const ok = await apiSaveFile(filePath, template);
    if (ok) {
      refreshTree();
      handleFileSelect(filePath, 'markdown');
    }
  }, [refreshTree, handleFileSelect]);

  const handleNewRootFolder = useCallback(() => {
    setNewFolderParent('');
  }, []);

  const hasTreeItems = tree.length > 0;

  return (
    <>
    {/* Mobile drawer backdrop */}
    {mobileDrawerOpen && (
      <div className={styles.mobileDrawerBackdrop} onClick={onToggleMobileDrawer} />
    )}
    <aside
      className={`${styles.modeSidebar} ${collapsed ? styles.sidebarCollapsed : ''} ${mobileDrawerOpen ? styles.mobileDrawerOpen : ''}`}
      style={!collapsed ? { width: sidebarWidth } : undefined}
    >
      {/* Header: Logo + collapse toggle */}
      <div className={styles.sidebarHeader}>
        {/* Mobile hamburger — visible only on mobile via CSS */}
        <button
          className={styles.mobileHamburger}
          onClick={onToggleMobileDrawer}
          title={mobileDrawerOpen ? 'Close menu' : 'Open menu'}
        >
          {mobileDrawerOpen ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          )}
        </button>
        {(!collapsed || mobileDrawerOpen) && (
          <button className={styles.sidebarLogo} onClick={onLogoClick} title="Back to workspace home">
            <span className={styles.sidebarLogoText}>
              ANYLEGAL<span className={styles.sidebarLogoAi}>.ai</span>
            </span>
          </button>
        )}
        <button
          className={styles.sidebarToggleBtn}
          onClick={toggleCollapse}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <svg width="16" height="16" viewBox="0 0 16 16">
            <rect x="1" y="1" width="14" height="14" rx="2" fill="none" stroke="#6b7280" strokeWidth="1.5" />
            <line x1="6" y1="1" x2="6" y2="15" stroke="#6b7280" strokeWidth="1.5" />
            <rect x="1" y="1" width="5" height="14" rx="2" fill="#6b7280" fillOpacity="0.3" />
          </svg>
        </button>
      </div>

      {/* Unified file tree — workspace session files with DnD */}
      {(!collapsed || mobileDrawerOpen) && hasTreeItems && (
        <DndContext
          sensors={sensors}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <div className={styles.modeList}>
            {tree.map((node) => (
              node.type === 'folder' ? (
                <DroppableFolderItem
                  key={node.path}
                  node={node}
                  onSelect={handleFileSelect}
                  onAdd={onUploadToFolder}
                  onDelete={onDeleteFile}
                  onDeleteFolder={handleDeleteFolder}
                  onAddInstructions={handleAddInstructions}
                  onCreateSubfolder={handleCreateSubfolder}
                  onRenameFolder={handleRenameFolder}
                  onCreatePlaybook={handleCreatePlaybook}
                  showNewPlaybookInput={showNewPlaybookInput}
                  onConfirmNewPlaybook={handleConfirmNewPlaybook}
                  onCancelNewPlaybook={() => setShowNewPlaybookInput(false)}
                  activePath={activePath}
                  sessionId={sessionId}
                />
              ) : (
                <DraggableFileItem key={node.path} node={node} onSelect={handleFileSelect} onDelete={onDeleteFile} activePath={activePath} />
              )
            ))}
            {/* Inline input for new root-level subfolder */}
            {newFolderParent !== null && newFolderParent === '' && (
              <InlineFolderInput
                parentPath=""
                depth={0}
                onConfirm={(name) => handleCreateFolder('', name)}
                onCancel={() => setNewFolderParent(null)}
              />
            )}
            {/* Inline input for subfolder (rendered after the parent expands) */}
            {newFolderParent !== null && newFolderParent !== '' && (
              <InlineFolderInput
                parentPath={newFolderParent}
                depth={(newFolderParent.split('/').filter(Boolean).length)}
                onConfirm={(name) => handleCreateFolder(newFolderParent, name)}
                onCancel={() => setNewFolderParent(null)}
              />
            )}
            {/* Memory — rendered as the last "system folder" entry in the tree
                so it's visually inline with Playbook / Templates / Skills.
                Click navigates to the Memory tab; the underlying surface is
                AnyLegal's wiki of the workspace. */}
            <MemoryNavButton
              active={activeTab === 'knowledge'}
              onClick={() => onTabChange('knowledge')}
            />
          </div>
          <DragOverlay>
            {draggingId ? (
              <div style={{ padding: '4px 10px', background: '#fff', borderRadius: 4, boxShadow: '0 2px 8px rgba(0,0,0,0.12)', fontSize: '0.73rem', color: '#374151', display: 'flex', alignItems: 'center', gap: 4 }}>
                {draggingId.startsWith('folder:') && (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                  </svg>
                )}
                {draggingId.replace(/^(file|folder):/, '').replace(/\/$/, '').split('/').pop()}
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {/* Empty state */}
      {(!collapsed || mobileDrawerOpen) && !hasTreeItems && (
        <div className={styles.sidebarEmptyState}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          <span>Upload or draft a document to get started</span>
        </div>
      )}

      {/* Collapsed: show folder icon strip (not in mobile drawer) */}
      {collapsed && !mobileDrawerOpen && (
        <div className={styles.sidebarCollapsedIcons}>
          <button className={styles.sidebarCollapsedIcon} onClick={toggleCollapse} title="Documents">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
          </button>
        </div>
      )}

      <div className={styles.sidebarSpacer} />

      {/* Bottom actions: upload + new folder */}
      {(!collapsed || mobileDrawerOpen) && (
        <div className={styles.sidebarBottomRow}>
          {onUploadClick && (
            <button
              className={styles.sidebarBottomBtn}
              onClick={onUploadClick}
              title="Upload file"
            >
              <span className={styles.modeIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </span>
              <span className={styles.modeLabel}>Upload</span>
            </button>
          )}
          <button
            className={styles.sidebarBottomBtn}
            onClick={handleNewRootFolder}
            title="New folder"
          >
            <span className={styles.modeIcon}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
              </svg>
            </span>
            <span className={styles.modeLabel}>New folder</span>
          </button>
        </div>
      )}
      {/* Mobile drawer actions — only rendered when drawer is open (avoids CSS specificity issues) */}
      {mobileDrawerOpen && (
        <div className={styles.mobileDrawerActions}>
          {onOpenModelSelector && (
            <button className={styles.mobileDrawerBtn} onClick={onOpenModelSelector}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
              </svg>
              <span>AI Model</span>
            </button>
          )}
          {onSignOut && (
            <button className={styles.mobileDrawerBtn} onClick={onSignOut}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              <span>Sign Out</span>
            </button>
          )}
        </div>
      )}
      {/* Resize handle */}
      {!collapsed && !mobileDrawerOpen && (
        <div
          className={styles.sidebarResizeHandle}
          onMouseDown={handleResizeMouseDown}
        />
      )}
    </aside>
    </>
  );
}
