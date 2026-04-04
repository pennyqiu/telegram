const tg = window.Telegram?.WebApp;
const BASE = import.meta.env.VITE_CLUB_API_URL ?? "";

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-Init-Data": tg?.initData ?? "", ...opts.headers },
  });
  if (res.status === 403) throw { code: 403, tier: "locked" };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const clubApi = {
  listClubs: (params?: { league_id?: number; search?: string; page?: number }) =>
    req<{ data: Club[] }>(`/clubs?${new URLSearchParams(params as any)}`),

  getClub: (id: number) => req<{ data: Club }>(`/clubs/${id}`),

  listPlayers: (params?: { position?: string; club_id?: number; status?: string; search?: string }) =>
    req<{ data: Player[] }>(`/players?${new URLSearchParams(params as any)}`),

  getPlayer: (id: number) => req<{ data: Player }>(`/players/${id}`),

  getSimilarPlayers: (id: number) => req<{ data: Player[] }>(`/players/${id}/similar`),

  listFreeAgents: (position?: string) =>
    req<{ data: Player[] }>(`/players/free-agents${position ? `?position=${position}` : ""}`),
};

export interface Club {
  id: number; name: string; short_name?: string; logo_url?: string;
  country?: string; league_name?: string; founded_year?: number;
  stadium?: string; description?: string; _locked?: boolean; _required_tier?: string;
  players?: Player[];
}

export interface Player {
  id: number; name: string; position?: string; nationality?: string;
  photo_url?: string; height_cm?: number; weight_kg?: number;
  birth_date?: string; rating?: number; tags?: string[];
  current_club_name?: string; bio?: string; transfers?: Transfer[];
  _locked?: boolean; _required_tier?: string; status?: string;
}

export interface Transfer {
  id: number; type: string; from_club?: string; to_club?: string;
  transfer_date: string; fee_display?: string;
}
