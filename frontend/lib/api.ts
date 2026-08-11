// Base URL of the FastAPI backend. This is read server-side only (every
// page here is a Server Component), so it deliberately does NOT use the
// NEXT_PUBLIC_ prefix: that prefix signals "safe to inline into the client
// bundle", which this value is not (inside Docker it resolves to the
// backend's *internal* compose hostname, which isn't reachable from the
// browser). Set API_URL in the frontend container's env (see
// docker-compose.yml).
const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

export interface DashboardSummary {
  accounts_total: number;
  accounts_active: number;
  masters_total: number;
  variants_by_status: Record<string, number>;
  missing_captions: number;
  dry_run: boolean;
}

export interface MasterSummary {
  id: string;
  master_code: string;
  filename: string;
  status: string;
  created_at: string;
  variant_count: number;
  available_count: number;
  consumed_count: number;
  accounts_used: number;
}

export interface Account {
  id: string;
  username: string;
  timezone: string;
  status: string;
  connection_status: string;
  daily_min_posts: number;
  daily_max_posts: number;
  active: boolean;
  created_at: string;
}

export interface InventoryRow {
  master_code: string;
  variant_code: string;
  caption_text: string | null;
  account_username: string | null;
  scheduled_at_utc: string | null;
  status: string;
}

export interface CalendarPlan {
  id: string;
  status: string;
  approved_at: string | null;
  params: Record<string, unknown> | null;
  created_at: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: string;
  code: string | null;
  message: string;
}

export interface PublishingJob {
  id: string;
  scheduled_post_id: string;
  status: string;
  attempts: number;
  last_error: string | null;
  account_username: string | null;
  variant_code: string | null;
  scheduled_at_utc: string | null;
}

export interface PublishingStatus {
  paused: boolean;
  due_now: number;
  by_status: Record<string, number>;
}

export const getDashboardSummary = () => apiGet<DashboardSummary>("/dashboard/summary");
export const listAccounts = () => apiGet<Account[]>("/accounts?limit=500");
export const listMasters = () => apiGet<MasterSummary[]>("/masters?limit=500");
export const listInventory = (status?: string) =>
  apiGet<InventoryRow[]>(`/inventory?limit=500${status ? `&status=${status}` : ""}`);
export const listCalendarPlans = () => apiGet<CalendarPlan[]>("/calendar/plans?limit=100");
export const listLogs = () => apiGet<LogEntry[]>("/logs?limit=200");
export const listPublishingJobs = () => apiGet<PublishingJob[]>("/publishing/jobs?limit=200");
export const getPublishingStatus = () => apiGet<PublishingStatus>("/publishing/status");
