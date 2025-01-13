
from collections import deque
from pathlib import Path
import pickle
from itertools import chain
from typing import Any, Iterable, Optional
from time import time

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, PrivateMessageEvent, GroupMessageEvent, Bot

from .interface import BaseMessage, UserMessage, ModelMessage
from .utils import get_chat_type, get_user_name
from .config import InstanceConfig
from . import shared


#-----------------------------
#
#           聊天实例
#
#-----------------------------

chat_instances: dict[str, 'ChatInstance'] = {}

class ChatInstance:
    def __init__(self, chat_key: str, chat_name: str, is_group: bool) -> None:
        self.name = chat_name
        self.is_group = is_group
        self.last_msg_time: int | float = 0
        self.chat_key = chat_key
        self.config = InstanceConfig(chat_key, chat_name)
        self.history = ChatHistory(self)
        chat_instances[self.chat_key] = self

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

    def record_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True, *, token_count: Optional[int] = None) -> ModelMessage | UserMessage:
        return self.history.add_chat_history(text, sender, auto_remove, token_count=token_count)

    def record_other_history(self, text: str, sender: str, auto_remove=True, *, token_count: Optional[int] = None) -> UserMessage:
        return self.history.add_other_history(text, sender, auto_remove, token_count=token_count)

    def clear_history(self):
        self.history = ChatHistory(self, False)

    @property
    def enabled(self):
        return self.is_group or self.config.reply_on_private

    @property
    def total_token_limit(self) -> int:
        return self.config.record_chat_context_token_limit + self.config.record_other_context_token_limit

    @property
    def other_context_token_limit(self) -> int:
        return self.config.record_other_context_token_limit if self.is_group else 0

    @property
    def chat_context_token_limit(self) -> int:
        return self.config.record_chat_context_token_limit if self.is_group else self.total_token_limit

    def in_throttle_time(self):
        msg_time = time()
        if msg_time - self.last_msg_time < self.config.reply_throttle_time:
            return True
        self.last_msg_time = msg_time
        return False

    def load_history_from_instance(self, instance: 'ChatInstance'):
        self.history.load_history_from_instance(instance)


#-----------------------------
#
#           历史记录
#
#-----------------------------
VERSION = 2

def history_data_0_to_1(data: dict) -> dict:
    old_chat_history: deque[tuple[float, dict, int]] = data['chat_history']
    old_other_history: deque[tuple[float, dict, int]] = data['other_history']
    new_chat_history = deque()
    new_other_history = deque()
    for timestamp, message_dict, token_count in old_chat_history:
        match message_dict['role']:
            case 'user':
                msg = UserMessage(message_dict['content'], message_dict['name'])
                msg.timestamp = timestamp
                new_chat_history.append(msg)
            case 'assistant':
                msg = ModelMessage(message_dict['content'], token_count=token_count)
                msg.timestamp = timestamp
                new_chat_history.append(msg)
    for timestamp, message_dict, token_count in old_other_history:
        msg = UserMessage(message_dict['content'], message_dict['name'])
        msg.timestamp = timestamp
        new_other_history.append(msg)
    data['chat_history'] = new_chat_history
    data['other_history'] = new_other_history
    return data

def history_data_1_to_2(data: dict) -> dict:
    return {
        'chat_history': {
            'deque': data['chat_history'],
            'total_tokens': data['chat_history_token_count'],
            'last_text': data['last_chat_text']
        },
        'other_history': {
            'deque': data['other_history'],
            'total_tokens': data['other_history_token_count'],
            'last_text': data['last_other_text']
        }
    }

upgrader_list = [
    history_data_0_to_1, history_data_1_to_2
]


