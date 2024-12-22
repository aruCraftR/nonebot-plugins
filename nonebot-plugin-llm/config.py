from collections.abc import Iterable
from pathlib import Path
import os
from typing import Any, Callable, Generator, NamedTuple, Optional, Tuple

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from openai import AsyncOpenAI

from .interface import SystemMessage
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

    def validate(self, config: 'LLMConfig', key: str, value: Any) -> bool:
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


class LLMConfig:
    attr_prefix = None
    allow_default = False
    config_path: Path
    config_checkers: dict[str, Item]
    start_comment: Optional[str]

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
            commented_map.yaml_add_eol_comment(f'# {checker.comment}', key)
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


class PluginConfig(LLMConfig):
    start_comment = 'LLM插件全局配置文件'
    config_path = Path('data/llm/config.yml')
    config_checkers = {
        'openai_api_v1': Item(str, None, 'https://api.openai.com/v1', '任意OpenAI标准的接口'),
        'models': Item(dict, STR_DICT_KV, {'ChatGPT-4o': 'gpt-4o'}),
        'text_model_name': Item(str, None, 'ChatGPT-4o', '用于文本生成的主模型名'),
        'vision_model_name': Item(str, None, 'ChatGPT-4o', '用于图像识别的辅助模型名'),
        'api_timeout': Item(int, lambda x: x > 0, 60, 'API请求超时时间'),
        'reply_throttle_time': Item((int, float), lambda x: x >= 0, 3, '节流时长, 同一会话在节流时间内仅能处理第一条消息'),
        'bot_name': Item(str, None, 'LLM', '机器人名称, 必须在系统提示词预设内'),
        'system_prompts': Item(dict, STR_DICT_KV, {'LLM': None}),
        'vision_model_prompt': Item(str, None, '请提取此图像中的文字并列出, 同时单独总结该图像的场景等除文本外的视觉内容', '用于告知视觉辅助模型生成图像描述, 以提供信息给主文本模型进行生成'),
        'image_size_limit': Item(list, (INT_LIST, (lambda x: len(x) == 2)), [720, 720], '发送给视觉模型的图像分辨率大小限制'),
        'image_quality': Item(int, lambda x: 1 <= x <= 100, 80, '编码的图像质量, 用于加快请求速度, 高于95的值基本无质量提升'),
        'image_subsampling': Item(int, lambda x: 0 <= x <= 2, 0, '子采样等级, 0=4:4:4; 1=4:2:2; 2=4:2:0'),
        'chat_top_p': Item((int, float), lambda x: 0 <= x <= 1, 1, '用于模型的Top P值, 越大越遵循输入'),
        'chat_temperature': Item((int, float), lambda x: 0 <= x <= 1, 0.75, '用于模型的温度值, 越大越随机'),
        'chat_presence_penalty': Item((int, float), lambda x: -2 <= x <= 2, 0.8, '重复惩罚'),
        'chat_frequency_penalty': Item((int, float), lambda x: -2 <= x <= 2, 0.8, '频率惩罚'),
        'reply_on_private': Item(bool, None, True, '是否为私聊消息生成文本'),
        'reply_on_name_mention': Item(bool, None, True, '是否在提及机器人名称时生成文本'),
        'reply_on_at': Item(bool, None, True, '是否在@机器人名称时生成文本'),
        'reply_on_welcome': Item(bool, None, False, '是否欢迎新成员入群'),
        'use_group_card': Item(bool, None, True, '获取昵称时是否使用群名片'),
        'only_text_message': Item(bool, None, False, '是否仅处理纯文本信息'),
        'record_other_context': Item(bool, None, True, '是否记录上下文无关对话'),
        'record_other_context_token_limit': Item(int, lambda x: x > 0, 2048, '上下文无关对话Token数上限'),
        'record_chat_context': Item(bool, None, True, '是否记录直接对话内容'),
        'record_chat_context_token_limit': Item(int, lambda x: x > 0, 2048, '直接对话内容Token上限'),
        'auto_save_history': Item(bool, None, True, '是否自动保存历史记录'),
        'auto_save_interval': Item((int, float), lambda x: x > 0, 5, '历史记录自动保存间隔'),
        'provide_username': Item(bool, None, True, '是否将用户名提供给模型(占用少量token)'),
        'provide_local_time': Item(bool, None, True, '是否将当前时间提供给模型(占用少量token)'),
        'forbidden_users': Item(list, INT_LIST, [], '禁止触发的QQ号'),
        'forbidden_groups': Item(list, INT_LIST, [], '禁止触发的QQ群'),
        'forbidden_words': Item(list, STR_LIST, [], '禁止触发的关键词'),
        'event_priority': Item(int, None, 99, '消息事件监听器优先级'),
        'block_event': Item(bool, None, False, '是否阻止消息事件向低优先级监听器分发'),
        'debug': Item(bool, None, False, '调试模式')
    }

    openai_api_v1: str
    models: dict[str, str]
    text_model_name: str
    vision_model_name: str
    api_timeout: int
    reply_throttle_time: int | float
    bot_name: str
    system_prompts: dict[str, str]
    image_size_limit: tuple[int, int]
    image_quality: int
    image_subsampling: int
    vision_model_prompt: str
    chat_top_p: int | float
    chat_temperature: int | float
    chat_presence_penalty: int | float
    chat_frequency_penalty: int | float
    reply_on_private: bool
    reply_on_name_mention: bool
    reply_on_at: bool
    reply_on_welcome: bool
    use_group_card: bool
    only_text_message: bool
    record_other_context: bool
    record_other_context_token_limit: int
    record_chat_context: bool
    record_chat_context_token_limit: int
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

    def apply_yaml(self) -> None:
        super().apply_yaml()
        self.image_size_limit = tuple(self.image_size_limit) # type: ignore
        if self.bot_name not in self.system_prompts:
            shared.logger.warning(f'全局预设名 {self.bot_name} 未在system_prompts中定义')
            if self.system_prompts:
                bot_name = next(iter(self.system_prompts.keys()))
                self.set_value('bot_name', bot_name, save=False)
                shared.logger.warning(f'已自动更改为 {bot_name}')
            else:
                self.set_value('bot_name', self.config_checkers['bot_name'][-1], save=False)

        if self.text_model_name not in self.models:
            shared.logger.warning(f'全局文本模型名 {self.text_model_name} 未在models中定义')
            if self.models:
                model_name = next(iter(self.models.keys()))
                self.set_value('text_model_name', model_name, save=False)
                shared.logger.warning(f'已自动更改为 {model_name}')
            else:
                self.set_value('text_model_name', self.config_checkers['text_model_name'][-1], save=False)

        if self.vision_model_name not in self.models:
            shared.logger.warning(f'全局视觉模型名 {self.vision_model_name} 未在models中定义')
            if self.models:
                model_name = next(iter(self.models.keys()))
                self.set_value('vision_model_name', model_name, save=False)
                shared.logger.warning(f'已自动更改为 {model_name}')
            else:
                self.set_value('vision_model_name', self.config_checkers['vision_model_name'][-1], save=False)


