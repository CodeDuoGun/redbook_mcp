"""图文发布，对应 Go 版本的 xiaohongshu/publish.go"""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger
from playwright.async_api import Page

URL_PUBLISH = "https://creator.xiaohongshu.com/publish/publish?source=official"


@dataclass
class PublishImageContent:
    title: str
    content: str
    image_paths: list[str]
    tags: list[str] = field(default_factory=list)
    schedule_time: Optional[datetime] = None
    is_original: bool = False
    visibility: str = ""
    products: list[str] = field(default_factory=list)


# ==================== 内部工具函数 ====================

async def _remove_pop_cover(page: Page) -> None:
    try:
        el = await page.query_selector("div.d-popover")
        if el:
            await el.evaluate("el => el.remove()")
    except Exception:
        pass
    # 点击空位
    x = 380 + random.randint(0, 100)
    y = 20 + random.randint(0, 60)
    await page.mouse.click(x, y)


async def _is_element_visible(page: Page, selector: str) -> bool:
    try:
        el = await page.query_selector(selector)
        if el is None:
            return False
        return await el.is_visible()
    except Exception:
        return False


async def _click_publish_tab(page: Page, tabname: str) -> None:
    """等待并点击指定名称的发布 TAB"""
    await page.wait_for_selector("div.upload-content", timeout=15_000)

    deadline = asyncio.get_event_loop().time() + 15
    while asyncio.get_event_loop().time() < deadline:
        tabs = await page.query_selector_all("div.creator-tab")
        for tab in tabs:
            # 检查可见性
            style = await tab.get_attribute("style") or ""
            if "left: -9999px" in style or "display: none" in style:
                continue
            visible = await tab.is_visible()
            if not visible:
                continue
            text = (await tab.text_content() or "").strip()
            if text != tabname:
                continue
            # 检查是否被遮挡
            blocked: bool = await tab.evaluate("""
                el => {
                    const rect = el.getBoundingClientRect();
                    if (!rect.width || !rect.height) return true;
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const target = document.elementFromPoint(x, y);
                    return !(target === el || el.contains(target));
                }
            """)
            if blocked:
                await _remove_pop_cover(page)
                await asyncio.sleep(0.2)
                continue
            await tab.click()
            return
        await asyncio.sleep(0.2)

    raise RuntimeError(f"没有找到发布 TAB: {tabname}")


async def _wait_for_upload_complete(page: Page, expected_count: int) -> None:
    """等待第 expected_count 张图片上传完成，最多 60 秒"""
    start = asyncio.get_event_loop().time()
    last_log = expected_count - 1
    while asyncio.get_event_loop().time() - start < 60:
        try:
            imgs = await page.query_selector_all(".img-preview-area .pr")
            cnt = len(imgs)
            if cnt != last_log:
                logger.info(f"等待图片上传 current={cnt} expected={expected_count}")
                last_log = cnt
            if cnt >= expected_count:
                logger.info(f"图片上传完成 count={cnt}")
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"第{expected_count}张图片上传超时")


async def _upload_images(page: Page, image_paths: list[str]) -> None:
    valid = [p for p in image_paths if os.path.exists(p)]
    if not valid:
        raise RuntimeError("没有有效的图片文件")

    for i, path in enumerate(valid):
        selector = ".upload-input" if i == 0 else 'input[type="file"]'
        inp = await page.query_selector(selector)
        if inp is None:
            raise RuntimeError(f"查找上传输入框失败(第{i+1}张)")
        await inp.set_input_files(path)
        logger.info(f"图片已提交上传 index={i+1} path={path}")
        await _wait_for_upload_complete(page, i + 1)
        await asyncio.sleep(1)


async def _get_content_element(page: Page):
    """查找正文输入框，优先 ql-editor，其次 data-placeholder"""
    try:
        el = await page.wait_for_selector("div.ql-editor", timeout=3_000)
        if el:
            return el
    except Exception:
        pass
    # 退回：查找含有 data-placeholder="输入正文描述" 的元素的父 textbox
    try:
        ps = await page.query_selector_all("p")
        for p in ps:
            ph = await p.get_attribute("data-placeholder") or ""
            if "输入正文描述" in ph:
                # 向上找 role=textbox
                current = p
                for _ in range(5):
                    parent = await current.evaluate_handle("el => el.parentElement")
                    if parent is None:
                        break
                    parent_el = parent.as_element()
                    if parent_el is None:
                        break
                    role = await parent_el.get_attribute("role") or ""
                    if role == "textbox":
                        return parent_el
                    current = parent_el
    except Exception:
        pass
    return None


