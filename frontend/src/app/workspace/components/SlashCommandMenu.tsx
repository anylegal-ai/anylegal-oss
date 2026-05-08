'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import styles from './SlashCommandMenu.module.css';

export interface SlashCommand {
  id: string;
  name: string;
  description: string;
  icon?: React.ReactNode;
  skill?: string;  // Backend skill name (e.g., "contract-review")
  emoji?: string;  // Emoji from skill metadata
}

const SKILL_ICONS: Record<string, React.ReactNode> = {
  'review': (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/>
      <rect x="9" y="3" width="6" height="4" rx="1"/>
      <path d="M9 14l2 2 4-4"/>
    </svg>
  ),
  'research': (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="8"/>
      <path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  'compare': (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="4" width="8" height="16" rx="1"/>
      <rect x="14" y="4" width="8" height="16" rx="1"/>
      <path d="M10 12h4" strokeDasharray="2 2"/>
    </svg>
  ),
  'draft': (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="12" y1="18" x2="12" y2="12"/>
      <line x1="9" y1="15" x2="15" y2="15"/>
    </svg>
  ),
  'compact': (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M19.4 14.6L9.8 5l3.5-3.5 9.6 9.6L19.4 14.6z"/>
      <path d="M9.8 5l-7 7c-.8.8-.8 2 0 2.8l4.4 4.4c.8.8 2 .8 2.8 0l7-7"/>
      <path d="M3 21h6"/>
    </svg>
  ),
};

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: 'review',
    name: '/review',
    description: 'Review document against playbook, flag risks, suggest changes',
    skill: 'review',
    icon: SKILL_ICONS['review'],
  },
  {
    id: 'research',
    name: '/research',
    description: 'Research a legal topic with citations (100+ jurisdictions)',
    skill: 'research',
    icon: SKILL_ICONS['research'],
  },
  {
    id: 'compare',
    name: '/compare',
    description: 'Compare two document versions and produce a redline',
    skill: 'compare',
    icon: SKILL_ICONS['compare'],
  },
  {
    id: 'draft',
    name: '/draft',
    description: 'Draft a new document, clause, or section',
    skill: 'draft',
    icon: SKILL_ICONS['draft'],
  },
  {
    id: 'compact',
    name: '/compact',
    description: 'Compact the conversation to free up context',
    icon: SKILL_ICONS['compact'],
  },
];

export function useSlashCommands(): {
  commands: SlashCommand[];
  loading: boolean;
  error: string | null;
} {
  const [commands, setCommands] = useState<SlashCommand[]>(SLASH_COMMANDS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchCommands = async () => {
      setLoading(true);
      try {
        const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:8000';
        const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
        const response = await fetch(`${baseUrl}/api/v1/editor/chat/agentic/skills`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        });
        if (response.ok) {
          const data = await response.json();

          const dynamicCommands: SlashCommand[] = (data.slash_commands || []).map((cmd: {
            command: string;
            skill: string;
            description: string;
            emoji?: string;
          }) => ({
            id: cmd.command.replace('/', ''),
            name: cmd.command,
            description: cmd.description,
            skill: cmd.skill,
            emoji: cmd.emoji,
            icon: SKILL_ICONS[cmd.skill] || null,
          }));

          if (dynamicCommands.length > 0) {
            const dynamicIds = new Set(dynamicCommands.map((c: SlashCommand) => c.id));
            const localOnly = SLASH_COMMANDS.filter(c => !dynamicIds.has(c.id));
            setCommands([...dynamicCommands, ...localOnly]);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch dynamic slash commands, using defaults:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch');
      } finally {
        setLoading(false);
      }
    };

    fetchCommands();
  }, []);

  return { commands, loading, error };
}

interface SlashCommandMenuProps {
  isOpen: boolean;
  filter: string; // The text after "/" for filtering
  onSelect: (command: SlashCommand) => void;
  onClose: () => void;
  position?: { bottom: number; left: number };
  commands?: SlashCommand[]; // Optional override for commands list
}

export default function SlashCommandMenu({
  isOpen,
  filter,
  onSelect,
  onClose,
  position,
  commands: externalCommands,
}: SlashCommandMenuProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  const availableCommands = externalCommands || SLASH_COMMANDS;

  const filteredCommands = availableCommands.filter(cmd => {
    const searchTerm = filter.toLowerCase();
    return cmd.name.toLowerCase().includes(searchTerm) || 
           cmd.description.toLowerCase().includes(searchTerm);
  });

  useEffect(() => {
    setSelectedIndex(0);
  }, [filter]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!isOpen) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < filteredCommands.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev > 0 ? prev - 1 : filteredCommands.length - 1
        );
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          onSelect(filteredCommands[selectedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
      case 'Tab':
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          onSelect(filteredCommands[selectedIndex]);
        }
        break;
    }
  }, [isOpen, filteredCommands, selectedIndex, onSelect, onClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, onClose]);

  if (!isOpen || filteredCommands.length === 0) return null;

  return (
    <div 
      ref={menuRef}
      className={styles.menu}
      style={position ? { bottom: position.bottom, left: position.left } : undefined}
    >
      <div className={styles.header}>
        <span className={styles.headerTitle}>Commands</span>
        <span className={styles.headerHint}>↑↓ to navigate, Enter to select</span>
      </div>
      <div className={styles.list}>
        {filteredCommands.map((cmd, index) => (
          <button
            key={cmd.id}
            className={`${styles.item} ${index === selectedIndex ? styles.itemSelected : ''}`}
            onClick={() => onSelect(cmd)}
            onMouseEnter={() => setSelectedIndex(index)}
          >
            <span className={styles.itemIcon}>
              {cmd.icon || (cmd.emoji ? <span className={styles.emoji}>{cmd.emoji}</span> : null)}
            </span>
            <span className={styles.itemContent}>
              <span className={styles.itemName}>{cmd.name}</span>
              <span className={styles.itemDescription}>{cmd.description}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
