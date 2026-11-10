# 第一个请求，注意环境变量.env的使用

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # 自动加载 .env 到环境变量

client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=os.environ["DASHSCOPE_BASE_URL"])
resp = client.chat.completions.create(
    model=os.environ.get("DASHSCOPE_MODEL", "deepseek-chat"),
    messages=[{"role": "user", "content": "用一句话解释 RAG"}],
    temperature=0.3,
)
print('resp.choices[0].message.content',resp.choices[0].message.content)
print('resp.usage',resp.usage)          # prompt_tokens / completion_tokens / total_tokens
print('resp.model, resp.id',resp.model, resp.id) # 线上排障要记录的字段
