import os
from config import config


class TextModel():
    def __init__(self) -> None:
        self.api_key = config.DASHSCOPE_API_KEY
        self.base_url = config.BASE_URL

    
        
