// AnyLegal OSS — auth shim.
//
// OSS is single-tenant by design: every backend request runs as a fixed
// internal user (see backend/anylegal_oss/fastapi_app.py:OSS_USER_ID = 1).
// The backend ignores the Authorization header entirely. This module exists
// only so legacy fetch call sites in the frontend keep compiling without
// emitting a dead `/api/v1/refresh` call or redirecting users at a sign-in
// page that doesn't exist.
//
// If you wire real auth on top of this OSS variant, replace this file with
// the real token-management implementation; everything else (HistoryModal,
// useThreadList, useAgenticChat, etc.) just consumes these primitives.

export const clearAuthState = () => {
  if (typeof window === 'undefined') return;
  // Best-effort cleanup of any stale tokens left over from a non-OSS deploy
  // sharing the same browser origin.
  try {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('isAuthenticated');
    localStorage.removeItem('token_expires_at');
    localStorage.removeItem('activeThreadId');
    localStorage.removeItem('userContext');
    localStorage.removeItem('auth_timestamp');
  } catch {
    /* localStorage unavailable */
  }
};

export const getAuthHeaders = (): Record<string, string> => {
  return { 'Content-Type': 'application/json' };
};

export const isTokenExpired = (): boolean => false;

export const refreshAccessToken = async (): Promise<boolean> => true;

export class AuthExpiredError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'AuthExpiredError';
  }
}

export const authedFetch = async (
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> => {
  const headers = {
    ...(init.headers as Record<string, string> | undefined),
    ...getAuthHeaders(),
  };
  return fetch(input, { ...init, headers });
};

export const setAuthState = (
  _token: string,
  _expiresIn: number,
  _refreshToken?: string,
): void => {
  /* no-op: OSS is single-tenant */
};
