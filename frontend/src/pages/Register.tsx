import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Register() {
  const { register, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "", email: "", password: "", role: "patient" as "patient" | "doctor", specialization: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        ...form,
        specialization: form.role === "doctor" ? form.specialization : undefined,
      });
      const me = await login(form.email, form.password); // log in straight after signing up
      navigate(me.role === "doctor" ? "/my-slots" : "/doctors");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>Create account</h1>
      {error && <p className="error">{error}</p>}
      <form onSubmit={onSubmit}>
        <label>Full name<input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required /></label>
        <label>Email<input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} required /></label>
        <label>Password (8+ characters)
          <input type="password" minLength={8} maxLength={64} value={form.password} onChange={(e) => set("password", e.target.value)} required />
        </label>
        <label>I am a
          <select value={form.role} onChange={(e) => set("role", e.target.value as "patient" | "doctor")}>
            <option value="patient">Patient</option>
            <option value="doctor">Doctor</option>
          </select>
        </label>
        {form.role === "doctor" && (
          <label>Specialization
            <input value={form.specialization} onChange={(e) => set("specialization", e.target.value)} placeholder="e.g. Cardiology" required />
          </label>
        )}
        <button disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
      </form>
      <p>Already registered? <Link to="/login">Log in</Link></p>
    </div>
  );
}
