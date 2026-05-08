'use client';

import { useState, useCallback } from 'react';
import { getAuthHeaders, isTokenExpired, refreshAccessToken } from '@/utils/auth';

export interface ThreadListItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  source?: string;  // 'web' | 'telegram'
}

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';
const THREADS_LIMIT = 10;

export function useThreadList() {
  const [threads, setThreads] = useState<ThreadListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchThreads = useCallback(async () => {
    if (isTokenExpired()) {
      const refreshed = await refreshAccessToken();
      if (!refreshed) {
        setError('Session expired');
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${BASE_URL}/api/v1/threads?page=1&limit=${THREADS_LIMIT}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...getAuthHeaders(),
          } as HeadersInit,
        }
      );

      if (!response.ok) {
        if (response.status === 401) {
          const refreshed = await refreshAccessToken();
          if (refreshed) return fetchThreads();
          setError('Session expired');
          return;
        }
        throw new Error(`Failed to load threads: ${response.status}`);
      }

      const data = await response.json();
      setThreads(Array.isArray(data.threads) ? data.threads : []);
    } catch (err) {
      console.error('Error fetching threads:', err);
      setError(err instanceof Error ? err.message : 'Failed to load');
      setThreads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteThread = useCallback(async (threadId: string) => {
    try {
      const response = await fetch(`${BASE_URL}/api/v1/threads/${threadId}`, {
        method: 'DELETE',
        headers: { ...getAuthHeaders() } as HeadersInit,
      });
      if (response.ok) {
        setThreads((prev) => prev.filter((t) => t.id !== threadId));
        return true;
      }
    } catch (err) {
      console.error('Error deleting thread:', err);
    }
    return false;
  }, []);

  return { threads, loading, error, fetchThreads, deleteThread };
}
