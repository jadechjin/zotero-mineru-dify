"""Zotero -> MinerU -> Dify 自动化流水线。"""

import argparse
import logging
import sys

from config import (
    DIFY_API_KEY,
    MINERU_API_TOKEN,
    ZOTERO_COLLECTION_KEYS,
    ZOTERO_COLLECTION_PAGE_SIZE,
    ZOTERO_COLLECTION_RECURSIVE,
)
from dify_client import RAG_PIPELINE_MODE, get_dataset_info, get_or_create_dataset, upload_all
from mineru_client import process_files
from progress import load_progress, save_progress
from zotero_client import check_connection, collect_files, list_collections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Zotero -> MinerU -> Dify 流水线")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--collections",
        type=str,
        default=None,
        help="要处理的分组 key（逗号分隔），例如 3PEKRG3J,XEVC7LKY",
    )
    group.add_argument(
        "--all-items",
        action="store_true",
        help="强制扫描整个文库（忽略分组配置）",
    )
    group.add_argument(
        "--interactive",
        action="store_true",
        help="强制使用交互式分组选择菜单",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="禁用子分组递归（默认开启递归）",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="分组条目查询分页大小",
    )
    return parser


def _parse_collection_keys(raw):
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def select_collections_interactively(recursive=True):
    logger.info("正在从 Zotero 获取分组列表...")
    try:
        collections = list_collections(mode="complete")
    except Exception as exc:
        logger.warning("获取分组失败：%s。将回退为处理整个文库。", exc)
        return {"collection_keys": None, "recursive": recursive, "source": "default-all"}

    if not collections:
        logger.warning("Zotero 文库中未找到分组，将回退为处理整个文库。")
        return {"collection_keys": None, "recursive": recursive, "source": "default-all"}

    print("\n===== Zotero Collections =====")
    print("  0) [ALL] 处理整个文库")
    for i, coll in enumerate(collections, start=1):
        name = coll.get("name", "未命名")
        key = coll.get("key", "")
        depth = coll.get("depth", 0)
        indent = "  " * depth
        print(f"  {i}) {indent}{name}  [{key}]")
    print()

    while True:
        try:
            raw = input("请选择分组编号（逗号分隔，输入 0 表示全部）：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            logger.info("已取消选择，将回退为处理整个文库。")
            return {"collection_keys": None, "recursive": recursive, "source": "default-all"}

        if not raw:
            continue

        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            continue

        if "0" in parts:
            logger.info("已选择：整个文库")
            return {"collection_keys": None, "recursive": recursive, "source": "interactive"}

        try:
            indices = [int(p) for p in parts]
        except ValueError:
            print("输入无效，请输入逗号分隔的数字。")
            continue

        if any(idx < 1 or idx > len(collections) for idx in indices):
            print(f"选择无效，请输入 0 到 {len(collections)} 之间的数字。")
            continue

        selected = []
        for idx in dict.fromkeys(indices):
            coll = collections[idx - 1]
            selected.append(coll["key"])
            print(f"  -> {coll['name']}  [{coll['key']}]")

        logger.info("已选择 %d 个分组，recursive=%s", len(selected), recursive)
        return {"collection_keys": selected, "recursive": recursive, "source": "interactive"}


def resolve_collection_selection(args):
    recursive = ZOTERO_COLLECTION_RECURSIVE and not args.no_recursive
    page_size = args.page_size or ZOTERO_COLLECTION_PAGE_SIZE
    if page_size < 1:
        logger.warning("page_size=%d 无效，回退为 50", page_size)
        page_size = 50

    if args.all_items:
        logger.info("模式：整个文库（--all-items）")
        return {"collection_keys": None, "recursive": recursive, "page_size": page_size, "source": "cli-all"}

    if args.collections:
        keys = _parse_collection_keys(args.collections)
        if keys:
            logger.info("模式：命令行分组 %s（recursive=%s）", keys, recursive)
            return {"collection_keys": keys, "recursive": recursive, "page_size": page_size, "source": "cli"}

    if args.interactive:
        if not sys.stdin.isatty():
            logger.warning("请求了 --interactive，但当前不是 TTY，回退为整个文库。")
            return {"collection_keys": None, "recursive": recursive, "page_size": page_size, "source": "default-all"}
        sel = select_collections_interactively(recursive=recursive)
        sel["page_size"] = page_size
        return sel

    env_keys = _parse_collection_keys(ZOTERO_COLLECTION_KEYS)
    if env_keys:
        logger.info("模式：环境变量分组 %s（recursive=%s）", env_keys, recursive)
        return {"collection_keys": env_keys, "recursive": recursive, "page_size": page_size, "source": "env"}

    if sys.stdin.isatty():
        sel = select_collections_interactively(recursive=recursive)
        sel["page_size"] = page_size
        return sel

    logger.warning("当前为非交互环境且未指定分组，将处理整个文库。")
    return {"collection_keys": None, "recursive": recursive, "page_size": page_size, "source": "default-all"}


def _clean_conflict_processed_records(progress, dataset_id):
    """清理同一 dataset 下 failed(dify) 与 processed 冲突记录。"""
    conflict_keys = []
    for key, failed_entry in progress["failed"].items():
        if key not in progress["processed"]:
            continue

        processed_entry = progress["processed"][key]
        processed_dataset = processed_entry.get("dify_dataset") if isinstance(processed_entry, dict) else None
        if processed_dataset and processed_dataset != dataset_id:
            continue

        if isinstance(failed_entry, dict):
            failed_stage = failed_entry.get("stage")
            failed_dataset = failed_entry.get("dify_dataset")
            if failed_dataset and failed_dataset != dataset_id:
                continue
            if failed_stage and failed_stage != "dify":
                continue
            conflict_keys.append(key)
            continue

        if isinstance(failed_entry, str) and "dify" in failed_entry.lower():
            conflict_keys.append(key)

    if not conflict_keys:
        return 0

    for key in conflict_keys:
        progress["processed"].pop(key, None)

    return len(conflict_keys)


def main():
    args = build_arg_parser().parse_args()

    if not DIFY_API_KEY:
        logger.error("未设置 DIFY_API_KEY，请检查 .env。")
        sys.exit(1)

    if not MINERU_API_TOKEN:
        logger.error("未设置 MINERU_API_TOKEN，无法进行 MinerU 解析。")
        sys.exit(1)

    logger.info("正在检查 Zotero MCP 连接...")
    if not check_connection():
        logger.error("无法连接 Zotero MCP 服务。请确认 Zotero 已启动且 MCP 插件已启用。")
        sys.exit(1)
    logger.info("Zotero MCP 连接正常。")

    selection = resolve_collection_selection(args)
    collection_keys = selection["collection_keys"]
    recursive = selection["recursive"]
    page_size = selection["page_size"]

    if collection_keys:
        logger.info(
            "处理分组：%s（recursive=%s, source=%s）",
            collection_keys,
            recursive,
            selection["source"],
        )
    else:
        logger.info("处理整个文库（source=%s）", selection["source"])

    logger.info("正在准备 Dify 知识库...")
    dataset_id = get_or_create_dataset()
    dataset_info = get_dataset_info(dataset_id)
    dataset_name = dataset_info.get("name") or "unknown"
    dataset_runtime_mode = dataset_info.get("runtime_mode") or "unknown"
    dataset_doc_form = dataset_info.get("doc_form") or "unknown"
    logger.info(
        "知识库信息: name=%s, id=%s, runtime_mode=%s, doc_form=%s",
        dataset_name,
        dataset_id,
        dataset_runtime_mode,
        dataset_doc_form,
    )
    if dataset_runtime_mode == RAG_PIPELINE_MODE:
        logger.info("检测到 rag_pipeline 知识库，开始解析上传任务。")

    progress = load_progress()
    conflict_count = _clean_conflict_processed_records(progress, dataset_id)
    if conflict_count:
        logger.warning(
            "检测到 %d 条 processed/failed 冲突记录，已从 processed 中移除并允许重试。",
            conflict_count,
        )
        save_progress(progress)

    logger.info("正在收集 Zotero 附件路径...")
    file_map = collect_files(
        progress_processed=progress["processed"],
        collection_keys=collection_keys,
        recursive=recursive,
        page_size=page_size,
        target_dataset=dataset_id,
    )

    if not file_map:
        logger.info("没有新的文件需要处理。")
        return

    logger.info("发现 %d 个新文件。", len(file_map))

    logger.info("开始 MinerU 批量解析...")
    md_results, md_failures = process_files(file_map)

    for key, reason in md_failures.items():
        progress["failed"][key] = {
            "stage": "mineru",
            "reason": reason,
        }
    if md_failures:
        save_progress(progress)

    if not md_results:
        logger.warning("没有文件成功解析，请检查日志。")
        return

    logger.info("成功解析为 Markdown：%d 个文件。", len(md_results))
    logger.info("正在上传 %d 篇文档到 Dify...", len(md_results))
    uploaded_keys, upload_failures = upload_all(
        dataset_id=dataset_id,
        md_results=md_results,
        dataset_info=dataset_info,
    )

    for key in uploaded_keys:
        file_name = md_results.get(key, {}).get("file_name", key)

        progress["processed"][key] = {
            "file_name": file_name,
            "dify_dataset": dataset_id,
        }

        failed_entry = progress["failed"].get(key)
        if not isinstance(failed_entry, dict):
            progress["failed"].pop(key, None)
        else:
            failed_dataset = failed_entry.get("dify_dataset")
            if not failed_dataset or failed_dataset == dataset_id:
                progress["failed"].pop(key, None)

    for key in upload_failures:
        progress["failed"][key] = {
            "stage": "dify",
            "dify_dataset": dataset_id,
            "reason": "dify 上传或索引失败",
        }

    save_progress(progress)

    logger.info("=" * 50)
    logger.info("流水线执行完成，上传失败的文件可重新尝试")
    logger.info("  解析成功: %d  |  解析失败: %d", len(md_results), len(md_failures))
    logger.info("  上传成功: %d  |  上传失败: %d", len(uploaded_keys), len(upload_failures))
    logger.info("  库中累计已处理: %d", len(progress["processed"]))


if __name__ == "__main__":
    main()
