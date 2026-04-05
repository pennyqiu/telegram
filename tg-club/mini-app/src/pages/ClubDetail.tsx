import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

interface Club {
  id: number;
  name: string;
  short_name?: string;
  country?: string;
  founded_year?: number;
  stadium?: string;
  logo_url?: string;
}

const API = import.meta.env.VITE_CLUB_API_URL ?? "";

export default function ClubDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [club, setClub] = useState<Club | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/v1/clubs/${id}`)
      .then((r) => r.json())
      .then((data) => {
        setClub(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id]);

  if (loading)
    return <div style={{ padding: 20, textAlign: "center" }}>加载中...</div>;
  if (!club) return <div style={{ padding: 20 }}>俱乐部不存在</div>;

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
      {club.logo_url && (
        <img
          src={club.logo_url}
          alt={club.name}
          style={{
            width: 80,
            height: 80,
            objectFit: "contain",
            display: "block",
            margin: "0 auto 12px",
          }}
        />
      )}
      <h2 style={{ textAlign: "center" }}>{club.name}</h2>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
        <tbody>
          {club.short_name && (
            <tr>
              <td style={{ padding: "8px 4px", color: "#888" }}>缩写</td>
              <td>{club.short_name}</td>
            </tr>
          )}
          {club.country && (
            <tr>
              <td style={{ padding: "8px 4px", color: "#888" }}>国家</td>
              <td>{club.country}</td>
            </tr>
          )}
          {club.founded_year && (
            <tr>
              <td style={{ padding: "8px 4px", color: "#888" }}>创建年份</td>
              <td>{club.founded_year}</td>
            </tr>
          )}
          {club.stadium && (
            <tr>
              <td style={{ padding: "8px 4px", color: "#888" }}>球场</td>
              <td>{club.stadium}</td>
            </tr>
          )}
        </tbody>
      </table>
      <button
        onClick={() => navigate(`/players?club_id=${club.id}`)}
        style={{
          marginTop: 16,
          width: "100%",
          padding: "10px",
          background: "#1890ff",
          color: "#fff",
          border: "none",
          borderRadius: 8,
          cursor: "pointer",
          fontSize: 15,
        }}
      >
        查看球员
      </button>
    </div>
  );
}
