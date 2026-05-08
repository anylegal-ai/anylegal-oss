import { useCallback } from 'react';
import type { Editor } from '@tiptap/react';
import type { RedlineSuggestion } from '../types/workspace';
import { buildClauseIndex, findClauseByNumber, getChildClauses } from '../services/clauseService';

interface TextReplacementResult {
  success: boolean;
  error?: string;
}

interface UseTextReplacementOptions {
  editor: Editor | null;
  onError: (message: string) => void;
  onEnableTracking: () => void;
  viewMode: 'redline' | 'clean';
  trackingEnabled: boolean;
}

export const normalizeForSearch = (text: string): string => text
  .replace(/[\u201C\u201D\u201E\u201F\u2033\u2036]/g, '"')  // Smart double quotes → straight
  .replace(/[\u2018\u2019\u201A\u201B\u2032\u2035]/g, "'")  // Smart single quotes → straight
  .replace(/[\u2013\u2014\u2015]/g, '-')                    // En/em dashes → hyphen
  .replace(/\u00A0/g, ' ')                                   // Non-breaking space → space
  .replace(/\s+/g, ' ')
  .trim();

export const buildTextPositionMap = (editor: Editor): { pos: number; char: string }[] => {
  const textPositions: { pos: number; char: string }[] = [];
  editor.state.doc.descendants((node, pos) => {
    if (node.isText && node.text) {
      for (let i = 0; i < node.text.length; i++) {
        textPositions.push({ pos: pos + i, char: node.text[i] });
      }
    }
  });
  return textPositions;
};

const buildNormToPlainMapping = (plainText: string): number[] => {
  const mapping: number[] = []; // mapping[normIdx] = plainIdx

  let plainIdx = 0;
  let inWhitespace = false;
  let trimmedStart = false;

  while (plainIdx < plainText.length && /\s/.test(plainText[plainIdx])) {
    plainIdx++;
  }
  trimmedStart = true;

  while (plainIdx < plainText.length) {
    const char = plainText[plainIdx];

    if (/\s/.test(char)) {
      if (!inWhitespace) {
        mapping.push(plainIdx);
        inWhitespace = true;
      }
      plainIdx++;
    } else {
      inWhitespace = false;
      mapping.push(plainIdx);
      plainIdx++;
    }
  }

  while (mapping.length > 0 && /\s/.test(plainText[mapping[mapping.length - 1]])) {
    mapping.pop();
  }

  return mapping;
};

const findInPlainText = (
  plainText: string,
  searchText: string,
  startFrom: number = 0
): { start: number; end: number } | null => {
  const normalizedPlain = normalizeForSearch(plainText);
  const normalizedSearch = normalizeForSearch(searchText);

  const normIdx = normalizedPlain.indexOf(normalizedSearch, 0);
  if (normIdx === -1) return null;

  const mapping = buildNormToPlainMapping(plainText);

  if (normIdx >= mapping.length) return null;
  if (normIdx + normalizedSearch.length > mapping.length) return null;

  const plainStart = mapping[normIdx];
  const lastCharIdx = normIdx + normalizedSearch.length - 1;
  const plainEnd = lastCharIdx < mapping.length - 1 
    ? mapping[lastCharIdx + 1] 
    : plainText.length;

  return { start: plainStart, end: plainEnd };
};

const normalizeChar = (char: string): string => {
  if (/[\u201C\u201D\u201E\u201F\u2033\u2036]/.test(char)) return '"';
  if (/[\u2018\u2019\u201A\u201B\u2032\u2035]/.test(char)) return "'";
  if (/[\u2013\u2014\u2015]/.test(char)) return '-';
  if (char === '\u00A0') return ' ';
  return char;
};