async def _input_tag(content_elem, page: Page, tag: str) -> None:
    tag = tag.lstrip("#")
    await content_elem.type("#")
    await asyncio.sleep(0.2)
    for ch in tag:
        await content_elem.type(ch)
        await asyncio.sleep(0.05)
    await asyncio.sleep(1)
    container = await page.query_selector("#creator-editor-topic-container")
    if container:
        item = await container.query_selector(".item")
        if item:
            await item.click()
            await asyncio.sleep(0.2)
            return
    await content_elem.type(" ")


async def _input_tags(content_elem, page: Page, tags: list[str]) -> None:
    if not tags:
        return
    await asyncio.sleep(1)
    # 移到末尾
    for _ in range(20):
        await content_elem.press("ArrowDown")
        await asyncio.sleep(0.01)
    await content_elem.press("Enter")
    await content_elem.press("Enter")
    await asyncio.sleep(1)
    for tag in tags:
        await _input_tag(content_elem, page, tag)


async def _set_visibility(page: Page, visibility: str) -> None:
    if not visibility or visibility == "公开可见":
        return
    supported = {"仅自己可见", "仅互关好友可见"}
    if visibility not in supported:
        raise ValueError(f"不支持的可见范围: {visibility}")
    dropdown = await page.query_selector("div.permission-card-wrapper div.d-select-content")
    if dropdown is None:
        raise RuntimeError("查找可见范围下拉框失败")
    await dropdown.click()
    await asyncio.sleep(0.5)
    opts = await page.query_selector_all("div.d-options-wrapper div.d-grid-item div.custom-option")
    for opt in opts:
        text = (await opt.text_content() or "").strip()
        if visibility in text:
            await opt.click()
            logger.info(f"已设置可见范围: {visibility}")
            return
    raise RuntimeError(f"未找到可见范围选项: {visibility}")


async def _set_schedule(page: Page, t: datetime) -> None:
    switch = await page.query_selector(".post-time-wrapper .d-switch")
    if switch is None:
        raise RuntimeError("查找定时发布开关失败")
    await switch.click()
    await asyncio.sleep(0.8)
    date_str = t.strftime("%Y-%m-%d %H:%M")
    inp = await page.query_selector(".date-picker-container input")
    if inp is None:
        raise RuntimeError("查找日期时间输入框失败")
    await inp.select_text()
    await inp.fill(date_str)
    logger.info(f"已设置定时发布: {date_str}")


