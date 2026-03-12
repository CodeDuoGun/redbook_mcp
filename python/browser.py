"""Playwright 浏览器工厂，对应 Go 版本的 browser/browser.go"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from cookies import new_cookie_manager


def _get_headless() -> bool:
    """读取 HEADLESS 环境变量，默认 True（无头模式）"""
    val = os.getenv("HEADLESS", "true").lower()
    return val not in ("false", "0", "no")


def _get_bin_path() -> str | None:
    return os.getenv("CHROME_BIN") or os.getenv("CHROMIUM_PATH") or None


def _get_proxy() -> dict[str, str] | None:
    proxy = os.getenv("XHS_PROXY", "")
    if not proxy:
        return None
    logger.info(f"Using proxy: {_mask_proxy(proxy)}")
    return {"server": proxy}


def _mask_proxy(proxy_url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(proxy_url)
        if p.username or p.password:
            masked = p._replace(netloc=f"***:***@{p.hostname}:{p.port}")
            return urlunparse(masked)
    except Exception:
        pass
    return proxy_url


class BrowserSession:
    """封装 Playwright browser + context + page 生命周期"""

    def __init__(
        self,
        playwright: Playwright,
        browser: Browser,
        context: BrowserContext,
    ) -> None:
        self._playwright = playwright
        self._browser = browser
        self._context = context

    async def new_page(self) -> Page:
        return await self._context.new_page()

    async def get_cookies(self) -> list[dict[str, Any]]:
        return await self._context.cookies()

    async def close(self) -> None:
        try:
            await self._context.close()
        except Exception:
            pass
        try:
            await self._browser.close()
        except Exception:
            pass
        try:
            await self._playwright.stop()
        except Exception:
            pass


async def new_browser_session() -> BrowserSession:
    """创建一个新的浏览器会话，自动加载 cookies"""
    pw = await async_playwright().start()

    launch_kwargs: dict[str, Any] = {
        "headless": _get_headless(),
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    }

    bin_path = _get_bin_path()
    if bin_path:
        launch_kwargs["executable_path"] = bin_path

    proxy = _get_proxy()
    if proxy:
        launch_kwargs["proxy"] = proxy

    browser = await pw.chromium.launch(**launch_kwargs)

    # 构建 context 参数
    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1280, "height": 900},
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "locale": "zh-CN",
    }

    context = await browser.new_context(**context_kwargs)

    # 加载已保存的 cookies
    cm = new_cookie_manager()
    saved = cm.load_cookies()
    if saved:
        try:
            await context.add_cookies(saved)
            logger.debug("loaded cookies from file successfully")
        except Exception as e:
            logger.warning(f"failed to add cookies to context: {e}")

    return BrowserSession(pw, browser, context)

