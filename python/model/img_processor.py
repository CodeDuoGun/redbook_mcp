from __future__ import annotations

import base64
import datetime
import mimetypes
import os

import httpx
from dashscope import MultiModalConversation
from dashscope.aigc.image_generation import ImageGeneration
from loguru import logger

from config import config
from utils import download_img


class ImageModel:
    def __init__(self) -> None:
        self.api_key = config.DASHSCOPE_API_KEY
        self.base_url = config.BASE_SDK_API_URL

    # ------------------------------------------------------------------
    # 图片理解：返回详细的风格描述文字
    # ------------------------------------------------------------------
    async def img_understand(self, messages: list) -> str:
        """调用 qwen-vl-max 理解图片，返回文本描述。messages 为标准 OpenAI 格式。"""
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "qwen-vl-max",
            "messages": messages,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = "\n".join(
                part.get("text", "") for part in raw if isinstance(part, dict)
            )
        return raw

    async def analyze_style(
        self,
        image_sources: list[str],
        title: str = "",
        content: str = "",
    ) -> str:
        """
        分析图片集合的视觉风格，返回一段结构化风格描述文字，供后续图片生成使用。
        image_sources: URL 列表 或 本地文件路径列表
        """
        img_parts: list[dict] = []
        for src in image_sources[:4]:
            try:
                if src.startswith("http://") or src.startswith("https://"):
                    img_parts.append({"type": "image_url", "image_url": {"url": src}})
                elif os.path.exists(src):
                    mime, _ = mimetypes.guess_type(src)
                    mime = mime or "image/jpeg"
                    with open(src, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    img_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
            except Exception as e:
                logger.warning(f"跳过图片 {src}: {e}")

        ref_text = ""
        if title:
            ref_text += f"标题：{title}\n"
        if content:
            ref_text += f"正文：{content}\n"

        system_msg = (
            "你是一位专业视觉设计师。请分析以下图片的视觉风格，"
            "按照以下结构输出一段详细的风格描述（直接输出，不要JSON）：\n"
            "主体（主体描述）| 场景（场景描述）| 风格（定义风格）| 镜头语言 | 氛围词 | 细节修饰"
        )
        user_content: list[dict] = []
        if ref_text:
            user_content.append({"type": "text", "text": ref_text})
        user_content.extend(img_parts)
        if not img_parts:
            user_content.append({"type": "text", "text": "请根据文字信息分析风格。"})

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]
        return await self.img_understand(messages)

    # ------------------------------------------------------------------
    # 文生图：使用 qwen-image-2.0-pro，返回本地路径列表
    # ------------------------------------------------------------------
    def qwen_text2image(self, prompt: str, n: int = 1) -> list[str]:
        """根据 prompt 生成图片，返回本地文件路径列表。"""
        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ]
        response = MultiModalConversation.call(
            api_key=self.api_key,
            model="qwen-image-2.0-pro",
            messages=messages,
            result_format="message",
            stream=False,
            watermark=False,
            prompt_extend=True,
            negative_prompt=(
                "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，"
                "人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"
            ),
            size="2048*2048",
            n=n,
        )
        if response.status_code != 200:
            logger.error(
                f"qwen_text2image 失败: {response.status_code} {response.code} {response.message}"
            )
            return []

        choices = response.get("output", {}).get("choices", [])
        imgs: list[dict] = []
        for msg in choices:
            imgs.extend(msg["message"]["content"])

        now = datetime.datetime.now().strftime("%Y%m%d")
        urls = [item["image"] for item in imgs if "image" in item]
        return download_img(urls, output_dir=f"output/image/{now}/")

    # ------------------------------------------------------------------
    # 文生图：使用 wan2.6-t2i，返回本地路径列表
    # ------------------------------------------------------------------
    def wanx_text2image(self, prompt: str, n: int = 1) -> list[str]:
        """根据 prompt 用万象模型生成图片，返回本地文件路径列表。"""
        from dashscope.api_entities.dashscope_response import Message

        message = Message(
            role="user",
            content=[{"text": prompt}],
        )
        rsp = ImageGeneration.call(
            model="wan2.6-t2i",
            api_key=self.api_key,
            messages=[message],
            negative_prompt=(
                "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，"
                "人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"
            ),
            prompt_extend=True,
            watermark=False,
            n=n,
            size="1280*1280",
        )
        if rsp.status_code != 200:
            logger.error(f"wanx_text2image 失败: {rsp.status_code} {rsp.code} {rsp.message}")
            return []

        choices = rsp.get("output", {}).get("choices", [])
        imgs: list[dict] = []
        for msg in choices:
            imgs.extend(msg["message"]["content"])

        now = datetime.datetime.now().strftime("%Y%m%d")
        urls = [item["image"] for item in imgs if "image" in item]
        return download_img(urls, output_dir=f"output/image/{now}/")
