"""配置管理 API 路由。"""

from flask import Blueprint, jsonify, request

from services.config_schema import CONFIG_SCHEMA, CATEGORY_LABELS
from web.errors import error_response

config_bp = Blueprint("config", __name__)

# 运行时注入，由 app.py 设置
_config_provider = None


def init_config_routes(config_provider):
    global _config_provider
    _config_provider = config_provider


@config_bp.route("/config", methods=["GET"])
def get_config():
    """获取当前配置（敏感字段脱敏）。"""
    masked = _config_provider.get_masked()
    version = _config_provider.get_version()
    return jsonify({"success": True, "data": masked, "version": version})


@config_bp.route("/config", methods=["PUT"])
def update_config():
    """更新配置。"""
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return error_response("请求体必须为 JSON 对象")
    try:
        masked = _config_provider.update(body)
        version = _config_provider.get_version()
        return jsonify({"success": True, "data": masked, "version": version})
    except Exception as exc:
        return error_response(f"配置更新失败: {exc}", 500)


@config_bp.route("/config/schema", methods=["GET"])
def get_schema():
    """返回配置 schema 定义。"""
    return jsonify({
        "success": True,
        "schema": CONFIG_SCHEMA,
        "category_labels": CATEGORY_LABELS,
    })


@config_bp.route("/config/import-env", methods=["POST"])
def import_env():
    """从 .env 文件导入配置。"""
    body = request.get_json(silent=True) or {}
    env_path = body.get("path", ".env")
    try:
        masked = _config_provider.import_env(env_path)
        version = _config_provider.get_version()
        return jsonify({"success": True, "data": masked, "version": version})
    except Exception as exc:
        return error_response(f".env 导入失败: {exc}", 500)


@config_bp.route("/config/reset", methods=["POST"])
def reset_config():
    """重置为默认配置。"""
    try:
        masked = _config_provider.reset_to_defaults()
        version = _config_provider.get_version()
        return jsonify({"success": True, "data": masked, "version": version})
    except Exception as exc:
        return error_response(f"重置失败: {exc}", 500)