const findTextInRegion = (
  plainText: string,
  regionStart: number,
  regionEnd: number,
  searchFor: string
): { startIdx: number; endIdx: number } | null => {
  const region = plainText.slice(regionStart, regionEnd);

  let idx = region.indexOf(searchFor);
  if (idx !== -1) {
    console.log(`Found exact match at region offset ${idx}`);
    return { startIdx: regionStart + idx, endIdx: regionStart + idx + searchFor.length };
  }

  const normalizedRegion = Array.from(region).map(normalizeChar).join('');
  const normalizedSearch = Array.from(searchFor).map(normalizeChar).join('');

  idx = normalizedRegion.indexOf(normalizedSearch);
  if (idx !== -1) {
    console.log(`Found char-normalized match at region offset ${idx}`);
    return { startIdx: regionStart + idx, endIdx: regionStart + idx + searchFor.length };
  }

  idx = normalizedRegion.toLowerCase().indexOf(normalizedSearch.toLowerCase());
  if (idx !== -1) {
    console.log(`Found case-insensitive normalized match at region offset ${idx}`);
    return { startIdx: regionStart + idx, endIdx: regionStart + idx + searchFor.length };
  }

  const wsNormalizedRegion = normalizedRegion.replace(/\s+/g, ' ');
  const wsNormalizedSearch = normalizedSearch.replace(/\s+/g, ' ').trim();

  const wsToOriginal: number[] = [];
  let inWs = false;
  for (let i = 0; i < normalizedRegion.length; i++) {
    if (/\s/.test(normalizedRegion[i])) {
      if (!inWs) {
        wsToOriginal.push(i);
        inWs = true;
      }
    } else {
      wsToOriginal.push(i);
      inWs = false;
    }
  }

  const wsIdx = wsNormalizedRegion.indexOf(wsNormalizedSearch);
  if (wsIdx !== -1 && wsIdx < wsToOriginal.length) {
    const startOffset = wsToOriginal[wsIdx];
    const wsEndIdx = wsIdx + wsNormalizedSearch.length - 1;
    let endOffset: number;
    if (wsEndIdx < wsToOriginal.length) {
      endOffset = wsToOriginal[wsEndIdx] + 1;
    } else {
      endOffset = region.length;
    }
    console.log(`Found whitespace-flexible match at ${wsIdx}, mapped to [${startOffset}, ${endOffset}]`);
    return { startIdx: regionStart + startOffset, endIdx: regionStart + endOffset };
  }

  console.log(`No match found in region. Region first 100: "${region.slice(0, 100)}"`);
  console.log(`Searching for (first 100): "${searchFor.slice(0, 100)}"`);
  return null;
};

