# housework-feishu-bot 🐝

飞书家务积分机器人 — 用 LLM 解析家务消息，记录积分，按双周周期结算并通过飞书消息卡片推送家庭积分榜。

## 项目目标

- 用户在飞书群里发送 `我洗了碗`，机器人自动识别家务类型并计算积分。
- 每次家务记录自动归入当前双周周期（period_id）。
- 固定双周周期到期后，自动汇总积分，通过飞书消息卡片推送家庭积分榜。
- 每次结算后自动开启下一轮积分周期，同时保留完整历史记录。
- 所有数据写入飞书多维表格，无需自建数据库。
- 部署在 Sealos，零运维。

## 架构概览

```
用户 ──飞书消息──▶ 事件接收（HTTP 回调 / WS 长连接）
                    │
                    ▼
               app/event_handler.py
                    │
                    ├─▶ 消息去重
                    │
                    ├─▶ LLM 家务解析
                    ├─▶ 积分计算 → 写入 raw_inputs + chore_records（含 period_id）
                    └─▶ 群内回复

结算调度器（每分钟扫描）
         │
         ▼
    检查已完成周期
         │
         ▼
    查询 settlement_records 是否已结算
         │
         ▼
    汇总本期积分 → 构建飞书消息卡片 → 推送
         │
         ▼
    更新 settlement_records
```

### 目录结构

| 路径 | 说明 |
|---|---|---|
| `app/main.py` | FastAPI 应用入口，/health + HTTP 回调 |
| `app/config.py` | 环境变量配置 |
| `app/event_handler.py` | 共享事件处理逻辑（两个入口共用） |
| `app/feishu_client.py` | 飞书 API 客户端（token、发消息、交互卡片） |
| `app/chore_service.py` | 家务积分业务逻辑 |
| `app/settlement_period.py` | 双周周期计算（基于固定锚点） |
| `app/settlement_service.py` | 结算服务（汇总积分、构建卡片、执行结算） |
| `app/settlement_scheduler.py` | 后台结算调度器（每分钟扫描应结算周期） |
| `app/schemas.py` | Pydantic 数据模型 |
| `app/bitable_client.py` | 多维表格客户端 |
| `app/llm_parser.py` | LLM 结构化家务解析 |
| `app/time_utils.py` | 统一时间工具 |
| `scripts/start_feishu_ws.py` | 飞书长连接（WebSocket）启动脚本 |
| `scripts/run.py` | 统一启动脚本（ws / http 模式） |
| `Dockerfile` | 容器镜像构建 |
| `.dockerignore` | Docker 构建忽略规则 |
| `docker-compose.yml` | 本地容器运行配置 |

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
- [x] 飞书交互卡片（interactive card）发送
- [x] 接收 `im.message.receive_v1` 事件
- [x] 过滤非文本消息
- [x] `家务：` / `家务:` 前缀判断
- [x] 机器人自动回复 `收到家务记录：{内容}`
- [x] 消息 ID 去重（内存 set，防止重复回复）+ 持久化去重
- [x] 共享事件处理逻辑（HTTP 与长连接统一调用）
- [x] LLM 结构化解析（家务 → 任务类型 + 数量）
- [x] 本地积分计算（13 类家务，统一 1 分）
- [x] 多维表格写入原始输入（raw_inputs）
- [x] 多维表格写入家务记录（chore_records，含 period_id）
- [x] 双周周期自动计算（固定锚点 + 周期 ID）
- [x] 双周结算调度器（每分钟扫描应结算周期，自动汇总推送）
- [x] 飞书消息卡片结算推送（积分排名 + 汇总）
- [x] 零积分成员展示
- [x] 空周期正常发送结算卡片
- [x] 结算重复扫描防护（基于 settlement_records 表）
- [x] 结算失败重试支持

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
# 或使用统一启动脚本
python scripts/run.py
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

当前支持 13 类家务记录，统一为 1 分/项：

- 做饭
- 洗碗
- 扫地
- 拖地
- 倒垃圾
- 洗衣服
- 晾衣服
- 收衣服
- 整理收纳
- 叠衣铺床
- 换洗床品
- 清洁打扫
- 虎妞照护

整理收纳包括：整理房间、整理柜子、整理桌面杂物、物品归位、收纳杂物等。

叠衣铺床包括：叠衣服、整理床铺、铺床、叠被子等。

换洗床品包括：换床单、换被套、换枕套、换四件套等。

清洁打扫包括：
- 擦桌子、擦餐桌、擦茶几、擦台面、擦灶台
- 清理厨房、打扫厨房、厨房台面清洁
- 清理卫生间、刷厕所、刷马桶、清理洗手台、清理地漏、清理浴室

