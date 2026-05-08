
export type WorkspaceTab = 'workspace' | 'revise' | 'draft' | 'research' | 'memo' | 'playbook' | 'knowledge';
export type ViewMode = 'redline' | 'clean';
export type ReviseScope = 'selection' | 'document';
export type DraftMode = 'clause' | 'agreement';
export type ResultsView = 'draft' | null;

export type EditorLayout = 'scroll' | 'page';
export type PageSize = 'a4' | 'letter' | 'legal';

export interface PageSettings {
  layout: EditorLayout;
  pageSize: PageSize;
  zoom: number; // percentage: 50, 75, 100, 125, 150
  showPageNumbers: boolean;
  showHeaders: boolean;
  headerText: string;
  footerText: string;
}

export const PAGE_DIMENSIONS: Record<PageSize, { width: number; height: number; name: string }> = {
  a4: { width: 210, height: 297, name: 'A4' },
  letter: { width: 216, height: 279, name: 'Letter' },
  legal: { width: 216, height: 356, name: 'Legal' },
};

export interface ConfirmModalState {
  open: boolean;
  message: string;
  onConfirm: () => void;
}

export interface SelectionRange {
  from: number;
  to: number;
}

export interface RedlineSuggestion {
  original: string;
  suggested: string;
  clause_ref?: string;
}
