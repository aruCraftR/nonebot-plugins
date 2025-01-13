
from collections import deque
from pathlib import Path
import pickle
from itertools import chain
from typing import Any, AsyncGenerator, Iterable, Optional
from time import time, asctime

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, PrivateMessageEvent, GroupMessageEvent, Bot

from .async_ragflow import Session
from .utils import get_chat_type, get_user_name
from .config import InstanceConfig
from . import shared


#-----------------------------
#
#           聊天实例
#
#-----------------------------
VERSION = 1

upgrader_list = []

chat_instances: dict[str, 'ChatInstance'] = {}

class ChatInstance:
    data_keys = ('chat_key', 'name', 'is_group', 'session')

    def __init__(self, chat_key: str, chat_name: str, is_group: bool) -> None:
        self.name = chat_name
        self.is_group = is_group
        self.last_msg_time: int | float = 0
        self.chat_key = chat_key
        self.config = InstanceConfig(chat_key, chat_name)
        self.context = ChatContext(self)
        self.pickle_path: Path = Path('data/ragflow', 'sessions', f'{self.chat_key}.pickle')
        self.session: Session = None # type: ignore
        chat_instances[self.chat_key] = self
        self.set_next_auto_save_time(time())

    @classmethod
    async def async_init(cls, bot: Bot, event: MessageEvent, chat_key: str, is_group: bool):
        if isinstance(event, GroupMessageEvent):
            name = (await bot.get_group_info(group_id=event.group_id))['group_name']
        elif isinstance(event, PrivateMessageEvent):
            name = await get_user_name(event, bot, event.user_id) or '未知'
        return cls(chat_key, name, is_group)

    async def get_user_name(self, event: MessageEvent, bot: Bot):
        if self.is_group or self.name is None:
            return await get_user_name(event, bot, event.user_id) or '未知'
        else:
            return self.name

    def check_auto_save(self, current_timestamp: float):
        if not (self.changed and self.config.auto_save_history and current_timestamp > self.next_auto_save_time):
            return
        self.save_pickle()
        self.set_next_auto_save_time(current_timestamp)

    def set_next_auto_save_time(self, current_timestamp: float):
        self.next_auto_save_time = current_timestamp + (self.config.auto_save_interval * 60)

    def create_pickle_data(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.data_keys} | {
            'context': self.context.get_data_dict(),
            'VERSION': VERSION
        }

    def save_pickle(self, force=False):
        if not (self.context.changed or force):
            return
        with self.pickle_path.open('wb') as f:
            pickle.dump(self.create_pickle_data(), f)
        self.changed = False

    def load_pickle(self):
        if not self.pickle_path.is_file():
            return
        with self.pickle_path.open('rb') as f:
            try:
                pickle_data: dict = pickle.load(f)
            except Exception:
                shared.logger.warning(f'{self.name} ({self.chat_key}) 的历史记录加载失败')
        try:
            version: int = pickle_data.get('VERSION', 1)
            while version < VERSION:
                pickle_data = upgrader_list[version](pickle_data)
                version += 1
        except Exception as e:
            shared.logger.warning(f'{self.name} ({self.chat_key}) 的历史记录转换失败(v{version}): {repr(e)}')
        else:
            for k in self.data_keys:
                value = pickle_data.get(k)
                if value is not None:
                    setattr(self, k, value)
        self.context.load_pickle_data(pickle_data['context'])

    async def get_session(self, *, new=False):
        if new:
            await self._create_session()
            return
        if self.session is not None:
            return
        sessions = await self.config.chat_api.list_sessions(page_size=1, name=self.name)
        if sessions:
            self.session = sessions[0]
        else:
            await self._create_session()

    async def _create_session(self):
        self.session = await self.config.chat_api.create_session(self.name)

    def record_context(self, text: str, sender: str, auto_remove=True, *, token_count: Optional[int] = None):
        return self.context.add_message(text, sender, auto_remove, token_count=token_count)

    def clear_history(self):
        self.context.clear()

    @property
    def message_kwargs(self):
        return {
            'provide_username': self.config.provide_username,
            'provide_local_time': self.config.provide_local_time
        }

    @property
    def enabled(self):
        return self.is_group or self.config.reply_on_private

    def in_throttle_time(self):
        msg_time = time()
        if msg_time - self.last_msg_time < self.config.reply_throttle_time:
            return True
        self.last_msg_time = msg_time
        return False

    def load_history_from_instance(self, instance: 'ChatInstance'):
        self.context.load_history_from_instance(instance)

    async def new_ragflow(self):
        await self.config.chat_api.delete_sessions([self.session.id])
        await self.get_session(new=True)

    async def ask_ragflow(self, text: str, sender: str) -> AsyncGenerator[str]:
        if self.config.record_context and self.context.data:
            text = f'以下是上下文\n{self.context.get_merged_context()}\n以上是上下文\n'
        message = ContextMessage(text, sender, token_count=0, **self.message_kwargs)
        async for i in self.session.ask(message.content):
            yield i.content
        self.context.clear()


#-----------------------------
#
#           历史记录
#
#-----------------------------


