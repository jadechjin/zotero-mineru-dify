"""运行时配置管理 — JSON 持久化 + 读写锁 + 版本追踪。"""

import json
import os
import tempfile
import threading
from pathlib import Path

from services.config_schema import (
    CONFIG_SCHEMA,
    ENV_KEY_MAP,
    build_defaults,
    validate_and_coerce,
    mask_sensitive,
)

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "runtime_config.json",
)


class RuntimeConfigProvider:
    """线程安全的运行时配置提供者。

    - JSON 文件持久化（原子写: tmp → rename）
    - 读写锁（RLock）
    - 版本号自增
    - 首启从 .env 自动导入
    """

    def __init__(self, config_path: str | None = None):
        self._path = config_path or _DEFAULT_CONFIG_PATH
        self._lock = threading.RLock()
        self._data: dict = {}
        self._version: int = 0
        self._ensure_dir()
        self._load_or_init()

    # ------ public API ------

    def get_snapshot(self) -> dict:
        """返回当前配置的深拷贝快照。"""
        with self._lock:
            return json.loads(json.dumps(self._data))

    def get_version(self) -> int:
        """返回当前配置版本号。"""
        with self._lock:
            return self._version

    def update(self, patch: dict) -> dict:
        """合并补丁到当前配置，校验 + 持久化，版本 +1。

        Args:
            patch: 部分配置字典，结构同完整配置（按 category/key）。

        Returns:
            脱敏后的完整配置。
        """
        with self._lock:
            merged = json.loads(json.dumps(self._data))
            current_masked = mask_sensitive(self._data)
            for category, fields in patch.items():
                if not isinstance(fields, dict):
                    continue
                if category not in merged:
                    merged[category] = {}
                schema_fields = CONFIG_SCHEMA.get(category, {})
                for key, value in fields.items():
                    spec = schema_fields.get(key, {})
                    # Prevent masked echo (e.g. ****abcd) from overwriting real secret.
                    if spec.get("sensitive") and isinstance(value, str):
                        masked_existing = (current_masked.get(category, {}) or {}).get(key)
                        if isinstance(masked_existing, str) and value == masked_existing:
                            continue
                    merged[category][key] = value
            validated = validate_and_coerce(merged)
            self._data = validated
            self._version += 1
            self._save()
            return mask_sensitive(self._data)

    def import_env(self, env_path: str = ".env") -> dict:
        """从 .env 文件导入配置值，覆盖现有同名项。

        Returns:
            脱敏后的完整配置。
        """
        env_values = self._parse_env_file(env_path)
        patch: dict = {}
        for env_key, value in env_values.items():
            mapping = ENV_KEY_MAP.get(env_key)
            if mapping is None:
                continue
            category, key = mapping
            if category not in patch:
                patch[category] = {}
            patch[category][key] = value
        if patch:
            return self.update(patch)
        return mask_sensitive(self.get_snapshot())

    def get_masked(self) -> dict:
        """返回脱敏后的配置快照。"""
        with self._lock:
            return mask_sensitive(self._data)

    def reset_to_defaults(self) -> dict:
        """重置为默认配置，版本 +1。"""
        with self._lock:
            self._data = build_defaults()
            self._version += 1
            self._save()
            return mask_sensitive(self._data)

    # ------ internal ------

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def _load_or_init(self):
        """加载 JSON 或首启初始化（尝试从 .env 导入）。"""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._data = validate_and_coerce(raw.get("data", raw))
                self._version = raw.get("version", 0)
                return
            except (json.JSONDecodeError, OSError):
                pass

        self._data = build_defaults()
        self._version = 0

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(project_root, ".env")
        if os.path.exists(env_path):
            env_values = self._parse_env_file(env_path)
            patch: dict = {}
            for env_key, value in env_values.items():
                mapping = ENV_KEY_MAP.get(env_key)
                if mapping is None:
                    continue
                category, key = mapping
                if category not in patch:
                    patch[category] = {}
                patch[category][key] = value
            if patch:
                merged = json.loads(json.dumps(self._data))
                for cat, fields in patch.items():
                    if cat not in merged:
                        merged[cat] = {}
                    merged[cat].update(fields)
                self._data = validate_and_coerce(merged)
            self._version = 1
        self._save()

    def _save(self):
        """原子写入: 写临时文件 → rename 覆盖。"""
        payload = {
            "version": self._version,
            "data": self._data,
        }
        dir_name = os.path.dirname(self._path)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            # Windows: os.rename 不能覆盖已存在文件，用 os.replace
            os.replace(tmp_path, self._path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def _parse_env_file(env_path: str) -> dict[str, str]:
        """简单解析 .env 文件，返回 key=value 映射。"""
        result = {}
        if not os.path.exists(env_path):
            return result
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                result[key] = value
        return result
