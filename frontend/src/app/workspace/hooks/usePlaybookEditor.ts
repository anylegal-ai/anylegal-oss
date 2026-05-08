
import { useState, useCallback, useEffect } from 'react';
import { useEditor, Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { markdownToHtmlAsync, htmlToMarkdown, validatePlaybookMarkdown } from '../utils/markdownUtils';

const API_BASE = process.env.NEXT_PUBLIC_BASE_URL || '';

export interface PlaybookEditorState {
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  lastSaved: Date | null;
  hasChanges: boolean;
  validationIssues: string[];
}

export interface UsePlaybookEditorReturn {
  editor: Editor | null;
  state: PlaybookEditorState;
  loadPlaybook: () => Promise<void>;
  savePlaybook: () => Promise<boolean>;
  resetPlaybook: () => Promise<void>;
  getMarkdown: () => string;
  setMarkdown: (markdown: string) => Promise<void>;
}

export function usePlaybookEditor(): UsePlaybookEditorReturn {
  const [state, setState] = useState<PlaybookEditorState>({
    isLoading: false,
    isSaving: false,
    error: null,
    lastSaved: null,
    hasChanges: false,
    validationIssues: [],
  });

  const [originalContent, setOriginalContent] = useState<string>('');

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3, 4],
        },
      }),
      Placeholder.configure({
        placeholder: 'Start writing your playbook...',
      }),
    ],
    content: '',
    onUpdate: ({ editor }) => {
      const currentHtml = editor.getHTML();
      setState(prev => ({
        ...prev,
        hasChanges: currentHtml !== originalContent,
      }));
    },
  });

  const getAuthHeaders = useCallback((): HeadersInit => {
    const token = localStorage.getItem('auth_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };
  }, []);

  const loadPlaybook = useCallback(async () => {
    if (!editor) return;

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await fetch(`${API_BASE}/editor/playbook/markdown`, {
        method: 'GET',
        headers: getAuthHeaders(),
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`Failed to load playbook: ${response.status}`);
      }

      const data = await response.json();
      const markdown = data.content || '';

      const html = await markdownToHtmlAsync(markdown);

      editor.commands.setContent(html);
      setOriginalContent(editor.getHTML());

      const validation = validatePlaybookMarkdown(markdown);

      setState(prev => ({
        ...prev,
        isLoading: false,
        hasChanges: false,
        validationIssues: validation.issues,
      }));
    } catch (error) {
      console.error('Failed to load playbook:', error);
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load playbook',
      }));
    }
  }, [editor, getAuthHeaders]);

  const savePlaybook = useCallback(async (): Promise<boolean> => {
    if (!editor) return false;

    setState(prev => ({ ...prev, isSaving: true, error: null }));

    try {
      const html = editor.getHTML();
      const markdown = htmlToMarkdown(html);

      const validation = validatePlaybookMarkdown(markdown);
      if (!validation.valid) {
        setState(prev => ({
          ...prev,
          isSaving: false,
          validationIssues: validation.issues,
          error: 'Playbook has validation issues',
        }));
        return false;
      }

      const response = await fetch(`${API_BASE}/editor/playbook/markdown`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ content: markdown }),
      });

      if (!response.ok) {
        throw new Error(`Failed to save playbook: ${response.status}`);
      }

      setOriginalContent(editor.getHTML());

      setState(prev => ({
        ...prev,
        isSaving: false,
        hasChanges: false,
        lastSaved: new Date(),
        validationIssues: [],
      }));

      return true;
    } catch (error) {
      console.error('Failed to save playbook:', error);
      setState(prev => ({
        ...prev,
        isSaving: false,
        error: error instanceof Error ? error.message : 'Failed to save playbook',
      }));
      return false;
    }
  }, [editor, getAuthHeaders]);

  const resetPlaybook = useCallback(async () => {
    if (!editor) return;

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await fetch(`${API_BASE}/editor/playbook/markdown`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`Failed to reset playbook: ${response.status}`);
      }

      await loadPlaybook();
    } catch (error) {
      console.error('Failed to reset playbook:', error);
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to reset playbook',
      }));
    }
  }, [editor, getAuthHeaders, loadPlaybook]);

  const getMarkdown = useCallback((): string => {
    if (!editor) return '';
    return htmlToMarkdown(editor.getHTML());
  }, [editor]);

  const setMarkdown = useCallback(async (markdown: string) => {
    if (!editor) return;

    const html = await markdownToHtmlAsync(markdown);
    editor.commands.setContent(html);

    const validation = validatePlaybookMarkdown(markdown);
    setState(prev => ({
      ...prev,
      hasChanges: true,
      validationIssues: validation.issues,
    }));
  }, [editor]);

  return {
    editor,
    state,
    loadPlaybook,
    savePlaybook,
    resetPlaybook,
    getMarkdown,
    setMarkdown,
  };
}