export function useTextReplacement({
  editor,
  onError,
  onEnableTracking,
  viewMode,
  trackingEnabled,
}: UseTextReplacementOptions) {

  const applySuggestion = useCallback((
    suggestion: RedlineSuggestion,
    onSuccess: () => void
  ): void => {
    if (!editor) return;

    const needsTrackingEnable = viewMode !== 'redline' || !trackingEnabled;
    if (needsTrackingEnable) {
      onEnableTracking();
      editor.commands.enableTrackingImmediate();
    }

    const doReplacement = () => {
      editor.commands.enableTrackingImmediate();

      const textPositions = buildTextPositionMap(editor);
      if (textPositions.length === 0) {
        onError('Document is empty');
        return;
      }

      const plainText = textPositions.map(p => p.char).join('');

      let regionStart = 0;
      let regionEnd = plainText.length;
      let clauseRefFound = false;

      if (suggestion.clause_ref) {
        const clauseIndex = buildClauseIndex(editor);
        const clause = findClauseByNumber(clauseIndex, suggestion.clause_ref);

        if (clause) {
          const clauseStartInPlain = textPositions.findIndex(tp => tp.pos >= clause.pos);
          const clauseEndInPlain = textPositions.findIndex(tp => tp.pos >= clause.endPos);

          if (clauseStartInPlain !== -1) {
            regionStart = clauseStartInPlain;
            clauseRefFound = true;

            if (clauseEndInPlain !== -1 && clauseEndInPlain > clauseStartInPlain) {
              regionEnd = Math.min(clauseEndInPlain + 500, plainText.length);
            } else {
              const childClauses = getChildClauses(clauseIndex, suggestion.clause_ref);
              if (childClauses.length > 0) {
                const lastChild = childClauses[childClauses.length - 1];
                const lastChildEnd = textPositions.findIndex(tp => tp.pos >= lastChild.endPos);
                if (lastChildEnd !== -1) {
                  regionEnd = Math.min(lastChildEnd + 200, plainText.length);
                }
              } else {
                regionEnd = Math.min(regionStart + 3000, plainText.length);
              }
            }

            console.log(`ClauseService: Found clause ${suggestion.clause_ref} at doc pos ${clause.pos}, plain text region [${regionStart}, ${regionEnd}]`);
          }
        }

        if (!clauseRefFound) {
          const clauseMatch = suggestion.clause_ref.match(/(\d+)\.?(\d*)/);
          if (clauseMatch) {
            const majorNum = clauseMatch[1];
            const minorNum = clauseMatch[2] || '';
            const pattern = new RegExp(`\\b${majorNum}\\.${minorNum}[.\\s]`);
            const match = plainText.match(pattern);
            if (match && match.index !== undefined) {
              regionStart = match.index;
              regionEnd = Math.min(regionStart + 3000, plainText.length);
              clauseRefFound = true;
              console.log(`Regex fallback: Found clause ${suggestion.clause_ref} at position ${regionStart}`);
            }
          }
        }

        if (!clauseRefFound) {
          console.warn(`Clause ${suggestion.clause_ref} not found in document`);
          onError(`Clause "${suggestion.clause_ref}" not found in document. The clause may have been renumbered or removed.`);
          navigator.clipboard?.writeText(suggestion.suggested);
          return;
        }
      }

      if (regionEnd - regionStart < 200) {
        regionEnd = Math.min(regionStart + 2000, plainText.length);
      }

      console.log(`Searching in region [${regionStart}, ${regionEnd}] for: "${suggestion.original.slice(0, 60)}..."`);
      console.log(`Region content (first 200): "${plainText.slice(regionStart, regionStart + 200)}"`);

      let match = findTextInRegion(plainText, regionStart, regionEnd, suggestion.original);

      if (!match && clauseRefFound) {
        console.log(`Not found in clause region, trying full document search...`);
        match = findTextInRegion(plainText, 0, plainText.length, suggestion.original);
        if (match) {
          console.log(`Found in full document at [${match.startIdx}, ${match.endIdx}]`);
        }
      }

      if (!match || match.endIdx <= match.startIdx) {
        console.warn(`Could not find text for clause ${suggestion.clause_ref}`);
        console.log(`Full search text: "${suggestion.original}"`);
        onError(`Could not match text in clause ${suggestion.clause_ref || ''}. Suggestion copied to clipboard.`);
        navigator.clipboard?.writeText(suggestion.suggested);
        return;
      }

      const { startIdx, endIdx } = match;

      const matchLen = endIdx - startIdx;
      const expectedLen = suggestion.original.length;
      if (matchLen > expectedLen * 2 || matchLen < expectedLen * 0.3) {
        console.warn(`Match length ${matchLen} too different from expected ${expectedLen}, rejecting`);
        onError(`Match length mismatch (${matchLen} vs ${expectedLen}). Suggestion copied to clipboard.`);
        navigator.clipboard?.writeText(suggestion.suggested);
        return;
      }

      const matchedText = plainText.slice(startIdx, endIdx);
      console.log(`Replacing text at [${startIdx}, ${endIdx}]: "${matchedText.slice(0, 80)}..."`);
      console.log(`With new text: "${suggestion.suggested.slice(0, 80)}..."`);

      const startPos = textPositions[Math.min(startIdx, textPositions.length - 1)].pos;
      const endPos = textPositions[Math.min(endIdx - 1, textPositions.length - 1)].pos + 1;

      console.log(`Document positions: from=${startPos}, to=${endPos}`);

      const markStartPos = startPos;

      editor.chain()
        .focus()
        .setTextSelection({ from: startPos, to: endPos })
        .insertContent(suggestion.suggested)
        .run();

      const markEndPos = editor.state.selection.from;

      console.log(`Marking insertion from ${markStartPos} to ${markEndPos}`);

      if (markEndPos > markStartPos) {
        editor.chain()
          .setTextSelection({ from: markStartPos, to: markEndPos })
          .setMark('insertion')
          .setTextSelection({ from: markEndPos, to: markEndPos })
          .scrollIntoView()
          .run();
      } else {
        console.warn(`Mark positions invalid: ${markStartPos} to ${markEndPos}`);
        editor.commands.scrollIntoView();
      }

      onSuccess();
    };

    if (needsTrackingEnable) {
      setTimeout(doReplacement, 100);
    } else {
      doReplacement();
    }
  }, [editor, onError, onEnableTracking, viewMode, trackingEnabled]);

  return { applySuggestion };
}
