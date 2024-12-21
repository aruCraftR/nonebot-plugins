
from collections import deque
from pathlib import Path
import pickle
from itertools import chain
from typing import Optional
from time import asctime, time

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, PrivateMessageEvent, GroupMessageEvent, Bot

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

    def record_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True):
        self.history.add_chat_history(text, sender, auto_remove)

    def record_other_history(self, text: str, sender: str, auto_remove=True):
        self.history.add_other_history(text, sender, auto_remove)

    def clear_history(self):
        self.history = ChatHistory(self, False)

    def get_chat_messages(self, _override: Optional[list[dict[str, str]]] = None) -> list[dict[str, str]]:
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

class ChatHistory:
    data_keys = ('other_history', 'other_history_token_count', 'last_other_text', 'chat_history', 'chat_history_token_count', 'last_chat_text')
    def __init__(self, instance: ChatInstance, load_pickle=True):
        self.instance = instance
        self.other_history: deque[tuple[float, dict, int]] = deque()
        self.other_history_token_count = 0
        self.last_other_text = None
        self.chat_history: deque[tuple[float, dict, int]] = deque()
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
            pickle.dump(self.get_data_dict(), f)
        self.changed = False

    def load_pickle(self):
        if not self.pickle_path.is_file():
            return
        with self.pickle_path.open('rb') as f:
            pickle_data: dict = pickle.load(f)
        for k in self.data_keys:
            value = pickle_data.get(k)
            if value is not None:
                setattr(self, k, value)

    def get_chat_messages(self, _override: Optional[list[dict[str, str]]] = None) -> list[dict[str, str]]:
        sys_prompt = self.instance.config.system_prompt
        messages = [{"role": "system", "content": sys_prompt}] if sys_prompt else []
        if _override is None:
            histories = sorted(chain(self.other_history, self.chat_history), key=lambda x: x[0])
            messages.extend(i[1] for i in histories)
        else:
            messages.extend(_override)
        return messages

    def add_other_history(self, text: str, sender: str, auto_remove=True):
        self.changed = True
        if self.last_other_text == text:
            token_count = self.other_history.pop()[-1]
        else:
            self.last_other_text = text
            text = self.add_extra_info(text, sender)
            token_count = self.count_token(text)
            self.other_history_token_count += token_count
        self.other_history.append((time(), self.gen_text_json(text, sender), token_count))
        if not auto_remove:
            return
        while len(self.other_history) > 0 and self.other_history_token_count > self.other_context_token_limit:
            self.other_history_token_count -= self.other_history.popleft()[-1]

    def add_chat_history(self, text: str, sender: Optional[str] = None, auto_remove=True):
        self.changed = True
        if self.last_chat_text == text:
            token_count = self.chat_history.pop()[-1]
        else:
            self.last_chat_text = text
            text = self.add_extra_info(text, sender)
            token_count = self.count_token(text)
            self.chat_history_token_count += token_count
        self.chat_history.append((time(), self.gen_text_json(text, sender), token_count))
        if not auto_remove:
            return
        while len(self.chat_history) > 0 and self.chat_history_token_count > self.chat_context_token_limit:
            self.chat_history_token_count -= self.chat_history.popleft()[-1]

    def add_extra_info(self, text: str, sender: Optional[str] = None):
        if sender is not None and self.instance.config.provide_username:
            text = f'{sender}说 {text}'
        if self.instance.config.provide_local_time:
            text = f'[时间: {asctime()}] {text}'
        return text

    @staticmethod
    def gen_text_json(text: str, sender: Optional[str] = None):
        return {
            'role': 'assistant',
            'content': text
        } if sender is None else {
            'role': 'user',
            'name': sender,
            'content': text
        }

    @staticmethod
    def count_token(text: str):
        return len(shared.tiktoken.encode(text))


async def get_chat_instance(matcher: type[Matcher], event: MessageEvent, bot: Bot) -> ChatInstance:
    chat_key, is_group = await get_chat_type(event)
    if chat_key in chat_instances:
        return chat_instances[chat_key]
    else:
        if is_group is None:
            await matcher.finish('未知的消息来源')
        return await ChatInstance.async_init(bot, event, chat_key, is_group)


def get_chat_instance_directly(chat_key) -> Optional[ChatInstance]:
    return chat_instances.get(chat_key)


def get_chat_instances():
    return chat_instances.values()