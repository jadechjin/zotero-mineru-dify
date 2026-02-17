"""任务管理 API 路由。"""

from flask import Blueprint, jsonify, request

from web.errors import error_response, not_found

tasks_bp = Blueprint("tasks", __name__)

# 运行时注入
_task_manager = None
_config_provider = None
_pipeline_runner_fn = None


def init_tasks_routes(task_manager, config_provider, pipeline_runner_fn):
    global _task_manager, _config_provider, _pipeline_runner_fn
    _task_manager = task_manager
    _config_provider = config_provider
    _pipeline_runner_fn = pipeline_runner_fn


@tasks_bp.route("/tasks", methods=["POST"])
def create_task():
    """创建新任务。"""
    body = request.get_json(silent=True) or {}
    collection_keys = body.get("collection_keys", [])

    if isinstance(collection_keys, str):
        collection_keys = [k.strip() for k in collection_keys.split(",") if k.strip()]

    config_snapshot = _config_provider.get_snapshot()
    config_version = _config_provider.get_version()

    try:
        task = _task_manager.create_task(
            collection_keys=collection_keys,
            config_snapshot=config_snapshot,
            config_version=config_version,
        )
    except RuntimeError as exc:
        return error_response(str(exc), 409)

    _task_manager.start_task(task.task_id, _pipeline_runner_fn)

    return jsonify({"success": True, "task_id": task.task_id}), 201


@tasks_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """获取任务列表。"""
    tasks = _task_manager.list_tasks()
    return jsonify({"success": True, "data": tasks})


@tasks_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """获取任务详情。"""
    task = _task_manager.get_task(task_id)
    if task is None:
        return not_found("任务不存在")
    return jsonify({"success": True, "data": task.detail()})


@tasks_bp.route("/tasks/<task_id>/events", methods=["GET"])
def get_events(task_id):
    """获取任务事件（支持增量查询）。"""
    after_seq = request.args.get("after_seq", 0, type=int)
    task = _task_manager.get_task(task_id)
    if task is None:
        return not_found("任务不存在")
    events = _task_manager.get_events(task_id, after_seq)
    return jsonify({"success": True, "data": events})


@tasks_bp.route("/tasks/<task_id>/files", methods=["GET"])
def get_files(task_id):
    """获取文件级状态。"""
    task = _task_manager.get_task(task_id)
    if task is None:
        return not_found("任务不存在")
    files = _task_manager.get_files(task_id)
    return jsonify({"success": True, "data": files})


@tasks_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """取消任务。"""
    ok = _task_manager.cancel_task(task_id)
    if not ok:
        return error_response("无法取消（任务不存在或已结束）", 409)
    return jsonify({"success": True, "message": "任务已取消"})
