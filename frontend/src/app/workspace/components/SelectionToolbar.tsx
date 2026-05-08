'use client';

import React, { useState, useRef, useEffect } from 'react';
import styles from '../workspace.module.css';

export interface SelectionPosition {
  top: number;
  left: number;
  bottom: number;
  width: number;
}

interface SelectionToolbarProps {
  selectedText: string;
  position: SelectionPosition | null;
  containerRef: React.RefObject<HTMLElement | null>;
  onRevise: (instruction: string, capturedText: string) => void;
  onExplain: () => void;
  onHighlightSelection?: () => void;  // Apply visual highlight when input shows
  onClearHighlight?: () => void;      // Clear highlight when done
  isLoading?: boolean;
}

export function SelectionToolbar({
  selectedText,
  position,
  containerRef,
  onRevise,
  onExplain,
  onHighlightSelection,
  onClearHighlight,
  isLoading = false,
}: SelectionToolbarProps) {
  const [showInput, setShowInput] = useState(false);
  const [instruction, setInstruction] = useState('');
  const toolbarRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const lastValidTextRef = useRef<string>('');
  const lastValidPositionRef = useRef<SelectionPosition | null>(null);

  const capturedTextRef = useRef<string>('');
  const capturedPositionRef = useRef<SelectionPosition | null>(null);

  useEffect(() => {
    if (selectedText && selectedText.length >= 10 && position) {
      lastValidTextRef.current = selectedText;
      lastValidPositionRef.current = position;
    }
  }, [selectedText, position]);

  const hasValidSelection = selectedText && selectedText.length >= 10 && position;
  const hasLastValidSelection = lastValidTextRef.current && lastValidTextRef.current.length >= 10;

  if (!hasValidSelection && !showInput && !hasLastValidSelection) {
    return null;
  }

  const activePosition = showInput 
    ? (capturedPositionRef.current || lastValidPositionRef.current || position) 
    : (position || lastValidPositionRef.current);

  if (!activePosition) {
    return null;
  }

  const containerRect = containerRef.current?.getBoundingClientRect();
  if (!containerRect) return null;

  const toolbarTop = activePosition.top - containerRect.top - 50; // 50px above selection
  const toolbarLeft = activePosition.left - containerRect.left + (activePosition.width / 2);

  const adjustedTop = Math.max(10, toolbarTop);
  const adjustedLeft = Math.max(80, Math.min(toolbarLeft, containerRect.width - 80));

  const handleReviseClick = () => {
    const textToCapture = selectedText || lastValidTextRef.current;
    const positionToCapture = position || lastValidPositionRef.current;

    console.log('SelectionToolbar Revise clicked:', {
      selectedTextProp: selectedText?.substring(0, 30),
      lastValidText: lastValidTextRef.current?.substring(0, 30),
      textToCapture: textToCapture?.substring(0, 30),
      textLength: textToCapture?.length
    });

    if (!textToCapture || textToCapture.length < 10) {
      console.warn('SelectionToolbar: No valid text to capture');
      return;
    }

    capturedTextRef.current = textToCapture;
    capturedPositionRef.current = positionToCapture;

    onHighlightSelection?.();

    setShowInput(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleSubmitRevise = () => {
    const textToRevise = capturedTextRef.current;
    const instructionText = instruction.trim();

    console.log('SelectionToolbar submit:', { 
      instructionText, 
      capturedTextLength: textToRevise?.length,
      capturedTextPreview: textToRevise?.substring(0, 50)
    });

    if (instructionText && textToRevise) {
      onClearHighlight?.();
      onRevise(instructionText, textToRevise);
      setInstruction('');
      setShowInput(false);
      capturedTextRef.current = '';
      capturedPositionRef.current = null;
      lastValidTextRef.current = '';
      lastValidPositionRef.current = null;
    } else {
      console.warn('SelectionToolbar: Missing instruction or captured text', {
        hasInstruction: !!instructionText,
        hasCapturedText: !!textToRevise
      });
    }
  };

  const handleCancel = () => {
    onClearHighlight?.();
    setShowInput(false);
    setInstruction('');
    capturedTextRef.current = '';
    capturedPositionRef.current = null;
    lastValidTextRef.current = '';
    lastValidPositionRef.current = null;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmitRevise();
    }
    if (e.key === 'Escape') {
      handleCancel();
    }
  };

  return (
    <div
      ref={toolbarRef}
      className={styles.selectionToolbar}
      style={{
        top: `${adjustedTop}px`,
        left: `${adjustedLeft}px`,
        transform: 'translateX(-50%)',
      }}
      onMouseDown={(e) => e.preventDefault()} // Prevent selection loss
    >
      {!showInput ? (
        <div className={styles.selectionToolbarButtons}>
          <button
            className={styles.selectionToolbarBtn}
            onClick={handleReviseClick}
            disabled={isLoading}
            title="Revise with instruction"
          >
            ✏️ Revise
          </button>
          <button
            className={styles.selectionToolbarBtn}
            onClick={onExplain}
            disabled={isLoading}
            title="Explain this clause"
          >
            💡 Explain
          </button>
        </div>
      ) : (
        <div className={styles.selectionToolbarInput}>
          <input
            ref={inputRef}
            type="text"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="How should I revise this?"
            className={styles.selectionInput}
            disabled={isLoading}
          />
          <button
            className={styles.selectionSubmitBtn}
            onClick={handleSubmitRevise}
            disabled={isLoading || !instruction.trim()}
          >
            {isLoading ? '...' : '→'}
          </button>
          <button
            className={styles.selectionCancelBtn}
            onClick={handleCancel}
          >
            ×
          </button>
        </div>
      )}

      {/* Arrow pointing to selection */}
      <div className={styles.selectionToolbarArrow} />
    </div>
  );
}
