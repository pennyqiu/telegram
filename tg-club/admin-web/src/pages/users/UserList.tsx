import { useState, useEffect } from "react";
import {
  Table, Button, Modal, Form, Input, Select, Switch,
  Space, Popconfirm, message, Tag, Tooltip,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  KeyOutlined, LockOutlined, UnlockOutlined,
} from "@ant-design/icons";
import { adminApi, AdminUserPayload, AdminUserRecord } from "../../api/client";
import { useAuthStore } from "../../store/useAuthStore";

const ROLE_COLOR = { admin: "red", editor: "blue" } as const;
const ROLE_LABEL = { admin: "超级管理员", editor: "编辑员" };

export default function UserList() {
  const currentUsername = useAuthStore((s) => s.username);

  const [users, setUsers]           = useState<AdminUserRecord[]>([]);
  const [loading, setLoading]       = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [pwdModal, setPwdModal]     = useState<{ open: boolean; user?: AdminUserRecord }>({ open: false });
  const [form]    = Form.useForm();
  const [pwdForm] = Form.useForm();

  const fetch = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listAdminUsers();
      setUsers(res.data.data ?? res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(); }, []);

  const handleCreate = async (values: AdminUserPayload) => {
    try {
      await adminApi.createAdminUser(values);
      message.success(`账号「${values.username}」创建成功`);
      setCreateModal(false);
      form.resetFields();
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail ?? "创建失败");
    }
  };

  const toggleActive = async (user: AdminUserRecord) => {
    try {
      await adminApi.updateAdminUser(user.id, { is_active: !user.is_active });
      message.success(user.is_active ? "已停用" : "已启用");
      fetch();
    } catch {
      message.error("操作失败");
    }
  };

  const changeRole = async (user: AdminUserRecord, role: string) => {
    try {
      await adminApi.updateAdminUser(user.id, { role });
      message.success("角色已更新");
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail ?? "更新失败");
    }
  };

  const handleDelete = async (user: AdminUserRecord) => {
    try {
      await adminApi.deleteAdminUser(user.id);
      message.success("已删除");
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail ?? "删除失败");
    }
  };

  const handleResetPwd = async (values: { new_password: string }) => {
    try {
      await adminApi.resetAdminPassword(pwdModal.user!.id, values.new_password);
      message.success("密码已重置");
      setPwdModal({ open: false });
      pwdForm.resetFields();
    } catch {
      message.error("重置失败");
    }
  };

  const columns = [
    {
      title: "用户名", dataIndex: "username",
      render: (name: string) => (
        <Space>
          {name}
          {name === currentUsername && <Tag color="green">当前账号</Tag>}
        </Space>
      ),
    },
    {
      title: "角色", dataIndex: "role", width: 140,
      render: (role: "admin" | "editor", record: AdminUserRecord) => (
        record.username === currentUsername
          ? <Tag color={ROLE_COLOR[role]}>{ROLE_LABEL[role]}</Tag>
          : (
            <Select
              value={role}
              size="small"
              style={{ width: 120 }}
              options={[
                { value: "admin",  label: "超级管理员" },
                { value: "editor", label: "编辑员" },
              ]}
              onChange={(v) => changeRole(record, v)}
            />
          )
      ),
    },
    {
      title: "状态", dataIndex: "is_active", width: 90,
      render: (active: boolean) => (
        <Tag color={active ? "success" : "default"}>{active ? "正常" : "已停用"}</Tag>
      ),
    },
    { title: "创建者", dataIndex: "created_by", width: 100, render: (v: string) => v ?? "—" },
    { title: "最近登录", dataIndex: "last_login_at", width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString() : "从未登录" },
    { title: "创建时间", dataIndex: "created_at", width: 160,
      render: (v: string) => new Date(v).toLocaleString() },
    {
      title: "操作", width: 180,
      render: (_: any, record: AdminUserRecord) => {
        const isSelf = record.username === currentUsername;
        return (
          <Space>
            <Tooltip title="重置密码">
              <Button
                size="small"
                icon={<KeyOutlined />}
                onClick={() => { pwdForm.resetFields(); setPwdModal({ open: true, user: record }); }}
              />
            </Tooltip>
            <Tooltip title={record.is_active ? "停用" : "启用"}>
              <Button
                size="small"
                icon={record.is_active ? <LockOutlined /> : <UnlockOutlined />}
                disabled={isSelf}
                onClick={() => toggleActive(record)}
              />
            </Tooltip>
            <Popconfirm
              title={`确认删除账号「${record.username}」？`}
              onConfirm={() => handleDelete(record)}
              disabled={isSelf}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={isSelf} />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0 }}>账号管理</h2>
          <p style={{ margin: "4px 0 0", color: "#888", fontSize: 13 }}>
            管理编辑账号，编辑员可增删改俱乐部/球员数据，但无法管理账号。
          </p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { form.resetFields(); setCreateModal(true); }}
        >
          新建账号
        </Button>
      </div>

      <Table
        dataSource={users}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      {/* 新建账号 */}
      <Modal
        title="新建账号"
        open={createModal}
        onOk={() => form.submit()}
        onCancel={() => setCreateModal(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input placeholder="字母 + 数字，不含空格" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[{ required: true, message: "请输入密码" }, { min: 8, message: "至少 8 位" }]}
          >
            <Input.Password placeholder="至少 8 位" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="editor">
            <Select
              options={[
                { value: "editor", label: "编辑员 — 可管理俱乐部/球员/转会数据" },
                { value: "admin",  label: "超级管理员 — 全权限，含账号管理" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 */}
      <Modal
        title={`重置密码：${pwdModal.user?.username}`}
        open={pwdModal.open}
        onOk={() => pwdForm.submit()}
        onCancel={() => setPwdModal({ open: false })}
        destroyOnClose
      >
        <Form form={pwdForm} layout="vertical" onFinish={handleResetPwd} style={{ marginTop: 16 }}>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true }, { min: 8, message: "至少 8 位" }]}
          >
            <Input.Password placeholder="至少 8 位" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={["new_password"]}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue("new_password") === value
                    ? Promise.resolve()
                    : Promise.reject("两次密码不一致");
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
