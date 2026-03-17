"""搜索功能，对应 Go 版本的 xiaohongshu/search.go"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.types import Feed, FilterOption

# 筛选选项映射表：{group_index: [(tag_index, text), ...]}
_FILTER_OPTIONS_MAP: dict[int, list[tuple[int, str]]] = {
    1: [(1, "综合"), (2, "最新"), (3, "最多点赞"), (4, "最多评论"), (5, "最多收藏")],
    2: [(1, "不限"), (2, "视频"), (3, "图文")],
    3: [(1, "不限"), (2, "一天内"), (3, "一周内"), (4, "半年内")],
    4: [(1, "不限"), (2, "已看过"), (3, "未看过"), (4, "已关注")],
    5: [(1, "不限"), (2, "同城"), (3, "附近")],
}


def _find_internal_option(group_index: int, text: str) -> tuple[int, int]:
    """返回 (group_index, tag_index)，找不到抛出 ValueError"""
    options = _FILTER_OPTIONS_MAP.get(group_index)
    if not options:
        raise ValueError(f"筛选组 {group_index} 不存在")
    for tag_idx, opt_text in options:
        if opt_text == text:
            return group_index, tag_idx
    logger.error(f"在筛选组 {group_index} 中未找到文本 '{text}'")
    raise ValueError(f"在筛选组 {group_index} 中未找到文本 '{text}'")


def _convert_filter_option(f: FilterOption) -> list[tuple[int, int]]:
    """将 FilterOption 转换为 (group_idx, tag_idx) 列表"""
    result: list[tuple[int, int]] = []
    if f.sort_by:
        result.append(_find_internal_option(1, f.sort_by))
    if f.note_type:
        result.append(_find_internal_option(2, f.note_type))
    if f.publish_time:
        result.append(_find_internal_option(3, f.publish_time))
    if f.search_scope:
        result.append(_find_internal_option(4, f.search_scope))
    if f.location:
        result.append(_find_internal_option(5, f.location))
    return result


def _make_search_url(keyword: str) -> str:
    params = urlencode({"keyword": keyword, "source": "web_explore_feed"})
    return f"https://www.xiaohongshu.com/search_result?{params}"


class SearchAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def search(self, keyword: str, filters: FilterOption | None = None) -> list[Feed]:
        """搜索小红书内容，返回 Feed 列表"""
        url = _make_search_url(keyword)
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_function("() => window.__INITIAL_STATE__ !== undefined")

        if filters:
            logger.info(f"filters {filters}")
            internal = _convert_filter_option(filters)
            if internal:
                # 悬停筛选按钮
                filter_btn = await self.page.query_selector("div.filter")
                if filter_btn:
                    await filter_btn.hover()
                    await self.page.wait_for_selector("div.filter-panel")

                    for group_idx, tag_idx in internal:
                        selector = (
                            f"div.filter-panel div.filters:nth-child({group_idx}) "
                            f"div.tags:nth-child({tag_idx})"
                        )
                        opt = await self.page.query_selector(selector)
                        if opt:
                            await opt.click()

                    await self.page.wait_for_load_state("networkidle")
                    await self.page.wait_for_function(
                        "() => window.__INITIAL_STATE__ !== undefined"
                    )

        result: str = await self.page.evaluate("""
            () => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.search &&
                    window.__INITIAL_STATE__.search.feeds) {
                    const feeds = window.__INITIAL_STATE__.search.feeds;
                    const feedsData = feeds.value !== undefined ? feeds.value : feeds._value;
                    if (feedsData) {
                        return JSON.stringify(feedsData);
                    }
                }
                return "";
            }
        """)

        if not result:
            raise ValueError("no search feeds found in __INITIAL_STATE__")

        raw_list: list[dict] = json.loads(result)
        feeds = [Feed.model_validate(item) for item in raw_list]
        logger.info(f"search '{keyword}' got {len(feeds)} feeds")
        logger.info(f"feed : {type(feeds[-1])} {feeds[-1]}")
        return feeds

