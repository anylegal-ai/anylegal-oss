'use client';

import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { Viewer, Worker, PageChangeEvent, SpecialZoomLevel } from '@react-pdf-viewer/core';
import { defaultLayoutPlugin, ToolbarSlot, ToolbarProps } from '@react-pdf-viewer/default-layout';

import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';

interface PdfPreviewProps {
  pdfData: Uint8Array | null;
  pdfError?: string | null;
  onDownloadDocx?: () => void;
  downloadLabel?: string;
  documentName?: string;
  scrollToText?: string | null;
  onScrollComplete?: () => void;
  isMobile?: boolean;
  onClose?: () => void;
  onHide?: () => void;
}

export default function PdfPreview({ pdfData, pdfError, onDownloadDocx, downloadLabel = 'DOCX', documentName, scrollToText, onScrollComplete, isMobile = false, onClose, onHide }: PdfPreviewProps) {
  const currentPageRef = useRef(0);
  const isFirstLoad = useRef(true);
  const isDocLoadingRef = useRef(false);
  const scrollToTextRef = useRef<string | null>(null);
  const onScrollCompleteRef = useRef<(() => void) | undefined>(undefined);

  const [blobUrl, setBlobUrl] = useState<string>('');
  useEffect(() => {
    if (!pdfData) {
      setBlobUrl('');
      return;
    }
    const blob = new Blob([pdfData as BlobPart], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    setBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pdfData]);

  useEffect(() => {
    scrollToTextRef.current = scrollToText || null;
  }, [scrollToText]);

  useEffect(() => {
    onScrollCompleteRef.current = onScrollComplete;
  }, [onScrollComplete]);

  const renderToolbar = useMemo(() => {
    return (Toolbar: (props: ToolbarProps) => React.ReactElement) => (
      <Toolbar>
        {(slots: ToolbarSlot) => {
          const {
            CurrentPageInput,
            GoToNextPage,
            GoToPreviousPage,
            NumberOfPages,
            ShowSearchPopover,
            Zoom,
            ZoomIn,
            ZoomOut,
            Print,
          } = slots;
          return (
            <div style={{ alignItems: 'center', display: 'flex', width: '100%', flexWrap: 'nowrap', minWidth: 0 }}>
              {/* Close button */}
              {onClose && (
                <button
                  onClick={onClose}
                  title="Close document"
                  style={{
                    alignItems: 'center',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    padding: '4px 6px',
                    color: '#666',
                    fontSize: 15,
                    fontWeight: 500,
                    lineHeight: 1,
                    flexShrink: 0,
                  }}
                >✕</button>
              )}

              {/* Document name — compact, shrinks to fit */}
              {!isMobile && documentName && (
                <div style={{
                  padding: '0 4px',
                  fontSize: 12,
                  fontWeight: 500,
                  color: '#555',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  minWidth: 0,
                  maxWidth: 160,
                  flexShrink: 1,
                }} title={documentName}>
                  {documentName}
                </div>
              )}

              {/* Page navigation */}
              <div style={{ padding: '0 2px' }}><GoToPreviousPage /></div>
              <div style={{ padding: '0 2px', display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0, whiteSpace: 'nowrap' }}>
                <div style={{ width: 36 }}><CurrentPageInput /></div>
                <span style={{ color: '#666', fontSize: 13 }}>/ <NumberOfPages /></span>
              </div>
              <div style={{ padding: '0 2px' }}><GoToNextPage /></div>

              <div style={{ padding: '0 4px', borderLeft: '1px solid #ddd', height: 24 }} />

              {/* Zoom */}
              <div style={{ padding: '0 2px' }}><ZoomOut /></div>
              <div style={{ padding: '0 2px' }}><Zoom /></div>
              <div style={{ padding: '0 2px' }}><ZoomIn /></div>

              <div style={{ padding: '0 4px', borderLeft: '1px solid #ddd', height: 24 }} />

              {/* Search */}
              <div style={{ padding: '0 2px' }}><ShowSearchPopover /></div>

              {/* Print — hidden on mobile */}
              {!isMobile && <div style={{ padding: '0 2px' }}><Print /></div>}

              {/* Spacer */}
              <div style={{ flex: 1 }} />

              {/* Download button */}
              {onDownloadDocx && (
                <button
                  onClick={onDownloadDocx}
                  title={`Download ${downloadLabel}`}
                  style={{
                    alignItems: 'center',
                    background: 'none',
                    border: '1px solid #ddd',
                    borderRadius: 6,
                    cursor: 'pointer',
                    display: 'flex',
                    gap: 5,
                    fontSize: 13,
                    fontWeight: 500,
                    padding: '6px 14px',
                    color: '#333',
                    flexShrink: 0,
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#f3f4f6'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  {!isMobile && <>Download {downloadLabel}</>}
                </button>
              )}

            </div>
          );
        }}
      </Toolbar>
    );
  }, [onDownloadDocx, downloadLabel, documentName, isMobile, onClose, onHide]);

  const defaultLayoutPluginInstance = defaultLayoutPlugin({
    sidebarTabs: () => [],  // No sidebar (thumbnails, bookmarks, etc.)
    renderToolbar,
  });

  const pluginInstanceRef = useRef(defaultLayoutPluginInstance);
  pluginInstanceRef.current = defaultLayoutPluginInstance;

  const handlePageChange = useCallback((e: PageChangeEvent) => {
    if (isDocLoadingRef.current) return;
    currentPageRef.current = e.currentPage;
  }, []);

  useEffect(() => {
    if (pdfData && !isFirstLoad.current) {
      isDocLoadingRef.current = true;
    }
  }, [pdfData]);

  const handleDocumentLoad = useCallback(() => {
    if (isFirstLoad.current) {
      isFirstLoad.current = false;
      return;
    }

    const pendingSearch = scrollToTextRef.current;
    console.log('[PDF] onDocumentLoad fired, pendingSearch:', pendingSearch ? `"${pendingSearch.substring(0, 60)}..."` : null);

    if (pendingSearch) {
      scrollToTextRef.current = null;

      const firstLine = pendingSearch.split(/[\r\n]/)[0]?.trim() || pendingSearch;
      const searchFragment = firstLine
        .replace(/\s+/g, ' ')
        .trim()
        .substring(0, 60)
        .trim();

      console.log('[PDF] Scroll-to-edit: searching for:', JSON.stringify(searchFragment));

      const attemptSearch = async () => {
        const plugin = pluginInstanceRef.current;
        const searchPlugin = plugin.toolbarPluginInstance.searchPluginInstance;
        const MAX_RETRIES = 5;
        const RETRY_DELAY = 600; // ms between retries

        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
          try {
            const matches = await searchPlugin.highlight(searchFragment);
            console.log(`[PDF] Search attempt ${attempt}/${MAX_RETRIES}: ${matches.length} matches`);

            if (matches.length > 0) {
              searchPlugin.jumpToMatch(0);
              currentPageRef.current = matches[0].pageIndex;
              console.log(`[PDF] Jumped to page ${matches[0].pageIndex}`);

              setTimeout(() => {
                searchPlugin.clearHighlights();
                isDocLoadingRef.current = false;
              }, 2500);
              return;
            }
          } catch (err) {
            console.warn(`[PDF] Search attempt ${attempt} error:`, err);
          }

          if (attempt < MAX_RETRIES) {
            await new Promise(r => setTimeout(r, RETRY_DELAY));
          }
        }

        console.log('[PDF] Search exhausted, falling back to page restore');
        isDocLoadingRef.current = false;
      };

      setTimeout(() => {
        attemptSearch();
        onScrollCompleteRef.current?.();
      }, 500);

    } else {
      const page = currentPageRef.current;
      if (page > 0) {
        setTimeout(() => {
          pluginInstanceRef.current
            .toolbarPluginInstance
            .pageNavigationPluginInstance
            .jumpToPage(page);
          setTimeout(() => { isDocLoadingRef.current = false; }, 200);
        }, 150);
      } else {
        isDocLoadingRef.current = false;
      }
    }
  }, []);

  if (!pdfData || !blobUrl) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: '#666',
          fontSize: 14,
          gap: 12,
        }}
      >
        {pdfError ? (
          <>
            <span>Preview unavailable</span>
            <span style={{ fontSize: 12, color: '#999' }}>
              The PDF preview service is not running. Use Download to view the document.
            </span>
            {onDownloadDocx && (
              <button
                onClick={onDownloadDocx}
                style={{
                  marginTop: 8,
                  padding: '8px 16px',
                  border: '1px solid #ccc',
                  borderRadius: 6,
                  background: '#fff',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                Download {downloadLabel}
              </button>
            )}
          </>
        ) : (
          'Loading preview...'
        )}
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <Worker workerUrl="/pdf.worker.min.js">
        <Viewer
          fileUrl={blobUrl}
          plugins={[defaultLayoutPluginInstance]}
          defaultScale={isMobile ? 0.6 : undefined}
          onPageChange={handlePageChange}
          onDocumentLoad={handleDocumentLoad}
        />
      </Worker>
    </div>
  );
}
