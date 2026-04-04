# 俱乐部与球员推荐系统设计文档

> 基于现有 Telegram 订阅体系，通过付费订阅解锁俱乐部与球员详细信息、转会数据及智能推荐功能。

---

## 1. 系统概述

### 1.1 业务定位

```
┌─────────────────────────────────────────────────────────┐
│                    系统价值链                             │
│                                                         │
│  管理员（Admin Web）                                     │
│    └── 录入/维护 俱乐部、球员、转会、退役数据             │
│                    │                                    │
│                    ▼                                    │
│           数据库（结构化数据 + 图片）                     │
│                    │                                    │
│                    ▼                                    │
│  用户（Telegram Mini App）                               │
│    ├── 免费：浏览俱乐部名称、球员姓名（脱敏预览）          │
│    ├── Basic 订阅：查看俱乐部详情 + 球员基础信息          │
│    └── Pro 订阅：全量数据 + 转会历史 + 智能推荐           │
└─────────────────────────────────────────────────────────┘
```

### 1.2 核心功能模块

| 模块 | 说明 |
|------|------|
| 俱乐部管理 | 增删查改俱乐部信息、Logo、联赛归属 |
| 球员管理 | 增删查改球员档案（含图片、身体数据） |
| 转会系统 | 记录球员在俱乐部间的转入/转出、转会费 |
| 退役系统 | 球员退役标记、历史成就记录 |
| 推荐引擎 | 基于位置/数据相似度推荐同类球员/俱乐部 |
| 订阅权限网关 | 按订阅等级控制数据可见范围 |

---

## 2. 数据模型设计

### 2.1 实体关系图

```
┌──────────────┐         ┌─────────────────────┐
│   leagues    │         │       clubs          │
│──────────────│         │─────────────────────│
│ id           │◄──N:1───│ league_id (FK)       │
│ name         │         │ id                   │
│ country      │         │ name                 │
│ logo_url     │         │ logo_url             │
│ level        │         │ country              │
└──────────────┘         │ founded_year         │
                         │ stadium              │
                         │ description          │
                         │ status               │
                         └──────────┬───────────┘
                                    │ 1:N
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
          ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
          │   players    │  │  transfers  │  │ club_stats   │
          │──────────────│  │─────────────│  │──────────────│
          │ id           │  │ id          │  │ season       │
          │ name         │  │ player_id   │  │ titles       │
          │ photo_url    │  │ from_club   │  │ members      │
          │ birth_date   │  │ to_club     │  └──────────────┘
          │ height_cm    │  │ transfer_at │
          │ weight_kg    │  │ fee_stars   │
          │ position     │  │ type        │
          │ nationality  │  └─────────────┘
          │ current_club │
          │ status       │
          │ bio          │
          └──────────────┘
```

### 2.2 完整 DDL

#### 联赛表 `leagues`

```sql
CREATE TABLE leagues (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,       -- e.g. 英超
    country     VARCHAR(64) NOT NULL,        -- e.g. 英格兰
    logo_url    VARCHAR(512),
    level       INTEGER DEFAULT 1,           -- 1=顶级联赛，2=次级...
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

#### 俱乐部表 `clubs`

```sql
CREATE TYPE club_status AS ENUM ('active', 'disbanded', 'merged');

