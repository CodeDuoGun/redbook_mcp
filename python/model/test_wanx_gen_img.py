import os
import dashscope
from dashscope.aigc.image_generation import ImageGeneration
from dashscope.api_entities.dashscope_response import Message
from utils import download_img
# 以下为北京地域url，各地域的base_url不同
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

# 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
# 各地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
def gen_img():
    api_key = os.getenv("DASHSCOPE_API_KEY")

    message = Message(
        role="user",
        content=[
            {
                'text': '一间有着精致窗户的花店，漂亮的木质门，摆放着花朵. 同时返回如下结构的构图理念：主体（主体描述）+ 场景（场景描述）+ 风格（定义风格）+ 镜头语言 + 氛围词 + 细节修饰'
            }
        ]
    )
    print("----sync call, please wait a moment----")
    rsp = ImageGeneration.call(
        model="wan2.6-t2i",
        api_key=api_key,
        messages=[message],
        negative_prompt="低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。",
        prompt_extend=True,
        watermark=False,
        n=1,
        size="1280*1280"
    )
    print(rsp)

    choices = rsp.get("output", {}).get("choices", [])
    if choices:
        for msg in choices:
            imgs = msg["message"]["content"]
            
    import datetime
    now = datetime.datetime.now().strftime("%Y%m%d")
    urls = [url["image"] for url in imgs]
    download_img(list(urls), output_dir=f"output/{now}")

if __name__ == "__main__":
    gen_img()