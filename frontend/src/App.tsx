import type { ReactNode } from "react";
import { Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import type { Role } from "./types";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Doctors from "./pages/Doctors";
import DoctorSlots from "./pages/DoctorSlots";
import MySlots from "./pages/MySlots";
import Appointments from "./pages/Appointments";
import Admin from "./pages/Admin";

const homeFor = (role: Role): string =>
  role === "patient" ? "/doctors" : role === "doctor" ? "/my-slots" : "/admin";

function Layout() {
  const { user, logout } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return (
    <>
      <header className="nav">
        <strong>🏥 Clinic Booking</strong>
        <nav>
          {user.role === "patient" && <Link to="/doctors">Find a doctor</Link>}
          {user.role === "doctor" && <Link to="/my-slots">My slots</Link>}
          {user.role === "admin" && <Link to="/admin">Admin</Link>}
          <Link to="/appointments">Appointments</Link>
        </nav>
        <span className="who">
          {user.full_name} <span className="badge">{user.role}</span>
          <button className="link" onClick={logout}>Log out</button>
        </span>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}

/** Only lets the given roles in; everyone else is sent to their own home page. */
function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return null;
  return roles.includes(user.role) ? <>{children}</> : <Navigate to={homeFor(user.role)} replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <p className="container">Loading…</p>;

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={homeFor(user.role)} replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to={homeFor(user.role)} replace /> : <Register />} />
      <Route element={<Layout />}>
        <Route path="/doctors" element={<RoleGate roles={["patient"]}><Doctors /></RoleGate>} />
        <Route path="/doctors/:id" element={<RoleGate roles={["patient"]}><DoctorSlots /></RoleGate>} />
        <Route path="/my-slots" element={<RoleGate roles={["doctor"]}><MySlots /></RoleGate>} />
        <Route path="/appointments" element={<Appointments />} />
        <Route path="/admin" element={<RoleGate roles={["admin"]}><Admin /></RoleGate>} />
      </Route>
      <Route path="*" element={<Navigate to={user ? homeFor(user.role) : "/login"} replace />} />
    </Routes>
  );
}
