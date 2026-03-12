"""用户主页获取，对应 Go 版本的 xiaohongshu/user_profile.go"""

from __future__ import annotations

import json

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.types import Feed, UserBasicInfo, UserInteractions, UserProfileResponse


def _make_user_profile_url(user_id: str, xsec_token: str) -> str:
    return (
        f"https://www.xiaohongshu.com/user/profile/{user_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_note"
    )


class UserProfileAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def user_profile(self, user_id: str, xsec_token: str) -> UserProfileResponse:
        """获取指定用户主页信息"""
        url = _make_user_profile_url(user_id, xsec_token)
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_function("() => window.__INITIAL_STATE__ !== undefined")
        return await self._extract_user_profile_data()

    async def _extract_user_profile_data(self) -> UserProfileResponse:
        # 用户基本信息 + interactions
        user_data_result: str = await self.page.evaluate("""
            () => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.user &&
                    window.__INITIAL_STATE__.user.userPageData) {
                    const d = window.__INITIAL_STATE__.user.userPageData;
                    const data = d.value !== undefined ? d.value : d._value;
                    if (data) return JSON.stringify(data);
                }
                return "";
            }
        """)
        if not user_data_result:
            raise ValueError("user.userPageData.value not found in __INITIAL_STATE__")

        # 用户帖子
        notes_result: str = await self.page.evaluate("""
            () => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.user &&
                    window.__INITIAL_STATE__.user.notes) {
                    const n = window.__INITIAL_STATE__.user.notes;
                    const data = n.value !== undefined ? n.value : n._value;
                    if (data) return JSON.stringify(data);
                }
                return "";
            }
        """)
        if not notes_result:
            raise ValueError("user.notes.value not found in __INITIAL_STATE__")

        user_page_data: dict = json.loads(user_data_result)
        basic_info = UserBasicInfo.model_validate(user_page_data.get("basicInfo", {}))
        interactions = [
            UserInteractions.model_validate(i)
            for i in user_page_data.get("interactions", [])
        ]

        # 帖子为双重数组
        notes_feeds: list[list[dict]] = json.loads(notes_result)
        feeds: list[Feed] = []
        for group in notes_feeds:
            for item in group:
                feeds.append(Feed.model_validate(item))

        logger.info(f"获取用户主页成功，帖子数: {len(feeds)}")
        return UserProfileResponse(
            userBasicInfo=basic_info,
            interactions=interactions,
            feeds=feeds,
        )

