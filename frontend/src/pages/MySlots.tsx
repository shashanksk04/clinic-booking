import { useState, type FormEvent } from "react";
import { api } from "../api";
import { fmt, useLoad } from "../hooks";

export default function MySlots() {
  // Load my slots AND my appointments, so we can show which slots are booked.
  const { data, error, loading, reload } = useLoad(async () => {
    const [slots, appointments] = await Promise.all([api.mySlots(), api.appointments()]);
    const taken = new Set(
      appointments
        .filter((a) => a.status === "pending_payment" || a.status === "confirmed")
        .map((a) => a.slot.id),
    );
    return slots.map((s) => ({ ...s, booked: taken.has(s.id) }));
  });

  const [date, setDate] = useState("");
  const [from, setFrom] = useState("09:00");
  const [to, setTo] = useState("12:00");
  const [minutes, setMinutes] = useState("30");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      // The browser gives local time; convert it to an unambiguous UTC instant for the API.
      const start = new Date(`${date}T${from}`);
      const end = new Date(`${date}T${to}`);
      await api.createSlots({
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        slot_minutes: minutes ? Number(minutes) : undefined,
      });
      reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>My availability</h1>
      <form className="inline-form" onSubmit={onSubmit}>
        <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
        <label>From<input type="time" value={from} onChange={(e) => setFrom(e.target.value)} required /></label>
        <label>To<input type="time" value={to} onChange={(e) => setTo(e.target.value)} required /></label>
        <label>Slot length
          <select value={minutes} onChange={(e) => setMinutes(e.target.value)}>
            <option value="15">15 min</option>
            <option value="30">30 min</option>
            <option value="45">45 min</option>
            <option value="60">60 min</option>
            <option value="">One single slot</option>
          </select>
        </label>
        <button disabled={busy}>{busy ? "Adding…" : "Add slots"}</button>
      </form>
      {(formError || error) && <p className="error">{formError ?? error}</p>}
      {loading && <p>Loading…</p>}
      {data?.length === 0 && !loading && <p className="muted">You haven't added any slots yet.</p>}
      <ul className="list">
        {data?.map((s) => (
          <li key={s.id}>
            <span>{fmt(s.start_time)} → {new Date(s.end_time).toLocaleTimeString(undefined, { timeStyle: "short" })}</span>
            <span className={`badge ${s.booked ? "warn" : "ok"}`}>{s.booked ? "booked" : "free"}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
