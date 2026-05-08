'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Editor, EditorContent } from '@tiptap/react';
import type { PageSettings } from '../types/workspace';
import { PAGE_DIMENSIONS } from '../types/workspace';
import styles from '../workspace.module.css';

interface PageViewEditorProps {
  editor: Editor | null;
  pageSettings: PageSettings;
  documentName: string | null;
}

const MM_TO_PX = 3.7795275591;

export function PageViewEditor({ editor, pageSettings, documentName }: PageViewEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageCount, setPageCount] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);

  const dimensions = PAGE_DIMENSIONS[pageSettings.pageSize];
  const pageHeightPx = dimensions.height * MM_TO_PX;
  const pageWidthPx = dimensions.width * MM_TO_PX;

  const contentPerPage = pageHeightPx - 100; // 50px top + 50px bottom margin

  useEffect(() => {
    if (!editor || !containerRef.current) return;

    const calculate = () => {
      const proseMirror = containerRef.current?.querySelector('.ProseMirror') as HTMLElement;
      if (!proseMirror) return;

      const height = proseMirror.scrollHeight;
      const pages = Math.max(1, Math.ceil(height / contentPerPage));
      setPageCount(pages);
    };

    setTimeout(calculate, 100);

    const observer = new MutationObserver(calculate);
    const proseMirror = containerRef.current?.querySelector('.ProseMirror');
    if (proseMirror) {
      observer.observe(proseMirror, { childList: true, subtree: true, characterData: true });
    }

    window.addEventListener('resize', calculate);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', calculate);
    };
  }, [editor, contentPerPage]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const scrollTop = container.scrollTop;
      const page = Math.floor(scrollTop / contentPerPage) + 1;
      setCurrentPage(Math.min(Math.max(1, page), pageCount));
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [contentPerPage, pageCount]);

  const goToPage = useCallback((page: number) => {
    const container = containerRef.current;
    if (!container || page < 1 || page > pageCount) return;
    container.scrollTop = (page - 1) * contentPerPage;
    setCurrentPage(page);
  }, [contentPerPage, pageCount]);

  const pageMarkers: React.ReactNode[] = [];
  for (let i = 1; i <= pageCount; i++) {
    const topPos = (i - 1) * contentPerPage;
    pageMarkers.push(
      <div
        key={i}
        className={styles.pageNumMarker}
        style={{ top: `${topPos}px` }}
      >
        {i}
      </div>
    );
  }

  const zoomScale = pageSettings.zoom / 100;

  return (
    <div className={styles.pageViewWrapper}>
      {/* Page indicator */}
      <div className={styles.pageIndicatorFloat}>
        <span>Page</span>
        <input
          type="number"
          min={1}
          max={pageCount}
          value={currentPage}
          onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
          className={styles.goToPageInput}
        />
        <span>of {pageCount}</span>
        <span className={styles.pageIndicatorSize}>{dimensions.name}</span>
      </div>

      {/* Scrollable container */}
      <div ref={containerRef} className={styles.wordPageScroller}>
        <div 
          className={styles.wordPagesContainer}
          style={{
            transform: `scale(${zoomScale})`,
            transformOrigin: 'top center',
          }}
        >
          <div 
            className={styles.wordPaper}
            style={{ width: `${pageWidthPx}px` }}
          >
            {/* Content with page markers inside */}
            <div className={styles.wordContentArea}>
              {/* Page number markers in left margin */}
              {pageSettings.showPageNumbers && pageMarkers}

              {editor && <EditorContent editor={editor} />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PageViewEditor;
