import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, InputNumber, Space, Popconfirm, message, Tag } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, SwapOutlined, TrophyOutlined } from "@ant-design/icons";
import { adminApi, PlayerPayload, TransferPayload, RetirementPayload } from "../../api/client";

const POSITIONS = ["GK","CB","LB","RB","CDM","CM","CAM","LW","RW","CF","ST"];

export default function PlayerList() {
  const [players, setPlayers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [formModal, setFormModal] = useState<{ open: boolean; record?: any }>({ open: false });
  const [transferModal, setTransferModal] = useState<{ open: boolean; playerId?: number }>({ open: false });
  const [retireModal, setRetireModal] = useState<{ open: boolean; playerId?: number }>({ open: false });
  const [form] = Form.useForm();
  const [transferForm] = Form.useForm();
  const [retireForm] = Form.useForm();

  const fetchPlayers = async () => {
    setLoading(true);
    const res = await adminApi.listPlayers();
    setPlayers(res.data.data);
    setLoading(false);
  };

  useEffect(() => { fetchPlayers(); }, []);

  const handleSave = async (values: PlayerPayload) => {
    if (formModal.record) {
      await adminApi.updatePlayer(formModal.record.id, values);
      message.success("更新成功");
    } else {
      await adminApi.createPlayer(values);
      message.success("创建成功");
    }
    setFormModal({ open: false });
    fetchPlayers();
  };

  const handleDelete = async (id: number) => {
    await adminApi.deletePlayer(id);
    message.success("已删除");
    fetchPlayers();
  };

  const handleTransfer = async (values: TransferPayload) => {
    await adminApi.createTransfer({ ...values, player_id: transferModal.playerId! });
    message.success("转会记录已录入");
    setTransferModal({ open: false });
  };

  const handleRetire = async (values: RetirementPayload) => {
    await adminApi.retirePlayer({ ...values, player_id: retireModal.playerId! });
    message.success("已办理退役");
    setRetireModal({ open: false });
    fetchPlayers();
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "姓名", dataIndex: "name" },
    { title: "位置", dataIndex: "position" },
    {
      title: "状态", dataIndex: "status",
      render: (s: string) => (
        <Tag color={s === "active" ? "green" : s === "retired" ? "gray" : "orange"}>
          {s === "active" ? "在役" : s === "retired" ? "已退役" : "自由球员"}
        </Tag>
      )
    },
    {
      title: "操作",
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />}
            onClick={() => { setFormModal({ open: true, record }); form.setFieldsValue(record); }}>编辑</Button>
          <Button size="small" icon={<SwapOutlined />}
            onClick={() => setTransferModal({ open: true, playerId: record.id })}>转会</Button>
          {record.status !== "retired" && (
            <Button size="small" icon={<TrophyOutlined />}
              onClick={() => setRetireModal({ open: true, playerId: record.id })}>退役</Button>
          )}
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>球员管理</h2>
        <Button type="primary" icon={<PlusOutlined />}
          onClick={() => { setFormModal({ open: true }); form.resetFields(); }}>新增球员</Button>
      </div>

      <Table dataSource={players} columns={columns} rowKey="id" loading={loading} />

      {/* 新增/编辑球员 */}
      <Modal title={formModal.record ? "编辑球员" : "新增球员"} open={formModal.open}
        onOk={() => form.submit()} onCancel={() => setFormModal({ open: false })} width={640}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label="英文名"><Input /></Form.Item>
          <Form.Item name="position" label="位置">
            <Select options={POSITIONS.map(p => ({ value: p, label: p }))} />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item name="height_cm" label="身高(cm)" style={{ flex: 1 }}><InputNumber style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="weight_kg" label="体重(kg)" style={{ flex: 1 }}><InputNumber style={{ width: "100%" }} /></Form.Item>
          </Space>
          <Form.Item name="nationality" label="国籍"><Input /></Form.Item>
          <Form.Item name="birth_date" label="出生日期"><Input type="date" /></Form.Item>
          <Form.Item name="preferred_foot" label="惯用脚">
            <Select options={[{ value: "left", label: "左脚" }, { value: "right", label: "右脚" }, { value: "both", label: "双脚" }]} />
          </Form.Item>
          <Form.Item name="rating" label="综合评分"><InputNumber min={0} max={10} step={0.1} /></Form.Item>
          <Form.Item name="access_tier" label="权限等级">
            <Select options={[{ value: "basic", label: "Basic" }, { value: "pro", label: "Pro" }]} />
          </Form.Item>
          <Form.Item name="bio" label="球员简介"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      {/* 转会 */}
      <Modal title="录入转会" open={transferModal.open}
        onOk={() => transferForm.submit()} onCancel={() => setTransferModal({ open: false })}>
        <Form form={transferForm} layout="vertical" onFinish={handleTransfer}>
          <Form.Item name="type" label="转会类型" rules={[{ required: true }]}>
            <Select options={[
              { value: "permanent", label: "永久转会" }, { value: "loan", label: "租借" },
              { value: "free", label: "自由转会" }, { value: "youth", label: "青训晋升" },
            ]} />
          </Form.Item>
          <Form.Item name="to_club_id" label="转入俱乐部ID"><InputNumber style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="from_club_id" label="转出俱乐部ID"><InputNumber style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="transfer_date" label="转会日期" rules={[{ required: true }]}><Input type="date" /></Form.Item>
          <Form.Item name="fee_display" label="转会费（展示）"><Input placeholder="如 €85M" /></Form.Item>
        </Form>
      </Modal>

      {/* 退役 */}
      <Modal title="办理退役" open={retireModal.open}
        onOk={() => retireForm.submit()} onCancel={() => setRetireModal({ open: false })}>
        <Form form={retireForm} layout="vertical" onFinish={handleRetire}>
          <Form.Item name="retired_at" label="退役日期" rules={[{ required: true }]}><Input type="date" /></Form.Item>
          <Form.Item name="career_summary" label="职业生涯总结"><Input.TextArea rows={4} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