注意：
- 扫地、拖地仍然是单独任务
- 洗碗仍然是单独任务
- 整理桌面杂物属于整理收纳
- 没有对象的「打扫了一下」「收拾了一下」仍然不自动计分

虎妞照护包括：铲屎、铲猫砂、清理猫砂盆、给虎妞换水、饮水机换水、添猫粮等。

暂不支持：

- 买菜
- 遛狗
- 收快递
- 维修
- 按摩
- 游戏
- 记账

> 系统**不是关键词匹配**，而是通过 LLM 语义理解用户实际做了什么。
> 但 LLM 只能映射到当前支持的 13 类任务，不支持的任务和模糊表达暂不计分。
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
| period_id | 文本 | | 所属双周周期（如 20260727_20260809） |

#### settlement_records 表

| 字段名 | 字段类型 | 必填 | 说明 |
|---|---|---|---|
| period_id | 文本 | ✓ | 周期唯一标识（如 20260727_20260809） |
| period_start | 日期时间 | ✓ | 周期开始时间 |
| period_end | 日期时间 | ✓ | 周期结束时间 |
| status | 文本 | ✓ | processing / sent / failed |
| total_points | 数字 | ✓ | 全体总积分 |
| member_summary | 文本 | ✓ | 各成员积分 JSON（如 {"shuyao":18,"zihao":15}） |
| record_count | 数字 | ✓ | 家务记录数量 |
| created_at | 日期时间 | ✓ | 创建时间 |
| sent_at | 日期时间 | | 实际发送时间 |
| feishu_message_id | 文本 | | 飞书消息 ID |
| error_message | 文本 | | 失败原因 |

### 获取 table_id

创建数据表后，从浏览器地址栏获取 `table_id`：

```
https://bytedance.feishu.cn/base/<app_token>?table=<table_id>
```

`table_id` 是以 `tbl` 开头的字符串。

### 环境变量配置

```env
FEISHU_BITABLE_APP_TOKEN=      # 多维表格 Base Token
FEISHU_TABLE_RAW_INPUTS=       # raw_inputs 表的 table_id
FEISHU_TABLE_CHORE_RECORDS=    # chore_records 表的 table_id
FEISHU_TABLE_SETTLEMENT_RECORDS= # settlement_records 表的 table_id
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

## 双周积分结算

从 v0.2 开始，小哈皮采用**固定锚点双周结算**机制。

### 结算流程

```
家务记录写入 chore_records（含 period_id）
        ↓
结算调度器每分钟扫描
        ↓
根据锚点日期计算已结束的最新周期
        ↓
查询 settlement_records 是否已结算
        ↓
若已发送 → 跳过
        ↓
若未发送 → 汇总该 period_id 下所有记录
        ↓
按 member_name 汇总 points
        ↓
生成飞书消息卡片（含排名、汇总、零积分成员）
        ↓
发送到指定群聊
        ↓
更新 settlement_records 为 sent
```

### 双周周期

基于固定锚点计算，不依赖服务运行时长：

| 周期 | 统计范围 | 推送时间 |
|---|---|---|
| 第一期 | 7月27日 00:00～8月9日 24:00 | 8月10日 09:00 |
| 第二期 | 8月10日 00:00～8月23日 24:00 | 8月24日 09:00 |

锚点日期通过 `SETTLEMENT_ANCHOR_DATE_STR` 配置。

### 结算卡片

到点后小哈皮自动在群里推送飞书消息卡片：

```
🏆 小哈皮双周家务结算

结算周期
2026年7月27日—8月9日

🥇 shuyao　18 分

🥈 zihao　15 分

