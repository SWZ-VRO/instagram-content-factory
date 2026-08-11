import { StatusBadge } from "@/components/StatusBadge";
import { listMasters } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MastersPage() {
  let masters;
  let error: string | null = null;
  try {
    masters = await listMasters();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  if (error || !masters) {
    return <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load masters ({error}).</div>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Masters ({masters.length})</h2>

      {masters.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No masters yet. Drop a video into <code>content/masters/</code> or click IMPORT NOW (<code>POST /masters/import</code>).
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-900 text-xs uppercase text-gray-400">
              <tr>
                <th className="px-4 py-3">Master</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Variants</th>
                <th className="px-4 py-3">Available</th>
                <th className="px-4 py-3">Consumed</th>
                <th className="px-4 py-3">Accounts used</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {masters.map((m) => (
                <tr key={m.id} className="hover:bg-gray-900/50">
                  <td className="px-4 py-3 font-medium">{m.master_code}</td>
                  <td className="px-4 py-3 text-gray-400">{new Date(m.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">{m.variant_count}</td>
                  <td className="px-4 py-3 text-emerald-400">{m.available_count}</td>
                  <td className="px-4 py-3 text-gray-400">{m.consumed_count}</td>
                  <td className="px-4 py-3 text-gray-400">{m.accounts_used}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={m.status} />
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
