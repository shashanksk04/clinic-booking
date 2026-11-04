import type { Appointment, RegisterInput, Slot, SlotInput, User, UserBrief } from "./types";

const BASE: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "clinic_token";

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null): void => {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null): void => {
  onUnauthorized = fn;
};

interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: Record<string, string>;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = new URLSearchParams(opts.form); // login uses form encoding (OAuth2)
  }

  let res: Response;
  try {
    res = await fetch(BASE + path, { method: opts.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (!res.ok) {
    let message = res.statusText || "Request failed";
    try {
      const data = await res.json();
      const d = data?.detail;
      if (typeof d === "string") message = d;
      else if (Array.isArray(d)) message = d.map((e: { msg: string }) => e.msg).join("; ");
    } catch {
      /* body was not JSON */
    }
    if (res.status === 401 && token) onUnauthorized?.(); // token expired -> log out
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // auth
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", form: { username: email, password } }),
  register: (input: RegisterInput) => request<User>("/auth/register", { method: "POST", json: input }),
  me: () => request<User>("/users/me"),

  // browsing (patients)
  doctors: (specialization?: string) =>
    request<UserBrief[]>(`/doctors${specialization ? `?specialization=${encodeURIComponent(specialization)}` : ""}`),
  doctorSlots: (doctorId: number) => request<Slot[]>(`/doctors/${doctorId}/slots`),

  // slots (doctors)
  mySlots: () => request<Slot[]>("/slots/mine"),
  createSlots: (input: SlotInput) => request<Slot[]>("/slots", { method: "POST", json: input }),

  // appointments
  appointments: () => request<Appointment[]>("/appointments"),
  book: (slotId: number) => request<Appointment>("/appointments", { method: "POST", json: { slot_id: slotId } }),
  pay: (id: number) => request<Appointment>(`/appointments/${id}/pay`, { method: "POST" }),
  cancel: (id: number) => request<Appointment>(`/appointments/${id}/cancel`, { method: "POST" }),

  // admin
  adminUsers: () => request<User[]>("/admin/users"),
  runExpiry: () => request<{ cancelled: number }>("/admin/jobs/expire-unpaid", { method: "POST" }),
};
