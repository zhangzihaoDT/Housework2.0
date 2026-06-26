# housework-feishu-bot 🐝

飞书家务积分机器人 — 用 LLM 解析家务消息并记录到飞书多维表格。

## 项目目标

- 用户在飞书群里发送 `家务：我洗了碗`，机器人自动识别任务类型并计算积分。
- 积分记录写入飞书多维表格，无需自建数据库。
- 部署在 Sealos，零运维。

## 架构概览

```
用户 ──飞书消息──▶ 事件接收（HTTP 回调 / WS 长连接）
                    │
                    ▼
               app/event_handler.py
                    │
                    ├─▶ 前缀过滤（家务：/家务:）
                    ├─▶ 消息去重
                    ├─▶ LLM 解析
                    ├─▶ 多维表格写入
                    └─▶ 群内回复
```

### 目录结构

| 路径 | 说明 |
|---|---|
| `app/main.py` | FastAPI 应用入口，/health + HTTP 回调 |
| `app/config.py` | 环境变量配置 |
| `app/event_handler.py` | 共享事件处理逻辑（两个入口共用） |
| `app/feishu_client.py` | 飞书 API 客户端（token、发消息） |
| `app/chore_service.py` | 家务前缀判断与清洗 |
| `app/schemas.py` | Pydantic 数据模型 |
| `app/bitable_client.py` | 多维表格客户端 |
| `app/llm_parser.py` | LLM 结构化解析 |
| `scripts/start_feishu_ws.py` | 飞书长连接（WebSocket）启动脚本 |

## 事件接收方式

项目支持两种接收飞书事件的方式：

### 方式一：HTTP 回调（需要公网地址）

适用于 Sealos 部署或有公网 IP/域名的场景。

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
```

飞书后台配置：事件回调地址 `https://<your-domain>/feishu/events`

本地调试可配合 ngrok / Cloudflare Tunnel 暴露本地端口。

### 方式二：WebSocket 长连接（本地开发首选）

适用于本地开发，不需要公网地址。

```bash
python scripts/start_feishu_ws.py
```

飞书后台配置：
1. 事件与回调 → 回调配置 → 订阅方式选择「使用长连接接收事件」
2. 添加事件 `im.message.receive_v1`
3. **必须**先运行启动脚本（长连接建立后），后台才能保存成功
4. 如果飞书后台提示 `app not online`，说明长连接未建立，需要先启动脚本

> ⚠️ 不要同时运行多个长连接实例，否则可能导致事件处理异常。
> ⚠️ 企业自建应用需要发版/授权后事件才生效。
> ⚠️ 长连接模式和 HTTP 回调模式互斥，飞书后台只能选择一种订阅方式。

## 当前实现状态

### 已完成 ✅

- [x] 项目初始化骨架
- [x] 健康检查接口
- [x] HTTP 回调事件入口 + challenge 校验
- [x] WebSocket 长连接事件入口
- [x] 飞书 tenant_access_token 获取（含内存缓存与自动刷新）
- [x] 飞书群聊 / 私聊文本消息发送
- [x] 接收 `im.message.receive_v1` 事件
- [x] 过滤非文本消息
- [x] `家务：` / `家务:` 前缀判断
- [x] 机器人自动回复 `收到家务记录：{内容}`
- [x] 消息 ID 去重（内存 set，防止重复回复）
- [x] 共享事件处理逻辑（HTTP 与长连接统一调用）
- [x] LLM 结构化解析（家务 → 任务类型 + 数量）
- [x] 本地积分计算
- [x] 多维表格写入原始输入（raw_inputs）
- [x] 多维表格写入家务记录（chore_records）

## 快速开始

### 前置条件

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 或 pip

### 安装

```bash
cp .env.example .env
# 编辑 .env，填入真实配置

uv sync
```

### 运行（HTTP 回调模式）

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
```

### 运行（长连接模式）

```bash
python scripts/start_feishu_ws.py
```

## 使用方式

### 群聊（推荐）

在飞书群聊中，需要 **@机器人** 才能触发消息事件。@机器人 本身就是记录入口，不再强制要求「家务：」前缀。

```
@小哈皮 我洗了碗
@小哈皮 我刚刚洗了碗，还拖了地
@小哈皮 晚饭我做的，饭后碗也洗了
```

兼容旧格式（仍然有效）：
```
@小哈皮 家务：我洗了碗
```

### 私聊

如果是机器人私聊，可以直接发送：

```
我洗了碗
我刚刚洗了碗，还拖了地


