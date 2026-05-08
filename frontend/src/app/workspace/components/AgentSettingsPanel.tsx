import React from 'react';
import styles from '../workspace.module.css';

interface AgentSettingsPanelProps {
  onClose: () => void;
  onEditAgentConfig: () => void;
  onEditPlaybook: (path?: string) => void;
  onBrowseSkills: () => void;
  playbookCount?: number;
  skillsCount?: number;
}

export function AgentSettingsPanel({
  onClose,
  onEditAgentConfig,
  onEditPlaybook,
  onBrowseSkills,
  playbookCount = 0,
  skillsCount = 5,
}: AgentSettingsPanelProps) {
  return (
    <div className={styles.settingsOverlay} onClick={onClose}>
      <div className={styles.settingsPanel} onClick={(e) => e.stopPropagation()}>
        <div className={styles.settingsPanelHeader}>
          <h2 className={styles.settingsPanelTitle}>Agent Settings</h2>
          <p className={styles.settingsPanelDesc}>Configure how your AI assistant works. Changes apply to all future conversations.</p>
          <button className={styles.settingsPanelClose} onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className={styles.settingsCards}>
          {/* Agent Config */}
          <div className={styles.settingsCard}>
            <div className={styles.settingsCardIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
              </svg>
            </div>
            <div className={styles.settingsCardBody}>
              <h3 className={styles.settingsCardTitle}>Agent Config</h3>
              <p className={styles.settingsCardText}>
                Define your AI&apos;s expertise, tone, and behavior. Loaded on every request.
              </p>
              <div className={styles.settingsCardMeta}>anylegal.md</div>
            </div>
            <button className={styles.settingsCardBtn} onClick={onEditAgentConfig}>Edit</button>
          </div>

          {/* Playbook */}
          <div className={styles.settingsCard}>
            <div className={styles.settingsCardIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
              </svg>
            </div>
            <div className={styles.settingsCardBody}>
              <h3 className={styles.settingsCardTitle}>Playbook</h3>
              <p className={styles.settingsCardText}>
                Your standard clause positions for contract reviews, drafting, and negotiations.
              </p>
              <div className={styles.settingsCardMeta}>{playbookCount} file{playbookCount !== 1 ? 's' : ''}</div>
            </div>
            <div className={styles.settingsCardActions}>
              <button className={styles.settingsCardBtn} onClick={() => onEditPlaybook()}>Edit</button>
              <button className={styles.settingsCardBtnSecondary} onClick={() => onEditPlaybook()}>+ Add</button>
            </div>
          </div>

          {/* Skills */}
          <div className={styles.settingsCard}>
            <div className={styles.settingsCardIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>
            <div className={styles.settingsCardBody}>
              <h3 className={styles.settingsCardTitle}>Skills</h3>
              <p className={styles.settingsCardText}>
                Review, drafting, and research tools the agent can use. Activated by task type.
              </p>
              <div className={styles.settingsCardMeta}>{skillsCount} built-in</div>
            </div>
            <button className={styles.settingsCardBtn} onClick={onBrowseSkills}>Browse</button>
          </div>
        </div>

        <div className={styles.settingsFooter}>
          <p className={styles.settingsFooterText}>
            These settings define how your AI assistant behaves across all conversations and document work.
          </p>
        </div>
      </div>
    </div>
  );
}
