from collections.abc import Iterable
from pathlib import Path
import os
from typing import Any, Callable, Generator, NamedTuple, Optional, Tuple

from httpx import Timeout
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from . import async_ragflow
from . import shared

DEFAULT = 'default'

yaml = YAML()
yaml.allow_unicode = True


class Filter:
    def __init__(self, func) -> None:
        self.filter: Callable = func

    def get_filtered_value(self, value: list | dict):
        if isinstance(value, list):
            return list(filter(self.filter, value))
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if self.filter(k, v)}
        return type(value)(filter(self.filter, value))


STR_DICT_KV = Filter(lambda k, v: (isinstance(k, str) and isinstance(v, str)))
INT_LIST = Filter(lambda x: isinstance(x, int))
NUM_LIST = Filter(lambda x: isinstance(x, (int, float)))
STR_LIST = Filter(lambda x: isinstance(x, str))


class Item(NamedTuple):
    types: type | Tuple[type, ...]
    condition: Optional[(Callable | Filter) | tuple[Callable | Filter, ...]]
    default: Any
    comment: Optional[str] = None

    def validate(self, config: 'BaseConfig', key: str, value: Any) -> bool:
        if self.condition is None:
            return True
        conditions = self.condition if isinstance(self.condition, tuple) else (self.condition,)
        for i in conditions:
            if isinstance(i, Filter):
                if value != DEFAULT and isinstance(value, Iterable):
                    value = i.get_filtered_value(value) # type: ignore
                    setattr(config, config.get_attr_name(key), value)
                    continue
            elif not i(value):
                return False
        return True


class BaseConfig:
    attr_prefix = None
    allow_default = False
    config_path: Path
    config_checkers: dict[str, Item]
    start_comment: Optional[str] = None

    def __init__(self) -> None:
        self.yaml: dict = None # type: ignore
        self.load_yaml()

    def get_attr_name(self, attr: str):
        return attr if self.attr_prefix is None else f'{self.attr_prefix}{attr}'

    def load_yaml(self) -> None:
        os.makedirs(os.path.split(self.config_path)[0], exist_ok=True)
        if self.config_path.is_file():
            with open(self.config_path, mode='r', encoding='utf-8') as f:
                self.yaml = yaml.load(f)
        else:
            self.yaml = {}
        self.apply_yaml()
        self.save_yaml()

    def save_yaml(self):
        with open(self.config_path, mode='w', encoding='utf-8') as f:
            yaml.dump(self.get_commented_map(), f)

    def get_commented_map(self) -> CommentedMap:
        commented_map = CommentedMap(self.get_kv())
        if self.start_comment is not None:
            commented_map.yaml_set_start_comment(self.start_comment)
        for key, checker in self.config_checkers.items():
            if checker.comment is None:
                continue
            commented_map.yaml_set_comment_before_after_key(key, checker.comment, after='\n\n')
        return commented_map

    def get_kv(self) -> Generator[Tuple[str, Any]]:
        return ((k, getattr(self, self.get_attr_name(k))) for k in self.config_checkers.keys())

    def get_dict(self) -> dict[str, Any]:
        return {k: getattr(self, self.get_attr_name(k)) for k in self.config_checkers.keys()}

    def apply_yaml(self) -> None:
        for key, item in self.config_checkers.items():
            value = self.yaml.get(key)
            if value is None:
                self.back_to_default(key, item)
                continue
            if value == DEFAULT:
                if not self.allow_default:
                    self.back_to_default(key, item)
                    continue
                setattr(self, self.get_attr_name(key), value)
                continue
            elif item.types is not None:
                if not isinstance(value, item.types):
                    self.back_to_default(key, item)
                    continue
            if (item.condition is not None) and (not item.validate(self, key, value)):
                self.back_to_default(key, item)
                continue
            setattr(self, self.get_attr_name(key), value)

    def back_to_default(self, key: str, item: Item):
        setattr(self, self.get_attr_name(key), item.default)

    def set_value(self, key: str, value: Any, *, save=True):
        setattr(self, self.get_attr_name(key), value)
        if save:
            self.save_yaml()