class ChatContext:
    def __init__(self, instance: ChatInstance):
        self.instance = instance
        self.data: HistoryData = HistoryData(self.instance.config.record_context_token_limit)
        self.changed = False

    def load_history_from_instance(self, instance: 'ChatInstance'):
        if self.instance.is_group:
            self.data.load(instance.context.data)

    def get_data_dict(self) -> dict[str, Any]:
        return self.data.get_data_dict()

    def load_pickle_data(self, data: dict[str, Any]):
        self.data.load_pickel_data(data)

    def clear(self):
        self.data.clear_context()

    def add_message(self, text: str, sender: str, auto_remove=True, *, token_count: Optional[int] = None):
        self.changed = True
        if self.data.is_last_text(text):
            self.data.update_timestamp(-1)
        else:
            self.data.add_message(
                ContextMessage(text, sender, token_count=token_count, **self.instance.message_kwargs),
                text=text, check_limit=auto_remove
            )

    def get_merged_context(self) -> str:
        return self.data.get_merged_context()


class HistoryData:
    data_keys = ('deque', 'total_tokens', 'last_text')

    def __init__(self, max_token_count: int, *, copy_from: Optional['HistoryData' | Iterable['HistoryData']] = None, _pickle_data: Optional[dict[str, Any]] = None) -> None:
        self.deque: deque[ContextMessage]
        self.total_tokens: int
        self.last_text: Optional[str]
        self.max_token_count = max_token_count
        self._last_message = None
        if copy_from is None:
            if _pickle_data is None:
                self.last_text = None
                self.total_tokens = 0
                self.deque = deque()
            else:
                self.load_pickel_data(_pickle_data)
        else:
            self.load(copy_from)

    def __len__(self) -> int:
        return self.deque.__len__()

    @property
    def last_message(self) -> Optional['ContextMessage']:
        if self._last_message is None and self.deque:
            self._last_message = self.deque[-1]
        return self._last_message

    def load(self, source: 'HistoryData' | Iterable['HistoryData']):
        self._last_message = None
        if isinstance(source, HistoryData):
            self.deque = source.deque.copy()
            self.last_text = source.last_text
            self.total_tokens = source.total_tokens
            self.check_limit()
        elif isinstance(source, Iterable):
            self.deque = deque(sorted(chain(*(i.deque for i in source)), key=lambda x: x.timestamp))
            self.total_tokens = sum(i.total_tokens for i in source)
            self.last_text = None

    def copy(self) -> 'HistoryData':
        return self.__class__(max_token_count=self.max_token_count, copy_from=self)

    def load_pickel_data(self, data: dict[str, Any]):
        for k, v in data.items():
            setattr(self, k ,v)

    def get_data_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.data_keys}

    def is_last_text(self, text: str) -> bool:
        return text == self.last_text

    def update_timestamp(self, index: int, timestamp: Optional[float] = None):
        self.deque[index].timestamp = time() if timestamp is None else timestamp

    def add_message(self, message: 'ContextMessage', *, text: Optional[str] = None, check_limit=True):
        self.total_tokens += message.token_count
        self.deque.append(message)
        self.last_text = message.content if text is None else text
        self._last_message = message
        if check_limit:
            self.check_limit()

    def check_limit(self):
        while self.deque and self.total_tokens > self.max_token_count:
            self.total_tokens -= self.deque.popleft().token_count

    def get_merged_context(self) -> str:
        return '\n'.join(i.content for i in self.deque)

    def clear_context(self):
        self.deque.clear()
        self.last_text = None
        self.total_tokens = 0


class ContextMessage:
    name: Optional[str]
    content: str
    token_count: int

    def __init__(self, content: str, name: Optional[str] = None, *, token_count: int | None = None, provide_username=False, provide_local_time=False) -> None:
        self.timestamp = time()
        self.content = content
        self.name = name
        self.token_count = count_token(content) if token_count is None else token_count
        extra_token = 0
        if provide_username:
                extra_token += count_token(self.add_username())
        if provide_local_time:
                extra_token += count_token(self.add_local_time())
        if token_count is not None:
            self.token_count = token_count + extra_token
        else:
            self.recount_token()

    def recount_token(self):
        self.token_count = count_token(self.content)

    def add_username(self):
        extra = f'{self.name}说 '
        self.content = f'{extra}{self.content}'
        return extra

    def add_local_time(self):
        extra = f'[当前时间: {asctime()}] '
        self.content = f'{extra}{self.content}'
        return extra


def count_token(text: str):
    return len(shared.tiktoken.encode(text))


#-----------------------------
#
#           外部方法
#
#-----------------------------


async def get_chat_instance(matcher: type[Matcher], event: MessageEvent, bot: Bot) -> ChatInstance:
    chat_key, is_group = await get_chat_type(event)
    if chat_key in chat_instances:
        return chat_instances[chat_key]
    if is_group is None:
        await matcher.finish('未知的消息来源')
    return await ChatInstance.async_init(bot, event, chat_key, is_group)


def get_chat_instance_directly(chat_key) -> Optional[ChatInstance]:
    return chat_instances.get(chat_key)


def get_chat_instances():
    return chat_instances.values()
