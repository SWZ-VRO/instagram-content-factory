import { revalidatePath } from "next/cache";

import { StatCard } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { getPublishingStatus, listPublishingJobs } from "@/lib/api";

export const dynamic = "force-dynamic";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function togglePause(formData: FormData) {
  "use server";
  const action = formData.get("action");
  await fetch(`${API_URL}/publishing/${action}`, { method: "POST" });
  revalidatePath("/queue");
}

async function runNow() {
  "use server";
  await fetch(`${API_URL}/publishing/start`, { method: "POST" });
  revalidatePath("/queue");
}

export default async function QueuePage() {
  let jobs, publishingStatus;
  let error: string | null = null;
  try {
    [jobs, publishingStatus] = await Promise.all([listPublishingJobs(), getPublishingStatus()]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  if (error || !jobs || !publishingStatus) {
    return <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load the queue ({error}).</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Publishing Queue</h2>
        <div className="flex gap-2">
          <form action={runNow}>
            <button className="rounded bg-gray-800 px-3 py-1.5 text-xs font-medium hover:bg-gray-700">RUN NOW</button>
          </form>
          <form action={togglePause}>
            <input type="hidden" name="action" value={publishingStatus.paused ? "resume" : "pause"} />
            <button
              className={`rounded px-3 py-1.5 text-xs font-medium ${
                publishingStatus.paused ? "bg-emerald-700 hover:bg-emerald-600" : "bg-amber-800 hover:bg-amber-700"
              }`}
            >
              {publishingStatus.paused ? "RESUME PUBLISHING" : "PAUSE ALL PUBLISHING"}
            </button>
          </form>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Worker state" value={publishingStatus.paused ? "Paused" : "Running"} tone={publishingStatus.paused ? "warning" : "success"} />
        <StatCard label="Due now" value={publishingStatus.due_now} />
        <StatCard label="Scheduled" value={publishingStatus.by_status.SCHEDULED ?? 0} />
        <StatCard label="Published" value={publishingStatus.by_status.PUBLISHED ?? 0} tone="success" />
      </div>

      {jobs.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No publishing jobs yet -- jobs appear once a plan is approved and posts become due.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-900 text-xs uppercase text-gray-400">
              <tr>
                <th className="px-4 py-3">Account</th>
                <th className="px-4 py-3">Variant</th>
                <th className="px-4 py-3">Scheduled</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Attempts</th>
                <th className="px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {jobs.map((j) => (
                <tr key={j.id} className="hover:bg-gray-900/50">
                  <td className="px-4 py-3">{j.account_username ?? "—"}</td>
                  <td className="px-4 py-3 font-medium">{j.variant_code ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-400">
                    {j.scheduled_at_utc ? new Date(j.scheduled_at_utc).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={j.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-400">{j.attempts}</td>
                  <td className="max-w-xs truncate px-4 py-3 text-red-400">{j.last_error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
