"""统一错误响应。"""

from flask import jsonify


def error_response(message: str, status_code: int = 400, details: str = ""):
    body = {"success": False, "error": message}
    if details:
        body["details"] = details
    return jsonify(body), status_code


def not_found(message: str = "资源不存在"):
    return error_response(message, 404)
