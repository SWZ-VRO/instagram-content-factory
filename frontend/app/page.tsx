import { StatCard } from "@/components/StatCard";
import { getDashboardSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let summary;
  let loadError: string | null = null;
  try {
    summary = await getDashboardSummary();
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Unknown error";
  }

  if (loadError || !summary) {
    return (
      <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">
        Could not reach the backend API ({loadError}). Is it running? See README "Run everything" section.
      </div>
    );
  }

  const variants = summary.variants_by_status;

  return (
    <div className="space-y-8">
      {summary.dry_run && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-200">
          DRY_RUN is enabled — no publishing calls will ever be made until it is turned off (§36).
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-400">Accounts</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard label="Connected" value={summary.accounts_total} />
          <StatCard label="Active" value={summary.accounts_active} tone="success" />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-400">Content</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard label="Masters" value={summary.masters_total} />
          <StatCard label="Available variants" value={variants.AVAILABLE ?? 0} tone="success" />
          <StatCard label="Reserved" value={variants.RESERVED ?? 0} />
          <StatCard label="Scheduled" value={variants.SCHEDULED ?? 0} />
          <StatCard label="Published" value={variants.PUBLISHED ?? 0} tone="success" />
          <StatCard label="Failed" value={variants.FAILED ?? 0} tone="danger" />
          <StatCard
            label="Missing captions"
            value={summary.missing_captions}
            tone={summary.missing_captions > 0 ? "warning" : "default"}
          />
        </div>
      </section>

      <section className="text-sm text-gray-500">
        Phase 1 (Foundation): accounts, masters, variants and captions are live from the database below.
        Folder watcher / variant generation (Phase 2), the 30-day scheduler (Phase 4) and real Instagram
        publishing (Phase 5) come next — see the project README for the phase plan.
      </section>
    </div>
  );
}
