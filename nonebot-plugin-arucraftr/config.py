from collections.abc import Iterable
from pathlib import Path
import os
from typing import Any, Callable, Generator, NamedTuple, Optional, Tuple
from httpx import Proxy

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from . import shared
from .api import start_async_client

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
NUMBER_TYPE = (int, float)


class Item(NamedTuple):
    types: type | Tuple[type, ...]
    condition: Optional[(Callable | Filter) | tuple[Callable | Filter, ...]]
    default: Any
    eof_comment: Optional[str] = None
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


class PluginConfig(BaseConfig):
    start_comment = 'LLM插件全局配置文件'
    config_path = Path('data/llm/config.yml')
    config_checkers = {
        'enable': Item(bool, None, False, '是否启用'),
        'use_proxy': Item(bool, None, False, '是否使用代理连接外部API'),
        'proxy_url': Item(str, lambda x: x.startswith('http'), 'http://127.0.0.1:7890', '代理地址, 如 http://127.0.0.1:7890'),
        'main_group': Item(int, None, -1, '主群群号'),
        'admin_group': Item(int, None, -1, '管理组群号'),
        'active_days_threshold': Item(int, lambda x: -1 <= x, -1, '群成员活跃判定阈值(距离上次发送消息)'),
        'debug': Item(bool, None, False, '调试模式')
    }

    enable: bool
    use_proxy: bool
    proxy_url: str
    main_group: int
    admin_group: int
    active_days_threshold: int
    debug: bool

    @property
    def active_threshold_timestamp(self) -> int:
        return self.active_days_threshold * 86400

    def __init__(self) -> None:
        super().__init__()
        self.proxy: Optional[Proxy] = None

    def apply_yaml(self) -> None:
        super().apply_yaml()
        if self.use_proxy:
            self.proxy = Proxy(self.proxy_url)


shared.plugin_config = PluginConfig()
start_async_client()