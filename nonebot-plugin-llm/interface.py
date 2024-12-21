
from time import time, asctime
from typing import Any, Literal, Optional, TYPE_CHECKING

from openai.types.chat.chat_completion import ChatCompletion

from . import shared

if TYPE_CHECKING:
    from .chat import ChatInstance


class BaseMessage:
    data_keys = ('role', 'name', 'content', 'token_count')
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
    def content(self) -> str:
        return self._content

    @content.setter
    def content(self, v: str):
        self._message = None
        self._content = v

    @property
    def message(self) -> dict[str, Any]:
        return self.to_message()

    def to_message(self) -> dict[str, str]:
        if self._message is None:
            self._message = self._to_message()
        return self._message

    def _to_message(self) -> dict[str, str]:
        return {
            'role': self.role,
            'content': self._content
        } if self._name is None else {
            'role': self.role,
            'name': self._name,
            'content': self._content
        } # type: ignore

    def to_dict(self) -> dict[str, Any]:
        return {i: getattr(self, i) for i in self.data_keys}

    def add_username(self):
        extra = f'{self._name}说 '
        self.content = f'{extra}{self._content}'
        return extra

    def add_local_time(self):
        extra = f'[时间: {asctime()}] '
        self.content = f'{extra}{self._content}'
        return extra


class SystemMessage(BaseMessage):
    role = 'system'


class UserMessage(BaseMessage):
    role = 'user'

    def __init__(self, content: str, name: str, *, provide_username=False, provide_local_time=False) -> None:
        super().__init__(content, name, token_count=0)
        if provide_username: self.add_username()
        if provide_local_time: self.add_local_time()
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


def count_token(text: str):
    return len(shared.tiktoken.encode(text))


async def request_chat_completion(chat_instance: 'ChatInstance', _override: Optional[list[BaseMessage]] = None) -> tuple[str, int, bool]:
    try:
        res: ChatCompletion = await chat_instance.config.async_open_ai.chat.completions.create(
            model=chat_instance.config.model_identifier,
            messages=chat_instance.get_chat_messages(_override), # type: ignore
            temperature=chat_instance.config.chat_temperature,
            # max_tokens=self.config['max_tokens'],
            top_p=chat_instance.config.chat_top_p,
            frequency_penalty=chat_instance.config.chat_frequency_penalty,
            presence_penalty=chat_instance.config.chat_presence_penalty,
            timeout=chat_instance.config.api_timeout,
        )
        content = res.choices[0].message.content.strip()
        if content.startswith('['):
            content = content.split(']', 1)[-1]
        return content.strip(), res.usage.completion_tokens, True
    except Exception as e:
        return f"请求API时发生错误: {repr(e)}", 0, False
