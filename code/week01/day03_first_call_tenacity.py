# 第一个请求，注意环境变量.env的使用

from openai import OpenAI, APITimeoutError, APIConnectionError
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

import os

load_dotenv()  # 自动加载 .env 到环境变量

@retry(
    stop=stop_after_attempt(3),                    # 最多 3 次（替代 range(3)）
    wait=wait_exponential_jitter(multiplier=1, max=8),  # 指数退避+抖动（替代手动计算 delay）
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError)),  # 重试条件
    reraise=True                                   # 最终失败时抛出原始异常
)
def call_llm():
    client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=os.environ["DASHSCOPE_BASE_URL"])
    return client.chat.completions.create(
    model=os.environ.get("DASHSCOPE_MODEL", "deepseek-chat"),
    messages=[{"role": "user", "content": "用一句话解释 RAG"}],
    temperature=0.3,
    )  


resp = call_llm()

print('resp.choices[0].message.content',resp.choices[0].message.content)
print('resp.usage',resp.usage)          # prompt_tokens / completion_tokens / total_tokens
print('resp.model, resp.id',resp.model, resp.id) # 线上排障要记录的字段
