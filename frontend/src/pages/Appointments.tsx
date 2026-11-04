import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { fmt, useLoad } from "../hooks";
import type { Appointment } from "../types";

const LABEL: Record<Appointment["status"], string> = {
  pending_payment: "Awaiting payment",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  completed: "Completed",
};

export default function Appointments() {
  const { user } = useAuth();
  const { data, error, loading, reload } = useLoad(() => api.appointments());
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setActionError(null);
    try {
      await action();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      reload(); // always refresh, so the screen matches the server
    }
  }

  if (!user) return null;
  return (
    <>
      <h1>Appointments</h1>
      {(error || actionError) && <p className="error">{actionError ?? error}</p>}
      {loading && <p>Loading…</p>}
      {data?.length === 0 && !loading && <p className="muted">Nothing here yet.</p>}
      <div className="grid">
        {data?.map((a) => {
          const isActive = a.status === "pending_payment" || a.status === "confirmed";
          const started = new Date(a.slot.start_time) <= new Date();
          return (
            <div key={a.id} className="card">
              <span className={`badge status-${a.status}`}>{LABEL[a.status]}</span>
              <h3>{fmt(a.slot.start_time)}</h3>
              <p>
                {user.role === "patient" && `Dr. ${a.doctor.full_name} (${a.doctor.specialization})`}
                {user.role === "doctor" && `Patient: ${a.patient.full_name}`}
                {user.role === "admin" && `${a.patient.full_name} with Dr. ${a.doctor.full_name}`}
              </p>
              {a.status === "pending_payment" && (
                <p className="warn-text">Pay before {fmt(a.payment_deadline)} or it will be cancelled automatically.</p>
              )}
              {a.status === "cancelled" && a.cancel_reason && (
                <p className="muted">Reason: {a.cancel_reason.replace("_", " ")}</p>
              )}
              <div className="actions">
                {user.role === "patient" && a.status === "pending_payment" && (
                  <button onClick={() => run(() => api.pay(a.id))}>Pay now</button>
                )}
                {isActive && !started && (
                  <button
                    className="danger"
                    onClick={() => window.confirm("Cancel this appointment?") && run(() => api.cancel(a.id))}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
