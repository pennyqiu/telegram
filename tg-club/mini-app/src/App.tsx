import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Clubs from "./pages/Clubs";
import PlayerDetail from "./pages/PlayerDetail";

const ClubDetail = lazy(() => import("./pages/ClubDetail"));
const Players = lazy(() => import("./pages/Players"));

const Loading = () => (
  <div style={{ padding: 20, textAlign: "center" }}>加载中...</div>
);

export default function App() {
  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Clubs />} />
        <Route
          path="/clubs/:id"
          element={
            <Suspense fallback={<Loading />}>
              <ClubDetail />
            </Suspense>
          }
        />
        <Route
          path="/players"
          element={
            <Suspense fallback={<Loading />}>
              <Players />
            </Suspense>
          }
        />
        <Route path="/players/:id" element={<PlayerDetail />} />
      </Routes>
    </BrowserRouter>
  );
}
