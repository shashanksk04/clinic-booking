import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { fmt, useLoad } from "../hooks";

export default function DoctorSlots() {
  const doctorId = Number(useParams().id);
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(() => api.doctorSlots(doctorId), [doctorId]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function book(slotId: number) {
    setBusyId(slotId);
    setActionError(null);
    try {
      await api.book(slotId);
      navigate("/appointments"); // next step for the patient: pay
    } catch (e) {
      setActionError((e as Error).message);
      reload(); // somebody else may have just taken it
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <p><Link to="/doctors">← All doctors</Link></p>
      <h1>Available slots</h1>
      {(error || actionError) && <p className="error">{actionError ?? error}</p>}
      {loading && <p>Loading…</p>}
      {data?.length === 0 && !loading && <p className="muted">No free slots right now.</p>}
      <ul className="list">
        {data?.map((s) => (
          <li key={s.id}>
            <span>{fmt(s.start_time)} → {new Date(s.end_time).toLocaleTimeString(undefined, { timeStyle: "short" })}</span>
            <button disabled={busyId === s.id} onClick={() => book(s.id)}>
              {busyId === s.id ? "Booking…" : "Book"}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
