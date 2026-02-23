"""Zotero 相关 API 路由。"""

from flask import Blueprint, jsonify

from web.errors import error_response

zotero_bp = Blueprint("zotero", __name__)

# 运行时注入
_config_provider = None


def init_zotero_routes(config_provider):
    global _config_provider
    _config_provider = config_provider


@zotero_bp.route("/zotero/health", methods=["GET"])
def zotero_health():
    """检查 Zotero MCP 连通性。"""
    cfg = _config_provider.get_snapshot()
    try:
        from zotero_client import check_connection
        ok = check_connection(cfg)
        message = "Zotero MCP 服务连通" if ok else "Zotero MCP 连接失败"
        return jsonify({"success": True, "connected": ok, "message": message})
    except Exception as exc:
        return error_response(f"连接检查失败: {exc}", 500)


@zotero_bp.route("/zotero/collections", methods=["GET"])
def zotero_collections():
    """获取 Zotero 分组树。"""
    cfg = _config_provider.get_snapshot()
    try:
        from zotero_client import list_collections
        collections = list_collections(cfg)
        return jsonify({"success": True, "data": collections})
    except Exception as exc:
        return error_response(f"获取分组失败: {exc}", 500)
