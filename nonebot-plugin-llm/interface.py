
from time import time, asctime
from traceback import print_exc
from typing import Any, Literal, Optional, TYPE_CHECKING, Self

from openai.types.chat.chat_completion import ChatCompletion
from openai import OpenAIError

from . import shared
from .image import QQImage
from .exception import RequestIncompleteError

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


class ChatCompletionRequest:
    def __init__(self, chat_instance: 'ChatInstance', *, use_vision_model=False) -> None:
        self.instance = chat_instance
        self.use_vision_model = use_vision_model
        self._success: Optional[bool] = None
        self._response: Optional[ChatCompletion] = None
        self._content: Optional[str] = None
        self._raw_content: Optional[str] = None

    @property
    def success(self) -> bool:
        if self._success is None:
            raise RequestIncompleteError('Request incomplete')
        return self._success

    @property
    def response(self) -> ChatCompletion:
        if self._response is None:
            raise RequestIncompleteError('Request incomplete')
        return self._response

    @property
    def content(self) -> str:
        if self._content is None:
            raise RequestIncompleteError('Request incomplete')
        return self._content

    @content.setter
    def content(self, v: str):
        self._content = v

    @property
    def raw_content(self) -> str:
        if self._raw_content is None:
            raise RequestIncompleteError('Request incomplete')
        return self._raw_content

    @property
    def completion_tokens(self) -> int:
        return self.response.usage.completion_tokens

    @property
    def prompt_tokens(self) -> int:
        return self.response.usage.prompt_tokens


    async def request(self, extra_messages: Optional[list[BaseMessage]] = None, *, use_system_message=True, use_history=True, extra_kwargs: Optional[dict[str, Any]] = None) -> Self:
        if extra_kwargs is None:
            extra_kwargs = {}
        try:
            self._response = await self.instance.config.async_open_ai.chat.completions.create(
                model=self.instance.config.vision_model_identifier if self.use_vision_model else self.instance.config.text_model_identifier,
                messages=await self.instance.get_chat_messages(extra_messages, use_system_message=use_system_message, use_history=use_history), # type: ignore
                **self.instance.config.chat_completion_kwargs,
                **extra_kwargs
            )
        except OpenAIError as e:
            self._content = self._raw_content = f"请求API时发生错误: {repr(e)[:100]}"
            shared.logger.warning(self._content)
        except Exception as e:
            print_exc(10)
            self._content = self._raw_content = f"内部错误: {repr(e)}"
        else:
            self._raw_content = content = self._response.choices[0].message.content.strip()
            if content.startswith('['):
                content = content.split(']', 1)[-1]
            self._content = content
        return self
