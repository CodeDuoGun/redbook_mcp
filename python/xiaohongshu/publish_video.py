"""视频发布，对应 Go 版本的 xiaohongshu/publish_video.go"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.publish import (
    PublishAction,
    _bind_products,
    _check_content_length,
    _get_content_element,
    _input_tags,
    _set_schedule,
    _set_visibility,
)


@dataclass
class PublishVideoContent:
    title: str
    content: str
    video_path: str
    tags: list[str] = field(default_factory=list)
    schedule_time: Optional[datetime] = None
    visibility: str = ""
    products: list[str] = field(default_factory=list)


async def _wait_for_publish_button_clickable(page: Page, timeout: float = 600.0):
    """等待发布按钮变为可点击状态（视频处理需要较长时间）"""
    selector = ".publish-page-publish-btn button.bg-red"
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                disabled = await btn.get_attribute("disabled")
                if disabled is None:
                    return btn
        except Exception:
            pass
        await asyncio.sleep(1)
    raise RuntimeError("等待发布按钮可点击超时")


async def _upload_video(page: Page, video_path: str) -> None:
    if not os.path.exists(video_path):
        raise RuntimeError(f"视频文件不存在: {video_path}")

    # 找文件上传输入框
    inp = await page.query_selector(".upload-input")
    if inp is None:
        inp = await page.query_selector("input[type='file']")
    if inp is None:
        raise RuntimeError("未找到视频上传输入框")

    await inp.set_input_files(video_path)
    logger.info(f"视频已提交上传: {video_path}")

    # 等待发布按钮可点击（表示视频处理完成）
    btn = await _wait_for_publish_button_clickable(page)
    logger.info(f"视频上传/处理完成，发布按钮可点击: {btn}")


class PublishVideoAction:
    def __init__(self, page: Page) -> None:
        self._publish_action = PublishAction(page)

    @property
    def page(self) -> Page:
        return self._publish_action.page

    async def publish_video(self, content: PublishVideoContent) -> None:
        if not content.video_path:
            raise RuntimeError("视频不能为空")

        await _upload_video(self.page, content.video_path)
        await self._submit_video(
            content.title, content.content, content.tags,
            content.schedule_time, content.visibility, content.products,
        )

    async def _submit_video(
        self,
        title: str,
        body: str,
        tags: list[str],
        schedule_time: Optional[datetime],
        visibility: str,
        products: list[str],
    ) -> None:
        page = self.page

        title_inp = await page.wait_for_selector("div.d-input input", timeout=10_000)
        if title_inp is None:
            raise RuntimeError("查找标题输入框失败")
        await title_inp.fill(title)
        await asyncio.sleep(1)

        content_elem = await _get_content_element(page)
        if content_elem is None:
            raise RuntimeError("没有找到内容输入框")
        await content_elem.fill(body)
        await asyncio.sleep(1)
        await title_inp.click()
        await _input_tags(content_elem, page, tags)
        await asyncio.sleep(1)
        await _check_content_length(page)

        if schedule_time:
            await _set_schedule(page, schedule_time)

        await _set_visibility(page, visibility)
        await _bind_products(page, products)

        # 等待发布按钮可点击（视频可能还在处理）
        btn = await _wait_for_publish_button_clickable(page)
        await btn.click()
        await asyncio.sleep(3)
        logger.info("视频发布完成")

