
from collections import deque
from pathlib import Path
import pickle
from itertools import chain
from typing import Optional
from time import asctime, time

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
    def __init__(self, chat_key: str, is_group: bool) -> None:
        self.name = None
        self.is_group = is_group
        self.last_msg_time: int | float = 0
        self.chat_key = chat_key
        self.config = InstanceConfig(chat_key)
        self.history = ChatHistory(self)
        chat_instances[self.chat_key] = self

    @classmethod
    async def async_init(cls, bot: Bot, event: MessageEvent, chat_key: str, is_group: bool):
        self = cls(chat_key, is_group)
        if isinstance(event, GroupMessageEvent):
            self.name = (await bot.get_group_info(group_id=event.group_id))['group_name']
        elif isinstance(event, PrivateMessageEvent):
            self.name = await self.get_user_name(event, bot)
        return self

    async def get_user_name(self, event: MessageEvent, bot: Bot):
        if self.is_group or self.name is None:
            return await get_user_name(event=event, bot=bot, user_id=event.user_id) or '未知'
        else:
            return self.name

    def record_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True, *, token_count: Optional[int] = None):
        self.history.add_chat_history(text, sender, auto_remove, token_count=token_count)

    def record_other_history(self, text: str, sender: str, auto_remove=True):
        self.history.add_other_history(text, sender, auto_remove)

    def clear_history(self):
        self.history = ChatHistory(self, False)

    def get_chat_messages(self, _override: Optional[list[BaseMessage]] = None) -> list[dict[str, str]]:
        return self.history.get_chat_messages(_override)

    @property
    def enabled(self):
        return self.is_group or self.config.reply_on_private

    def in_throttle_time(self):
        msg_time = time()
        if msg_time - self.last_msg_time < self.config.reply_throttle_time:
            return True
        self.last_msg_time = msg_time
        return False


#-----------------------------
#
#           历史记录
#
#-----------------------------
VERSION = 1

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
    data['VERSION'] = 1
    return data

upgrader_list = [
    history_data_0_to_1
]


class ChatHistory:
    data_keys = ('other_history', 'other_history_token_count', 'last_other_text', 'chat_history', 'chat_history_token_count', 'last_chat_text')
    def __init__(self, instance: ChatInstance, load_pickle=True):
        self.instance = instance
        self.other_history: deque[BaseMessage] = deque()
        self.other_history_token_count = 0
        self.last_other_text = None
        self.chat_history: deque[BaseMessage] = deque()
        self.chat_history_token_count = 0
        self.last_chat_text = None
        self.pickle_path: Path = Path('data/llm', self.instance.chat_key, 'history.pickle')
        self.changed = False
        self.set_next_auto_save_time(time())
        if load_pickle:
            self.load_pickle()

    @property
    def other_context_token_limit(self) -> int:
        return self.instance.config.record_other_context_token_limit if self.instance.is_group else 0

    @property
    def chat_context_token_limit(self) -> int:
        return self.instance.config.record_chat_context_token_limit if self.instance.is_group else self.instance.config.record_chat_context_token_limit + self.instance.config.record_other_context_token_limit

    def get_data_dict(self):
        return {k: getattr(self, k) for k in self.data_keys}

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
            for k in self.data_keys:
                value = pickle_data.get(k)
                if value is not None:
                    setattr(self, k, value)

    def get_chat_messages(self, _override: Optional[list[BaseMessage]] = None) -> list[dict[str, str]]:
        system_message = self.instance.config.system_message
        messages = [system_message] if system_message else []
        if _override is None:
            histories = sorted(chain(self.other_history, self.chat_history), key=lambda x: x.timestamp)
            messages.extend(i.to_message() for i in histories)
        else:
            messages.extend(i.to_message() for i in _override)
        return messages

    def add_other_history(self, text: str, sender: str, auto_remove=True):
        self.changed = True
        if self.last_other_text == text:
            self.other_history[-1].timestamp = time()
        else:
            self.last_other_text = text
            message = UserMessage(text, sender, provide_username=self.instance.config.provide_username, provide_local_time=self.instance.config.provide_local_time)
            self.other_history_token_count += message.token_count
            self.other_history.append(message)
            if not auto_remove:
                return
            while len(self.other_history) > 0 and self.other_history_token_count > self.other_context_token_limit:
                self.other_history_token_count -= self.other_history.popleft().token_count

    def add_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True, *, token_count: Optional[int] = None):
        self.changed = True
        if sender is not None and self.last_chat_text == text:
            self.chat_history[-1].timestamp = time()
        else:
            self.last_chat_text = text
            if sender is None:
                message = ModelMessage(text, token_count=token_count, provide_local_time=self.instance.config.provide_local_time)
            else:
                message = UserMessage(text, sender, provide_username=self.instance.config.provide_username, provide_local_time=self.instance.config.provide_local_time)
            self.chat_history_token_count += message.token_count
            self.chat_history.append(message)
            if not auto_remove:
                return
            while len(self.chat_history) > 0 and self.chat_history_token_count > self.chat_context_token_limit:
                self.chat_history_token_count -= self.chat_history.popleft().token_count


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
