# 🧠 Personal Knowledge Management System

AI 驱动的个人知识管理系统，支持多渠道内容采集、知识图谱构建、智能问答和间隔重复复习。

## 功能

### 📥 多渠道采集
- 网页 URL 抓取
- RSS 订阅自动拉取
- 飞书文件/文档导入（txt、md、docx、pdf）
- Obsidian / Notion Markdown 导入
- 手动文本录入

### 🕸️ 知识图谱
- 自动抽取实体和关系
- D3.js 力导向图可视化
- 全图概览 + 实体搜索
- 12 种实体类型着色（人物、组织、技术、框架等）

### 💬 智能问答
- BM25 关键词检索 + jieba 中文分词
- DeepSeek LLM 生成回答
- 拼写纠错 + 查询扩展
- 语义缓存，重复问题秒回
- 元问题识别（"最近采集了什么"直接查库）

### 🧩 间隔复习
- SM-2 算法闪卡
- LLM 自动生成问答对
- 飞书卡片交互评分

### 🤖 飞书机器人
- 问答、实体查询、文档导入
- 闪卡创建和复习
- 过期知识预警、相似推荐
- 文件直接回复原文

### 📊 Web 管理后台
- DeepSeek 风格问答界面
- 知识库文档浏览/编辑/删除
- 数据洞察面板（统计、来源、保鲜、推荐）

## 使用场景

飞书打开即用，无需切换 App。以下是五个典型的日常场景：

### 📝 场景一：随手记笔记

> 读到一段有启发的文字，想立刻存下来。

在飞书聊天框直接发：

```
今天读了一篇关于 RAG 的文章：
检索增强生成（RAG）是一种将信息检索与大语言模型结合的架构，
通过先检索外部知识库再生成回答，有效减少幻觉问题……
```

机器人自动识别为笔记，提取标题（首行），存入知识库，秒回确认：

```
✅ 笔记已保存 📝 今天读了一篇关于 RAG 的文章
```

### 🔗 场景二：收藏网页

> 看到一篇好文章，想把整篇存入知识库。

在飞书发链接：

```
https://example.com/deep-learning-guide
```

或者用命令：

```
/collect https://example.com/deep-learning-guide
```

机器人抓取网页内容 → 存储 → 自动抽取实体和关系 → 回复：

```
✅ 已收藏!
• 实体: 15 个
• 关系: 8 条
• 索引块: 12 个
```

之后随时问"深度学习入门学什么"就能从这篇文档找答案。

### 📄 场景三：导入飞书云文档

> 团队在飞书上写了很多文档，想统一纳管。

```
/collect doc_token_xxxxx
```

或直接发飞书文档链接，机器人自动读取内容入库。支持单篇和整个文件夹批量导入（`?folder_token=`）。

### 📎 场景四：上传文件

> 手头有 PDF、Word、Markdown 文件，想全部装进知识库。

在飞书聊天直接发送文件（支持 txt、md、docx、pdf、代码文件），机器人：

1. 📥 下载文件并提取文字
2. 📄 回复**原文全文**（不做 LLM 转述）
3. 🧠 后台自动抽取实体、建索引

之后就能用自然语言搜索文件内容。

### 💬 场景五：随时随地查知识

> 想不起来某个概念，打开飞书问一句。

```
Docker 和虚拟机有什么区别？
```

机器人检索知识库 → DeepSeek 生成回答：

```
根据知识库，Docker 容器与虚拟机的主要区别在于：
容器共享宿主操作系统内核，启动速度快、资源占用小；
虚拟机则需要完整的操作系统，隔离性更强但开销更大……
```

回答后还会自动推荐相关知识点，串联学习路径。

---

### 🌐 场景六：知识库没有？网络搜索兜底

> 问了一个知识库里还没有的内容，不想空手而归。

在飞书发问：

```
Claude Opus 和 GPT-4 哪个更强？
```

