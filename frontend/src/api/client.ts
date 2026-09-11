import type {
  Alert,
  AlertFilters,
  AuditLogEntry,
  Camera,
  CameraHealth,
  ChainVerificationResult,
  EvidencePackage,
  Event,
  FPSDataPoint,
  HashVerificationResult,
  LoginCredentials,
  ModelVersion,
  PaginatedResponse,
  Personnel,
  TrackSighting,
  User,
  Zone,
  Tripwire,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

function getCookie(name: string): string | null {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop()?.split(';').shift() ?? null;
  }
  return null;
}

function setCookie(name: string, value: string, maxAgeSeconds: number): void {
  document.cookie = `${name}=${value}; max-age=${maxAgeSeconds}; path=/; SameSite=Strict`;
}

function deleteCookie(name: string): void {
  document.cookie = `${name}=; max-age=0; path=/`;
}

export function getAccessToken(): string | null {
  return getCookie('smartcctv_access_token') ?? localStorage.getItem('smartcctv_access_token');
}

export function setAccessToken(token: string, expiresIn: number): void {
  setCookie('smartcctv_access_token', token, expiresIn);
  localStorage.setItem('smartcctv_access_token', token);
}

export function clearTokens(): void {
  deleteCookie('smartcctv_access_token');
  localStorage.removeItem('smartcctv_access_token');
}

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

let isRefreshing = false;
let refreshQueue: Array<(token: string | null) => void> = [];

async function refreshToken(): Promise<string | null> {
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) return null;
    const data = await res.json();
    setAccessToken(data.access_token, data.expires_in ?? 3600);
    return data.access_token as string;
  } catch {
    return null;
  }
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { skipAuth = false, headers: extraHeaders = {}, ...rest } = options;

  const buildHeaders = (token?: string | null): Record<string, string> => {
    const h: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(extraHeaders as Record<string, string>),
    };
    if (!skipAuth && token) {
      h['Authorization'] = `Bearer ${token}`;
    }
    return h;
  };

  const token = getAccessToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    credentials: 'include',
    headers: buildHeaders(token),
  });

  if (response.status === 401 && !skipAuth) {
    if (isRefreshing) {
      return new Promise<T>((resolve, reject) => {
        refreshQueue.push(async (newToken) => {
          if (!newToken) {
            reject(new Error('Authentication failed'));
            return;
          }
          try {
            const retryRes = await fetch(`${BASE_URL}${path}`, {
              ...rest,
              credentials: 'include',
              headers: buildHeaders(newToken),
            });
            if (!retryRes.ok) reject(new Error(`Request failed: ${retryRes.status}`));
            else resolve((await retryRes.json()) as T);
          } catch (err) {
            reject(err);
          }
        });
      });
    }

    isRefreshing = true;
    const newToken = await refreshToken();
    isRefreshing = false;
    refreshQueue.forEach((cb) => cb(newToken));
    refreshQueue = [];

    if (!newToken) {
      clearTokens();
      window.location.href = '/login';
      throw new Error('Session expired');
    }

    const retryRes = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      credentials: 'include',
      headers: buildHeaders(newToken),
    });

    if (!retryRes.ok) {
      const errBody = await retryRes.text().catch(() => '');
      throw new Error(`Request failed ${retryRes.status}: ${errBody}`);
    }
    return (await retryRes.json()) as T;
  }

  if (!response.ok) {
    const errBody = await response.text().catch(() => '');
    throw new Error(`Request failed ${response.status}: ${errBody}`);
  }

  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

// ============================================================
// Auth
// ============================================================
export async function apiLogin(credentials: LoginCredentials) {
  return apiFetch<{ access_token: string; token_type: string; expires_in: number; user: User }>(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify(credentials),
      skipAuth: true,
    }
  );
}

export async function apiLogout(): Promise<void> {
  await apiFetch<void>('/auth/logout', { method: 'POST' });
  clearTokens();
}

export async function apiGetCurrentUser(): Promise<User> {
  return apiFetch<User>('/auth/me');
}

// ============================================================
// Alerts
// ============================================================
export async function getAlerts(
  filters?: AlertFilters,
  page = 1,
  pageSize = 50
): Promise<PaginatedResponse<Alert>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters?.severity?.length) params.set('severity', filters.severity.join(','));
  if (filters?.camera_id) params.set('camera_id', filters.camera_id);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  if (filters?.disposition) params.set('disposition', filters.disposition);
  if (filters?.event_type) params.set('event_type', filters.event_type);
  return apiFetch<PaginatedResponse<Alert>>(`/alerts?${params}`);
}

export async function getAlert(alertId: string): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}`);
}

export async function disposeAlert(
  alertId: string,
  disposition: string,
  reason?: string
): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}/disposition`, {
    method: 'POST',
    body: JSON.stringify({ disposition, reason }),
  });
}

export async function bulkDisposeAlerts(
  alertIds: string[],
  disposition: string,
  reason?: string
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>('/alerts/bulk-disposition', {
    method: 'POST',
    body: JSON.stringify({ alert_ids: alertIds, disposition, reason }),
  });
}

