import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

interface Player {
  id: number;
  name: string;
  position?: string;
  nationality?: string;
  photo_url?: string;
}

const API = import.meta.env.VITE_CLUB_API_URL ?? "";

export default function Players() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const clubId = searchParams.get("club_id");
  const [players, setPlayers] = useState<Player[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const url = clubId
      ? `${API}/api/v1/players?club_id=${clubId}&page=1&page_size=50`
      : `${API}/api/v1/players?page=1&page_size=50`;
    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        setPlayers(data.items ?? []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [clubId]);

  if (loading)
    return <div style={{ padding: 20, textAlign: "center" }}>加载中...</div>;

  return (
    <div style={{ padding: 16, maxWidth: 600, margin: "0 auto" }}>
      <button
        onClick={() => navigate(-1)}
        style={{
          marginBottom: 12,
          background: "none",
          border: "none",
          color: "#1890ff",
          cursor: "pointer",
          fontSize: 16,
        }}
      >
        ← 返回
      </button>
      <h2 style={{ marginBottom: 12 }}>球员列表</h2>
      {players.length === 0 && (
        <div style={{ color: "#888", textAlign: "center" }}>暂无球员数据</div>
      )}
      {players.map((p) => (
        <div
          key={p.id}
          onClick={() => navigate(`/players/${p.id}`)}
          style={{
            display: "flex",
            alignItems: "center",
            padding: "10px 8px",
            borderBottom: "1px solid #f0f0f0",
            cursor: "pointer",
          }}
        >
          {p.photo_url ? (
            <img
              src={p.photo_url}
              alt={p.name}
              style={{
                width: 40,
                height: 40,
                borderRadius: "50%",
                objectFit: "cover",
                marginRight: 12,
              }}
            />
          ) : (
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: "50%",
                background: "#e0e0e0",
                marginRight: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#888",
                flexShrink: 0,
              }}
            >
              👤
            </div>
          )}
          <div>
            <div style={{ fontWeight: 600 }}>{p.name}</div>
            <div style={{ fontSize: 13, color: "#888" }}>
              {p.position ?? "—"} · {p.nationality ?? "—"}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