知识库检索无结果 → 自动发起 DuckDuckGo 网络搜索：

```
🌐 知识库中暂无相关内容，以下来自网络搜索:

1. Claude Opus vs GPT-4 Comparison
   Claude Opus excels at long-form reasoning and code generation...
   🔗 https://example.com/claude-vs-gpt4

2. AI Model Benchmark 2026
   Latest benchmark results comparing top LLMs across...
   🔗 https://example.com/ai-benchmark

💡 要将这些内容存入知识库吗？发送 /collect 网址 即可收藏。
```

下次再问就有答案了——**知识库越用越聪明**。

---

**总结：飞书就是你的第二大脑。** 看到好的 → 随手发进去；需要查的 → 直接问就行。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env   # 编辑填入 DeepSeek API Key 等

# 3. 启动
python main.py

# 4. 打开浏览器
# 管理后台: http://localhost:8000/admin
# 知识图谱: http://localhost:8000/static/graph.html
# 数据洞察: http://localhost:8000/static/insights.html
# API 文档: http://localhost:8000/docs
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `DEEPSEEK_CHAT_MODEL` | 对话模型（默认 deepseek-chat） |
| `DEEPSEEK_EMBED_MODEL` | 嵌入模型（默认 deepseek-embed） |
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用密钥 |
| `FEISHU_VERIFICATION_TOKEN` | 飞书验证 Token |
| `SQLITE_PATH` | SQLite 路径（默认 data/metadata.db） |
| `GRAPH_DB_PATH` | 图谱路径（默认 data/graph.json） |
| `VECTOR_DB_PATH` | 向量库路径（默认 data/vectors） |
| `HOST` / `PORT` | 服务地址（默认 0.0.0.0:8000） |

## 项目架构

```
                        ┌─────────────────────────────────────┐
                        │           👤 用户入口层               │
                        │  ┌──────────┐  ┌──────────────────┐ │
                        │  │ 飞书客户端 │  │  Web 管理后台     │ │
                        │  │ (消息/文件)│  │ (admin/graph/    │ │
                        │  │          │  │  insights)       │ │
                        │  └────┬─────┘  └────────┬─────────┘ │
                        └───────┼──────────────────┼───────────┘
                                │                  │
                                ▼                  ▼
                        ┌─────────────────────────────────────┐
                        │          🌐 API 网关层 (FastAPI)      │
                        │  /api/qa  /api/collect  /api/graph  │
                        │  /api/admin  /api/personal  /api/feishu │
                        └───────┬──────────────┬───────────────┘
                                │              │
              ┌─────────────────┘              └─────────────────┐
              ▼                                                   ▼
┌──────────────────────────┐                    ┌──────────────────────────┐
│     🧠 业务逻辑层 (Agents) │                    │     🛠️ 工具层 (Utils)     │
│                          │                    │                          │
│  ┌──────────────────┐   │                    │  🤖 LLM Client            │
│  │ qa/ 问答          │   │                    │  (DeepSeek Chat API)      │
│  │ 检索→重排→生成    │   │                    │                          │
│  └──────────────────┘   │                    │  🔍 BM25 Retriever        │
│  ┌──────────────────┐   │                    │  (jieba 分词 + 索引)      │
│  │ knowledge/ 抽取  │   │                    │                          │
│  │ 实体→关系        │   │                    │  📐 Embedding Client      │
│  └──────────────────┘   │                    │  (DeepSeek Embed)         │
│  ┌──────────────────┐   │                    │                          │
│  │ collector/ 采集  │   │                    │  💾 Semantic Cache        │
│  │ URL→RSS→飞书→MD │   │                    │  (SHA256 + TTL)           │
│  └──────────────────┘   │                    │                          │
│  ┌──────────────────┐   │                    │  🌐 Web Search            │
│  │ personal/ 闪卡   │   │                    │  (DuckDuckGo 回退)        │
│  │ SM-2 + LLM生成   │   │                    │                          │
│  └──────────────────┘   │                    └──────────────────────────┘
│  ┌──────────────────┐   │
│  │ lifecycle/ 保鲜  │   │
│  │ recommend/ 推荐  │   │
│  └──────────────────┘   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│         💾 存储层 (Storage)          │
│                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────┐ │
│  │ SQLite   │ │ NetworkX │ │LanceDB│ │
│  │ 元数据   │ │ 知识图谱 │ │向量库 │ │
│  │ documents│ │ entities │ │embeddings│
│  │ entities │ │ relations│ │       │ │
│  │ reviews  │ │          │ │       │ │
│  └──────────┘ └──────────┘ └───────┘ │
└─────────────────────────────────────┘
```