### 验证

```bash
curl http://localhost:8020/health
# {"status":"ok"}
```

## 飞书应用配置

### 权限

- `im:message` — 获取与发送消息
- `im:message:send_as_bot` — 以机器人身份发送消息

### 事件订阅

- `im.message.receive_v1` — 接收消息事件

## 任务类型与积分规则

当前 MVP 采用**统一计分**：

- 每完成 1 项支持的家务 = 1 分
- 不区分任务强度
- 这样做是为了先降低争议，验证记录习惯和看板价值
- 后续如果需要，可以再恢复分档积分或接入 task_rules 动态规则表

支持的 9 个家务任务：

| 任务 | 积分 |
|---|---|
| 倒垃圾 | 1 |
| 收衣服 | 1 |
| 晾衣服 | 1 |
| 洗碗 | 1 |
| 扫地 | 1 |
| 洗衣服 | 1 |
| 整理房间 | 1 |
| 拖地 | 1 |
| 做饭 | 1 |

> 系统**不是关键词匹配**，而是通过 LLM 语义理解用户实际做了什么。
> 但 LLM 只能映射到当前支持的 9 类任务，不支持的任务和模糊表达暂不计分。
> 统一 1 分意味着看板更接近「完成次数」和「参与度」观察，而非劳动强度衡量。

## LLM 配置

项目使用 OpenAI-compatible API 进行家务文本解析。支持 DeepSeek、豆包、Qwen 等兼容接口。

仅需在 `.env` 中配置：

```
LLM_API_KEY=sk-xxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

如果 LLM 环境变量未配置，服务启动不受影响，仅调用解析时返回错误。

### 本地测试 LLM 解析

```bash
uv run python scripts/test_llm_parser.py
```

## 多维表格集成（Phase 4）

机器人解析家务消息后，将结果写入飞书多维表格的两张表：`raw_inputs` 和 `chore_records`。

### 流程

```
收到「家务：」消息
  → 提取 chore_text
  → LLM 解析
  → 计算积分
  → 写入 raw_inputs
  → 写入 chore_records
  → 回复飞书群
