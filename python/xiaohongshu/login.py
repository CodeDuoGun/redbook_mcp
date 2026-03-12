"""登录相关操作，对应 Go 版本的 xiaohongshu/login.go"""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger
from playwright.async_api import Page


class LoginAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def check_login_status(self) -> bool:
        """检查是否已登录，返回 True 表示已登录"""
        await self.page.goto("https://www.xiaohongshu.com/explore", wait_until="load")
        await asyncio.sleep(1)
        try:
            elem = await self.page.query_selector(
                ".main-container .user .link-wrapper .channel"
            )
            return elem is not None
        except Exception as e:
            logger.warning(f"check login status failed: {e}")
            return False

    async def fetch_qrcode_image(self) -> tuple[str, bool]:
        """
        获取登录二维码图片。
        返回 (img_src, is_logged_in)。
        - img_src: data:image/... base64 字符串，已登录时为空字符串
        - is_logged_in: 是否已经登录
        """
        await self.page.goto("https://www.xiaohongshu.com/explore", wait_until="load")
        await asyncio.sleep(2)

        # 检查是否已登录
        elem = await self.page.query_selector(
            ".main-container .user .link-wrapper .channel"
        )
        if elem is not None:
            return "", True

        # 获取二维码 src
        try:
            qr_elem = await self.page.wait_for_selector(
                ".login-container .qrcode-img", timeout=10_000
            )
            if qr_elem is None:
                raise ValueError("qrcode element not found")
            src: Optional[str] = await qr_elem.get_attribute("src")
            if not src:
                raise ValueError("qrcode src is empty")
            return src, False
        except Exception as e:
            raise RuntimeError(f"get qrcode src failed: {e}") from e

    async def wait_for_login(self, timeout: float = 240.0) -> bool:
        """
        轮询等待登录完成，timeout 单位秒。
        登录成功返回 True，超时返回 False。
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                elem = await self.page.query_selector(
                    ".main-container .user .link-wrapper .channel"
                )
                if elem is not None:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

