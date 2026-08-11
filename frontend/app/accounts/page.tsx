import { StatusBadge } from "@/components/StatusBadge";
import { listAccounts } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AccountsPage() {
  let accounts;
  let error: string | null = null;
  try {
    accounts = await listAccounts();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  if (error || !accounts) {
    return <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load accounts ({error}).</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Accounts ({accounts.length})</h2>
      </div>

      {accounts.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No accounts yet. Create one via <code>POST /accounts</code> (see /docs), then connect it with{" "}
          <code>POST /accounts/{"{id}"}/connect/manual</code>.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-900 text-xs uppercase text-gray-400">
              <tr>
                <th className="px-4 py-3">Username</th>
                <th className="px-4 py-3">Timezone</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Connection</th>
                <th className="px-4 py-3">Posts/day</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {accounts.map((a) => (
                <tr key={a.id} className="hover:bg-gray-900/50">
                  <td className="px-4 py-3 font-medium">{a.username}</td>
                  <td className="px-4 py-3 text-gray-400">{a.timezone}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.status} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.connection_status} />
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {a.daily_min_posts}–{a.daily_max_posts}
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