**请求流程（以问答为例）：**

```
用户提问 "Docker 是什么？"
  → FastAPI /api/qa/ask
  → Semantic Cache (命中则直接返回)
  → BM25 检索 (jieba 分词 → 倒排索引 → Top-K 文档)
  → 分数低? → LLM 查询扩展 (纠错 + 多词搜索)
  → DeepSeek Chat 生成回答
  → 缓存结果 (7天)
  → 返回 {answer, sources[]}
```

**数据写入流程（以采集为例）：**

```
用户发 URL / 文本 / 文件
  → collector 下载/解析
  → SimHash 去重
  → 存入 SQLite (documents 表)
  → knowledge agent: LLM 抽取实体 + 关系
  → 写入 SQLite + NetworkX 图谱 + LanceDB 向量
  → BM25 分块索引
  → 回复用户确认
```

## 项目结构

```
project1/
├── main.py                  # FastAPI 入口
├── config.py                # 配置管理
├── api/                     # API 路由层
│   ├── admin.py             # 仪表盘聚合接口
│   ├── qa.py                # 问答接口
│   ├── collect.py           # 采集接口
│   ├── graph.py             # 图谱查询接口
│   ├── personal.py          # 闪卡/批注接口
│   ├── lifecycle.py         # 保鲜检测接口
│   ├── recommend.py         # 推荐接口
│   ├── feishu.py            # 飞书回调接口
│   └── review.py            # 复习/导出接口
├── agents/                  # 业务逻辑层
│   ├── qa/                  # 检索+LLM 问答
│   ├── knowledge/           # 实体/关系抽取
│   ├── collector/           # 内容采集（URL/RSS/飞书/Obsidian）
│   ├── personal/            # SM-2 闪卡管理
│   ├── lifecycle/           # 过期实体检测
│   └── recommend/           # 相似推荐+学习路径
├── storage/                 # 存储层
│   ├── __init__.py          # SQLite 元数据
│   └── graph_db.py          # NetworkX 图存储
├── utils/                   # 工具
│   ├── llm.py               # DeepSeek LLM 客户端
│   ├── retriever.py          # BM25 检索引擎
│   ├── cache.py             # 语义缓存
│   └── embedding.py         # 向量嵌入
├── feishu/                  # 飞书集成
│   ├── __init__.py          # 消息收发
│   ├── handlers.py          # 事件路由
│   └── cards.py             # 卡片模板
├── static/                  # 前端页面
│   ├── admin.html           # 管理后台（DeepSeek 风格）
│   ├── graph.html           # 知识图谱可视化
│   └── insights.html        # 数据洞察面板
├── data/                    # 数据文件
│   ├── metadata.db          # SQLite 数据库
│   ├── graph.json           # 知识图谱
│   └── vectors/             # 向量索引
└── requirements.txt
```

## 需求文档

### P0 — 已完成 ✅

