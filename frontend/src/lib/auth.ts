"use client";

import { apiFetch } from "./api";

export interface User {
  id: string;
  email: string;
  tier: "free" | "pro" | "legend";
  subscription_expires: string | null;
}

export async function login(
  email: string,
  password: string
): Promise<User> {
  const data = await apiFetch<{
    access_token: string;
    refresh_token: string;
  }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);

  return getMe();
}

export async function register(
  email: string,
  password: string
): Promise<User> {
  const data = await apiFetch<{
    access_token: string;
    refresh_token: string;
  }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);

  return getMe();
}

export async function getMe(): Promise<User> {
  return apiFetch<User>("/api/auth/me", { requireAuth: true });
}

export function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  window.location.href = "/login";
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("access_token");
}
