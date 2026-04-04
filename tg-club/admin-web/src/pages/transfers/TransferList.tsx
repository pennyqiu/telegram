import { useState, useEffect } from "react";
import {
  Table, Button, Modal, Form, Input, Select, InputNumber,
  Space, message, Tag, Descriptions,
} from "antd";
import { PlusOutlined, EyeOutlined } from "@ant-design/icons";
import { adminApi, TransferPayload } from "../../api/client";

const TRANSFER_TYPES: Record<string, { label: string; color: string }> = {
  permanent: { label: "永久转会", color: "red" },
  loan: { label: "租借", color: "blue" },
  free: { label: "自由转会", color: "green" },
  youth: { label: "青训晋升", color: "purple" },
};

export default function TransferList() {
  const [players, setPlayers] = useState<any[]>([]);
  const [transfers, setTransfers] = useState<any[]>([]);
  const [loadingPlayers, setLoadingPlayers] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [detailModal, setDetailModal] = useState<{ open: boolean; record?: any }>({ open: false });
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoadingPlayers(true);
    try {
      const [pRes, tRes] = await Promise.all([
        adminApi.listPlayers(),
        adminApi.listTransfers(),
      ]);
      setPlayers(pRes.data.data ?? pRes.data);
      setTransfers(tRes.data.data ?? tRes.data);
    } finally {
      setLoadingPlayers(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreate = async (values: TransferPayload) => {
    try {
      await adminApi.createTransfer(values);
      message.success("转会记录已录入");
      setCreateModal(false);
      form.resetFields();
      fetchData();
    } catch {
      message.error("录入失败，请检查输入");
    }
  };

  const playerOptions = players.map((p) => ({ value: p.id, label: `#${p.id} ${p.name}` }));
  const clubOptions = players
    .filter((p) => p.current_club_id)
    .map((p) => ({ value: p.current_club_id, label: `俱乐部 #${p.current_club_id}` }));

  const columns = [
    { title: "ID", dataIndex: "id", width: 64 },
    {
      title: "球员",
      dataIndex: "player_name",
      render: (_: any, r: any) => r.player_name ?? `#${r.player_id}`,
    },
    {
      title: "类型",
      dataIndex: "type",
      width: 110,
      render: (t: string) => {
        const info = TRANSFER_TYPES[t] ?? { label: t, color: "default" };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: "转出俱乐部",
      dataIndex: "from_club_name",
      render: (_: any, r: any) => r.from_club_name ?? (r.from_club_id ? `#${r.from_club_id}` : "—"),
    },
    {
      title: "转入俱乐部",
      dataIndex: "to_club_name",
      render: (_: any, r: any) => r.to_club_name ?? (r.to_club_id ? `#${r.to_club_id}` : "—"),
    },
    { title: "转会费", dataIndex: "fee_display", width: 100, render: (v: string) => v ?? "—" },
    { title: "日期", dataIndex: "transfer_date", width: 110 },
    {
      title: "操作",
      width: 80,
      render: (_: any, record: any) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailModal({ open: true, record })}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>转会记录</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateModal(true); }}>
          录入转会
        </Button>
      </div>

      <Table
        dataSource={transfers}
        columns={columns}
        rowKey="id"
        loading={loadingPlayers}
        pagination={{ pageSize: 20 }}
      />

      {/* 录入转会 */}
      <Modal
        title="录入转会记录"
        open={createModal}
        onOk={() => form.submit()}
        onCancel={() => setCreateModal(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item name="player_id" label="球员" rules={[{ required: true, message: "请选择球员" }]}>
            <Select
              showSearch
              options={playerOptions}
              placeholder="搜索球员姓名或 ID"
              filterOption={(input, opt) =>
                (opt?.label as string).toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="type" label="转会类型" rules={[{ required: true }]}>
            <Select
              options={Object.entries(TRANSFER_TYPES).map(([v, { label }]) => ({ value: v, label }))}
            />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item name="from_club_id" label="转出俱乐部 ID" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={1} placeholder="留空=无" />
            </Form.Item>
            <Form.Item name="to_club_id" label="转入俱乐部 ID" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={1} placeholder="留空=自由" />
            </Form.Item>
          </Space>
          <Form.Item name="transfer_date" label="转会日期" rules={[{ required: true }]}>
            <Input type="date" />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item name="fee_display" label="转会费（展示）" style={{ flex: 1 }}>
              <Input placeholder="如 €85M" />
            </Form.Item>
            <Form.Item name="fee_stars" label="Stars 价格" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={0} placeholder="可选" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title="转会详情"
        open={detailModal.open}
        onCancel={() => setDetailModal({ open: false })}
        footer={null}
      >
        {detailModal.record && (
          <Descriptions column={1} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="ID">{detailModal.record.id}</Descriptions.Item>
            <Descriptions.Item label="球员">
              {detailModal.record.player_name ?? `#${detailModal.record.player_id}`}
            </Descriptions.Item>
            <Descriptions.Item label="类型">
              {TRANSFER_TYPES[detailModal.record.type]?.label ?? detailModal.record.type}
            </Descriptions.Item>
            <Descriptions.Item label="转出">
              {detailModal.record.from_club_name ?? detailModal.record.from_club_id ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="转入">
              {detailModal.record.to_club_name ?? detailModal.record.to_club_id ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="转会费">{detailModal.record.fee_display ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="日期">{detailModal.record.transfer_date}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}