本期共完成 33 项家务，累计 33 分
新一期积分已开始累计
下次结算：2026年8月24日
```

### 边界行为

- 零积分成员仍然显示（防止误以为系统遗漏）
- 无记录的周期正常发送空结算卡片
- 容器重启后不会漏结算（固定锚点决定周期）
- 调度器每分钟扫描，错过时间后自动补发
- 发送失败重试（最大 `SETTLEMENT_MAX_RETRIES` 次）
- 基于 settlement_records 表防止重复发送

### 边界行为（家务）

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

## 为什么不能长期跑在本地 Mac

WebSocket 长连接依赖本地进程和网络持续在线：

- **Mac 息屏/睡眠**会导致网络挂起或进程暂停
- 即使关闭息屏，Mac 的电源管理（如 Power Nap）仍可能中断网络
- 一旦连接断开，飞书后台会标记为 `app not online`，消息收不到

**结论**：本地运行只适合开发调试和短期验证。长期使用应部署到 Sealos 这类云端常驻环境。

## Sealos 应用管理部署

本项目使用 [Sealos 应用管理](https://sealos.run/docs/guides/app-management) 部署为长期运行的容器服务。飞书使用长连接接收事件，不需要公网域名或 HTTP 回调地址。

### 前提

- 已注册 [Sealos](https://cloud.sealos.io) 并创建工作空间
- 本机已安装 Docker（用于本地构建和验证）

### 1. 准备可用镜像

先本地构建镜像并验证它能正常启动。

#### 本地构建

```bash
docker build -t housework-feishu-bot:latest .
```

#### 本地镜像验证

用 docker-compose 启动并确认飞书长连接建立：

```bash
docker compose up --build
```

观察日志，确认出现：
```
starting feishu websocket channel
connected to wss://msg-frontier.feishu.cn
```

然后在飞书群聊中发送 `@小哈皮 我洗了碗`，确认机器人正常回复。

#### 推送镜像到镜像仓库

本地验证通过后，将镜像推送到你的镜像仓库（Docker Hub / 阿里云 ACR 等）：

```bash
docker tag housework-feishu-bot:latest <your-registry>/housework-feishu-bot:latest
docker push <your-registry>/housework-feishu-bot:latest
```

> Sealos 内置 Docker Hub 代理，如果使用 Docker Hub 可直接填写 `your-dockerhub-id/housework-feishu-bot:latest`。

### 2. 填入镜像信息

在 Sealos 控制台操作：

1. 打开「应用管理」，点击「创建新应用」
2. 选择「通过 Docker 镜像部署」
3. 填写应用名称：`housework-feishu-bot`
4. 填写镜像地址：`<your-registry>/housework-feishu-bot:latest`（或 Docker Hub 地址）
5. 如果是私有镜像，补充仓库认证信息

### 3. 配置资源

- **部署模式**：固定实例（适合长期在线服务）
- **实例数**：1
- **资源规格**：最小规格即可（本机器人资源消耗极低）

### 4. 配置端口

- **端口**：`8000`
- **暴露方式**：仅保留端口，不开启公网访问
- **用途**：`/health` 健康检查端口，当前 ws 模式下不占用，保留以备未来 HTTP callback 使用

> 本项目不需要公网域名。飞书使用长连接接收事件，不回调公网地址。
> 未来如果改用 HTTP callback，才需要 Sealos 公网域名 + `/feishu/events`。

### 5. 配置启动命令、环境变量和存储

#### 启动命令

镜像的 `Dockerfile` 已定义默认启动命令为 `python scripts/run.py`，一般情况下不需要额外覆盖。

Sealos 应用管理的「启动命令」可留空，使用镜像默认 CMD 即可。

#### 环境变量

在 Sealos 应用管理中配置以下环境变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `BOT_RUN_MODE` | 是 | 固定为 `ws`（飞书 WebSocket 长连接模式） |
| `TIMEZONE` | 否 | 时区，固定为 `Asia/Shanghai` |
| `FEISHU_APP_ID` | 是 | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 是 | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 否 | 飞书事件验证令牌 |
| `FEISHU_ENCRYPT_KEY` | 否 | 飞书事件加密 Key |
| `FEISHU_BITABLE_APP_TOKEN` | 是 | 多维表格 Base Token |
| `FEISHU_TABLE_RAW_INPUTS` | 是 | raw_inputs 表 table_id |
| `FEISHU_TABLE_CHORE_RECORDS` | 是 | chore_records 表 table_id |
| `FEISHU_TABLE_SETTLEMENT_RECORDS` | 是 | settlement_records 表 table_id |
| `SETTLEMENT_ENABLED` | 否 | 是否启用结算，默认 false |
| `SETTLEMENT_ANCHOR_DATE_STR` | 是 | 锚点日期，如 2026-07-27 |
| `SETTLEMENT_TIME` | 否 | 结算时间，默认 09:00 |
| `SETTLEMENT_INTERVAL_DAYS` | 否 | 周期天数，默认 14 |
| `SETTLEMENT_CHAT_ID` | 是 | 结算推送目标群聊 chat_id |
| `LLM_API_KEY` | 是 | LLM API Key |
| `LLM_BASE_URL` | 是 | LLM API 地址（如 `https://api.openai.com/v1`） |
| `LLM_MODEL` | 是 | 模型名称（如 `gpt-4o-mini`） |
| `MEMBER_MAP_JSON` | 否 | 成员映射 JSON（如 `{"ou_xxx":"Alice"}`） |

