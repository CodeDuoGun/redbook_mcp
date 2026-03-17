from contextlib import ExitStack
import requests
from urllib.parse import urlparse
import os

def download_img(imgs:list, output_dir):
    """遍历地址落盘文件"""    
    os.makedirs(output_dir,exist_ok=True)
    res_paths = []
    for url in imgs:
        filename = os.path.basename(urlparse(url).path)
        out_path = os.path.join(output_dir, filename)
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        res_paths.append(out_path)
    return res_paths

def download_video(video_url: str, output_dir: str) -> str:
    """下载视频到 output_dir，返回本地绝对路径。"""
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(urlparse(video_url).path) or "video.mp4"
    out_path = os.path.join(output_dir, filename)
    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return os.path.abspath(out_path)



def get_best_video_url(note) -> str:
    """从 note 数据中获取最优视频播放地址"""
    stream = note.video.media.stream

    # 优先级：h265 > h264 > av1 > h266
    for codec in ["h265", "h264", "av1", "h266"]:
        streams = stream.get(codec, [])
        if not streams:
            continue
        # 按 resolution（或 weight）降序排，取画质最高的
        best = max(streams, key=lambda x: (x.get("resolution", 0), x.get("weight", 0)))
        url = best.get("masterUrl") or (best.get("backupUrls") or [None])[0]
        if url:
            return url

    return ""

