// Thin fetch wrapper around the SkinGraph FastAPI backend.
//
// Base URL comes from VITE_API_BASE_URL (see .env.example); defaults to the
// local uvicorn / docker-compose port.
import type {
  RoutineDashboard,
  RoutineProduct,
  RoutineProductRequest,
  RoutineProductResponse,
  ScanResponse,
  UserCreateResponse,
  UserDetail,
  UserSummary,
  UserUpsertRequest,
} from "./types";

const BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      `Could not reach the API at ${BASE_URL}. Is the backend running?`,
    );
  }

  if (!res.ok) {
    // FastAPI error bodies look like { "detail": "..." }.
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

const jsonHeaders = { "Content-Type": "application/json" };

export const api = {
  baseUrl: BASE_URL,

  health(): Promise<{ status: string }> {
    return request("/health");
  },

  // --- users ----------------------------------------------------------------

  listUsers(): Promise<UserSummary[]> {
    return request("/users");
  },

  getUser(userId: string): Promise<UserDetail> {
    return request(`/users/${encodeURIComponent(userId)}`);
  },

  createUser(body: UserUpsertRequest): Promise<UserCreateResponse> {
    return request("/users", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    });
  },

  updateUser(userId: string, body: UserUpsertRequest): Promise<UserDetail> {
    return request(`/users/${encodeURIComponent(userId)}`, {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    });
  },

  deleteUser(userId: string): Promise<void> {
    return request(`/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    });
  },

  // --- routine --------------------------------------------------------------

  getRoutine(userId: string): Promise<RoutineProduct[]> {
    return request(`/users/${encodeURIComponent(userId)}/routine`);
  },

  getRoutineDashboard(userId: string): Promise<RoutineDashboard> {
    return request(`/users/${encodeURIComponent(userId)}/routine/dashboard`);
  },

  addRoutineProduct(
    userId: string,
    body: RoutineProductRequest,
  ): Promise<RoutineProductResponse> {
    return request(`/users/${encodeURIComponent(userId)}/routine`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    });
  },

  removeRoutineProduct(productId: string): Promise<void> {
    return request(`/routine/${encodeURIComponent(productId)}`, {
      method: "DELETE",
    });
  },

  // --- scan -----------------------------------------------------------------

  scan(opts: {
    image: File;
    imageType?: "front" | "back";
    userId?: string;
    addToRoutine?: boolean;
  }): Promise<ScanResponse> {
    const form = new FormData();
    form.append("image", opts.image);
    if (opts.imageType) form.append("image_type", opts.imageType);
    if (opts.userId) form.append("user_id", opts.userId);
    form.append("add_to_routine", String(Boolean(opts.addToRoutine)));
    return request("/scan", { method: "POST", body: form });
  },
};
