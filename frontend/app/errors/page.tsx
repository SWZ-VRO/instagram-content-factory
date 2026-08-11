import { listLogs } from "@/lib/api";

export const dynamic = "force-dynamic";

const LEVEL_COLOR: Record<string, string> = {
  ERROR: "text-red-400",
  WARNING: "text-amber-400",
  INFO: "text-gray-400",
};

export default async function ErrorsPage() {
  let logs;
  let error: string | null = null;
  try {
    logs = await listLogs();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  if (error || !logs) {
    return <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load logs ({error}).</div>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Errors &amp; Events ({logs.length})</h2>
      <p className="text-sm text-gray-500">
        §35 error codes: MISSING_CAPTION, INVALID_MEDIA, UPLOAD_FAILED, PUBLISH_FAILED, TOKEN_EXPIRED, RATE_LIMIT,
        ACCOUNT_AUTH_ERROR, SCHEDULING_CONFLICT, CONTENT_SHORTAGE, POSSIBLE_DUPLICATE.
      </p>

      {logs.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No errors logged. Good sign.
        </div>
      ) : (
        <div className="divide-y divide-gray-800 rounded-lg border border-gray-800">
          {logs.map((l) => (
            <div key={l.id} className="flex items-start gap-3 px-4 py-3 text-sm">
              <span className="w-40 shrink-0 text-gray-500">{new Date(l.timestamp).toLocaleString()}</span>
              <span className={`w-32 shrink-0 font-mono text-xs ${LEVEL_COLOR[l.level] ?? "text-gray-400"}`}>
                {l.code ?? l.level}
              </span>
              <span className="text-gray-300">{l.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