class InstanceConfig(LLMConfig):
    start_comment = '用于 {name} 会话的配置文件覆盖\n设为 default 的项将使用全局配置文件中的值'
    attr_prefix = '_'
    allow_default = True
    config_checkers = {
        'openai_api_v1': Item(str, None, DEFAULT),
        'text_model_name': Item(str, None, DEFAULT),
        'vision_model_name': Item(str, None, DEFAULT),
        'api_timeout': Item(int, lambda x: x > 0, DEFAULT),
        'reply_throttle_time': Item((int, float), lambda x: x >= 0, DEFAULT),
        'bot_name': Item(str, None, DEFAULT),
        'vision_model_prompt': Item(str, None, DEFAULT),
        'chat_top_p': Item((int, float), lambda x: 0 <= x <= 1, DEFAULT),
        'chat_temperature': Item((int, float), lambda x: 0 <= x <= 1, DEFAULT),
        'chat_presence_penalty': Item((int, float), lambda x: -2 <= x <= 2, DEFAULT),
        'chat_frequency_penalty': Item((int, float), lambda x: -2 <= x <= 2, DEFAULT),
        'reply_on_private': Item(bool, None, DEFAULT),
        'reply_on_name_mention': Item(bool, None, DEFAULT),
        'reply_on_at': Item(bool, None, DEFAULT),
        'reply_on_welcome': Item(bool, None, DEFAULT),
        'record_other_context': Item(bool, None, DEFAULT),
        'record_other_context_token_limit': Item(int, lambda x: x > 0, DEFAULT),
        'record_chat_context': Item(bool, None, DEFAULT),
        'record_chat_context_token_limit': Item(int, lambda x: x > 0, DEFAULT),
        'auto_save_history': Item(bool, None, DEFAULT),
        'auto_save_interval': Item((int, float), lambda x: x > 0, DEFAULT),
        'provide_username': Item(bool, None, DEFAULT),
        'provide_local_time': Item(bool, None, DEFAULT)
    }

    def get_value(self, key: str) -> Any:
        value = getattr(self, self.get_attr_name(key))
        return getattr(shared.plugin_config, key) if value == 'default' else value

    @property
    def openai_api_v1(self) -> str:
        return self.get_value('openai_api_v1')

    @property
    def text_model_name(self) -> str:
        return self.get_value('text_model_name')

    @property
    def vision_model_name(self) -> str:
        return self.get_value('vision_model_name')

    @property
    def api_timeout(self) -> int:
        return self.get_value('api_timeout')

    @property
    def reply_throttle_time(self) -> int | float:
        return self.get_value('reply_throttle_time')

    @property
    def bot_name(self) -> str:
        return self.get_value('bot_name')

    @property
    def vision_model_prompt(self) -> str:
        return self.get_value('vision_model_prompt')

    @property
    def chat_top_p(self) -> int | float:
        return self.get_value('chat_top_p')

    @property
    def chat_temperature(self) -> int | float:
        return self.get_value('chat_temperature')

    @property
    def chat_presence_penalty(self) -> int | float:
        return self.get_value('chat_presence_penalty')

    @property
    def chat_frequency_penalty(self) -> int | float:
        return self.get_value('chat_frequency_penalty')

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
    def record_other_context(self) -> bool:
        return self.get_value('record_other_context')

    @property
    def record_other_context_token_limit(self) -> int:
        return self.get_value('record_other_context_token_limit')

    @property
    def record_chat_context(self) -> bool:
        return self.get_value('record_chat_context')

    @property
    def record_chat_context_token_limit(self) -> int:
        return self.get_value('record_chat_context_token_limit')

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

    @property
    def system_prompt(self) -> Optional[str]:
        return shared.plugin_config.system_prompts.get(self.bot_name)

    @property
    async def system_message(self) -> Optional[dict[str, str]]:
        if self.system_prompt is None:
            return
        if self._sys_msg_cache is None:
            self._sys_msg_cache = await SystemMessage(self.system_prompt, token_count=0).to_message()
        return self._sys_msg_cache

    @property
    def text_model_identifier(self) -> str:
        return shared.plugin_config.models.get(self.text_model_name) # type: ignore

    @property
    def vision_model_identifier(self) -> str:
        return shared.plugin_config.models.get(self.vision_model_name) # type: ignore

    @property
    def async_open_ai(self) -> AsyncOpenAI:
        if self._async_open_ai is None:
            self._async_open_ai = AsyncOpenAI(
                base_url=self.openai_api_v1,
                api_key='none'
            )
        return self._async_open_ai

    @property
    def chat_completion_kwargs(self):
        if self._chat_completion_kwargs is None:
            self._chat_completion_kwargs = {
                # 'max_tokens': self.chat_max_tokens,
                'temperature': self.chat_temperature,
                'top_p': self.chat_top_p,
                'frequency_penalty': self.chat_frequency_penalty,
                'presence_penalty': self.chat_presence_penalty,
                'timeout': self.api_timeout
            }
        return self._chat_completion_kwargs

    def __init__(self, chat_key: str, chat_name: str) -> None:
        self.chat_key = chat_key
        self.chat_name = chat_name
        self.start_comment = self.start_comment.format(name=self.chat_name)
        super().__init__()

    def apply_yaml(self) -> None:
        super().apply_yaml()
        if self.system_prompt is None:
            shared.logger.warning(f'{self.chat_key}配置中的预设名 {self.bot_name} 未在system_prompts中定义, 已自动回退为默认值')
            self.set_value('bot_name', DEFAULT, save=False)
        if self.text_model_name is None:
            shared.logger.warning(f'{self.chat_key}配置中的预设名 {self.text_model_name} 未在models中定义, 已自动回退为默认值')
            self.set_value('text_model_name', DEFAULT, save=False)
        if self.vision_model_name is None:
            shared.logger.warning(f'{self.chat_key}配置中的预设名 {self.vision_model_name} 未在models中定义, 已自动回退为默认值')
            self.set_value('vision_model_name', DEFAULT, save=False)
        self._async_open_ai = None
        self._sys_msg_cache = None
        self._chat_completion_kwargs = None


shared.plugin_config = PluginConfig()
