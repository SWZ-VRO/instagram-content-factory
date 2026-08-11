import { StatusBadge } from "@/components/StatusBadge";
import { listInventory } from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUSES = ["AVAILABLE", "MISSING_CAPTION", "RESERVED", "SCHEDULED", "PUBLISHED", "FAILED"];

// Next.js 14 passes searchParams synchronously (the async/Promise-wrapped
// searchParams API is a Next.js 15 change -- this project pins next@14.2.15
// for stability, see frontend/package.json).
export default async function InventoryPage({ searchParams }: { searchParams: { status?: string } }) {
  const { status } = searchParams;
  let rows;
  let error: string | null = null;
  try {
    rows = await listInventory(status);
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Content Inventory {rows ? `(${rows.length})` : ""}</h2>
        <div className="flex gap-2 text-sm">
          <a href="/inventory" className={`rounded px-2 py-1 ${!status ? "bg-gray-800" : "text-gray-400 hover:text-white"}`}>
            All
          </a>
          {STATUSES.map((s) => (
            <a
              key={s}
              href={`/inventory?status=${s}`}
              className={`rounded px-2 py-1 ${status === s ? "bg-gray-800" : "text-gray-400 hover:text-white"}`}
            >
              {s}
            </a>
          ))}
        </div>
      </div>

      {error || !rows ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load inventory ({error}).</div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No variants{status ? ` with status ${status}` : ""} yet.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-900 text-xs uppercase text-gray-400">
              <tr>
                <th className="px-4 py-3">Master</th>
                <th className="px-4 py-3">Variant</th>
                <th className="px-4 py-3">Caption</th>
                <th className="px-4 py-3">Account</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {rows.map((r) => (
                <tr key={r.variant_code} className="hover:bg-gray-900/50">
                  <td className="px-4 py-3 text-gray-400">{r.master_code}</td>
                  <td className="px-4 py-3 font-medium">{r.variant_code}</td>
                  <td className="max-w-xs truncate px-4 py-3 text-gray-400">{r.caption_text ?? "—"}</td>
                  <td className="px-4 py-3">{r.account_username ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-400">
                    {r.scheduled_at_utc ? new Date(r.scheduled_at_utc).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