```

### 创建多维表格

在飞书多维表格中手动创建两个数据表，字段定义如下：

#### raw_inputs 表

| 字段名 | 字段类型 | 必填 | 说明 |
|---|---|---|---|
| message_id | 文本 | ✓ | 飞书消息 ID |
| chat_id | 文本 | ✓ | 群聊/私聊 ID |
| sender_id | 文本 | ✓ | 发送者 Open ID |
| raw_text | 文本 | ✓ | 原始消息文本（含 @） |
| normalized_text | 文本 | ✓ | 去除 @ 后的文本 |
| chore_text | 文本 | ✓ | 提取的家务描述 |
| status | 文本 | ✓ | parsed / ignored / failed / need_confirm |
| received_at | 日期 | ✓ | Unix 时间戳（秒） |
| ai_result_json | 文本 | | LLM 解析结果 JSON |
| total_points | 数字 | | 本次总积分 |
| task_count | 数字 | | 任务数量 |
| reply_text | 文本 | | 机器人回复文本 |
| error_message | 文本 | | 错误信息 |

#### chore_records 表

| 字段名 | 字段类型 | 必填 | 说明 |
|---|---|---|---|
| message_id | 文本 | ✓ | 关联的消息 ID |
| chat_id | 文本 | ✓ | 群聊/私聊 ID |
| sender_id | 文本 | ✓ | 发送者 Open ID |
| member_name | 文本 | | 成员名（经映射） |
| task_type | 文本 | ✓ | 任务类型（如洗碗、拖地） |
| points | 数字 | ✓ | 积分 |
| confidence | 数字 | ✓ | 置信度 0~1 |
| evidence | 文本 | ✓ | 原文中的匹配关键词 |
| source_text | 文本 | ✓ | 来源家务描述 |
| status | 文本 | ✓ | confirmed / pending |
| created_at | 日期 | ✓ | Unix 时间戳（秒） |
| date | 日期 | | 任务日期（YYYY-MM-DD） |
| week | 文本 | | ISO 年周（如 2026-W26） |
| month | 文本 | | 月份（YYYY-MM） |

### 获取 table_id

创建数据表后，从浏览器地址栏获取 `table_id`：

```
https://bytedance.feishu.cn/base/<app_token>?table=<table_id>
```

`table_id` 是以 `tbl` 开头的字符串。

### 环境变量配置

```env
FEISHU_BITABLE_APP_TOKEN=   # 多维表格 Base Token
FEISHU_TABLE_RAW_INPUTS=    # raw_inputs 表的 table_id
FEISHU_TABLE_CHORE_RECORDS= # chore_records 表的 table_id
```

### 本地测试写入

```bash
uv run python scripts/test_bitable_write.py
```

### 权限要求

飞书应用需要额外添加以下权限：

- `bitable:app` — 多维表格读写

### 注意事项

- 写入多维表格失败**不影响** LLM 解析和机器人回复
- 未配置多维表格环境变量时，服务正常启动，仅跳过写表
- 如果字段名不匹配，会在服务端日志打印详细错误
- `status=need_confirm` 或 `status=failed` 的原始输入也会写入 raw_inputs

## MVP 稳定性加固（Phase 4.5）

### 持久化去重

当前有两层去重机制：

1. **内存去重**：`_processed_message_ids` set，快速跳过同一进程内的重复消息
2. **持久化去重**：通过飞书多维表格 `records/search` API 查询 `raw_inputs` 表是否已存在相同 `message_id`

收到消息 → 内存去重 → 家务前缀判断 → 持久化去重 → LLM 解析

持久化去重失败不中断流程，仅记录 warning。脚本重启后不会重复处理已写入的消息。

### 成员映射

通过环境变量 `MEMBER_MAP_JSON` 配置 `sender_id` → 成员名映射：

```env
MEMBER_MAP_JSON={"ou_xxx":"Alice","ou_yyy":"Bob"}
```

- `chore_records` 的 `member_name` 字段会写入映射后的名称
- 未映射的 `sender_id` 显示为缩写（如 `ou_c8dc...bd86`）
- 机器人回复中暂不显示成员名

### 回复格式优化

写表成功时：
```
已记录 2 项家务，共 13 分：
- 洗碗：5 分
- 拖地：8 分
```

写表失败时：
```
已识别 2 项家务，共 13 分，但写入多维表格失败，请稍后检查：
- 洗碗：5 分
- 拖地：8 分
```

重复消息不回复，避免刷屏。

### raw_inputs 完整字段

| 字段名 | 字段类型 | 必填 | 说明 |
|---|---|---|---|
| message_id | 文本 | ✓ | 飞书消息 ID |
| chat_id | 文本 | ✓ | 群聊/私聊 ID |
| sender_id | 文本 | ✓ | 发送者 Open ID |
| raw_text | 文本 | ✓ | 原始消息文本（含 @） |
| normalized_text | 文本 | ✓ | 去除 @ 后的文本 |
| chore_text | 文本 | ✓ | 提取的家务描述 |
| status | 文本 | ✓ | parsed / ignored / failed / need_confirm |
| received_at | 日期 | ✓ | Unix 时间戳（秒） |
| ai_result_json | 文本 | | LLM 解析结果 JSON |
| total_points | 数字 | | 本次总积分 |
| task_count | 数字 | | 任务数量 |
| reply_text | 文本 | | 机器人回复文本 |
| error_message | 文本 | | 错误信息 |

### chore_records 完整字段

| 字段名 | 字段类型 | 必填 | 说明 |
|---|---|---|---|
| message_id | 文本 | ✓ | 关联的消息 ID |
| chat_id | 文本 | ✓ | 群聊/私聊 ID |
| sender_id | 文本 | ✓ | 发送者 Open ID |
| member_name | 文本 | | 成员名（经映射） |
| task_type | 文本 | ✓ | 任务类型（如洗碗、拖地） |
| points | 数字 | ✓ | 积分 |
| confidence | 数字 | ✓ | 置信度 0~1 |
| evidence | 文本 | ✓ | 原文中的匹配关键词 |
| source_text | 文本 | ✓ | 来源家务描述 |
| status | 文本 | ✓ | confirmed / pending |
| created_at | 日期 | ✓ | Unix 时间戳（秒） |
| date | 日期 | | 任务日期（YYYY-MM-DD） |
| week | 文本 | | ISO 年周（如 2026-W26） |
| month | 文本 | | 月份（YYYY-MM） |

## 多维表格字段说明（Phase 4.6）

本章节详细说明每个字段的含义、用途和看板使用方式。

### raw_inputs 字段一览

| # | 字段名 | 类型 | 写入时机 | 用途 |
|---|---|---|---|---|
| 1 | message_id | 文本 | 每次 | **排查**：消息唯一 ID，用于去重和追溯 |
| 2 | chat_id | 文本 | 每次 | **排查**：群聊/私聊 ID |
| 3 | sender_id | 文本 | 每次 | **排查**：发送者 Open ID |
| 4 | raw_text | 文本 | 每次 | **排查**：含 @ 的完整消息原文 |
| 5 | normalized_text | 文本 | 每次 | **排查**：去除 @ 后的文本 |
| 6 | chore_text | 文本 | 每次 | **排查**：LLM 收到的实际家务描述 |
| 7 | status | 文本 | 每次 | **排查**：`parsed` / `ignored` / `failed` / `need_confirm` |
| 8 | received_at | 日期 | 每次 | **看板/排查**：接收时间（Unix 时间戳） |
| 9 | ai_result_json | 文本 | 每次 | **排查**：LLM 返回的完整 JSON（含 tasks/ignored/need_confirm） |
| 10 | total_points | 数字 | 有 tasks 时 | **看板**：本次总积分 |
| 11 | task_count | 数字 | 有 tasks 时 | **看板**：本次任务数量 |
| 12 | reply_text | 文本 | 每次 | **排查**：机器人实际回复的文本 |
| 13 | error_message | 文本 | 异常时 | **排查**：写表失败等错误信息 |

用途归类：
- **排查**（9 个）：message_id / chat_id / sender_id / raw_text / normalized_text / chore_text / status / ai_result_json / reply_text / error_message
- **看板**（2 个）：total_points / task_count
- **共用**（1 个）：received_at

### chore_records 字段一览

| # | 字段名 | 类型 | 写入时机 | 用途 |
|---|---|---|---|---|
| 1 | record_id | 文本 | 自动 | **看板**：飞书自动生成的记录 ID，用于 COUNT 计数 |
| 2 | message_id | 文本 | 每次 | **排查**：关联的原始消息 ID |
| 3 | chat_id | 文本 | 每次 | **排查**：群聊/私聊 ID |
| 4 | sender_id | 文本 | 每次 | **排查**：发送者 Open ID |
| 5 | member_name | 文本 | 每次 | **看板**：映射后的成员名，看板维度 |
| 6 | task_type | 文本 | 每次 | **看板**：任务类型，看板维度 |
| 7 | points | 数字 | 每次 | **看板**：积分值，看板指标（SUM） |
| 8 | confidence | 数字 | 每次 | **排查**：LLM 置信度 |
| 9 | evidence | 文本 | 每次 | **排查**：原文中的匹配关键词 |
| 10 | source_text | 文本 | 每次 | **排查**：来源家务描述 |
| 11 | status | 文本 | 每次 | **排查**：`confirmed` / `pending` |
| 12 | created_at | 日期 | 每次 | **排查**：写入时间（Unix 时间戳） |
| 13 | date | 日期 | 每次 | **看板**：任务日期（YYYY-MM-DD） |
| 14 | week | 文本 | 每次 | **看板**：ISO 年周（如 2026-W26），用于周聚合 |
| 15 | month | 文本 | 每次 | **看板**：月份（YYYY-MM），用于月聚合 |

用途归类：
- **看板**（7 个）：record_id / member_name / task_type / points / date / week / month
- **排查**（7 个）：message_id / chat_id / sender_id / confidence / evidence / source_text / status / created_at
- **共用**（1 个）：— （各字段用途清晰）

## 飞书看板搭建建议（Phase 4.6）

以下看板均基于 **chore_records** 表，在飞书多维表格的「仪表盘」视图创建。

### A. 本周积分

```
数据源：chore_records
图表类型：柱状图
筛选条件：week 等于 当前周（如 2026-W26）
维度：member_name
指标：SUM(points)
```

步骤：
1. 打开 chore_records 表 → 新建「仪表盘」视图
2. 添加「柱状图」组件
3. 筛选器：`week` = `%CurrentWeek%`（飞书支持当前周变量）
4. X 轴：`member_name`
5. Y 轴：`points` 聚合方式选「求和」
6. 标题：本周家务积分

### B. 本月积分

```
数据源：chore_records
图表类型：柱状图
筛选条件：month 等于 当前月（如 2026-06）
维度：member_name
指标：SUM(points)
```

步骤：
1. 添加「柱状图」组件
2. 筛选器：`month` = `%CurrentMonth%`
3. X 轴：`member_name`
4. Y 轴：`points` 聚合方式选「求和」
5. 标题：本月家务积分

### C. 家务类型分布

```
数据源：chore_records
图表类型：饼图 或 柱状图
筛选条件：无（统计全部）
维度：task_type
指标：COUNT(record_id) 和 SUM(points)
```

步骤：
1. 添加「饼图」组件
2. 维度：`task_type`
3. 指标：`record_id` 聚合方式选「计数」
4. 复制一份改为「柱状图」
5. X 轴：`task_type`
6. Y 轴：`points` 聚合方式选「求和」
7. 标题：家务类型频次 / 家务类型积分

### D. 高强度任务承担

```
数据源：chore_records
图表类型：柱状图
筛选条件：points >= 8
维度：member_name
指标：COUNT(record_id) 和 SUM(points)
```

步骤：
1. 添加「柱状图」组件
2. 筛选器：`points` ≥ 8
3. X 轴：`member_name`
4. Y 轴：`record_id` 计数 + `points` 求和
5. 标题：高强度任务（≥8分）分布

### E. 最近家务记录

```
数据源：chore_records
图表类型：表格
排序：created_at 倒序
展示列：created_at / member_name / task_type / points / source_text
```

步骤：
1. 添加「表格」组件
2. 选择展示字段：`created_at`、`member_name`、`task_type`、`points`、`source_text`
3. 排序：`created_at` 降序
4. 限制行数：20 或 50
5. 标题：最近家务记录

## 当前 MVP 使用方式

### 群聊中使用

在飞书群聊中 **需要 @机器人** 才能触发消息事件。@机器人 本身就是记录入口，不再强制要求「家务：」前缀。

```
@小哈皮 我洗了碗
@小哈皮 我刚刚洗了碗，还拖了地
@小哈皮 晚饭我做的，饭后碗也洗了
```

兼容旧格式（仍然有效）：

```
@小哈皮 家务：我洗了碗
```

机器人回复：
```
已记录 1 项家务，共 1 分：
- 洗碗：1 分
```

### 私聊中使用

直接发送，不需要 @：

```
我洗了碗
我刚刚洗了碗，还拖了地
```

### 边界行为

- 群聊中不 @ 机器人的普通消息**不会触发**
- 旧格式「家务：」前缀**仍然兼容**
- 重复消息（相同 message_id）**不会重复回复**
- 脚本重启后，已写入多维表格的消息**不会重复处理**（持久化去重）
- 闲聊（你好、你是谁）、疑问（洗碗了吗？）、计划（我等会儿洗碗）、提醒（提醒我拖地）、抱怨（厨房好乱）**不会计分**
- LLM 会判断是否为已完成家务
- 不支持任务不会写入 chore_records，但会写 raw_inputs 便于复盘
- 如果多维表格写入失败，回复：
  ```
  已识别 2 项家务，共 2 分，但写入多维表格失败，请稍后检查：
  ...
  ```

### 本地验证流程

发送一条两任务消息后：

1. 检查 `raw_inputs` 表新增 **1 行**，字段完整且 `status=parsed`
2. 检查 `chore_records` 表新增 **2 行**（洗碗 + 拖地），`member_name` 已映射
3. 打开仪表盘视图，看板数据应自动更新

### 本地测试命令

```bash
# 核心业务逻辑测试（无需飞书 API）
uv run python scripts/test_chore_flow.py

