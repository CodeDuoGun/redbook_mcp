"""首页 Feed 列表获取，对应 Go 版本的 xiaohongshu/feeds.go"""

from __future__ import annotations

import asyncio
import json

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.types import Feed


class FeedsListAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def get_feeds_list(self) -> list[Feed]:
        """导航到小红书首页并提取 Feed 列表"""
        await self.page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
        # 等待 DOM 稳定
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        result: str = await self.page.evaluate("""
            () => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.feed &&
                    window.__INITIAL_STATE__.feed.feeds) {
                    const feeds = window.__INITIAL_STATE__.feed.feeds;
                    const feedsData = feeds.value !== undefined ? feeds.value : feeds._value;
                    if (feedsData) {
                        return JSON.stringify(feedsData);
                    }
                }
                return "";
            }
        """)

        if not result:
            raise ValueError("no feeds found in __INITIAL_STATE__")

        raw_list: list[dict] = json.loads(result)
        feeds = [Feed.model_validate(item) for item in raw_list]
        logger.info(f"got {len(feeds)} feeds from homepage")
        return feeds

