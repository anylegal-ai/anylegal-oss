import { useCallback } from 'react';
import type { Editor } from '@tiptap/react';
import { markdownToHtmlAsync } from '../utils/markdownUtils';
import { setSkipTracking } from '../trackChangesExtension';
import { buildClauseIndex, findClauseInsertPosition, debugClauseIndex } from '../services/clauseService';
import { parseClauseNumber, CLAUSE_NUMBER_PATTERN } from '../extensions/clauseNode';
import type { ViewMode, WorkspaceTab } from '../types/workspace';

interface UseChatActionsOptions {
  editor: Editor | null;
  viewMode: ViewMode;
  trackingEnabled: boolean;
  setViewMode: (mode: ViewMode) => void;
  setTrackingEnabled: (enabled: boolean) => void;
  setActiveTab: (tab: WorkspaceTab) => void;
}

const normalizeChar = (char: string): string => {
  if (/[\u201C\u201D\u201E\u201F\u2033\u2036]/.test(char)) return '"';
  if (/[\u2018\u2019\u201A\u201B\u2032\u2035]/.test(char)) return "'";
  if (/[\u2013\u2014\u2015]/.test(char)) return '-';
  if (char === '\u00A0') return ' ';
  return char;
};

const collapseWhitespace = (s: string) => s.replace(/\s+/g, ' ').trim();

const removeAllWhitespace = (s: string) => s.replace(/\s+/g, '').toLowerCase();

const normalizeClauseFormat = (s: string): string => {
  return s.replace(/^(\d+(?:\.\d+)*)[.\s]+/g, '$1 ')
          .replace(/(\d+(?:\.\d+)*)[.\s]+/g, '$1 ');
};

const addLegalLineBreaks = (text: string): string => {
  let result = text;
  result = result.replace(/([;.])\s*(\([a-z]\)|\([ivx]+\)|\([A-Z]\))/gi, '$1\n$2');
  result = result.replace(/([a-z])\s*(\([a-z]\))/gi, '$1\n$2');
  result = result.replace(/(\d+\.\s*[A-Z][A-Z\s]{3,})([A-Z][a-z])/g, '$1\n$2');
  return result;
};