async def _set_original(page: Page) -> None:
    cards = await page.query_selector_all("div.custom-switch-card")
    for card in cards:
        text = (await card.text_content() or "")
        if "原创声明" not in text:
            continue
        switch = await card.query_selector("div.d-switch")
        if switch is None:
            continue
        checked: bool = await switch.evaluate("""
            el => {
                const inp = el.querySelector('input[type="checkbox"]');
                return inp ? inp.checked : false;
            }
        """)
        if checked:
            return
        await switch.click()
        await asyncio.sleep(0.8)
        # 处理确认弹窗
        await page.evaluate("""
            () => {
                for (const footer of document.querySelectorAll('div.footer')) {
                    if (!footer.textContent.includes('原创声明须知')) continue;
                    const cb = footer.querySelector('div.d-checkbox input[type="checkbox"]');
                    if (cb && !cb.checked) cb.click();
                }
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("""
            () => {
                for (const footer of document.querySelectorAll('div.footer')) {
                    if (!footer.textContent.includes('声明原创')) continue;
                    const btn = footer.querySelector('button.custom-button');
                    if (btn && !btn.disabled) btn.click();
                }
            }
        """)
        logger.info("已开启原创声明")
        return


async def _bind_products(page: Page, products: list[str]) -> None:
    if not products:
        return
    # 找并点击"添加商品"按钮
    spans = await page.query_selector_all("span.d-text")
    clicked_add = False
    for span in spans:
        text = (await span.text_content() or "").strip()
        if text != "添加商品":
            continue
        # 向上找 button 或 d-button
        current = span
        for _ in range(5):
            parent = await current.evaluate_handle("el => el.parentElement")
            if parent is None:
                break
            pel = parent.as_element()
            if pel is None:
                break
            tag: str = await pel.evaluate("el => el.tagName.toLowerCase()")
            cls = await pel.get_attribute("class") or ""
            if tag == "button" or "d-button" in cls:
                await pel.click()
                clicked_add = True
                await asyncio.sleep(0.3)
                break
            current = pel
        if clicked_add:
            break

    if not clicked_add:
        raise RuntimeError("未找到添加商品按钮，账号可能未开通商品功能")

    # 等待弹窗
    modal = None
    for _ in range(100):
        modal = await page.query_selector(".multi-goods-selector-modal")
        if modal and await modal.is_visible():
            break
        await asyncio.sleep(0.1)
    if modal is None:
        raise RuntimeError("等待商品弹窗超时")

    failed: list[str] = []
    for kw in products:
        try:
            inp = await modal.query_selector('input[placeholder="搜索商品ID 或 商品名称"]')
            if inp is None:
                raise RuntimeError("未找到商品搜索框")
            await inp.select_text()
            await asyncio.sleep(0.1)
            await inp.fill(kw)
            await asyncio.sleep(0.3)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
            # 等待结果
            for _ in range(100):
                card = await modal.query_selector(".goods-list-normal .good-card-container")
                if card:
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.5)
            checkbox = await modal.query_selector(".goods-list-normal .good-card-container .d-checkbox")
            if checkbox is None:
                raise RuntimeError("未找到商品选择框")
            await checkbox.click()
            await asyncio.sleep(0.8 + random.random() * 0.7)
        except Exception as e:
            logger.warning(f"搜索选择商品失败 keyword={kw}: {e}")
            failed.append(kw)

    # 点击保存
    try:
        btn = await modal.query_selector(".goods-selected-footer button")
        if btn:
            await btn.click()
    except Exception:
        pass

    # 等待弹窗关闭
    for _ in range(50):
        exists = await page.query_selector(".multi-goods-selector-modal")
        if not exists:
            break
        await asyncio.sleep(0.2)

    if failed:
        raise RuntimeError(f"部分商品未找到: {failed}")
    await asyncio.sleep(1)


async def _check_title_length(page: Page) -> None:
    el = await page.query_selector("div.title-container div.max_suffix")
    if el:
        text = (await el.text_content() or "").strip()
        parts = text.split("/")
        if len(parts) == 2:
            raise RuntimeError(f"标题超过长度限制: {parts[0]}/{parts[1]}")


async def _check_content_length(page: Page) -> None:
    el = await page.query_selector("div.edit-container div.length-error")
    if el:
        text = (await el.text_content() or "").strip()
        parts = text.split("/")
        if len(parts) == 2:
            raise RuntimeError(f"正文超过长度限制: {parts[0]}/{parts[1]}")


# ==================== 主 Action ====================

class PublishAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    @classmethod
    async def create_image_action(cls, page: Page) -> "PublishAction":
        pp = page
        await pp.goto(URL_PUBLISH, wait_until="load")
        await asyncio.sleep(2)
        try:
            await pp.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
        await asyncio.sleep(1)
        await _click_publish_tab(pp, "上传图文")
        await asyncio.sleep(1)
        return cls(pp)

    @classmethod
    async def create_video_action(cls, page: Page) -> "PublishAction":
        pp = page
        await pp.goto(URL_PUBLISH, wait_until="load")
        await asyncio.sleep(2)
        try:
            await pp.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
        await asyncio.sleep(1)
        await _click_publish_tab(pp, "上传视频")
        await asyncio.sleep(1)
        return cls(pp)

    async def publish(self, content: PublishImageContent) -> None:
        if not content.image_paths:
            raise RuntimeError("图片不能为空")
        tags = content.tags[:10] if len(content.tags) > 10 else content.tags
        await _upload_images(self.page, content.image_paths)
        await self._submit(content.title, content.content, tags,
                           content.schedule_time, content.is_original,
                           content.visibility, content.products)

    async def _submit(
        self,
        title: str,
        body: str,
        tags: list[str],
        schedule_time: Optional[datetime],
        is_original: bool,
        visibility: str,
        products: list[str],
    ) -> None:
        title_inp = await self.page.wait_for_selector("div.d-input input", timeout=10_000)
        if title_inp is None:
            raise RuntimeError("查找标题输入框失败")
        await title_inp.fill(title)
        await asyncio.sleep(0.5)
        await _check_title_length(self.page)
        await asyncio.sleep(1)

        content_elem = await _get_content_element(self.page)
        if content_elem is None:
            raise RuntimeError("没有找到内容输入框")
        await content_elem.fill(body)
        # 回点标题输入框增强稳定性
        await asyncio.sleep(1)
        await title_inp.click()
        await _input_tags(content_elem, self.page, tags)
        await asyncio.sleep(1)
        await _check_content_length(self.page)

        if schedule_time:
            await _set_schedule(self.page, schedule_time)

        await _set_visibility(self.page, visibility)

        if is_original:
            try:
                await _set_original(self.page)
            except Exception as e:
                logger.warning(f"设置原创声明失败，继续发布: {e}")

        await _bind_products(self.page, products)

        submit_btn = await self.page.wait_for_selector(
            ".publish-page-publish-btn button.bg-red", timeout=10_000
        )
        if submit_btn is None:
            raise RuntimeError("查找发布按钮失败")
        await submit_btn.click()
        await asyncio.sleep(3)
        logger.info("图文发布完成")

