import { revalidatePath } from "next/cache";

import { StatusBadge } from "@/components/StatusBadge";
import { listCalendarPlans } from "@/lib/api";

export const dynamic = "force-dynamic";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function generatePlan() {
  "use server";
  await fetch(`${API_URL}/calendar/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  revalidatePath("/calendar");
}

async function approvePlan(formData: FormData) {
  "use server";
  const planId = formData.get("plan_id");
  await fetch(`${API_URL}/calendar/approve/${planId}`, { method: "POST" });
  revalidatePath("/calendar");
}

export default async function CalendarPage() {
  let plans;
  let error: string | null = null;
  try {
    plans = await listCalendarPlans();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Calendar Plans {plans ? `(${plans.length})` : ""}</h2>
        <form action={generatePlan}>
          <button className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium hover:bg-emerald-600">
            GENERATE 30-DAY PLAN
          </button>
        </form>
      </div>

      {error || !plans ? (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm">Could not load plans ({error}).</div>
      ) : plans.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center text-sm text-gray-400">
          No calendar plan yet -- click &quot;GENERATE 30-DAY PLAN&quot; above (needs at least one active account with
          available variants).
        </div>
      ) : (
        <div className="space-y-3">
          {plans.map((p) => {
            const params = (p.params ?? {}) as Record<string, number | string>;
            return (
              <div key={p.id} className="rounded-lg border border-gray-800 bg-gray-900 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={p.status} />
                    <span className="text-sm text-gray-400">{new Date(p.created_at).toLocaleString()}</span>
                  </div>
                  {(p.status === "DRAFT" || p.status === "REVIEW") && (
                    <form action={approvePlan}>
                      <input type="hidden" name="plan_id" value={p.id} />
                      <button className="rounded bg-blue-700 px-3 py-1.5 text-xs font-medium hover:bg-blue-600">
                        APPROVE PLAN
                      </button>
                    </form>
                  )}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div>
                    <div className="text-xs uppercase text-gray-500">Required</div>
                    <div>{params.required_posts ?? "—"}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase text-gray-500">Available at start</div>
                    <div>{params.available_variants_at_start ?? "—"}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase text-gray-500">Reserved</div>
                    <div>{params.reserved_count ?? "—"}</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase text-gray-500">Shortage</div>
                    <div className={Number(params.shortage) > 0 ? "text-amber-400" : ""}>{params.shortage ?? "—"}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
