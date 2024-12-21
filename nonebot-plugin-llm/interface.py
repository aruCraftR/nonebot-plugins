
from typing import Optional
import openai

from .chat import ChatInstance


async def request_chat_completion(chat_instance: ChatInstance, _override: Optional[list[dict[str, str]]] = None) -> tuple[str, bool]:
    """对话文本生成"""
    openai.api_base = chat_instance.config.openai_api_v1
    openai.api_key = 'none'
    try:
        response = openai.ChatCompletion.create(
            model=chat_instance.config.model_identifier,
            messages=chat_instance.get_chat_messages(_override),
            temperature=chat_instance.config.chat_temperature,
            # max_tokens=self.config['max_tokens'],
            top_p=chat_instance.config.chat_top_p,
            frequency_penalty=chat_instance.config.chat_frequency_penalty,
            presence_penalty=chat_instance.config.chat_presence_penalty,
            timeout=chat_instance.config.api_timeout,
        )
        res: str = response['choices'][0]['message']['content'].strip() # type: ignore
        if res.startswith('['):
            res = res.split(']', 1)[-1]
        return res.strip(), True
    except Exception as e:
        return f"请求API时发生错误: {repr(e)}", False