| 模块 | 需求 | 状态 |
|------|------|:---:|
| 采集 | URL 网页抓取、文本录入、RSS 订阅 | ✅ |
| 采集 | 飞书文件导入（txt/md/docx/pdf） | ✅ |
| 采集 | 飞书云文档/文件夹导入 | ✅ |
| 采集 | Obsidian/Notion Markdown 批量导入 | ✅ |
| 采集 | SimHash 去重 | ✅ |
| 知识抽取 | LLM 自动提取实体（12 种类型）和关系 | ✅ |
| 知识图谱 | NetworkX 存储 + D3.js 力导向图可视化 | ✅ |
| 知识图谱 | 实体搜索 + 邻居展开 + 全图概览 | ✅ |
| 知识图谱 | URL 参数跳转（`?entity=xxx`） | ✅ |
| 检索 | BM25 + jieba 中文分词搜索 | ✅ |
| 检索 | 启动时从 SQLite 恢复索引 | ✅ |
| 检索 | 查询扩展（LLM 纠错 + 多词搜索） | ✅ |
| 问答 | DeepSeek LLM 基于知识库生成回答 | ✅ |
| 问答 | 语义缓存（SHA256 key，7 天 TTL） | ✅ |
| 问答 | 元问题直查数据库（"最近采集了什么"） | ✅ |
| 问答 | 来源引用 + 点击追问 | ✅ |
| 闪卡 | SM-2 间隔重复算法 | ✅ |
| 闪卡 | LLM 自动生成问答对（正面/背面/提示） | ✅ |
| 闪卡 | 飞书卡片交互评分（简单/困难/忘了） | ✅ |
| 飞书 | 消息路由（问答/实体查询/采集/命令） | ✅ |
| 飞书 | `/flashcard` `/review` `/stale` `/rec` 命令 | ✅ |
| 飞书 | 文件消息直接回复原文（不走 LLM） | ✅ |
| 飞书 | 问答后自动追发推荐（相似实体） | ✅ |
| Web | DeepSeek 风格管理后台（左文档 + 右问答） | ✅ |
| Web | 知识图谱可视化页面 | ✅ |
| Web | 数据洞察面板（统计/来源/保鲜/推荐） | ✅ |
| Web | 文档预览 + Markdown 渲染 + 编辑/删除 | ✅ |
| Web | 推荐问题快捷按钮 | ✅ |
| 管理 | 文档 CRUD（删除清关联、编辑重索引） | ✅ |
| 管理 | Graph 重建同步、语义缓存清除 | ✅ |
| 存储 | SQLite 元数据 + JSON 图存储 + LanceDB 向量 | ✅ |
| 部署 | FastAPI + uvicorn，单文件配置 | ✅ |

### P1 — 可选 💡

| 需求 | 说明 |
|------|------|
| 深色模式 | 一套 CSS 变量即可切换 |
| 实体编辑 | 手动修正 LLM 提取不准确的实体名/描述 |
| Web 端闪卡复习 | 网页上直接评分，不依赖飞书 |
| 图表增强 | 用 ECharts 替换纯 CSS 柱状图 |
| 全文搜索高亮 | BM25 搜索结果中高亮匹配词 |
| 多知识库 | 支持切换不同 SQLite 文件（工作/学习） |
| 备份恢复 | 一键导出/导入 data/ 目录 |
| Docker 部署 | Dockerfile + docker-compose |
| 测试 | pytest 单元测试 + 集成测试 |
| 向量检索 | 语义搜索补充 BM25，混合检索重排序 |

## API 接口