class PluginConfig(BaseConfig):
    start_comment = 'RAGFlow插件全局配置文件'
    config_path = Path('data/llm/config.yml')
    config_checkers = {
        'enable': Item(bool, None, False, '是否启用'),
        'ragflow_api_v1': Item(str, None, 'https://api.openai.com/v1', '任意OpenAI标准的接口'),
        'api_key': Item(str, None, '', '接口密钥'),
        'api_timeout': Item(int, lambda x: x > 0, 60, 'API请求超时时间'),
        'reply_throttle_time': Item((int, float), lambda x: x >= 0, 3, '节流时长, 同一会话在节流时间内仅能处理第一条消息'),
        'assistant_name': Item(str, None, 'LLM', '机器人名称, 必须在系统提示词预设内'),
        'image_size_limit': Item(list, (INT_LIST, (lambda x: len(x) == 2)), [720, 720], '发送给视觉模型的图像分辨率大小限制'),
        'image_quality': Item(int, lambda x: 1 <= x <= 100, 80, '编码的图像质量, 用于加快请求速度, 高于95的值基本无质量提升'),
        'image_subsampling': Item(int, lambda x: 0 <= x <= 2, 0, '子采样等级, 0=4:4:4; 1=4:2:2; 2=4:2:0'),
        'reply_on_private': Item(bool, None, True, '是否为私聊消息生成文本'),
        'reply_on_name_mention': Item(bool, None, True, '是否在提及机器人名称时生成文本'),
        'reply_on_at': Item(bool, None, True, '是否在@机器人名称时生成文本'),
        'reply_on_welcome': Item(bool, None, False, '是否欢迎新成员入群'),
        'use_group_card': Item(bool, None, True, '获取昵称时是否使用群名片'),
        'only_text_message': Item(bool, None, False, '是否仅处理纯文本信息'),
        'record_context': Item(bool, None, True, '是否记录上下文对话'),
        'record_context_token_limit': Item(int, lambda x: x > 0, 2048, '上下文对话Token数上限'),
        'auto_save_history': Item(bool, None, DEFAULT),
        'auto_save_interval': Item((int, float), lambda x: x > 0, DEFAULT),
        'provide_username': Item(bool, None, True, '是否将用户名提供给模型(占用少量token)'),
        'provide_local_time': Item(bool, None, True, '是否将当前时间提供给模型(占用少量token)'),
        'forbidden_users': Item(list, INT_LIST, [], '禁止触发的QQ号'),
        'forbidden_groups': Item(list, INT_LIST, [], '禁止触发的QQ群'),
        'forbidden_words': Item(list, STR_LIST, [], '禁止触发的关键词'),
        'event_priority': Item(int, None, 99, '消息事件监听器优先级'),
        'block_event': Item(bool, None, False, '是否阻止消息事件向低优先级监听器分发'),
        'debug': Item(bool, None, False, '调试模式')
    }

    enable: bool
    ragflow_api_v1: str
    api_key: str
    api_timeout: int
    reply_throttle_time: int | float
    assistant_name: str
    image_size_limit: tuple[int, int]
    image_quality: int
    image_subsampling: int
    reply_on_private: bool
    reply_on_name_mention: bool
    reply_on_at: bool
    reply_on_welcome: bool
    use_group_card: bool
    only_text_message: bool
    record_context: bool
    record_context_token_limit: int
    auto_save_history: bool
    auto_save_interval: int | float
    provide_username: bool
    provide_local_time: bool
    forbidden_users: list[int]
    forbidden_groups: list[int]
    forbidden_words: list[str]
    event_priority: int
    block_event: bool
    debug: bool

    def __init__(self) -> None:
        super().__init__()
        self.ragflow_api: async_ragflow.RAGFlow

    async def reload_yaml(self) -> None:
        self.load_yaml()
        await self.init_ragflow_api()

    async def init_ragflow_api(self):
        self.ragflow_api = async_ragflow.RAGFlow(self.ragflow_api, self.api_key, timeout=Timeout(self.api_timeout))

