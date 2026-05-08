import React, { useState } from 'react';
import type { DraftMode } from '../types/workspace';
import styles from '../workspace.module.css';
import PlaybookPickerModal from '@/components/PlaybookPickerModal';

interface DraftFormProps {
  draftMode: DraftMode;
  onDraftModeChange: (mode: DraftMode) => void;
  draftPrompt: string;
  onDraftPromptChange: (value: string) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  onSelectTemplate?: (content: string, name: string) => void;
}

export function DraftForm({
  draftMode,
  onDraftModeChange,
  draftPrompt,
  onDraftPromptChange,
  onGenerate,
  isGenerating,
  onSelectTemplate,
}: DraftFormProps) {
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);

  return (
    <div className={styles.draftOverlay}>
      <div className={styles.draftFormCard}>
        <h2 className={styles.draftFormTitle}>Draft New Legal Document</h2>
        <p className={styles.draftFormSubtitle}>Describe what you need and AI will generate it</p>

        <div className={styles.draftModeToggle}>
          <button
            className={styles.fromTemplateBtn}
            onClick={() => setShowTemplatePicker(true)}
            title="Start from a saved template"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            From Template
          </button>
          <button 
            className={draftMode === 'clause' ? styles.active : ''} 
            onClick={() => onDraftModeChange('clause')}
          >
            Single Clause
          </button>
          <button 
            className={draftMode === 'agreement' ? styles.active : ''} 
            onClick={() => onDraftModeChange('agreement')}
          >
            Full Agreement
          </button>
        </div>

        <textarea
          className={styles.draftTextarea}
          value={draftPrompt}
          onChange={(e) => onDraftPromptChange(e.target.value)}
          placeholder={draftMode === 'clause' 
            ? "E.g., Limitation of liability clause capping damages at contract value..."
            : "E.g., NDA between two tech companies for software development collaboration..."}
          rows={3}
        />

        <button 
          className={styles.draftGenerateBtn}
          onClick={onGenerate}
          disabled={isGenerating || !draftPrompt}
        >
          {isGenerating ? 'Generating...' : `Generate ${draftMode === 'clause' ? 'Clause' : 'Agreement'}`}
        </button>
      </div>

      {/* Template Picker Modal */}
      <PlaybookPickerModal
        isOpen={showTemplatePicker}
        onClose={() => setShowTemplatePicker(false)}
        showTabs={['templates']}
        initialTab="templates"
        title="Select Template"
        onSelectTemplate={(template) => {
          onSelectTemplate?.(template.content, template.name);
        }}
      />
    </div>
  );
}
