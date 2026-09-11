// All TypeScript interfaces for SmartCCTV Border Intelligence Platform

export type HealthState = 'healthy' | 'degraded' | 'offline' | 'unknown';
export type SeverityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type DispositionStatus = 'pending' | 'confirmed' | 'false_positive' | 'inconclusive';
export type UserRole = 'operator' | 'analyst' | 'admin' | 'viewer';
export type CameraType = 'PTZ' | 'fixed' | 'thermal' | 'multispectral';
export type ZoneSensitivity = 'low' | 'medium' | 'high' | 'critical';
export type EventType =
  | 'perimeter_intrusion'
  | 'no_traceable_origin'
  | 'route_anomaly'
  | 'off_hours_activity'
  | 'behavior_anomaly'
  | 'unknown_identity'
  | 'group_clustering'
  | 'vehicle_intrusion';

export interface Camera {
  camera_id: string;
  name: string;
  location_name: string;
  gps_lat: number;
  gps_lon: number;
  health_state: HealthState;
  expected_fps: number;
  camera_type: CameraType;
  orientation?: number;
  is_active: boolean;
  stream_url?: string;
  capability_profile?: CapabilityProfile;
}

export interface CapabilityProfile {
  has_night_vision: boolean;
  has_thermal: boolean;
  has_ptz: boolean;
  resolution: string;
  coverage_radius_m: number;
}

export interface FactorBreakdown {
  zone_violation: boolean;
  no_traceable_origin: boolean;
  route_anomaly: boolean;
  off_hours: boolean;
  behavior_signals: boolean;
  identity_score: number;
  behavior_score: number;
  total_score: number;
  severity: SeverityLevel;
  zone_sensitivity_multiplier?: number;
  time_factor_multiplier?: number;
  explanation?: string;
}

export interface Alert {
  alert_id: string;
  event_id: string;
  event_type: EventType;
  severity: SeverityLevel;
  risk_score: number;
  camera_id: string;
  camera_name: string;
  timestamp: string;
  factor_breakdown: FactorBreakdown;
  snapshot_url?: string;
  disposition: DispositionStatus;
  global_identity_id?: string;
  zone_id?: string;
  zone_name?: string;
  acknowledged_by?: string;
  acknowledged_at?: string;
  notes?: string;
}

export interface Event {
  event_id: string;
  event_type: EventType;
  severity: SeverityLevel;
  risk_score: number;
  camera_id: string;
  camera_name: string;
  zone_id?: string;
  zone_name?: string;
  timestamp: string;
  ended_at?: string;
  duration_seconds?: number;
  track_id?: string;
  global_identity_id?: string;
  factor_breakdown: FactorBreakdown;
  alert_ids: string[];
  evidence_package_id?: string;
  status: 'active' | 'resolved' | 'investigating';
}

export interface CameraHealth {
  health_id: string;
  camera_id: string;
  state: HealthState;
  fps_actual: number;
  fps_expected: number;
  timestamp: string;
  blank_frame_score: number;
  sharpness_score: number;
  latency_ms?: number;
  uptime_seconds?: number;
}

export interface FPSDataPoint {
  timestamp: string;
  fps: number;
}

export interface TrackSighting {
  sighting_id: string;
  track_id: string;
  camera_id: string;
  camera_name: string;
  zone_id?: string;
  zone_name?: string;
  timestamp: string;
  confidence: number;
  location: {
    lat: number;
    lon: number;
  };
  reid_link_type?: 'confirmed' | 'provisional';
  reid_confidence?: number;
}

export interface User {
  user_id: string;
  username: string;
  role: UserRole;
  full_name?: string;
  last_login?: string;
  is_active: boolean;
}

export interface EvidencePackage {
  event_id: string;
  package_id: string;
  pre_clip_url?: string;
  post_clip_url?: string;
  snapshot_url?: string;
  hashes: {
    snapshot_sha256?: string;
    pre_clip_sha256?: string;
    post_clip_sha256?: string;
    package_sha256?: string;
  };
  model_versions: ModelVersion[];
  verification_status: 'verified' | 'unverified' | 'tampered' | 'pending';
  created_at: string;
  chain_hash?: string;
  encryption_status: 'encrypted' | 'unencrypted';
}

export interface ModelVersion {
  model_name: string;
  version: string;
  type: 'detection' | 'reid' | 'behavior' | 'pose';
  deployed_at: string;
  is_current: boolean;
  accuracy_metrics?: Record<string, number>;
}

export interface Zone {
  zone_id: string;
  name: string;
  sensitivity_level: ZoneSensitivity;
  polygon_points: Array<{ lat: number; lon: number }>;
  is_active: boolean;
  camera_ids: string[];
  description?: string;
  permitted_hours?: { start: string; end: string };
  tripwire_ids?: string[];
}

export interface Tripwire {
  tripwire_id: string;
  camera_id: string;
  name: string;
  start_point: { x: number; y: number };
  end_point: { x: number; y: number };
  permitted_direction: 'both' | 'left_to_right' | 'right_to_left' | 'none';
  is_active: boolean;
  sensitivity: ZoneSensitivity;
}

export interface AuditLogEntry {
  log_id: string;
  timestamp: string;
  actor_id: string;
  actor_username: string;
  actor_role: UserRole;
  action: AuditAction;
  target_type?: string;
  target_id?: string;
  details?: Record<string, unknown>;
  ip_address: string;
  chain_hash: string;
  prev_hash: string;
  chain_valid: boolean;
}

export type AuditAction =
  | 'LOGIN'
  | 'LOGOUT'
  | 'ALERT_DISPOSITION'
  | 'CONFIG_CHANGE'
  | 'ADMIN_ACTION'
  | 'EVIDENCE_ACCESS'
  | 'EXPORT'
  | 'MODEL_DEPLOY'
  | 'ZONE_MODIFY'
  | 'CAMERA_MODIFY'
  | 'PERSONNEL_ENROLL';

export interface Personnel {
  person_id: string;
  name: string;
  badge_number: string;
  department: string;
  authorized_zones: string[];
  enrolled_at: string;
  face_enrolled: boolean;
  is_active: boolean;
}

export interface AlertFilters {
  severity?: SeverityLevel[];
  camera_id?: string;
  date_from?: string;
  date_to?: string;
  disposition?: DispositionStatus;
  event_type?: EventType;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface ChainVerificationResult {
  is_valid: boolean;
  total_entries: number;
  broken_at?: string;
  verified_at: string;
}

export interface HashVerificationResult {
  is_valid: boolean;
  expected_hash: string;
  computed_hash: string;
  verified_at: string;
}
