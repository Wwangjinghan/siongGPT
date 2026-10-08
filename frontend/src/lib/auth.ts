import { apiFetch } from "@/lib/api";
import type {
  LoginRequest,
  LoginResponse,
  LogoutResponse,
  User,
} from "@/types/auth";

export function login(payload: LoginRequest): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getCurrentUser(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export function logout(): Promise<LogoutResponse> {
  return apiFetch<LogoutResponse>("/auth/logout", {
    method: "POST",
  });
}