# 多维表格写入测试（需要配置 FEISHU_BITABLE_APP_TOKEN）
uv run python scripts/test_bitable_write.py

# LLM 解析测试（需要 LLM_API_KEY）
uv run python scripts/test_llm_parser.py

# 启动长连接，接入飞书消息
python scripts/start_feishu_ws.py
```

## 环境变量

| 变量 | 说明 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 飞书事件验证令牌（HTTP 回调用） |
| `FEISHU_ENCRYPT_KEY` | 飞书事件加密 Key（HTTP 回调用） |
| `FEISHU_BITABLE_APP_TOKEN` | 多维表格 Base Token |
| `FEISHU_TABLE_RAW_INPUTS` | raw_inputs 表 table_id |
| `FEISHU_TABLE_TASK_RULES` | task_rules 表 table_id（TODO） |
| `FEISHU_TABLE_CHORE_RECORDS` | chore_records 表 table_id |
| `MEMBER_MAP_JSON` | 成员映射 JSON（可选） |
| `LLM_API_KEY` | LLM API Key |
| `LLM_BASE_URL` | LLM API 地址 |
| `LLM_MODEL` | 模型名称 |

## 故障排查

### 日期显示为 1970 / 1970-01-21 / 1970-W04

多维表格的日期字段显示 1970 年：

1. **根因**：秒级 Unix timestamp（如 `1782450593`）被写入飞书日期/日期时间字段。飞书将这些值按毫秒解释，导致 `1782450 秒 ≈ 1970-01-21`。
2. **修复**：项目统一通过 `app/time_utils.py` 生成时间字段，所有 DateTime 字段写入毫秒级 timestamp（13 位数字）。
3. **验证**：
   ```bash
   python scripts/test_time_utils.py
   python scripts/test_bitable_time_fields.py
   ```
4. **清理**：如果多维表格中已有 1970 年的测试记录，可以手动删除这些行，或设置看板筛选条件过滤 `date > 2025-01-01`。

### FieldNameNotFound / 字段不存在

持久化去重查询或写入时报 `code=99992402 msg=field validation failed`：

1. 飞书多维表格的字段名必须与代码写入的字段名**完全一致**（包括大小写和下划线）
2. `raw_inputs` 表必须包含以下字段：`reply_text`、`task_count`
3. `chore_records` 表必须包含以下字段：`date`、`week`、`month`
4. 运行以下命令检查字段完整性：
   ```bash
   python scripts/check_bitable_schema.py
   ```
5. 如果显示字段缺失，在飞书多维表格中手动添加对应字段后重新检查

> 注意：字段名有空格或大小写不一致会导致写入失败。例如 `reply_text`（下划线）正确，`reply text`（空格）错误。

## TODO

- [x] 项目初始化骨架
- [x] 健康检查接口
- [x] HTTP 回调事件入口 + challenge 校验
- [x] WebSocket 长连接事件入口
- [x] 飞书 tenant_access_token 获取 & 缓存
- [x] 飞书机器人群内回复
- [x] 消息去重（内存）
- [x] LLM 结构化解析（家务 → 任务类型 + 数量）
- [x] 本地积分计算
- [x] 多维表格写入原始输入
- [x] 多维表格写入家务记录
- [x] 持久化去重（基于 raw_inputs 表查询）
- [x] 成员映射（MEMBER_MAP_JSON）
- [x] 写表失败回复感知（"已识别" vs "已记录"）
- [x] 多维表格字段完整覆盖（15 chore_records 字段 + 13 raw_inputs 字段）
- [x] 飞书仪表盘看板配置指南（5 种看板）
- [x] 多维表格字段用途分类（看板/排查）
- [ ] 任务规则表读取 & 积分计算（从多维表格）— Phase 5
- [ ] Sealos Dockerfile + 部署配置 — Phase 6
- [ ] 单元测试（mock 层）— Phase 7

## 许可

MIT
