import { useState, useEffect } from "react";
import {
  Table, Button, Modal, Form, Input, Select, InputNumber,
  Space, Popconfirm, message, Tag,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { adminApi, ClubPayload } from "../../api/client";

const TIERS = [
  { value: "free", label: "Free（免费可见）" },
  { value: "basic", label: "Basic" },
  { value: "pro", label: "Pro" },
];

const TIER_COLOR: Record<string, string> = { free: "default", basic: "blue", pro: "gold" };

export default function ClubList() {
  const [clubs, setClubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState<{ open: boolean; record?: any }>({ open: false });
  const [form] = Form.useForm();

  const fetchClubs = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listClubs();
      setClubs(res.data.data ?? res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchClubs(); }, []);

  const openCreate = () => {
    form.resetFields();
    setModal({ open: true });
  };

  const openEdit = (record: any) => {
    form.setFieldsValue(record);
    setModal({ open: true, record });
  };

  const handleSave = async (values: ClubPayload) => {
    try {
      if (modal.record) {
        await adminApi.updateClub(modal.record.id, values);
        message.success("更新成功");
      } else {
        await adminApi.createClub(values);
        message.success("创建成功");
      }
      setModal({ open: false });
      fetchClubs();
    } catch {
      message.error("操作失败，请检查输入");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await adminApi.deleteClub(id);
      message.success("已删除");
      fetchClubs();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 64 },
    { title: "俱乐部名称", dataIndex: "name", width: 160 },
    { title: "缩写", dataIndex: "short_name", width: 80 },
    { title: "国家/地区", dataIndex: "country", width: 120 },
    { title: "成立年份", dataIndex: "founded_year", width: 100 },
    { title: "主场", dataIndex: "stadium" },
    {
      title: "访问权限",
      dataIndex: "access_tier",
      width: 120,
      render: (t: string) => <Tag color={TIER_COLOR[t] ?? "default"}>{t ?? "free"}</Tag>,
    },
    {
      title: "操作",
      width: 140,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除该俱乐部？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>俱乐部管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增俱乐部</Button>
      </div>

      <Table
        dataSource={clubs}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title={modal.record ? "编辑俱乐部" : "新增俱乐部"}
        open={modal.open}
        onOk={() => form.submit()}
        onCancel={() => setModal({ open: false })}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
          <Form.Item name="name" label="俱乐部名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="如：曼彻斯特城" />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item name="short_name" label="缩写" style={{ flex: 1 }}>
              <Input placeholder="如：MCI" />
            </Form.Item>
            <Form.Item name="country" label="国家/地区" style={{ flex: 1 }}>
              <Input placeholder="如：英格兰" />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item name="founded_year" label="成立年份" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={1800} max={2099} placeholder="1880" />
            </Form.Item>
            <Form.Item name="league_id" label="联赛 ID" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={1} />
            </Form.Item>
          </Space>
          <Form.Item name="stadium" label="主场球场">
            <Input placeholder="如：伊蒂哈德球场" />
          </Form.Item>
          <Form.Item name="access_tier" label="访问权限等级">
            <Select options={TIERS} placeholder="默认 free" allowClear />
          </Form.Item>
          <Form.Item name="description" label="俱乐部简介">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
