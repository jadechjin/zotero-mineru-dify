"""外部服务连通性检查 API 路由。"""

from flask import Blueprint, jsonify

from web.errors import error_response

services_bp = Blueprint("services", __name__)

_config_provider = None


def init_services_routes(config_provider):
    global _config_provider
    _config_provider = config_provider


@services_bp.route("/mineru/health", methods=["GET"])
def mineru_health():
    """检查 MinerU API 连通性。"""
    cfg = _config_provider.get_snapshot()
    try:
        from mineru_client import check_connection

        result = check_connection(cfg)
        return jsonify({
            "success": True,
            "connected": result["connected"],
            "message": result.get("message", ""),
        })
    except Exception as exc:
        return error_response(f"连接检查失败: {exc}", 500)


@services_bp.route("/dify/health", methods=["GET"])
def dify_health():
    """检查 Dify API 连通性。"""
    cfg = _config_provider.get_snapshot()
    try:
        from dify_client import check_connection

        result = check_connection(cfg)
        return jsonify({
            "success": True,
            "connected": result["connected"],
            "message": result.get("message", ""),
        })
    except Exception as exc:
        return error_response(f"连接检查失败: {exc}", 500)


@services_bp.route("/image-summary/health", methods=["GET"])
def image_summary_health():
    """检查视觉模型 API 连通性。"""
    cfg = _config_provider.get_snapshot()
    try:
        from md_cleaner import check_vision_connection

        result = check_vision_connection(cfg)
        return jsonify({
            "success": True,
            "connected": result["connected"],
            "message": result.get("message", ""),
        })
    except Exception as exc:
        return error_response(f"连接检查失败: {exc}", 500)
