import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { clubApi, Club } from "../api/client";

export default function Clubs() {
  const [clubs, setClubs] = useState<Club[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const fetchClubs = async (q?: string) => {
    setLoading(true);
    try {
      const res = await clubApi.listClubs({ search: q });
      setClubs(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchClubs(); }, []);

  return (
    <div style={{ padding: 16 }}>
      <input
        placeholder="搜索俱乐部..."
        value={search}
        onChange={(e) => { setSearch(e.target.value); fetchClubs(e.target.value); }}
        style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd", marginBottom: 12 }}
      />

      {loading && <div style={{ textAlign: "center", padding: 20 }}>加载中...</div>}

      {clubs.map((club) => (
        <div key={club.id}
          onClick={() => navigate(`/clubs/${club.id}`)}
          style={{ display: "flex", alignItems: "center", gap: 12, padding: 12,
            border: "1px solid #eee", borderRadius: 10, marginBottom: 8, cursor: "pointer" }}>
          {club.logo_url
            ? <img src={club.logo_url} style={{ width: 40, height: 40, objectFit: "contain" }} />
            : <div style={{ width: 40, height: 40, background: "#ddd", borderRadius: 8 }} />
          }
          <div>
            <div style={{ fontWeight: "bold" }}>{club.name}</div>
            <div style={{ fontSize: 12, color: "#888" }}>{club.league_name} · {club.country}</div>
          </div>
          {club._locked && <span style={{ marginLeft: "auto", fontSize: 12, color: "#f5a623" }}>🔒 {club._required_tier}</span>}
        </div>
      ))}
    </div>
  );
}
