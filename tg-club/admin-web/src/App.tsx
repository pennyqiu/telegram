import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Avatar, Space, Typography, Tag } from "antd";
import {
  TeamOutlined, BankOutlined, SwapOutlined,
  LogoutOutlined, UserOutlined, SafetyOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "./store/useAuthStore";
import Login    from "./pages/Login";
import ClubList    from "./pages/clubs/ClubList";
import PlayerList  from "./pages/players/PlayerList";
import TransferList from "./pages/transfers/TransferList";
import UserList    from "./pages/users/UserList";

const { Sider, Content, Header } = Layout;

const CONTENT_NAV = [
  { key: "clubs",     icon: <BankOutlined />,  label: "俱乐部", path: "/clubs"     },
  { key: "players",   icon: <TeamOutlined />,  label: "球员",   path: "/players"   },
  { key: "transfers", icon: <SwapOutlined />,  label: "转会",   path: "/transfers" },
];

const ADMIN_NAV = [
  { key: "users", icon: <SafetyOutlined />, label: "账号管理", path: "/users" },
];

function AdminLayout() {
  const location  = useLocation();
  const { logout, username, role, isAdmin } = useAuthStore();

  const allNav = [...CONTENT_NAV, ...(isAdmin() ? ADMIN_NAV : [])];
  const selectedKey = allNav.find((n) => location.pathname.startsWith(n.path))?.key ?? "clubs";

  const roleTag = role === "admin"
    ? <Tag color="red" style={{ fontSize: 11 }}>超管</Tag>
    : <Tag color="blue" style={{ fontSize: 11 }}>编辑</Tag>;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={200} theme="dark">
        <div style={{
          color: "#fff", padding: "18px 16px 14px",
          fontWeight: "bold", fontSize: 15,
          borderBottom: "1px solid rgba(255,255,255,.1)",
        }}>
          ⚽ 俱乐部管理
        </div>

        {/* 内容管理区 */}
        <div style={{ padding: "10px 16px 4px", color: "rgba(255,255,255,.4)", fontSize: 11 }}>
          内容管理
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={CONTENT_NAV.map(({ key, icon, label, path }) => ({
            key, icon, label: <Link to={path}>{label}</Link>,
          }))}
        />

        {/* 超管区域 */}
        {isAdmin() && (
          <>
            <div style={{ padding: "10px 16px 4px", color: "rgba(255,255,255,.4)", fontSize: 11, marginTop: 4 }}>
              系统管理
            </div>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[selectedKey]}
              items={ADMIN_NAV.map(({ key, icon, label, path }) => ({
                key, icon, label: <Link to={path}>{label}</Link>,
              }))}
            />
          </>
        )}
      </Sider>

      <Layout>
        <Header style={{
          background: "#fff", padding: "0 24px",
          display: "flex", alignItems: "center", justifyContent: "flex-end",
          borderBottom: "1px solid #f0f0f0", height: 52,
        }}>
          <Space>
            <Avatar size="small" icon={<UserOutlined />} style={{ background: "#1677ff" }} />
            <Typography.Text style={{ fontSize: 13 }}>{username ?? "admin"}</Typography.Text>
            {roleTag}
            <Button
              type="text" size="small"
              icon={<LogoutOutlined />}
              onClick={logout}
              style={{ color: "#888" }}
            >
              退出
            </Button>
          </Space>
        </Header>

        <Content style={{ padding: 24, background: "#f5f5f5", minHeight: "calc(100vh - 52px)" }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: 24, minHeight: 400 }}>
            <Routes>
              <Route path="/clubs"     element={<ClubList />}     />
              <Route path="/players"   element={<PlayerList />}   />
              <Route path="/transfers" element={<TransferList />} />
              {/* 账号管理仅超管可访问 */}
              <Route
                path="/users"
                element={isAdmin() ? <UserList /> : <Navigate to="/clubs" />}
              />
              <Route path="/"  element={<Navigate to="/clubs" />} />
              <Route path="*"  element={<Navigate to="/clubs" />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  const token = useAuthStore((s) => s.token);
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={token ? <AdminLayout /> : <Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}
