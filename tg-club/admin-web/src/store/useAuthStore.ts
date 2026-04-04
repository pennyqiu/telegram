import { create } from "zustand";

interface AuthStore {
  token:    string | null;
  username: string | null;
  role:     string | null;   // "admin" | "editor"
  login:  (token: string, username?: string, role?: string) => void;
  logout: () => void;
  isAdmin: () => boolean;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  token:    localStorage.getItem("admin_token"),
  username: localStorage.getItem("admin_username"),
  role:     localStorage.getItem("admin_role"),

  login: (token, username, role) => {
    localStorage.setItem("admin_token", token);
    if (username) localStorage.setItem("admin_username", username);
    if (role)     localStorage.setItem("admin_role", role);
    set({ token, username: username ?? null, role: role ?? null });
  },

  logout: () => {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_username");
    localStorage.removeItem("admin_role");
    set({ token: null, username: null, role: null });
    window.location.href = "/login";
  },

  isAdmin: () => get().role === "admin",
}));