### 管理员

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/dashboard` | 聚合仪表盘数据（统计/复习/文档/保鲜/推荐） |
| `GET` | `/api/admin/document/{doc_id}` | 获取文档详情（含分块和关联实体） |
| `PUT` | `/api/admin/document/{doc_id}` | 更新文档标题/内容，自动重分块重索引 |
| `DELETE` | `/api/admin/document/{doc_id}` | 删除文档及关联的 BM25 索引、实体、复习记录 |
| `POST` | `/api/admin/clear-cache` | 清除语义缓存 |
| `POST` | `/api/admin/rebuild-graph` | 从 SQLite 重建知识图谱 |

### 采集

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/collect/url` | `{url}` 抓取网页内容并入库 |
| `POST` | `/api/collect/text` | `{title, text}` 手动录入文本 |
| `POST` | `/api/collect/rss` | `{rss_feed_url}` 拉取 RSS 订阅 |
| `POST` | `/api/collect/feishu-doc` | `?doc_token=或?folder_token=` 导入飞书云文档 |
| `POST` | `/api/collect/note` | `?title=&content=` 快速笔记（自动取首行为标题） |
| `POST` | `/api/collect/feishu-file` | `?message_id=&file_key=&file_name=` 下载飞书文件 |
| `POST` | `/api/collect/markdown-file` | `?filepath=` 导入单个 Markdown 文件 |
| `POST` | `/api/collect/markdown-folder` | `?folder_path=&recursive=` 批量导入文件夹 |

### 问答

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/qa/ask` | `{question, top_k}` BM25 检索 + LLM 生成回答 |
| `POST` | `/api/qa/feedback` | `{query_id, rating, comment}` 记录用户反馈 |

### 图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/graph/query` | `{entity_name, max_depth}` 查询实体及邻居 |
| `GET` | `/api/graph/search` | `?q=&limit=` 按名称搜索实体 |
| `GET` | `/api/graph/full` | `?limit=` 返回全图节点和边 |

### 闪卡 / 个人记忆

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/personal/flashcard/create` | `?entity_name=` 为实体创建 SM-2 闪卡 |
| `POST` | `/api/personal/flashcard/batch` | `{entity_names}` 批量创建闪卡 |
| `POST` | `/api/personal/flashcard/from-doc` | `?doc_id=` 为文档下所有实体创建闪卡 |
| `POST` | `/api/personal/flashcard/review` | `?entity_name=&quality=0-5` SM-2 复习评分 |
| `GET` | `/api/personal/flashcard/stats` | 闪卡统计（总数/到期/已复习） |
| `GET` | `/api/personal/flashcard/due` | 到期闪卡列表 |
| `POST` | `/api/personal/annotate` | `{entity_name, content}` 给实体加批注 |
| `GET` | `/api/personal/annotations` | `?entity_name=` 查询批注 |
| `POST` | `/api/personal/review-quick` | `?entity_name=&grade=easy\|hard\|skip` 快捷评分 |

### 推荐

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/recommend/similar` | `?entity=&top_k=` 基于嵌入相似度推荐 |
| `GET` | `/api/recommend/learning-path` | `?entity=&max_depth=` 图谱遍历学习路径 |
| `GET` | `/api/recommend/latest` | `?limit=` 最近采集的文档列表 |

### 生命周期

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/lifecycle/stale` | `?days=90` 长期未访问的过期实体 |
| `GET` | `/api/lifecycle/cluster-updates` | `?entity=&days=30` 实体簇的新增内容 |

### 复习 & 导出

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/review/due` | 到期复习列表 |
| `POST` | `/api/recap` | `{period: "7d"/"30d"/"90d"}` 知识周报 |
| `GET` | `/api/export` | 导出全部数据 |
| `GET` | `/api/health` | 健康检查 + 统计 |

### 飞书

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/feishu/event` | 飞书事件回调（消息/卡片动作） |
| `GET` | `/api/feishu/health` | 飞书集成状态检查 |

### 调度器

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/scheduler/rss/register` | `?feed_url=` 注册 RSS 定时拉取 |
| `POST` | `/api/scheduler/rss/poll` | 立即拉取全部 RSS |
| `POST` | `/api/scheduler/review/push` | 立即推送每日复习 |

## 技术栈

- **后端**: FastAPI + SQLite + NetworkX
- **检索**: BM25 (rank-bm25) + jieba 分词
- **向量**: LanceDB + DeepSeek Embedding
- **问答**: DeepSeek Chat API
- **前端**: 原生 HTML/CSS/JS + D3.js
- **集成**: 飞书开放平台 (lark-oapi)