#### 存储

本项目不写入本地文件系统，所有数据写入飞书多维表格，**不需要配置存储卷**。

### 6. 发布应用并验证结果

完成配置后，点击「发布」创建应用。建议检查以下内容：

1. **应用概览**：显示实例已正常运行（Running）
2. **容器日志**：出现以下关键日志行：
   ```
   BOT_RUN_MODE=ws, starting feishu websocket channel
   starting feishu websocket channel
   connected to wss://msg-frontier.feishu.cn
   ```
3. **事件**：无镜像拉取失败、启动失败或探针异常

### 7. 飞书开放平台配置

飞书后台一直保持「使用长连接接收事件」，不需要切换到 HTTP 回调：

1. 事件订阅方式选择「使用长连接接收事件」
2. 添加事件 `im.message.receive_v1`
3. 确认应用机器人已加入群聊
4. 确认多维表格已授权机器人应用编辑权限（`bitable:app`）
5. 发布应用新版本后事件才会生效

> ⚠️ 如果飞书后台提示 `app not online`，说明 Sealos 容器尚未启动或长连接未建立。

### 8. 部署后自检

按以下顺序验证部署是否完整：

1. **容器日志**：确认出现 `connected to wss://msg-frontier.feishu.cn`
2. **群聊测试**：发送 `@小哈皮 我洗了碗`
3. **机器人回复**：`已记录 1 项家务，共 1 分：`
4. **raw_inputs 表**：新增一行记录，`status=parsed`
5. **chore_records 表**：新增一行记录，`date/week/month` 不是 1970
6. **看板检查**：仪表盘数据自动更新
7. **提醒验证**：发送 `@小哈皮 明天晚上 8 点提醒我扔垃圾`，确认回复"已记录提醒"
8. **到点验证**：到达提醒时间后，检查群内是否自动收到推送消息

### 运行模式说明

项目支持两种运行模式，通过 `BOT_RUN_MODE` 控制：

| 模式 | 用途 | 说明 |
|---|---|---|
| `ws` | 生产运行（默认） | 飞书 WebSocket 长连接，无需公网地址 |
| `http` | 健康检查 / HTTP 回调 | FastAPI 服务，监听 `0.0.0.0:8000` |

### 容器稳定性机制

- **SDK 自动重连**：lark-oapi 的 FeishuChannel 内建自动重连机制，连接断开后自动恢复
- **进程退出策略**：如果脚本遇到致命异常，进程退出，容器平台根据 restart policy 重新拉起
- **Sealos 重启策略**：容器意外退出后自动重启
- 不需要在脚本内部写死循环重试，充分利用平台能力

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
- [x] 飞书机器人群内回复 + 交互卡片
- [x] 消息去重（内存 + 持久化）
- [x] LLM 结构化解析（家务 → 任务类型 + 数量）
- [x] 本地积分计算（13 类任务，统一 1 分）
- [x] 多维表格写入原始输入 + 家务记录 + 结算记录
- [x] 成员映射（MEMBER_MAP_JSON）
- [x] 写表失败回复感知（"已识别" vs "已记录"）
- [x] 飞书仪表盘看板配置指南（5 种看板）
- [x] Sealos 容器化部署（Dockerfile / docker-compose / 统一启动脚本）
- [x] 双周积分结算（固定锚点 + 周期 ID + 调度器 + 飞书消息卡片推送）— v0.2.0

## 构建与推送（Apple Silicon Mac → Sealos）

在 Mac M 芯片上构建并推送到 Docker Hub 供 Sealos（amd64 节点）使用时，必须指定 `linux/amd64` 平台：

```bash
# 构建并推送（单架构 amd64）
docker buildx build --platform linux/amd64 -t byte1717712/housework-feishu-bot:latest --push .

# 或构建多架构清单（同时支持 amd64 + arm64，推荐）
docker buildx build --platform linux/amd64,linux/arm64 -t byte1717712/housework-feishu-bot:latest --push .
```

**注意**：
- 直接 `docker build` 在 Mac Silicon 上构建的是 `arm64` 镜像，推送到 Docker Hub 后 Sealos（amd64）上会报 `exec format error`。
- 首次使用 `docker buildx create --name multiarch --driver docker-container --bootstrap --use` 创建 multiarch builder，之后可复用。
- 后续只需执行 `docker buildx build --push` 即可，builder 实例已存在。
- 如果 `.env` 等配置文件有改动，加 `--no-cache` 避免 Docker 使用旧层缓存。
- 推送后必须在 Sealos 上重启应用以拉取新镜像。

## 许可

MIT