// ============================================================
// Cameras
// ============================================================
export async function getCameras(): Promise<Camera[]> {
  return apiFetch<Camera[]>('/cameras');
}

export async function getCamera(cameraId: string): Promise<Camera> {
  return apiFetch<Camera>(`/cameras/${cameraId}`);
}

export async function getCameraHealth(cameraId: string): Promise<CameraHealth> {
  return apiFetch<CameraHealth>(`/cameras/${cameraId}/health`);
}

export async function getCameraFPSHistory(cameraId: string): Promise<FPSDataPoint[]> {
  return apiFetch<FPSDataPoint[]>(`/cameras/${cameraId}/fps-history`);
}

// ============================================================
// Events
// ============================================================
export async function getEvents(
  filters?: Partial<AlertFilters>,
  page = 1,
  pageSize = 50
): Promise<PaginatedResponse<Event>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters?.camera_id) params.set('camera_id', filters.camera_id);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  if (filters?.severity?.length) params.set('severity', filters.severity.join(','));
  if (filters?.event_type) params.set('event_type', filters.event_type);
  return apiFetch<PaginatedResponse<Event>>(`/events?${params}`);
}

export async function getEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/events/${eventId}`);
}

export async function getEventAlerts(eventId: string): Promise<Alert[]> {
  return apiFetch<Alert[]>(`/events/${eventId}/alerts`);
}

export async function getTrackSightings(trackId: string): Promise<TrackSighting[]> {
  return apiFetch<TrackSighting[]>(`/tracks/${trackId}/sightings`);
}

// ============================================================
// Evidence
// ============================================================
export async function getEvidencePackage(eventId: string): Promise<EvidencePackage> {
  return apiFetch<EvidencePackage>(`/evidence/${eventId}`);
}

export async function verifyEvidenceHash(
  packageId: string,
  component: string
): Promise<HashVerificationResult> {
  return apiFetch<HashVerificationResult>(`/evidence/${packageId}/verify`, {
    method: 'POST',
    body: JSON.stringify({ component }),
  });
}

// ============================================================
// Audit Log
// ============================================================
export async function getAuditLog(
  page = 1,
  pageSize = 50,
  filters?: { actor?: string; action?: string; date_from?: string; date_to?: string }
): Promise<PaginatedResponse<AuditLogEntry>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters?.actor) params.set('actor', filters.actor);
  if (filters?.action) params.set('action', filters.action);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  return apiFetch<PaginatedResponse<AuditLogEntry>>(`/audit?${params}`);
}

export async function verifyAuditChain(): Promise<ChainVerificationResult> {
  return apiFetch<ChainVerificationResult>('/audit/verify-chain');
}

// ============================================================
// Zones
// ============================================================
export async function getZones(): Promise<Zone[]> {
  return apiFetch<Zone[]>('/zones');
}

export async function getZone(zoneId: string): Promise<Zone> {
  return apiFetch<Zone>(`/zones/${zoneId}`);
}

export async function updateZone(zoneId: string, data: Partial<Zone>): Promise<Zone> {
  return apiFetch<Zone>(`/zones/${zoneId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function createZone(data: Omit<Zone, 'zone_id'>): Promise<Zone> {
  return apiFetch<Zone>('/zones', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================================
// Tripwires
// ============================================================
export async function getTripwires(cameraId?: string): Promise<Tripwire[]> {
  const path = cameraId ? `/tripwires?camera_id=${cameraId}` : '/tripwires';
  return apiFetch<Tripwire[]>(path);
}

// ============================================================
// Personnel
// ============================================================
export async function getPersonnel(): Promise<Personnel[]> {
  return apiFetch<Personnel[]>('/personnel');
}

export async function enrollPersonnel(
  data: Omit<Personnel, 'person_id' | 'enrolled_at' | 'face_enrolled'>,
  faceImage?: File
): Promise<Personnel> {
  if (faceImage) {
    const formData = new FormData();
    formData.append('data', JSON.stringify(data));
    formData.append('face_image', faceImage);
    const token = getAccessToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${BASE_URL}/personnel`, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });
    if (!res.ok) throw new Error(`Failed to enroll personnel: ${res.status}`);
    return (await res.json()) as Personnel;
  }
  return apiFetch<Personnel>('/personnel', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================================
// Models
// ============================================================
export async function getModelVersions(): Promise<ModelVersion[]> {
  return apiFetch<ModelVersion[]>('/models');
}

export async function deprecateModel(modelName: string, reason: string): Promise<ModelVersion> {
  return apiFetch<ModelVersion>(`/models/${modelName}/deprecate`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

// ============================================================
// Dashboard Stats
// ============================================================
export async function getDashboardStats(): Promise<{
  active_alerts: number;
  cameras_online: number;
  total_cameras: number;
  events_today: number;
  false_positive_rate: number;
  alert_trend: number;
  event_trend: number;
}> {
  return apiFetch('/dashboard/stats');
}
