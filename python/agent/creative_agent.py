"""
CreativeAgent
=============
接收用户输入的标题、文本、图片或视频，自动：
1. 解析输入媒体，理解风格特征
2. 用 AI 生成最多 3 套方案（标题 + 文案 + 真实图片/视频）
3. 将每套方案以「仅自己可见」发布到小红书
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from loguru import logger

from config import config
from model.img_processor import ImageModel
from model.video_processor import VideoModel


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class CreativePlan:
    index: int
    title: str
    content: str
    image_prompt: str = ""
    video_prompt: str = ""
    generated_images: list[str] = field(default_factory=list)   # 本地路径
    generated_video: str = ""                                   # 本地路径
    published: bool = False
    post_id: str = ""
    error: str = ""


@dataclass
class CreativeAgentResult:
    plans: list[CreativePlan]
    mode: str           # "image" | "video"
    style_analysis: str = ""
    model: str = ""
    raw_ai_response: str = ""


# ---------------------------------------------------------------------------
# Agent 主类
# ---------------------------------------------------------------------------

class CreativeAgent:
    """
    图片模式：images 非空时触发
    视频模式：video 非空时触发（优先于图片模式）
    """

    MAX_PLANS = 3

    def __init__(self) -> None:
        self.img_model = ImageModel()
        self.vid_model = VideoModel()
        self.api_key = config.DASHSCOPE_API_KEY

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    async def run(
        self,
        title: Optional[str] = None,
        content: Optional[str] = None,
        images: Optional[list[str]] = None,
        video: Optional[str] = None,
        topic: Optional[str] = None,
        publish_fn_image=None,   # async callable(title, content, images) -> post_id
        publish_fn_video=None,   # async callable(title, content, video_path) -> post_id
    ) -> CreativeAgentResult:
        """
        主流程：分析 -> 生成方案文案 -> 生成媒体 -> 发布
        publish_fn_image / publish_fn_video 由外部（service.py）注入，
        保持 agent 与发布逻辑解耦。
        """
        has_video = bool(video)
        mode = "video" if has_video else "image"

        # ── Step 1: 理解输入媒体，提取风格描述 ────────────────────────────
        style_analysis = await self._analyze_media(
            title=title or "",
            content=content or "",
            images=images or [],
            video=video or "",
            has_video=has_video,
        )
        logger.info(f"[CreativeAgent] 风格分析完成，前100字: {style_analysis[:100]}")

        # ── Step 2: 调用 LLM 生成最多 3 套文案方案 ────────────────────────
        raw_response, plans_data = await self._generate_plans_text(
            title=title or "",
            content=content or "",
            style_analysis=style_analysis,
            topic=topic or "",
            has_video=has_video,
        )
        logger.info(f"[CreativeAgent] 生成 {len(plans_data)} 套文案方案")

        # ── Step 3: 为每套方案生成真实媒体 ───────────────────────────────
        plans: list[CreativePlan] = []
        media_tasks = [
            self._generate_media_for_plan(idx, p, has_video)
            for idx, p in enumerate(plans_data)
        ]
        plan_objects = await asyncio.gather(*media_tasks, return_exceptions=True)

        for obj in plan_objects:
            if isinstance(obj, Exception):
                logger.error(f"[CreativeAgent] 媒体生成异常: {obj}")
                continue
            plans.append(obj)

        # ── Step 4: 发布每套方案 ─────────────────────────────────────────
        for plan in plans:
            await self._publish_plan(
                plan,
                has_video=has_video,
                ref_images=images or [],
                ref_video=video or "",
                publish_fn_image=publish_fn_image,
                publish_fn_video=publish_fn_video,
            )

        return CreativeAgentResult(
            plans=plans,
            mode=mode,
            style_analysis=style_analysis,
            model="qwen-vl-max / wan2.6",
            raw_ai_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Step 1: 媒体理解
    # ------------------------------------------------------------------

    async def _analyze_media(
        self,
        title: str,
        content: str,
        images: list[str],
        video: str,
        has_video: bool,
    ) -> str:
        try:
            if has_video:
                return await self.vid_model.video_understand(
                    video_source=video,
                    title=title,
                    content=content,
                )
            elif images:
                return await self.img_model.analyze_style(
                    image_sources=images,
                    title=title,
                    content=content,
                )
            else:
                # 纯文字输入，直接构造描述
                parts = []
                if title:
                    parts.append(f"标题：{title}")
                if content:
                    parts.append(f"正文：{content}")
                return "\n".join(parts) if parts else "请根据主题生成小红书爆款内容。"
        except Exception as e:
            logger.warning(f"[CreativeAgent] 媒体理解失败，使用备用描述: {e}")
            return f"标题：{title}\n正文：{content}"

    # ------------------------------------------------------------------
    # Step 2: LLM 生成文案方案
    # ------------------------------------------------------------------

    async def _generate_plans_text(
        self,
        title: str,
        content: str,
        style_analysis: str,
        topic: str,
        has_video: bool,
    ) -> tuple[str, list[dict]]:
        """
        调用 qwen-plus 生成最多3套方案，每套包含：
        title / content / image_prompt / video_prompt(可选)
        返回 (raw_response, list[dict])
        """
        ref_lines = []
        if title:
            ref_lines.append(f"【参考标题】{title}")
        if content:
            ref_lines.append(f"【参考正文】{content}")
        if topic:
            ref_lines.append(f"【创作方向】{topic}")
        ref_lines.append(f"【媒体风格分析】\n{style_analysis}")

        media_field = '"video_prompt": "视频拍摄要点（含时长/节奏/BGM风格）"' if has_video else '"image_prompt": "配图拍摄或AI生成要点（具体可执行的画面描述，中文，50字以内）"'

        system_prompt = (
            "你是一位顶级小红书内容策划专家，擅长爆款内容创作。\n"
            "根据用户提供的参考内容和媒体风格分析，生成最多3套完整的小红书发布方案。\n"
            "要求：\n"
            "- title: 标题不超过20字，含emoji，符合小红书爆款规律\n"
            "- content: 正文150字以内，含2-3个#话题标签，语言活泼接地气\n"
            f"- {media_field}\n"
            "\n请严格以如下JSON数组格式输出，不要有任何其他文字或markdown代码块标记：\n"
        )
        if has_video:
            system_prompt += '[{"title":"...","content":"...","video_prompt":"..."}]'
        else:
            system_prompt += '[{"title":"...","content":"...","image_prompt":"..."}]'

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(ref_lines)},
        ]

        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "qwen-plus",
            "messages": messages,
            "max_tokens": 2048,
        }

        raw = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(api_url, json=payload, headers=headers)
                resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            if isinstance(raw, list):
                raw = "\n".join(
                    p.get("text", "") for p in raw if isinstance(p, dict)
                )
        except Exception as e:
            logger.error(f"[CreativeAgent] LLM 调用失败: {e}")
            return raw, []

        plans: list[dict] = []
        try:
            # 去掉可能的 markdown ```json 包裹
            clean = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            m = re.search(r"\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]", clean, re.S)
            if m:
                plans = json.loads(m.group())
        except Exception as e:
            logger.warning(f"[CreativeAgent] 解析方案 JSON 失败: {e}\n原始: {raw[:300]}")

        return raw, plans[: self.MAX_PLANS]

    # ------------------------------------------------------------------
    # Step 3: 为单套方案生成媒体（可并行）
    # ------------------------------------------------------------------

    async def _generate_media_for_plan(
        self, idx: int, plan_data: dict, has_video: bool
    ) -> CreativePlan:
        plan = CreativePlan(
            index=idx + 1,
            title=str(plan_data.get("title", ""))[:20],
            content=str(plan_data.get("content", "")),
            image_prompt=str(plan_data.get("image_prompt", "")),
            video_prompt=str(plan_data.get("video_prompt", "")),
        )

        try:
            if has_video:
                prompt = plan.video_prompt or plan.title
                logger.info(f"[CreativeAgent] 方案{plan.index} 开始生成视频...")
                # 视频生成是阻塞同步调用，放入线程池避免阻塞事件循环
                loop = asyncio.get_event_loop()
                local_path = await loop.run_in_executor(
                    None, self.vid_model.wanx_text2video, prompt
                )
                plan.generated_video = local_path
                logger.info(f"[CreativeAgent] 方案{plan.index} 视频生成完毕: {local_path}")
            else:
                prompt = plan.image_prompt or plan.title
                logger.info(f"[CreativeAgent] 方案{plan.index} 开始生成图片...")
                loop = asyncio.get_event_loop()
                local_paths = await loop.run_in_executor(
                    None, self.img_model.qwen_text2image, prompt, 1
                )
                plan.generated_images = local_paths
                logger.info(f"[CreativeAgent] 方案{plan.index} 图片生成完毕: {local_paths}")
        except Exception as e:
            logger.error(f"[CreativeAgent] 方案{plan.index} 媒体生成失败: {e}")
            plan.error = f"媒体生成失败: {e}"

        return plan

    # ------------------------------------------------------------------
    # Step 4: 发布单套方案
    # ------------------------------------------------------------------

    async def _publish_plan(
        self,
        plan: CreativePlan,
        has_video: bool,
        ref_images: list[str],
        ref_video: str,
        publish_fn_image,
        publish_fn_video,
    ) -> None:
        try:
            if has_video:
                video_path = plan.generated_video or ref_video
                if not video_path or not os.path.exists(video_path):
                    plan.error = "无可用视频文件，跳过发布"
                    return
                if publish_fn_video:
                    post_id = await publish_fn_video(
                        plan.title, plan.content, video_path
                    )
                    plan.published = True
                    plan.post_id = post_id or ""
            else:
                image_paths = plan.generated_images or ref_images
                if not image_paths:
                    plan.error = "无可用图片，跳过发布"
                    return
                if publish_fn_image:
                    post_id = await publish_fn_image(
                        plan.title, plan.content, image_paths
                    )
                    plan.published = True
                    plan.post_id = post_id or ""
        except Exception as e:
            logger.error(f"[CreativeAgent] 方案{plan.index} 发布失败: {e}")
            plan.error = str(e)
