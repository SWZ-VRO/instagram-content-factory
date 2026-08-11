const TONE_BY_STATUS: Record<string, string> = {
  AVAILABLE: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
  RESERVED: "bg-blue-950/40 text-blue-300 border-blue-800",
  SCHEDULED: "bg-blue-950/40 text-blue-300 border-blue-800",
  PUBLISHED: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
  FAILED: "bg-red-950/40 text-red-300 border-red-800",
  CANCELLED: "bg-gray-800 text-gray-400 border-gray-700",
  MISSING_CAPTION: "bg-amber-950/40 text-amber-300 border-amber-800",
  QUEUED: "bg-gray-800 text-gray-300 border-gray-700",
  UPLOADING: "bg-blue-950/40 text-blue-300 border-blue-800",
  RETRYING: "bg-amber-950/40 text-amber-300 border-amber-800",
  ACTIVE: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
  PAUSED: "bg-amber-950/40 text-amber-300 border-amber-800",
  DISABLED: "bg-gray-800 text-gray-400 border-gray-700",
  CONNECTED: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
  TOKEN_EXPIRING: "bg-amber-950/40 text-amber-300 border-amber-800",
  TOKEN_EXPIRED: "bg-red-950/40 text-red-300 border-red-800",
  DISCONNECTED: "bg-gray-800 text-gray-400 border-gray-700",
  ERROR: "bg-red-950/40 text-red-300 border-red-800",
  DRAFT: "bg-gray-800 text-gray-300 border-gray-700",
  REVIEW: "bg-amber-950/40 text-amber-300 border-amber-800",
  APPROVED: "bg-emerald-950/40 text-emerald-300 border-emerald-800",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = TONE_BY_STATUS[status] ?? "bg-gray-800 text-gray-300 border-gray-700";
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>{status}</span>;
}
