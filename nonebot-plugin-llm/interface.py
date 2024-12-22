
from time import time, asctime
from traceback import print_exc
from typing import Any, Literal, Optional, TYPE_CHECKING

from openai.types.chat.chat_completion import ChatCompletion
from openai import OpenAIError

from . import shared
from .image import QQImage

if TYPE_CHECKING:
    from .chat import ChatInstance


class BaseMessage:
    role = Literal['system', 'user', 'assistant']
    _name: Optional[str]
    _content: str
    token_count: int

    def __init__(self, content: str, name: Optional[str] = None, *, token_count: Optional[int] = None) -> None:
        self.timestamp = time()
        self._message = None
        self._content = content
        self._name = name
        self.token_count = count_token(content) if token_count is None else token_count

    def recount_token(self):
        self.token_count = count_token(self._content)

    @property
    def name(self) -> Optional[str]:
        return self._name

    @name.setter
    def name(self, v: str):
        self._message  = None
        self._name = v

    @property
    async def content(self) -> str | list[dict[str, str]]:
        return self._content

    @content.setter
    def content(self, v: str):
        self._message = None
        self._content = v

    async def to_message(self) -> dict[str, Any]:
        if self._message is None:
            self._message = await self._to_message()
        return self._message

    async def _to_message(self) -> dict[str, Any]:
        return {
            'role': self.role,
            'content': await self.content
        } if self._name is None else {
            'role': self.role,
            'name': self._name,
            'content': await self.content
        } # type: ignore

    def add_username(self):
        extra = f'{self._name}说 '
        self.content = f'{extra}{self._content}'
        return extra

    def add_local_time(self):
        extra = f'[当前时间: {asctime()}] '
        self.content = f'{extra}{self._content}'
        return extra


class SystemMessage(BaseMessage):
    role = 'system'


class UserMessage(BaseMessage):
    role = 'user'

    def __init__(self, content: str, name: Optional[str], *, token_count: int | None = None, provide_username=False, provide_local_time=False) -> None:
        super().__init__(content, name, token_count=0)
        extra_token = 0
        if provide_username:
                extra_token += count_token(self.add_username())
        if provide_local_time:
                extra_token += count_token(self.add_local_time())
        if token_count is not None:
            self.token_count = token_count + extra_token
        else:
            self.recount_token()


class ModelMessage(BaseMessage):
    role = 'assistant'

    def __init__(self, content: str, name: Optional[str] = None, *, token_count: int | None = None, provide_local_time=False) -> None:
        super().__init__(content, name, token_count=0)
        if token_count is not None:
            extra_token = 0
            if provide_local_time:
                extra_token += count_token(self.add_local_time())
            self.token_count = token_count + extra_token
        else:
            if provide_local_time: self.add_local_time()
            self.recount_token()


class UserImageMessage(UserMessage):
    def __init__(self, image_urls: list[str], text_content: str) -> None:
        super().__init__(text_content, None)
        self.image_urls = image_urls
        self.images = [QQImage(i) for i in image_urls]

    @property
    async def content(self) -> list[dict[str, Any]]:
        return [
            {"type": "text", "text": self._content},
            *[
                {"type": "image_url", "image_url": {"url": await i.get_base64()}}
                for i in self.images
            ],
        ]

    def recount_token(self):
        """UserImageMessage暂时仅用作过渡消息, 无需计算token占用量"""
        return


def count_token(text: str):
    return len(shared.tiktoken.encode(text))


async def request_chat_completion(chat_instance: 'ChatInstance', extra_messages: Optional[list[BaseMessage]] = None, *, use_vision_model=False, use_system_message=True, use_history=True) -> tuple[str, int, bool]:
    try:
        res: ChatCompletion = await chat_instance.config.async_open_ai.chat.completions.create(
            model=chat_instance.config.vision_model_identifier if use_vision_model else chat_instance.config.text_model_identifier,
            messages=await chat_instance.get_chat_messages(extra_messages, use_system_message=use_system_message, use_history=use_history), # type: ignore
            **chat_instance.config.chat_completion_kwargs
        )
        content = res.choices[0].message.content.strip()
        if content.startswith('['):
            content = content.split(']', 1)[-1]
        return content.strip(), res.usage.completion_tokens, True
    except OpenAIError as e:
        return f"请求API时发生错误: {repr(e)[:100]}", 0, False
    except Exception as e:
        print_exc(10)
        return f"内部错误: {repr(e)}", 0, False
