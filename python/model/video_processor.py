from __future__ import annotations

import base64
import datetime
import mimetypes
import os
from http import HTTPStatus

import httpx
from dashscope import VideoSynthesis
from loguru import logger

from config import config
from utils import download_video


class VideoModel:
    def __init__(self) -> None:
        self.api_key = config.DASHSCOPE_API_KEY
        self.base_url = config.BASE_SDK_API_URL

    # ------------------------------------------------------------------
    # 视频理解：用 qwen-vl-max 分析视频帧/URL，返回内容+风格描述
    # ------------------------------------------------------------------
    async def video_understand(
        self,
        video_source: str,
        title: str = "",
        content: str = "",
    ) -> str:
        """
        理解视频内容与风格。
        video_source: 视频 URL 或本地文件路径（本地文件转 base64）。
        返回结构化文字描述：内容摘要 | 风格 | 镜头语言 | 节奏感 | 氛围词
        """
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        user_content: list[dict] = []

        ref_text = ""
        if title:
            ref_text += f"标题：{title}\n"
        if content:
            ref_text += f"正文：{content}\n"
        if ref_text:
            user_content.append({"type": "text", "text": ref_text})

        # 构造视频输入
        try:
            if video_source.startswith("http://") or video_source.startswith("https://"):
                user_content.append({
                    "type": "video_url",
                    "video_url": {"url": video_source},
                })
            elif os.path.exists(video_source):
                mime, _ = mimetypes.guess_type(video_source)
                mime = mime or "video/mp4"
                with open(video_source, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                user_content.append({
                    "type": "video_url",
                    "video_url": {"url": f"data:{mime};base64,{b64}"},
                })
        except Exception as e:
            logger.warning(f"视频读取失败，仅使用文字描述: {e}")
            user_content.append({"type": "text", "text": f"视频路径：{video_source}"})

        system_msg = (
            "你是一位专业的视频导演和内容策划。请分析这段视频的内容与风格，"
            "按以下结构输出详细描述（直接输出，不要JSON）：\n"
            "内容摘要 | 视觉风格 | 镜头语言 | 节奏感 | BGM风格建议 | 氛围词 | 核心亮点"
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]

        payload = {
            "model": "qwen-vl-max",
            "messages": messages,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = "\n".join(
                part.get("text", "") for part in raw if isinstance(part, dict)
            )
        return raw

    # ------------------------------------------------------------------
    # 文生视频：使用 wan2.6-t2v，返回本地文件路径
    # ------------------------------------------------------------------
    def wanx_text2video(
        self,
        prompt: str,
        audio_url: str | None = None,
        size: str = "1280*720",
        duration: int = 10,
    ) -> str:
        """
        根据 prompt 生成视频，同步等待完成，返回本地文件路径。
        失败时返回空字符串。
        """
        if not prompt:
            logger.error("video prompt 不能为空")
            return ""

        logger.info(f"开始生成视频，prompt 前50字: {prompt[:50]}...")

        kwargs: dict = dict(
            api_key=self.api_key,
            model="wan2.6-t2v",
            prompt=prompt,
            size=size,
            duration=duration,
            negative_prompt="",
            prompt_extend=True,
            watermark=False,
            seed=42,
        )
        if audio_url:
            kwargs["audio_url"] = audio_url

        rsp = VideoSynthesis.async_call(**kwargs)
        if rsp.status_code != HTTPStatus.OK:
            logger.error(
                f"视频任务提交失败: {rsp.status_code} {rsp.code} {rsp.message}"
            )
            return ""

        logger.info(f"视频任务已提交，task_id: {rsp.output.task_id}，等待生成...")

        # 等待任务完成（阻塞，视频生成通常需要 1-3 分钟）
        rsp = VideoSynthesis.wait(task=rsp, api_key=self.api_key)
        if rsp.status_code != HTTPStatus.OK:
            logger.error(
                f"视频生成失败: {rsp.status_code} {rsp.code} {rsp.message}"
            )
            return ""

        video_url = rsp.output.video_url
        logger.info(f"视频生成成功，下载地址: {video_url}")

        now = datetime.datetime.now().strftime("%Y%m%d")
        out_dir = f"output/video/{now}/"
        local_path = download_video(video_url, out_dir)
        logger.info(f"视频已下载至: {local_path}")
        return local_path or ""
