import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import Clubs from "./pages/Clubs";
import PlayerDetail from "./pages/PlayerDetail";

export default function App() {
  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Clubs />} />
        <Route path="/clubs/:id" element={<ClubDetailLazy />} />
        <Route path="/players" element={<PlayersLazy />} />
        <Route path="/players/:id" element={<PlayerDetail />} />
      </Routes>
    </BrowserRouter>
  );
}

// 懒加载占位（可按需拆分）
import { lazy, Suspense } from "react";
const ClubDetailLazy = lazy(() => import("./pages/ClubDetail"));
const PlayersLazy = lazy(() => import("./pages/Players"));

function ClubDetailLazy() {
  return <Suspense fallback={<div style={{ padding: 20, textAlign: "center" }}>加载中...</div>}><ClubDetailInner /></Suspense>;
}
function PlayersLazy() {
  return <Suspense fallback={<div style={{ padding: 20, textAlign: "center" }}>加载中...</div>}><PlayersInner /></Suspense>;
}
// 这两个页面与 Clubs.tsx / PlayerDetail.tsx 结构类似，省略重复实现
function ClubDetailInner() { return <div>俱乐部详情页</div>; }
function PlayersInner() { return <div>球员列表页</div>; }