const parseMarkdownInline = (text: string): any[] => {
  const content: any[] = [];

  const markdownPattern = /(\*\*|__)(.+?)(\*\*|__)|(\*|_)(.+?)(\*|_)/g;
  let lastIndex = 0;
  let match;

  while ((match = markdownPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const beforeText = text.slice(lastIndex, match.index);
      if (beforeText) {
        content.push({ type: 'text', text: beforeText });
      }
    }

    if (match[1] && (match[1] === '**' || match[1] === '__')) {
      content.push({
        type: 'text',
        text: match[2],
        marks: [{ type: 'bold' }]
      });
    } else if (match[4] && (match[4] === '*' || match[4] === '_')) {
      content.push({
        type: 'text',
        text: match[5],
        marks: [{ type: 'italic' }]
      });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    const afterText = text.slice(lastIndex);
    if (afterText) {
      content.push({ type: 'text', text: afterText });
    }
  }

  if (content.length === 0 && text) {
    content.push({ type: 'text', text: text });
  }

  return content;
};

const parseMarkdownToContent = (text: string, forceInline: boolean = false): any[] => {
  if (forceInline) {
    return parseMarkdownInline(text);
  }

  const processed = addLegalLineBreaks(text);
  const lines = processed.split('\n').filter(p => p.trim());

  if (lines.length <= 1) {
    return parseMarkdownInline(lines[0] || text);
  }

  return lines.map(line => ({
    type: 'paragraph',
    content: parseMarkdownInline(line)
  }));
};

const stripMarkdownForMatching = (text: string): string => {
  let result = text;
  result = result.replace(/\*\*([\s\S]*?)\*\*/g, '$1');
  result = result.replace(/__([\s\S]*?)__/g, '$1');
  result = result.replace(/(?<![a-zA-Z])\*([^*\n]+)\*(?![a-zA-Z])/g, '$1');
  result = result.replace(/(?<![a-zA-Z])_([^_\n]+)_(?![a-zA-Z])/g, '$1');
  return result;
};

export function useChatActions({
  editor,
  viewMode,
  trackingEnabled,
  setViewMode,
  setTrackingEnabled,
  setActiveTab,
}: UseChatActionsOptions) {

  const buildTextPositionMap = useCallback((ed: Editor) => {
    const textPositions: { pos: number; char: string }[] = [];
    let blockIndex = 0;

    ed.state.doc.forEach((block, offset) => {
      if (blockIndex > 0 && textPositions.length > 0) {
        const lastChar = textPositions[textPositions.length - 1]?.char;
        if (lastChar && lastChar !== ' ' && lastChar !== '\n') {
          textPositions.push({ pos: offset, char: ' ' });
        }
      }

      block.descendants((node, nodePos) => {
        if (node.isText && node.text) {
          for (let i = 0; i < node.text.length; i++) {
            textPositions.push({ pos: offset + nodePos + i + 1, char: node.text[i] });
          }
        }
      });

      blockIndex++;
    });

    return textPositions;
  }, []);

  const handleApplySuggestion = useCallback((original: string, suggested: string): boolean => {
    if (!editor) return false;

    const textPositions = buildTextPositionMap(editor);
    if (textPositions.length === 0) return false;

    const docText = textPositions.map(p => p.char).join('');
    const normalizedDoc = Array.from(docText).map(normalizeChar).join('');
    const normalizedOriginal = Array.from(original.replace(/\n+/g, ' ')).map(normalizeChar).join('');

    const collapsedDoc = collapseWhitespace(normalizedDoc);
    const collapsedOriginal = collapseWhitespace(normalizedOriginal);

    console.log('=== TEXT MATCHING DEBUG ===');
    console.log('Original from LLM (raw):', JSON.stringify(original.slice(0, 150)));
    console.log('Normalized original:', JSON.stringify(normalizedOriginal.slice(0, 150)));
    console.log('Document text sample:', JSON.stringify(docText.slice(0, 400)));
    console.log('Collapsed original:', JSON.stringify(collapsedOriginal.slice(0, 100)));
    console.log('Collapsed doc sample:', JSON.stringify(collapsedDoc.slice(0, 200)));

    const clauseMatch = original.match(/^(\d+(?:\.\d+)*)[.\s]/);
    let searchStart = 0;

    if (clauseMatch) {
      const clauseNum = clauseMatch[1];
      const clausePattern = new RegExp(`\\b${clauseNum.replace(/\./g, '\\.')}[.\\s]`);
      const clauseInDoc = normalizedDoc.match(clausePattern);
      if (clauseInDoc && clauseInDoc.index !== undefined) {
        searchStart = clauseInDoc.index;
      }
    }

    let startIdx = -1;

    startIdx = docText.indexOf(original, searchStart);

    if (startIdx === -1) {
      startIdx = normalizedDoc.indexOf(normalizedOriginal, searchStart);
    }

    if (startIdx === -1) {
      startIdx = normalizedDoc.toLowerCase().indexOf(normalizedOriginal.toLowerCase(), searchStart);
    }

    if (startIdx === -1) {
      const collapsedIdx = collapsedDoc.toLowerCase().indexOf(collapsedOriginal.toLowerCase());
      if (collapsedIdx !== -1) {
        const firstWords = collapsedOriginal.slice(0, 30).toLowerCase();
        for (let i = searchStart; i < normalizedDoc.length - 20; i++) {
          const testSlice = collapseWhitespace(normalizedDoc.slice(i, i + 50)).toLowerCase();
          if (testSlice.startsWith(firstWords.slice(0, 20))) {
            startIdx = i;
            break;
          }
        }
      }
    }

    if (startIdx === -1 && searchStart > 0) {
      startIdx = normalizedDoc.indexOf(normalizedOriginal);
      if (startIdx === -1) {
        startIdx = normalizedDoc.toLowerCase().indexOf(normalizedOriginal.toLowerCase());
      }
    }

    if (startIdx === -1) {
      const partialOriginal = collapseWhitespace(normalizedOriginal).slice(0, 60).toLowerCase();
      console.log('Trying partial match with:', JSON.stringify(partialOriginal));

      const partialIdx = collapsedDoc.toLowerCase().indexOf(partialOriginal);
      if (partialIdx !== -1) {
        let collapsedCount = 0;
        for (let i = 0; i < normalizedDoc.length; i++) {
          const collapsedSlice = collapseWhitespace(normalizedDoc.slice(0, i + 1));
          if (collapsedSlice.length >= partialIdx + 5) {
            const nearbyStart = Math.max(0, i - 20);
            if (clauseMatch) {
              const clauseNum = clauseMatch[1];
              const nearbyText = normalizedDoc.slice(nearbyStart, i + 30);
              const clauseInNearby = nearbyText.indexOf(clauseNum);
              if (clauseInNearby !== -1) {
                startIdx = nearbyStart + clauseInNearby;
                console.log('Partial match found at:', startIdx);
                break;
              }
            }
            startIdx = i;
            break;
          }
        }
      }
    }

    if (startIdx === -1 && clauseMatch) {
      const clauseNum = clauseMatch[1];
      const clausePattern = new RegExp(`\\b${clauseNum.replace(/\./g, '\\.')}\\b`);
      const clauseInDoc = normalizedDoc.match(clausePattern);
      if (clauseInDoc && clauseInDoc.index !== undefined) {
        startIdx = clauseInDoc.index;
        console.log('Using clause number position as fallback:', startIdx);
      }
    }

    if (startIdx === -1) {
      console.error('Text matching failed. Original:', original.slice(0, 100));
      console.error('Document excerpt:', docText.slice(0, 200));
      try {
        navigator.clipboard?.writeText(suggested);
        alert('Could not find the text to replace. Suggested text copied to clipboard - please paste manually.');
      } catch (e) {
        alert('Could not find the text to replace. The document may have changed.');
      }
      return false;
    }

    const foundText = docText.slice(startIdx, startIdx + Math.min(50, original.length));
    const expectedText = original.slice(0, Math.min(50, original.length));

    const normalizedFoundRaw = Array.from(foundText).map(normalizeChar).join('');
    const normalizedExpectedRaw = Array.from(expectedText).map(normalizeChar).join('');

    const normalizedFound = removeAllWhitespace(normalizeClauseFormat(normalizedFoundRaw));
    const normalizedExpected = removeAllWhitespace(normalizeClauseFormat(normalizedExpectedRaw));

    if (!normalizedFound.slice(0, 30).startsWith(normalizedExpected.slice(0, 30))) {
      console.warn(`Match validation failed. Found: "${normalizedFound.slice(0, 40)}", Expected: "${normalizedExpected.slice(0, 40)}"`);
      try {
        navigator.clipboard?.writeText(suggested);
      } catch (e) {
        console.warn('Clipboard write failed:', e);
      }
      alert('Could not find exact match. Text copied to clipboard - please paste manually.');
      return false;
    }

    if (viewMode !== 'redline' || !trackingEnabled) {
      setViewMode('redline');
      setTrackingEnabled(true);
      editor.commands.setTrackChangesEnabled(true);
    }
    editor.commands.enableTrackingImmediate();

    const matchNoWhitespace = removeAllWhitespace(normalizedOriginal);
    let docCharsMatched = 0;
    let matchedChars = 0;

    for (let i = startIdx; i < textPositions.length && matchedChars < matchNoWhitespace.length; i++) {
      const char = normalizeChar(textPositions[i].char).toLowerCase();
      docCharsMatched++;

      if (/\s/.test(char)) {
        continue;
      }

      if (matchedChars < matchNoWhitespace.length && char === matchNoWhitespace[matchedChars]) {
        matchedChars++;
      }
    }

    const endIdx = startIdx + docCharsMatched;
    if (endIdx > textPositions.length) return false;

    const startPos = textPositions[startIdx].pos;
    const endPos = textPositions[Math.min(endIdx - 1, textPositions.length - 1)].pos + 1;

    const docSizeBefore = editor.state.doc.content.size;
    const originalTextLength = original.length;

    const isInlineReplacement = !original.includes('\n');

    const content = parseMarkdownToContent(suggested, isInlineReplacement);

    editor.chain()
      .focus()
      .setTextSelection({ from: startPos, to: endPos })
      .insertContent(content)
      .run();

    setTimeout(() => {
      try {
        const { state, view } = editor;
        const docSizeAfter = state.doc.content.size;
        const sizeChange = docSizeAfter - docSizeBefore;
        const insertedLength = sizeChange + originalTextLength;

        const markStart = startPos;
        let markEnd = markStart + insertedLength;

        const cursorPos = state.selection.from;
        if (cursorPos > markStart && cursorPos <= docSizeAfter) {
          markEnd = cursorPos;
        }

        console.log(`Applying mark: ${markStart} to ${markEnd}, docSize: ${docSizeAfter}`);

        if (markEnd > markStart && markEnd <= docSizeAfter) {
          const insertionMark = state.schema.marks.insertion;
          if (insertionMark) {
            const tr = state.tr.addMark(
              markStart, 
              markEnd, 
              insertionMark.create({ author: 'user' })
            );
            view.dispatch(tr);
            console.log('Mark applied successfully');
          } else {
            console.warn('Insertion mark not found in schema');
          }
          editor.chain()
            .setTextSelection({ from: markStart, to: markStart })
            .scrollIntoView()
            .run();
        }
      } catch (e) {
        console.error('Error applying mark:', e);
      }
    }, 100);

    return true;
  }, [editor, viewMode, trackingEnabled, setViewMode, setTrackingEnabled, buildTextPositionMap]);

  const handleInsertText = useCallback((text: string): void => {
    if (!editor) return;

    if (viewMode !== 'redline' || !trackingEnabled) {
      setViewMode('redline');
      setTrackingEnabled(true);
      editor.commands.setTrackChangesEnabled(true);
    }
    editor.commands.enableTrackingImmediate();

    const clauseMatch = text.match(CLAUSE_NUMBER_PATTERN);
    let insertPos: number = editor.state.selection.from;

    if (clauseMatch) {
      const clauseNum = clauseMatch[1];

      const clauseIndex = buildClauseIndex(editor);

      console.log(`Smart insert: inserting clause ${clauseNum}`);
      debugClauseIndex(clauseIndex);

      const docSize = editor.state.doc.content.size;
      const { pos, strategy } = findClauseInsertPosition(clauseIndex, clauseNum, docSize);

      console.log(`Smart insert: clause ${clauseNum} - strategy: ${strategy}, position: ${pos}`);

      if (pos > 0 && pos <= docSize) {
        insertPos = pos;
      } else {
        insertPos = docSize > 1 ? docSize - 1 : 1;
        console.warn(`Smart insert: falling back to end of document for clause ${clauseNum}`);
      }
    }

    if (insertPos <= 1 || (insertPos === editor.state.selection.from && insertPos < 10)) {
      insertPos = editor.state.doc.content.size - 1;
      console.log('Insert position fallback: using end of document');
    }

    const maxPos = editor.state.doc.content.size;
    insertPos = Math.min(Math.max(1, insertPos), maxPos);

    editor.chain().focus().setTextSelection(insertPos).run();

    const parsedContent = parseMarkdownToContent(text);

    const content = Array.isArray(parsedContent) && parsedContent.length > 0 && parsedContent[0].type === 'paragraph'
      ? parsedContent
      : [{ type: 'paragraph', content: parsedContent }];

    editor.chain()
      .focus()
      .insertContent(content)
      .run();

    const insertEndPos = editor.state.selection.from;

    if (insertEndPos > insertPos) {
      editor.chain()
        .setTextSelection({ from: insertPos, to: insertEndPos })
        .setMark('insertion')
        .setTextSelection({ from: insertPos, to: insertPos }) // Move cursor to START
        .scrollIntoView()
        .run();
    }
  }, [editor, viewMode, trackingEnabled, setViewMode, setTrackingEnabled]);

  const handleReplaceDocument = useCallback(async (text: string): Promise<void> => {
    if (!editor) return;

    let html = await markdownToHtmlAsync(text);

    html = html
      .replace(/<hr\s*\/?>/gi, '')
      .replace(/^(\s*<p>\s*<\/p>\s*)+/gi, '')
      .trim();

    console.log('HTML for replace:', html.slice(0, 300));

    // CRITICAL: Disable track changes BEFORE any editor operations
    setSkipTracking(true);
    editor.commands.setTrackChangesEnabled(false);

    setViewMode('clean');
    setTrackingEnabled(false);

    editor.commands.setContent('');
    editor.commands.insertContent(html as string);

    editor.commands.setTextSelection({ from: 1, to: 1 });

    setActiveTab('revise');

    setTimeout(() => setSkipTracking(false), 100);
  }, [editor, setViewMode, setTrackingEnabled, setActiveTab]);

  return {
    handleApplySuggestion,
    handleInsertText,
    handleReplaceDocument,
  };
}
