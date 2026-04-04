import axios from "axios";

const http = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "" });

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("admin_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("admin_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export const adminApi = {
  login: (username: string, password: string) =>
    http.post<{ token: string; username: string; role: string }>(
      "/api/v1/admin/auth/login", { username, password }
    ),

  // 账号管理（仅超级管理员可调用）
  listAdminUsers: () => http.get("/api/v1/admin/users"),
  createAdminUser: (data: AdminUserPayload) => http.post("/api/v1/admin/users", data),
  updateAdminUser: (id: number, data: { is_active?: boolean; role?: string }) =>
    http.put(`/api/v1/admin/users/${id}`, data),
  resetAdminPassword: (id: number, new_password: string) =>
    http.post(`/api/v1/admin/users/${id}/reset-password`, { new_password }),
  deleteAdminUser: (id: number) => http.delete(`/api/v1/admin/users/${id}`),

  // 俱乐部
  listClubs: () => http.get("/api/v1/admin/clubs"),
  createClub: (data: ClubPayload) => http.post("/api/v1/admin/clubs", data),
  updateClub: (id: number, data: ClubPayload) => http.put(`/api/v1/admin/clubs/${id}`, data),
  deleteClub: (id: number) => http.delete(`/api/v1/admin/clubs/${id}`),

  // 球员
  listPlayers: () => http.get("/api/v1/admin/players"),
  createPlayer: (data: PlayerPayload) => http.post("/api/v1/admin/players", data),
  updatePlayer: (id: number, data: PlayerPayload) => http.put(`/api/v1/admin/players/${id}`, data),
  deletePlayer: (id: number) => http.delete(`/api/v1/admin/players/${id}`),

  // 转会
  listTransfers: () => http.get("/api/v1/admin/transfers"),
  createTransfer: (data: TransferPayload) => http.post("/api/v1/admin/transfers", data),

  // 退役
  retirePlayer: (data: RetirementPayload) => http.post("/api/v1/admin/retirements", data),
};

export interface ClubPayload {
  name: string; short_name?: string; league_id?: number;
  country?: string; founded_year?: number; stadium?: string;
  description?: string; access_tier?: string;
}
export interface PlayerPayload {
  name: string; current_club_id?: number; birth_date?: string;
  nationality?: string; position?: string; height_cm?: number;
  weight_kg?: number; preferred_foot?: string; bio?: string;
  jersey_number?: number; tags?: string[]; rating?: number; access_tier?: string;
}
export interface TransferPayload {
  player_id: number; from_club_id?: number; to_club_id?: number;
  type: string; transfer_date: string; fee_display?: string; fee_stars?: number;
}
export interface RetirementPayload {
  player_id: number; retired_at: string; last_club_id?: number;
  career_summary?: string; achievements?: string[];
}

export interface AdminUserPayload {
  username: string;
  password: string;
  role: "admin" | "editor";
}

export interface AdminUserRecord {
  id: number;
  username: string;
  role: "admin" | "editor";
  is_active: boolean;
  created_by: string | null;
  last_login_at: string | null;
  created_at: string;
}

