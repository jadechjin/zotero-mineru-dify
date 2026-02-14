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

## 使用教程

首先确保电脑中已经下载安装有：Python 3.8+、zotero（需要安装 [zotero-mcp](https://github.com/nicholasgasior/zotero-mcp)）

### 准备工作——Dify

在 Dify 中注册申请一个账号（建议订阅 pro，否则免费版只能上传 50 篇文献且限制库容量为 50MB），在设置中填写好自己的模型，推荐模型配置：
![image-20260214165530836](images/165500.png)

随后创建 Dify 知识库，创建一个带有父子模式的知识库模板的流水线，可按需要选择删除不必要的节点。最简示例：

![image-20260214170301138](images/170258.png)

找到用户输入字段点击预览，必填的处理文档参数如下：

![image-20260214170525878](images/170446.png)

然后填写知识库节点的参数，使用高质量索引，嵌入模型推荐选择 Qwen3-Embedding-8B。检索选择混合检索，重排模型推荐使用 Qwen3-Reranker-8B，Top K 和 score 可按需自行配置，配置完成后点击发布流水线，选择导出流水线 pipeline 文件到本地项目目录下。

最后点击服务 API--选择 API 密钥--创建一个新的密钥--复制密钥备用

### 准备工作——MinerU

注册登录使用 [MinerU](https://mineru.net/) 服务--选择 API--点击 API 管理--创建一个新的 token--复制 token 备用

### 开始项目

打开终端，一行行执行以下命令：

```bash
# 克隆仓库
git clone https://github.com/jadechjin/zotero-mineru-dify.git
cd zotero-mineru-dify

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 此时找到本地的.env 文件打开，编辑 .env 文件，填入你刚刚申请的 MinerU 和 Dify 的 API 密钥和偏好设置，Dify 的知识库配置如果在准备阶段下载了 pipeline 文件就不用填写，程序会自动识别然后应用配置

# 运行流水线
python pipeline.py
```

# 使用方法

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
