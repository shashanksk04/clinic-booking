import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";

export default function Doctors() {
  const [filter, setFilter] = useState("");
  const { data, error, loading } = useLoad(() => api.doctors(filter || undefined), [filter]);

  return (
    <>
      <h1>Find a doctor</h1>
      <input
        className="search"
        placeholder="Filter by specialization (e.g. cardio)"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      {loading && <p>Loading…</p>}
      {data?.length === 0 && !loading && <p className="muted">No doctors found.</p>}
      <div className="grid">
        {data?.map((d) => (
          <Link key={d.id} to={`/doctors/${d.id}`} className="card">
            <h3>Dr. {d.full_name}</h3>
            <p className="muted">{d.specialization}</p>
            <span>View available slots →</span>
          </Link>
        ))}
      </div>
    </>
  );
}
