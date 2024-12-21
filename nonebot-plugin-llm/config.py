from collections.abc import Iterable
from pathlib import Path
import os
from typing import Any, Callable, Optional, Union
import yaml

from . import shared

DEFAULT = 'default'


class Filter:
    def __init__(self, func) -> None:
        self.filter: Callable[[Any], bool] = func


class LLMConfig:
    attr_prefix = None
    allow_default = False
    config_path: Path
    config_checkers: 'dict[str, tuple[Union[tuple, type], Optional[Union[Callable, Filter]], Any]]'

    def __init__(self) -> None:
        self.yaml: dict = None # type: ignore
        self.load_yaml()

    def get_attr_name(self, attr: str):
        if self.attr_prefix is None:
            return attr
        else:
            return f'{self.attr_prefix}{attr}'

    def load_yaml(self) -> None:
        os.makedirs(os.path.split(self.config_path)[0], exist_ok=True)
        if self.config_path.is_file():
            with open(self.config_path, mode='r', encoding='utf-8') as f:
                self.yaml = yaml.load(f, Loader=yaml.FullLoader)
        else:
            self.yaml = {}
        self.apply_yaml()
        self.save_yaml()

    def save_yaml(self):
        with open(self.config_path, mode='w', encoding='utf-8') as f:
            yaml.dump(self.get_dict(), f, allow_unicode=True, sort_keys=False)

    def get_dict(self) -> dict[str, Any]:
        return {k: getattr(self, self.get_attr_name(k)) for k in self.config_checkers.keys()}

    def apply_yaml(self) -> None:
        for key, (types, condition, default) in self.config_checkers.items():
            value = self.yaml.get(key)
            use_default = False
            if value is None:
                use_default = True
            else:
                is_default = self.allow_default and value == DEFAULT
                if not (is_default or types is None):
                    use_default = not isinstance(value, types)
                if (not (use_default or is_default)) and condition is not None:
                    if isinstance(condition, Filter):
                        if value != DEFAULT and isinstance(value, Iterable):
                            setattr(self, self.get_attr_name(key), type(value)(filter(condition.filter, value))) # type: ignore
                            continue
                    else:
                        use_default = not condition(value)
            if use_default:
                setattr(self, self.get_attr_name(key), default)
            else:
                setattr(self, self.get_attr_name(key), value)

    def set_value(self, key: str, value: Any, *, save=True):
        setattr(self, self.get_attr_name(key), value)
        if save:
            self.save_yaml()


class PluginConfig(LLMConfig):
    config_path = Path('data/llm/config.yml')
    config_checkers = {
        'openai_api_v1': (str, None, ''),
        'model_identifier': (str, None, ''),
        'api_timeout': (int, lambda x: x > 0, 60),
        'reply_throttle_time': ((int, float), lambda x: x >= 0, 3),
        'bot_name': (str, None, 'LLM'),
        'system_prompts': (dict, None, {'LLM': None}),
        'chat_top_p': ((int, float), lambda x: 0 <= x <= 1, 0.95),
        'chat_temperature': ((int, float), lambda x: 0 <= x <= 1, 0.75),
        'chat_presence_penalty': ((int, float), lambda x: -2 <= x <= 2, 0.8),
        'chat_frequency_penalty': ((int, float), lambda x: -2 <= x <= 2, 0.8),
        'reply_on_private': (bool, None, True),
        'reply_on_name_mention': (bool, None, True),
        'reply_on_at': (bool, None, True),
        'reply_on_welcome': (bool, None, False),
        'use_group_card': (bool, None, True),
        'only_text_message': (bool, None, False),
        'record_other_context': (bool, None, True),
        'record_other_context_token_limit': (int, lambda x: x > 0, 2048),
        'record_chat_context': (bool, None, True),
        'record_chat_context_token_limit': (int, lambda x: x > 0, 2048),
        'auto_save_history': (bool, None, True),
        'auto_save_interval': ((int, float), lambda x: x > 0, 5),
        'provide_username': (bool, None, True),
        'provide_local_time': (bool, None, True),
        'forbidden_users': (list, Filter(lambda x: isinstance(x, int)), []),
        'forbidden_groups': (list, Filter(lambda x: isinstance(x, int)), []),
        'forbidden_words': (list, Filter(lambda x: isinstance(x, str)), []),
        'event_priority': (int, None, 99),
        'block_event': (bool, None, False),
        'debug': (bool, None, False)
    }

    openai_api_v1: str
    model_identifier: str
    api_timeout: int
    reply_throttle_time: int | float
    bot_name: str
    system_prompts: dict[str, str]
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
        if self.bot_name not in self.system_prompts:
            shared.logger.warning(f'全局预设名 {self.bot_name} 未在system_prompts中定义')
            if self.system_prompts:
                bot_name = next(iter(self.system_prompts.keys()))
                self.set_value('bot_name', bot_name, save=False)
                shared.logger.warning(f'已自动更改为 {bot_name}')
            else:
                self.set_value('bot_name', self.config_checkers['bot_name'][-1], save=False)