class ChatHistory:
    history_keys = ('chat_history', 'other_history')
    def __init__(self, instance: ChatInstance, load_pickle=True):
        self.instance = instance
        self.other_history: HistoryData = HistoryData(self.instance.other_context_token_limit)
        self.chat_history: HistoryData = HistoryData(self.instance.chat_context_token_limit)
        self.pickle_path: Path = Path('data/llm', self.instance.chat_key, 'history.pickle')
        self.changed = False
        self.set_next_auto_save_time(time())
        if load_pickle:
            self.load_pickle()

    def load_history_from_instance(self, instance: 'ChatInstance'):
        if self.instance.is_group:
            self.other_history.load(instance.history.other_history)
            self.chat_history.load(instance.history.chat_history)
        else:
            self.chat_history.load((instance.history.other_history, instance.history.chat_history))

    def get_data_dict(self):
        return {k: getattr(self, k).get_data_dict() for k in self.history_keys}

    def set_next_auto_save_time(self, current_timestamp: float):
        self.next_auto_save_time = current_timestamp + (self.instance.config.auto_save_interval * 60)

    def check_auto_save(self, current_timestamp: float):
        if not (self.changed and self.instance.config.auto_save_history and current_timestamp > self.next_auto_save_time):
            return
        self.save_pickle()
        self.set_next_auto_save_time(current_timestamp)

    def save_pickle(self, force=False):
        if not (self.changed or force):
            return
        with self.pickle_path.open('wb') as f:
            data = self.get_data_dict()
            data['VERSION'] = VERSION
            pickle.dump(data, f)
        self.changed = False

    def load_pickle(self):
        if not self.pickle_path.is_file():
            return
        with self.pickle_path.open('rb') as f:
            try:
                pickle_data: dict = pickle.load(f)
            except Exception:
                shared.logger.warning(f'{self.instance.chat_key} 的历史记录加载失败')
        try:
            version: int = pickle_data.get('VERSION', 0)
            while version < VERSION:
                pickle_data = upgrader_list[version](pickle_data)
                version += 1
        except Exception as e:
            shared.logger.warning(f'{self.instance.chat_key} 的历史记录转换失败(v{version}): {repr(e)}')
        else:
            for k in self.history_keys:
                value = pickle_data.get(k)
                if value is not None:
                    data: HistoryData = getattr(self, k)
                    data.load_pickel_data(value)

    def add_other_history(self, text: str, sender: str, auto_remove=True, *, token_count: Optional[int] = None) -> UserMessage:
        self.changed = True
        if self.other_history.is_last_text(text):
            self.other_history.update_timestamp(-1)
        else:
            self.other_history.add_message(
                UserMessage(
                    text, sender, token_count=token_count,
                    provide_username=self.instance.config.provide_username,
                    provide_local_time=self.instance.config.provide_local_time
                ),
                text=text, check_limit=auto_remove
            )
        return self.other_history.last_message # type: ignore

    def add_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True, *, token_count: Optional[int] = None) -> ModelMessage | UserMessage:
        self.changed = True
        if self.chat_history.is_last_text(text):
            self.chat_history.update_timestamp(-1)
        else:
            self.last_chat_text = text
            if sender is None:
                message = ModelMessage(
                    text, token_count=token_count,
                    provide_local_time=self.instance.config.provide_local_time
                )
            else:
                message = UserMessage(
                    text, sender, token_count=token_count,
                    provide_username=self.instance.config.provide_username,
                    provide_local_time=self.instance.config.provide_local_time
                )
            self.chat_history.add_message(message, text=text, check_limit=auto_remove)
        return self.chat_history.last_message # type: ignore


class HistoryData:
    data_keys = ('deque', 'total_tokens', 'last_text')

    def __init__(self, max_token_count: int, *, copy_from: Optional['HistoryData' | Iterable['HistoryData']] = None, _pickle_data: Optional[dict[str, Any]] = None) -> None:
        self.deque: deque[BaseMessage]
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
    def last_message(self) -> Optional[BaseMessage]:
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

    def add_message(self, message: UserMessage | ModelMessage, *, text: Optional[str] = None, check_limit=True):
        self.total_tokens += message.token_count
        self.deque.append(message)
        self.last_text = message._content if text is None else text
        self._last_message = message
        if check_limit:
            self.check_limit()

    def check_limit(self):
        while self.deque and self.total_tokens > self.max_token_count:
            self.total_tokens -= self.deque.popleft().token_count


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
