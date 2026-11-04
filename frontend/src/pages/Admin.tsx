import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";

export default function Admin() {
  const users = useLoad(() => api.adminUsers());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runExpiry() {
    setError(null);
    try {
      const { cancelled } = await api.runExpiry();
      setMessage(`Auto-cancelled ${cancelled} unpaid appointment(s).`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Count users per role in the browser (the API gives us the full list)
  const counts: Record<string, number> = {};
  users.data?.forEach((u) => {
    counts[u.role] = (counts[u.role] ?? 0) + 1;
  });

  return (
    <>
      <h1>Admin</h1>
      {(error || users.error) && <p className="error">{error ?? users.error}</p>}
      {message && <p className="success">{message}</p>}

      <div className="grid stats">
        {Object.entries(counts).map(([role, n]) => (
          <div key={role} className="card"><h3>{n}</h3><p className="muted">{role}s</p></div>
        ))}
      </div>
      <p><button onClick={runExpiry}>Run auto-cancel job now</button></p>

      <h2>Users</h2>
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>
          {users.data?.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td>{u.email}</td>
              <td><span className="badge">{u.role}</span></td>
              <td>{u.is_active ? "active" : "disabled"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
