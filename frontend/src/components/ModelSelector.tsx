'use client';

import React, { useState, useEffect, useCallback } from 'react';
import styles from './ModelSelector.module.css';
import { authedFetch } from '@/utils/auth';

const getBaseUrl = () => {
  if (typeof window === 'undefined') return '';
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:8000';
  }
  return process.env.NEXT_PUBLIC_BASE_URL || '';
};

const Icons = {
  openSource: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
    </svg>
  ),
  proprietary: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  ),
  shield: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  check: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  chevronDown: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
};

interface Model {
  id: string;
  display_name: string;
  min_tier: string;
  capabilities: string[];
  input_price_per_million: number;
  output_price_per_million: number;
  context_window: number;
  is_open_source: boolean;
  is_featured: boolean;
  estimated_cost_per_action: number;
}

interface ModelsResponse {
  models: Model[];
  user_tier: string;
  preferred_model: string | null;
  default_model: string;
  privacy_info: {
    title: string;
    summary: string;
    open_source_note: string;
    proprietary_note: string;
    bullet_points: string[];
  };
}

interface ModelSelectorProps {
  onModelChange?: (modelId: string) => void;
  className?: string;
}

export default function ModelSelector({ onModelChange, className }: ModelSelectorProps) {
  const [models, setModels] = useState<Model[]>([]);
  const [userTier, setUserTier] = useState<string>('free_trial');
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [defaultModel, setDefaultModel] = useState<string>('');
  const [privacyInfo, setPrivacyInfo] = useState<ModelsResponse['privacy_info'] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showOtherModels, setShowOtherModels] = useState(false);

  const fetchModels = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl();
      const response = await authedFetch(`${baseUrl}/api/v1/models`, {
        method: 'GET',
      });

      if (response.ok) {
        const data: ModelsResponse = await response.json();
        setModels(data.models);
        setUserTier(data.user_tier);
        setSelectedModel(data.preferred_model || data.default_model);
        setDefaultModel(data.default_model);
        setPrivacyInfo(data.privacy_info);
        setError(null);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error('[ModelSelector] API error:', response.status, errorData);
        setError(errorData.error || `Failed to load models (${response.status})`);
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AuthExpiredError') return;
      console.error('[ModelSelector] Network error:', err);
      setError('Failed to connect to server');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleModelSelect = async (modelId: string) => {
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const baseUrl = getBaseUrl();
      const response = await authedFetch(`${baseUrl}/api/v1/user/model`, {
        method: 'PUT',
        body: JSON.stringify({ model_id: modelId }),
      });

      if (response.ok) {
        setSelectedModel(modelId);
        setSuccessMessage('Model preference saved');
        onModelChange?.(modelId);

        setTimeout(() => setSuccessMessage(null), 2000);
      } else {
        const data = await response.json();
        setError(data.error || 'Failed to save preference');
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AuthExpiredError') return;
      setError('Failed to save preference');
    } finally {
      setIsSaving(false);
    }
  };

  const formatTokenPrice = (pricePerMillion: number) => {
    if (pricePerMillion === 0) return 'Free';
    if (pricePerMillion < 0.01) return `$${(pricePerMillion * 1000).toFixed(2)}/B`;
    if (pricePerMillion < 1) return `$${pricePerMillion.toFixed(2)}/M`;
    return `$${pricePerMillion.toFixed(1)}/M`;
  };

  const formatContext = (tokens: number) => {
    if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
    return `${Math.round(tokens / 1000)}K`;
  };

  const featuredModels = models.filter(m => m.is_featured);
  const otherModels = models.filter(m => !m.is_featured);

  const featuredOpenSource = featuredModels.filter(m => m.is_open_source);
  const featuredProprietary = featuredModels.filter(m => !m.is_open_source);

  const renderModelCard = (model: Model) => {
    const isLocked = model.min_tier !== 'free_trial' && model.min_tier !== userTier && 
      ['free_trial'].includes(userTier);

    return (
      <button
        key={model.id}
        className={`${styles.modelCard} ${selectedModel === model.id ? styles.selected : ''} ${isLocked ? styles.locked : ''}`}
        onClick={() => !isLocked && handleModelSelect(model.id)}
        disabled={isSaving || isLocked}
      >
        <div className={styles.modelHeader}>
          <span className={styles.modelName}>
            {model.display_name}
            {isLocked && <span className={styles.lockIcon}>{model.min_tier.replace('_', ' ')}</span>}
          </span>
          {selectedModel === model.id && <span className={styles.checkmark}>{Icons.check()}</span>}
        </div>
        <div className={styles.modelMeta}>
          <span className={styles.modelCost}>
            {formatTokenPrice(model.input_price_per_million)} read · {formatTokenPrice(model.output_price_per_million)} write
          </span>
          <span className={styles.modelContext}>{formatContext(model.context_window)} context</span>
        </div>
      </button>
    );
  };

  if (isLoading) {
    return (
      <div className={`${styles.container} ${className || ''}`}>
        <div className={styles.loading}>Loading models...</div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className || ''}`}>
      {/* Tier badge */}
      <div className={styles.tierRow}>
        <span className={styles.tierLabel}>Your tier:</span>
        <span className={styles.tierBadge}>{userTier.replace('_', ' ').toUpperCase()}</span>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {successMessage && <div className={styles.success}>{successMessage}</div>}

      {/* Featured Open Source Models */}
      {featuredOpenSource.length > 0 && (
        <div className={styles.modelGroup}>
          <div className={styles.groupHeader}>
            <span className={styles.groupIcon}>{Icons.openSource()}</span>
            <span className={styles.groupTitle}>OPEN-SOURCE (ZDR)</span>
            <span className={styles.groupNote}>Routed via OpenRouter, data not stored or trained on</span>
          </div>
          <div className={styles.modelList}>
            {featuredOpenSource.map(renderModelCard)}
          </div>
        </div>
      )}

      {/* Featured Proprietary Models */}
      {featuredProprietary.length > 0 && (
        <div className={styles.modelGroup}>
          <div className={styles.groupHeader}>
            <span className={styles.groupIcon}>{Icons.proprietary()}</span>
            <span className={styles.groupTitle}>PROPRIETARY</span>
            <span className={styles.groupNote}>Subject to provider terms</span>
          </div>
          <div className={styles.modelList}>
            {featuredProprietary.map(renderModelCard)}
          </div>
        </div>
      )}

      {/* Other Models - Collapsible */}
      {otherModels.length > 0 && (
        <div className={styles.otherModelsSection}>
          <button 
            className={`${styles.otherModelsToggle} ${showOtherModels ? styles.expanded : ''}`}
            onClick={() => setShowOtherModels(!showOtherModels)}
          >
            <span>Other models ({otherModels.length})</span>
            <span className={styles.chevron}>{Icons.chevronDown()}</span>
          </button>

          {showOtherModels && (
            <div className={styles.otherModelsList}>
              {otherModels.map(renderModelCard)}
            </div>
          )}
        </div>
      )}

      {/* Privacy Info */}
      {privacyInfo && (
        <div className={styles.privacyBox}>
          <div className={styles.privacyHeader}>
            <span className={styles.privacyIcon}>{Icons.shield()}</span>
            <span className={styles.privacyTitle}>{privacyInfo.title}</span>
          </div>
          <p className={styles.privacyText}>{privacyInfo.summary}</p>
          <ul className={styles.privacyList}>
            {privacyInfo.bullet_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
