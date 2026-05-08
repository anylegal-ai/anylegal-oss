import type { Editor } from '@tiptap/react';
import { CLAUSE_NUMBER_PATTERN, parseClauseNumber, startsWithClauseNumber } from '../extensions/clauseNode';

export interface ClauseInfo {
  number: string;        // "5.3.1"
  parts: number[];       // [5, 3, 1]
  level: number;         // 3 (depth)
  pos: number;           // Document position (start of node)
  endPos: number;        // End of clause block (position after node)
  nodeType: 'clause' | 'paragraph'; // Whether it's a ClauseNode or detected paragraph
}

export function compareClauseParts(a: number[], b: number[]): number {
  const maxLen = Math.max(a.length, b.length);
  for (let i = 0; i < maxLen; i++) {
    const aVal = a[i] ?? 0;
    const bVal = b[i] ?? 0;
    if (aVal !== bVal) {
      return aVal - bVal;
    }
  }
  return 0;
}

export function isParentClause(parent: number[], child: number[]): boolean {
  if (parent.length >= child.length) return false;
  for (let i = 0; i < parent.length; i++) {
    if (parent[i] !== child[i]) return false;
  }
  return true;
}

export function areSiblingClauses(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  if (a.length === 0) return false;
  for (let i = 0; i < a.length - 1; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function getPreviousSibling(parts: number[]): number[] | null {
  if (parts.length === 0) return null;
  const lastPart = parts[parts.length - 1];
  if (lastPart <= 1) return null;
  return [...parts.slice(0, -1), lastPart - 1];
}

export function getParentClause(parts: number[]): number[] | null {
  if (parts.length <= 1) return null;
  return parts.slice(0, -1);
}

export function buildClauseIndex(editor: Editor): ClauseInfo[] {
  const clauses: ClauseInfo[] = [];

  editor.state.doc.forEach((node, offset) => {
    const pos = offset + 1; // TipTap positions are 1-indexed inside nodes
    const endPos = offset + node.nodeSize;

    if (node.type.name === 'clause') {
      const number = node.attrs.number as string;
      const parts = node.attrs.parts as number[];
      const level = node.attrs.level as number;

      if (number && parts.length > 0) {
        clauses.push({
          number,
          parts,
          level,
          pos,
          endPos,
          nodeType: 'clause',
        });
      }
      return;
    }

    if (node.type.name === 'paragraph' || node.type.name === 'heading') {
      const text = node.textContent;
      const clauseCheck = startsWithClauseNumber(text);

      if (clauseCheck.match && clauseCheck.number && clauseCheck.parts) {
        clauses.push({
          number: clauseCheck.number,
          parts: clauseCheck.parts,
          level: clauseCheck.level || clauseCheck.parts.length,
          pos,
          endPos,
          nodeType: 'paragraph',
        });
      }
    }
  });

  clauses.sort((a, b) => compareClauseParts(a.parts, b.parts));

  return clauses;
}

export function findClauseInsertPosition(
  clauseIndex: ClauseInfo[],
  targetClause: string,
  docSize: number
): { pos: number; strategy: string } {
  const { parts: targetParts } = parseClauseNumber(targetClause);

  if (targetParts.length === 0) {
    return { pos: docSize, strategy: 'invalid-clause-number' };
  }

  const prevSiblingParts = getPreviousSibling(targetParts);
  if (prevSiblingParts) {
    const prevSibling = clauseIndex.find(c => 
      c.parts.length === prevSiblingParts.length &&
      c.parts.every((p, i) => p === prevSiblingParts[i])
    );
    if (prevSibling) {
      return { 
        pos: prevSibling.endPos, 
        strategy: `after-previous-sibling-${prevSibling.number}` 
      };
    }
  }

  const parentParts = getParentClause(targetParts);
  if (parentParts && parentParts.length > 0) {
    const sameParentClauses = clauseIndex.filter(c => 
      c.parts.length === targetParts.length &&
      isParentClause(parentParts, c.parts)
    );

    if (sameParentClauses.length > 0) {
      const beforeTarget = sameParentClauses.filter(c => 
        compareClauseParts(c.parts, targetParts) < 0
      );

      if (beforeTarget.length > 0) {
        const lastBefore = beforeTarget[beforeTarget.length - 1];
        return { 
          pos: lastBefore.endPos, 
          strategy: `after-last-sibling-${lastBefore.number}` 
        };
      }
    }
  }

  if (parentParts && parentParts.length > 0) {
    const parent = clauseIndex.find(c => 
      c.parts.length === parentParts.length &&
      c.parts.every((p, i) => p === parentParts[i])
    );
    if (parent) {
      return { 
        pos: parent.endPos, 
        strategy: `after-parent-${parent.number}` 
      };
    }
  }

  const allBefore = clauseIndex.filter(c => 
    compareClauseParts(c.parts, targetParts) < 0
  );

  if (allBefore.length > 0) {
    const lastBefore = allBefore[allBefore.length - 1];
    return { 
      pos: lastBefore.endPos, 
      strategy: `after-preceding-clause-${lastBefore.number}` 
    };
  }

  const allAfter = clauseIndex.filter(c => 
    compareClauseParts(c.parts, targetParts) > 0
  );

  if (allAfter.length > 0) {
    const firstAfter = allAfter[0];
    return { 
      pos: firstAfter.pos, 
      strategy: `before-following-clause-${firstAfter.number}` 
    };
  }

  return { pos: docSize, strategy: 'end-of-document' };
}

export function findClauseByNumber(
  clauseIndex: ClauseInfo[],
  clauseNumber: string
): ClauseInfo | undefined {
  const { parts } = parseClauseNumber(clauseNumber);
  return clauseIndex.find(c => 
    c.parts.length === parts.length &&
    c.parts.every((p, i) => p === parts[i])
  );
}

export function getChildClauses(
  clauseIndex: ClauseInfo[],
  parentNumber: string
): ClauseInfo[] {
  const { parts: parentParts } = parseClauseNumber(parentNumber);
  return clauseIndex.filter(c => isParentClause(parentParts, c.parts));
}

export function debugClauseIndex(clauseIndex: ClauseInfo[]): void {
  console.log('=== Clause Index ===');
  console.log(`Total clauses: ${clauseIndex.length}`);
  clauseIndex.forEach(c => {
    console.log(`  ${c.number} (level ${c.level}) @ pos ${c.pos}-${c.endPos} [${c.nodeType}]`);
  });
  console.log('===================');
}
