"""Cookie 持久化管理，对应 Go 版本的 cookies/cookies.go"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger


def get_cookies_file_path() -> str:
    """获取 cookies 文件路径（向后兼容旧路径 /tmp/cookies.json）"""
    import tempfile

    old_path = Path(tempfile.gettempdir()) / "cookies.json"
    if old_path.exists():
        return str(old_path)

    env_path = os.getenv("COOKIES_PATH", "")
    if env_path:
        return env_path

    return "cookies.json"


class CookieManager:
    """本地文件 Cookie 管理器"""

    def __init__(self, path: str) -> None:
        if not path:
            raise ValueError("path is required")
        self.path = path

    def load_cookies(self) -> list[dict[str, Any]] | None:
        """从文件加载 cookies，返回 None 表示文件不存在或解析失败"""
        try:
            data = Path(self.path).read_bytes()
            return json.loads(data)
        except FileNotFoundError:
            logger.warning(f"cookies file not found: {self.path}")
            return None
        except Exception as e:
            logger.warning(f"failed to load cookies: {e}")
            return None

    def save_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """保存 cookies 到文件"""
        Path(self.path).write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        logger.debug(f"cookies saved to {self.path}")

    def delete_cookies(self) -> None:
        """删除 cookies 文件"""
        p = Path(self.path)
        if p.exists():
            p.unlink()
            logger.info(f"cookies file deleted: {self.path}")
        # 文件不存在视为已删除，不报错


def new_cookie_manager() -> CookieManager:
    return CookieManager(get_cookies_file_path())

