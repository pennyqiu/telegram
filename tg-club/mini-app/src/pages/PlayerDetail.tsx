import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { clubApi, Player } from "../api/client";

export default function PlayerDetail() {
  const { id } = useParams<{ id: string }>();
  const [player, setPlayer] = useState<Player | null>(null);
  const [similar, setSimilar] = useState<Player[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    if (!id) return;
    clubApi.getPlayer(Number(id)).then((r) => {
      setPlayer(r.data);
      clubApi.getSimilarPlayers(Number(id)).then((s) => setSimilar(s.data)).catch(() => {});
    });
  }, [id]);

  if (!player) return <div style={{ padding: 20, textAlign: "center" }}>加载中...</div>;

  return (
    <div style={{ padding: 16 }}>
      <button onClick={() => navigate(-1)} style={{ background: "none", border: "none", fontSize: 14, cursor: "pointer", marginBottom: 12 }}>← 返回</button>

      {/* 球员头像 + 基础信息 */}
      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        {player.photo_url
          ? <img src={player.photo_url} style={{ width: 80, height: 80, borderRadius: "50%", objectFit: "cover" }} />
          : <div style={{ width: 80, height: 80, borderRadius: "50%", background: "#ddd" }} />
        }
        <div>
          <h2 style={{ margin: "0 0 4px" }}>{player.name}</h2>
          <div style={{ fontSize: 13, color: "#888" }}>{player.position} · {player.nationality}</div>
          {player.rating && <div style={{ marginTop: 4, color: "#f5a623", fontWeight: "bold" }}>⭐ {player.rating}</div>}
        </div>
      </div>

      {/* 身体数据（有权限才显示） */}
      {player._locked ? (
        <div style={{ background: "#fff8e1", borderRadius: 10, padding: 16, textAlign: "center", marginBottom: 16 }}>
          <div>🔒 升级到 <strong>{player._required_tier?.toUpperCase()}</strong> 解锁完整数据</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 16 }}>
          {[
            { label: "身高", value: player.height_cm ? `${player.height_cm} cm` : "-" },
            { label: "体重", value: player.weight_kg ? `${player.weight_kg} kg` : "-" },
            { label: "惯用脚", value: player.status ?? "-" },
          ].map((item) => (
            <div key={item.label} style={{ background: "#f5f5f5", borderRadius: 8, padding: "8px 0", textAlign: "center" }}>
              <div style={{ fontSize: 11, color: "#888" }}>{item.label}</div>
              <div style={{ fontWeight: "bold" }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 标签 */}
      {player.tags && player.tags.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          {player.tags.map((t) => (
            <span key={t} style={{ background: "#e8f4fd", color: "#0088cc", borderRadius: 12, padding: "3px 10px", marginRight: 6, fontSize: 12 }}>{t}</span>
          ))}
        </div>
      )}

      {/* Bio */}
      {player.bio && <p style={{ fontSize: 14, color: "#555", lineHeight: 1.6, marginBottom: 16 }}>{player.bio}</p>}

      {/* 转会历史 */}
      {player.transfers && player.transfers.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <h3 style={{ marginBottom: 8 }}>转会历史</h3>
          {player.transfers.map((t) => (
            <div key={t.id} style={{ padding: "8px 0", borderBottom: "1px solid #eee", fontSize: 13 }}>
              <strong>{t.from_club ?? "—"}</strong> → <strong>{t.to_club ?? "退役"}</strong>
              <span style={{ color: "#888", marginLeft: 8 }}>{t.transfer_date}</span>
              {t.fee_display && <span style={{ marginLeft: 8, color: "#0088cc" }}>{t.fee_display}</span>}
            </div>
          ))}
        </div>
      )}

      {/* 相似球员推荐 */}
      {similar.length > 0 && (
        <div>
          <h3 style={{ marginBottom: 8 }}>相似球员</h3>
          <div style={{ display: "flex", gap: 8, overflowX: "auto" }}>
            {similar.map((p) => (
              <div key={p.id} onClick={() => navigate(`/players/${p.id}`)}
                style={{ flex: "0 0 80px", textAlign: "center", cursor: "pointer" }}>
                {p.photo_url
                  ? <img src={p.photo_url} style={{ width: 56, height: 56, borderRadius: "50%", objectFit: "cover" }} />
                  : <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#ddd", margin: "0 auto" }} />
                }
                <div style={{ fontSize: 11, marginTop: 4 }}>{p.name}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
