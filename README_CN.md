# Zotero-MinerU-Dify Pipeline

[English](README.md)

一个自动化流水线，从 **Zotero** 提取 PDF 附件，通过 **MinerU** 解析为 Markdown，并上传到 **Dify** 知识库，用于 RAG 应用。

## 架构

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│              │       │              │       │              │
│    Zotero    │──────>│    MinerU    │──────>│     Dify     │
│  (本地数据库) │  MCP  │  (解析 API)   │  HTTP │  (RAG 知识库) │
│              │       │              │       │              │
└──────────────┘       └──────────────┘       └──────────────┘
  PDF / DOCX / ...       -> Markdown              知识库
```

## 功能特性

- **全链路自动化** - 一条命令完成从 Zotero 文献库到 Dify 知识库的全流程
- **幂等执行** - 基于 JSON 状态文件的进度追踪，可安全重复运行
- **批量处理** - 每个 MinerU 批次最多处理 200 个文件
- **分类筛选** - 支持指定 Zotero 分类（Collection），递归包含子分类
- **自动重试** - 网络错误时指数退避重试
- **多格式支持** - PDF、DOC、DOCX、PPT、PPTX、PNG、JPG、JPEG

## 前置条件

| 依赖 | 版本 | 备注 |
|------|------|------|
| Python | 3.8+ | |
| Zotero | 7.0+ | 需安装 [zotero-mcp](https://github.com/nicholasgasior/zotero-mcp) 插件并运行 |
| MinerU API Token | - | 在 [mineru.net](https://mineru.net) 注册获取 |
| Dify API Key | - | 从 Dify 实例获取 Dataset API Key |

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/<your-username>/zotero-mineru-dify.git
cd zotero-mineru-dify

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥和偏好设置

# 运行流水线
python pipeline.py
```

## 使用方法

```bash
# 交互模式 - 从菜单选择分类
python pipeline.py --interactive

# 处理整个 Zotero 文献库
python pipeline.py --all-items

# 处理指定分类
python pipeline.py --collections KEY1,KEY2

# 不递归包含子分类
python pipeline.py --collections KEY1 --no-recursive

# 自定义分页大小
python pipeline.py --all-items --page-size 100
```

## 配置说明

所有配置通过 `.env` 文件管理。完整模板见 `.env.example`。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ZOTERO_MCP_URL` | Zotero MCP 服务地址 | `http://127.0.0.1:23120/mcp` |
| `MINERU_API_TOKEN` | MinerU API 认证令牌 | - |
| `DIFY_API_KEY` | Dify Dataset API 密钥 | - |
| `DIFY_BASE_URL` | Dify API 基础 URL | `https://api.dify.ai/v1` |
| `DIFY_DATASET_NAME` | 目标知识库名称 | `Zotero Literature` |
| `DIFY_PROCESS_MODE` | 分段策略（`custom` / `automatic`） | `custom` |
| `DIFY_SEGMENT_MAX_TOKENS` | 每个分段最大 Token 数 | `800` |
| `ZOTERO_COLLECTION_KEYS` | 逗号分隔的分类 Key（可选） | - |
| `ZOTERO_COLLECTION_RECURSIVE` | 是否递归包含子分类 | `true` |

## 项目结构

```
zotero-mineru-dify/
├── pipeline.py          # 主入口，编排整个工作流
├── config.py            # 集中化的环境变量配置
├── zotero_client.py     # Zotero MCP 客户端（分类、附件）
├── mineru_client.py     # MinerU API 客户端（上传、解析、下载）
├── dify_client.py       # Dify API 客户端（知识库、文档、索引）
├── progress.py          # 基于 JSON 的进度追踪
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
└── progress.json        # 运行时状态（自动生成）
```

## 工作原理

1. **收集** - 通过 MCP 查询 Zotero，获取附件文件路径，可按分类筛选
2. **解析** - 将文件批量上传到 MinerU API，轮询等待完成，下载生成的 Markdown
3. **上传** - 在目标 Dify 知识库中创建文档，支持自定义分段规则
4. **追踪** - 在 `progress.json` 中记录已处理/失败的条目，后续运行自动跳过已完成项

## 许可证

MIT