class InstanceConfig(LLMConfig):
    attr_prefix = '_'
    allow_default = True
    config_checkers = {
        'openai_api_v1': ((DEFAULT, str), None, DEFAULT),
        'model_identifier': ((DEFAULT, str), None, DEFAULT),
        'api_timeout': ((DEFAULT, int), lambda x: x > 0, DEFAULT),
        'reply_throttle_time': ((DEFAULT, int, float), lambda x: x >= 0, DEFAULT),
        'bot_name': ((DEFAULT, str), None, DEFAULT),
        'chat_top_p': ((DEFAULT, int, float), lambda x: 0 <= x <= 1, DEFAULT),
        'chat_temperature': ((DEFAULT, int, float), lambda x: 0 <= x <= 1, DEFAULT),
        'chat_presence_penalty': ((DEFAULT, int, float), lambda x: -2 <= x <= 2, DEFAULT),
        'chat_frequency_penalty': ((DEFAULT, int, float), lambda x: -2 <= x <= 2, DEFAULT),
        'reply_on_private': ((DEFAULT, bool), None, DEFAULT),
        'reply_on_name_mention': ((DEFAULT, bool), None, DEFAULT),
        'reply_on_at': ((DEFAULT, bool), None, DEFAULT),
        'reply_on_welcome': ((DEFAULT, bool), None, DEFAULT),
        'record_other_context': ((DEFAULT, bool), None, DEFAULT),
        'record_other_context_token_limit': ((DEFAULT, int), lambda x: x > 0, DEFAULT),
        'record_chat_context': ((DEFAULT, bool), None, DEFAULT),
        'record_chat_context_token_limit': ((DEFAULT, int), lambda x: x > 0, DEFAULT),
        'auto_save_history': ((DEFAULT, bool), None, DEFAULT),
        'auto_save_interval': ((DEFAULT, int, float), lambda x: x > 0, DEFAULT),
        'provide_username': ((DEFAULT, bool), None, DEFAULT),
        'provide_local_time': ((DEFAULT, bool), None, DEFAULT)
    }

    def get_value(self, key: str) -> Any:
        value = getattr(self, self.get_attr_name(key))
        return getattr(shared.plugin_config, key) if value == 'default' else value

    @property
    def openai_api_v1(self) -> str:
        return self.get_value('openai_api_v1')

    @property
    def model_identifier(self) -> str:
        return self.get_value('model_identifier')

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

    def __init__(self, chat_key: str) -> None:
        self.chat_key = chat_key
        super().__init__()

    def apply_yaml(self) -> None:
        super().apply_yaml()
        if self.system_prompt is None:
            shared.logger.warning(f'{self.chat_key}配置中的预设名 {self.bot_name} 未在system_prompts中定义, 已自动回退为默认值')
            self.set_value('bot_name', DEFAULT, save=False)


shared.plugin_config = PluginConfig()