class InstanceConfig(BaseConfig):
    start_comment = '用于 {name} 会话的配置文件覆盖\n设为 default 的项将使用全局配置文件中的值'
    attr_prefix = '_'
    allow_default = True
    config_checkers = {
        'reply_throttle_time': Item((int, float), lambda x: x >= 0, DEFAULT),
        'assistant_name': Item(str, None, DEFAULT),
        'reply_on_private': Item(bool, None, DEFAULT),
        'reply_on_name_mention': Item(bool, None, DEFAULT),
        'reply_on_at': Item(bool, None, DEFAULT),
        'reply_on_welcome': Item(bool, None, DEFAULT),
        'record_context': Item(bool, None, DEFAULT),
        'record_context_token_limit': Item(int, lambda x: x > 0, DEFAULT),
        'auto_save_history': Item(bool, None, DEFAULT),
        'auto_save_interval': Item((int, float), lambda x: x > 0, DEFAULT),
        'provide_username': Item(bool, None, DEFAULT),
        'provide_local_time': Item(bool, None, DEFAULT)
    }

    def get_value(self, key: str) -> Any:
        value = getattr(self, self.get_attr_name(key))
        return getattr(shared.plugin_config, key) if value == 'default' else value

    @property
    def reply_throttle_time(self) -> int | float:
        return self.get_value('reply_throttle_time')

    @property
    def assistant_name(self) -> str:
        return self.get_value('assistant_name')

    @property
    def reply_on_private(self) -> bool:
        return self.get_value('reply_on_private')

    @property
    def reply_on_name_mention(self) -> bool:
        return self.get_value('reply_on_name_mention')

    @property
    def reply_on_at(self) -> bool:
        return self.get_value('reply_on_at')

    @property
    def reply_on_welcome(self) -> bool:
        return self.get_value('reply_on_welcome')

    @property
    def record_context(self) -> bool:
        return self.get_value('record_context')

    @property
    def record_context_token_limit(self) -> int:
        return self.get_value('record_context_token_limit')

    @property
    def auto_save_history(self) -> bool:
        return self.get_value('auto_save_history')

    @property
    def auto_save_interval(self) -> int | float:
        return self.get_value('auto_save_interval')

    @property
    def provide_username(self) -> bool:
        return self.get_value('provide_username')

    @property
    def provide_local_time(self) -> bool:
        return self.get_value('provide_local_time')

    @property
    def config_path(self) -> Path:
        return Path('data/llm', self.chat_key, 'config.yml')

    async def reload_yaml(self) -> None:
        self.load_yaml()
        await self.init_ragflow_api()

    async def set_assistant(self, name: str):
        assistants = await shared.plugin_config.ragflow_api.list_chats(page_size=1, name=name)
        if not assistants:
            return False
        self.chat_api = assistants[0]
        self.set_value('assistant_name', name)
        return True

    async def init_ragflow_api(self):
        assistants = await shared.plugin_config.ragflow_api.list_chats(page_size=1, name=self.assistant_name)
        if not assistants:
            shared.logger.warning(f'{self.chat_name} 配置中的预设名 {self.assistant_name} 未在RAGFlow中定义, 已自动回退为默认值')
            self.set_value('assistant_name', DEFAULT)
        self.chat_api = assistants[0]

    @classmethod
    async def async_init(cls, chat_key: str, chat_name: str):
        self = cls(chat_key, chat_name)
        await self.init_ragflow_api()

    def __init__(self, chat_key: str, chat_name: str) -> None:
        self.chat_key = chat_key
        self.chat_name = chat_name
        self.start_comment = self.start_comment.format(name=self.chat_name)
        self.chat_api: async_ragflow.Chat
        super().__init__()


shared.plugin_config = PluginConfig()