CREATE TABLE clubs (
    id              SERIAL PRIMARY KEY,
    league_id       INTEGER REFERENCES leagues(id),
    name            VARCHAR(128) NOT NULL,
    short_name      VARCHAR(32),             -- 缩写，如 MCI
    logo_url        VARCHAR(512),
    country         VARCHAR(64),
    founded_year    INTEGER,
    stadium         VARCHAR(128),
    stadium_capacity INTEGER,
    description     TEXT,
    status          club_status DEFAULT 'active',
    -- 订阅权限标记
    access_tier     VARCHAR(16) DEFAULT 'basic', -- free / basic / pro
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_clubs_league ON clubs(league_id);
CREATE INDEX idx_clubs_status ON clubs(status);
```

#### 球员表 `players`

```sql
CREATE TYPE player_status AS ENUM ('active', 'retired', 'free_agent', 'loan');
CREATE TYPE player_position AS ENUM (
    'GK',           -- 门将
    'CB', 'LB', 'RB', 'LWB', 'RWB',  -- 后卫
    'CDM', 'CM', 'CAM',               -- 中场
    'LM', 'RM', 'LW', 'RW',           -- 边路
    'CF', 'ST'                        -- 前锋
);

CREATE TABLE players (
    id              SERIAL PRIMARY KEY,
    current_club_id INTEGER REFERENCES clubs(id),

    -- 基础信息
    name            VARCHAR(128) NOT NULL,
    name_en         VARCHAR(128),            -- 英文名
    photo_url       VARCHAR(512),
    birth_date      DATE,
    nationality     VARCHAR(64),
    position        player_position,
    status          player_status DEFAULT 'active',

    -- 身体数据
    height_cm       SMALLINT,
    weight_kg       SMALLINT,
    preferred_foot  VARCHAR(8),              -- left / right / both

    -- 详细信息（Pro 权限）
    bio             TEXT,
    market_value    INTEGER,                 -- Stars 估值
    jersey_number   SMALLINT,

    -- 推荐系统标签
    tags            JSONB DEFAULT '[]',      -- ["速度型", "技术流", "强壮"]
    rating          NUMERIC(3,1),            -- 综合评分 0-10

    -- 权限标记
    access_tier     VARCHAR(16) DEFAULT 'basic',

    retired_at      DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_players_club ON players(current_club_id);
CREATE INDEX idx_players_status ON players(status);
CREATE INDEX idx_players_position ON players(position);
```

#### 转会记录表 `transfers`

```sql
CREATE TYPE transfer_type AS ENUM (
    'permanent',    -- 永久转会
    'loan',         -- 租借
    'loan_end',     -- 租借结束回归
    'free',         -- 自由转会
    'youth'         -- 青训晋升
);

CREATE TABLE transfers (
    id              SERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    from_club_id    INTEGER REFERENCES clubs(id),   -- NULL = 无主
    to_club_id      INTEGER REFERENCES clubs(id),   -- NULL = 退役/自由
    type            transfer_type NOT NULL,
    transfer_date   DATE NOT NULL,
    fee_display     VARCHAR(64),                    -- 展示用，如 "€85M"
    fee_stars       INTEGER DEFAULT 0,              -- Stars 换算估值
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transfers_player ON transfers(player_id);
CREATE INDEX idx_transfers_date ON transfers(transfer_date DESC);
```

#### 退役记录表 `retirements`

```sql
CREATE TABLE retirements (
    id              SERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id) UNIQUE,
    retired_at      DATE NOT NULL,
    last_club_id    INTEGER REFERENCES clubs(id),
    career_summary  TEXT,                           -- 职业生涯总结
    achievements    JSONB DEFAULT '[]',             -- ["英超冠军x3", "金球奖x1"]
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### 图片资源表 `media_assets`

```sql
CREATE TYPE asset_type AS ENUM ('club_logo', 'player_photo', 'stadium_photo', 'trophy');

CREATE TABLE media_assets (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(32) NOT NULL,   -- 'club' / 'player'
    entity_id       INTEGER NOT NULL,
    asset_type      asset_type NOT NULL,
    url             VARCHAR(512) NOT NULL,  -- 对象存储 URL
    thumbnail_url   VARCHAR(512),
    width           INTEGER,
    height          INTEGER,
    size_bytes      INTEGER,
    is_primary      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assets_entity ON media_assets(entity_type, entity_id);
```

---

## 3. 订阅权限分级

### 3.1 内容分级规则

| 内容 | 免费 | Basic（250 XTR/月） | Pro（550 XTR/月） |
|------|------|---------------------|------------------|
| 俱乐部名称、所在联赛 | ✅ | ✅ | ✅ |
| 俱乐部 Logo | ✅ | ✅ | ✅ |
| 俱乐部详情（简介、球场、成立年份） | ❌ 模糊 | ✅ | ✅ |
| 球员姓名 | ✅ | ✅ | ✅ |
| 球员照片 | ❌ | ✅ | ✅ |
| 球员身高/体重/位置 | ❌ | ✅ | ✅ |
| 球员详细 Bio + 评分 | ❌ | ❌ | ✅ |
| 转会历史 | ❌ | 最近 1 次 | ✅ 全部 |
| 退役球员档案 | ❌ | ❌ | ✅ |
| 智能推荐（相似球员/俱乐部） | ❌ | ❌ | ✅ |
| 散装球员（自由球员）列表 | ❌ | ✅ | ✅ |

### 3.2 权限控制实现

```python
def filter_player_by_tier(player: dict, user_tier: str) -> dict:
    """根据订阅等级过滤球员数据字段"""
    if user_tier == "free":
        return {
            "id": player["id"],
            "name": player["name"],
            "position": player["position"],
            "current_club": player["current_club_name"],
        }
    elif user_tier == "basic":
        return {**player, "bio": None, "transfers": player["transfers"][:1]}
    else:  # pro
        return player  # 全量返回
```

---

## 4. 管理端设计

### 4.1 技术方案

```
管理端采用独立 Web 应用：
  框架：React + Ant Design Pro（功能丰富，表格/表单现成）
  路由：React Router
  状态：Zustand
  请求：Axios
  部署：与 Bot 后端同域，/admin/* 路径，Nginx 反代
  认证：JWT（管理员账号独立，非 Telegram 用户体系）
```

### 4.2 页面结构

```
管理后台（/admin）
│
├── 登录页
│
├── 仪表盘
│   ├── 俱乐部总数 / 球员总数 / 本月转会次数
│   └── 最近操作记录
│
├── 联赛管理
│   ├── 联赛列表（搜索/筛选）
│   ├── 新建联赛
│   └── 编辑/删除联赛
│
├── 俱乐部管理
│   ├── 俱乐部列表（按联赛筛选）
│   ├── 新建俱乐部（含 Logo 上传）
│   ├── 编辑俱乐部
│   ├── 查看球员名单
│   └── 解散俱乐部
│
├── 球员管理
│   ├── 球员列表（按俱乐部/位置/状态筛选）
│   ├── 新建球员（含照片上传）
│   ├── 编辑球员信息
│   ├── 操作：转会 / 租借 / 退役
│   └── 查看转会历史
│
├── 转会中心
│   ├── 转会记录列表
│   ├── 录入转会
│   └── 录入租借
│
└── 系统设置
    ├── 管理员账号管理
    └── 图片存储配置
```

### 4.3 核心表单设计

#### 新建/编辑俱乐部

```
俱乐部信息
├── 俱乐部名称 *         [文本输入]
├── 缩写                [文本输入，最多 5 字]
├── 所属联赛 *           [下拉选择]
├── 国家 *              [下拉选择]
├── 成立年份             [数字输入]
├── 主场球场             [文本输入]
├── 球场容量             [数字输入]
├── Logo 上传 *         [图片上传，自动生成缩略图]
├── 俱乐部简介           [富文本编辑器]
├── 内容权限等级         [单选：免费 / Basic / Pro]
└── 状态                [单选：活跃 / 解散 / 合并]
```

#### 新建/编辑球员

```
球员档案
├── 基础信息
│   ├── 姓名 *           [文本输入]
│   ├── 英文名           [文本输入]
│   ├── 照片上传 *        [图片上传]
│   ├── 出生日期 *        [日期选择器]（自动计算年龄）
│   ├── 国籍 *           [下拉选择]
│   └── 惯用脚           [单选：左脚 / 右脚 / 双脚]
│
├── 球场信息
│   ├── 位置 *           [下拉选择，含图示]
│   ├── 当前俱乐部        [下拉搜索]
│   ├── 球衣号码          [数字输入]
│   └── 综合评分          [滑块 0-10]
│
├── 身体数据
│   ├── 身高（cm）*       [数字输入]
│   └── 体重（kg）*       [数字输入]
│
├── 标签                 [多选标签，如：速度型/技术流/强壮]
├── 球员简介（Bio）       [富文本]
├── 内容权限等级          [单选：Basic / Pro]
└── 状态                 [单选：在役 / 租借中 / 自由球员]
```

#### 录入转会

```
转会信息
├── 球员 *              [搜索选择]
├── 转会类型 *          [单选：永久 / 租借 / 自由 / 青训]
├── 转出俱乐部          [搜索选择，可为空（无主）]
├── 转入俱乐部 *        [搜索选择]
├── 转会日期 *          [日期选择]
├── 转会费（展示）       [文本，如 €85M]
├── 转会费（Stars 估值）[数字输入]
└── 备注               [文本]

→ 保存后自动更新球员的 current_club_id
```

#### 办理退役

```
退役信息
├── 球员 *              [已预填]
├── 退役日期 *          [日期选择]
├── 最终效力俱乐部       [已预填，可修改]
├── 职业生涯总结         [富文本]
└── 荣誉成就            [可多行添加，如 "英超冠军 x3"]

→ 保存后将球员 status 改为 retired
```

---

## 5. 推荐系统设计

### 5.1 相似球员推荐

基于以下维度计算相似度：

```python
def compute_player_similarity(p1, p2) -> float:
    """计算两名球员相似度（0-1）"""
    score = 0.0

    # 位置相同 +0.4
    if p1.position == p2.position:
        score += 0.4

    # 身高差 <5cm +0.1
    if abs(p1.height_cm - p2.height_cm) < 5:
        score += 0.1

    # 年龄差 <3岁 +0.1
    if abs(p1.age - p2.age) < 3:
        score += 0.1

    # 评分差 <1分 +0.2
    if abs(p1.rating - p2.rating) < 1.0:
        score += 0.2

    # 标签重叠比例 0-0.2
    common_tags = set(p1.tags) & set(p2.tags)
    tag_score = len(common_tags) / max(len(p1.tags), len(p2.tags), 1)
    score += tag_score * 0.2

    return score
```

### 5.2 推荐场景

| 场景 | 推荐逻辑 | 权限 |
|------|----------|------|
| 查看球员详情页 | 推荐 Top5 相似球员 | Pro |
| 查看俱乐部页 | 推荐同联赛其他俱乐部 | Basic+ |
| 自由球员列表 | 按位置推荐适合该俱乐部的球员 | Pro |
| 首页 | 推荐本周最热门球员/转会新闻 | 免费 |

---

## 6. Mini App 用户端设计

### 6.1 页面结构

```
Mini App（用户端）
│
├── 首页
│   ├── 热门俱乐部（横向滚动卡片）
│   ├── 最新转会动态
│   └── 本周推荐球员
│
├── 俱乐部
│   ├── 联赛筛选 + 搜索
│   ├── 俱乐部卡片列表
│   └── 俱乐部详情页
│       ├── Logo + 基本信息
│       ├── 球员名单（按位置分组）
│       └── 近期转会记录
│
├── 球员
│   ├── 位置筛选 + 搜索
│   ├── 球员卡片列表（含照片）
│   └── 球员详情页
│       ├── 照片 + 基础数据
│       ├── 身体数据
│       ├── 转会历史时间轴
│       ├── 相似球员推荐（Pro）
│       └── 职业生涯成就
│
├── 自由球员
│   └── 状态为 free_agent 的球员列表（Basic+）
│
└── 我的订阅
    └── 跳转订阅中心 Mini App
```

### 6.2 权限锁定 UI 示例

```
┌───────────────────────────────┐
│  球员：克里斯蒂亚诺·罗纳尔多    │
│  位置：前锋  国籍：葡萄牙       │
│                               │
│  身高：███ cm   体重：███ kg    │ ← 模糊处理
│  评分：██ / 10                 │
│                               │
│  ┌─────────────────────────┐  │
│  │  🔒 升级到 Basic 订阅     │  │
│  │  解锁完整球员数据          │  │
│  │  [250 Stars/月 立即订阅]  │  │
│  └─────────────────────────┘  │
└───────────────────────────────┘
```

---

## 7. 图片存储方案

```
上传流程：
管理员上传图片
    │
    ▼
Admin 后端接收（multipart/form-data）
    │
    ▼
压缩 + 生成缩略图（Pillow）
  原图：最大 1920px，压缩至 <500KB
  缩略图：300x300，<50KB
    │
    ▼
上传至对象存储
  推荐：Cloudflare R2（免费额度 10GB/月）
  备选：AWS S3 / 阿里云 OSS
    │
    ▼
存储 URL 到 media_assets 表
```

**Cloudflare R2 费用**：10GB 存储 + 100万次请求/月 免费，超出 $0.015/GB，球员/俱乐部数据量极小，基本免费。

---

## 8. 后端 API 补充

在现有接口基础上新增：

```
# 俱乐部
GET  /clubs                   # 列表（支持 league_id / search 参数）
GET  /clubs/{id}              # 详情（按权限过滤字段）
GET  /clubs/{id}/players      # 俱乐部球员名单

# 球员
GET  /players                 # 列表（position / club_id / status / search）
GET  /players/{id}            # 详情（按权限过滤）
GET  /players/{id}/transfers  # 转会历史（Basic=1条，Pro=全部）
GET  /players/{id}/similar    # 相似球员推荐（Pro）

# 自由球员
GET  /players/free-agents     # 自由球员列表（Basic+）

# 管理端（需 Admin JWT）
POST   /admin/clubs
PUT    /admin/clubs/{id}
DELETE /admin/clubs/{id}
POST   /admin/players
PUT    /admin/players/{id}
DELETE /admin/players/{id}
POST   /admin/transfers        # 录入转会
POST   /admin/retirements      # 办理退役
POST   /admin/upload/image     # 图片上传
```

---

## 9. 开发阶段规划

| Sprint | 周期 | 交付内容 |
|--------|------|----------|
| Sprint 1 | 1 周 | 数据库建表 + 俱乐部/球员/联赛 CRUD API |
| Sprint 2 | 1 周 | 管理端前端（俱乐部 + 球员增删查改 + 图片上传） |
| Sprint 3 | 1 周 | 转会录入 + 退役办理 + 管理端完善 |
| Sprint 4 | 1 周 | 订阅权限网关 + Mini App 俱乐部/球员浏览页 |
| Sprint 5 | 1 周 | 推荐引擎 + 相似球员功能 + 自由球员列表 |
| Sprint 6 | 按需 | 数据导入工具（批量录入历史数据） |
