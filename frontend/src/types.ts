// These mirror the JSON your FastAPI backend returns (see schemas.py).
export type Role = "admin" | "doctor" | "patient";
export type AppointmentStatus = "pending_payment" | "confirmed" | "cancelled" | "completed";

/** Short, safe view of a person (UserBrief in schemas.py) */
export interface UserBrief {
  id: number;
  full_name: string;
  specialization: string | null;
}

/** Full view of a user (UserOut in schemas.py) */
export interface User extends UserBrief {
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Slot {
  id: number;
  doctor_id: number;
  start_time: string;
  end_time: string;
}

export interface Appointment {
  id: number;
  status: AppointmentStatus;
  slot: Slot;
  patient: UserBrief;
  doctor: UserBrief;
  payment_deadline: string;
  paid_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  role: "patient" | "doctor";
  specialization?: string;
}

export interface SlotInput {
  start_time: string;
  end_time: string;
  slot_minutes?: number;
}
