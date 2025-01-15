from collections.abc import Iterable
from dataclasses import dataclass
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
HTTPX_STR = lambda x: x.startswith('http')


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


@dataclass
class McsmInstanceData:
    instance_aliase: str
    node_id: str
    instance_id: str


class PluginConfig(BaseConfig):
    start_comment = 'aruCraftR插件全局配置文件'
    config_path = Path(shared.data_path, 'config.yml')
    config_checkers = {
        'enable': Item(bool, None, False, '是否启用'),
        'use_proxy': Item(bool, None, False, '是否使用代理连接外部API'),
        'proxy_url': Item(str, HTTPX_STR, 'http://127.0.0.1:7890', '代理地址, 如 http://127.0.0.1:7890'),
        'main_group': Item(int, None, -1, '主群群号'),
        'admin_group': Item(int, None, -1, '管理组群号'),
        'mcsm_api_url': Item(str, HTTPX_STR, 'https://example.com/api', 'MCSM的API地址(xxx/api)'),
        'mcsm_api_key': Item(str, None, 'xxx', 'MCSM的API密钥'),
        'mcsm_instances': Item(dict, (STR_DICT_KV, Filter(lambda k, v: len(v.split(':')) == 2)), {'example': 'node_id:instance_id'}),
        'active_days_threshold': Item(int, lambda x: -1 <= x, -1, '群成员活跃判定阈值(距离上次发送消息)'),
        'message_forwarding_format': Item(str, None, '{"text":"[QQ] <【name】> 【text】","color":"gray"}', '消息转发格式, 【name】为用户名, 【text】为内容'),
        'forbidden_users': Item(list, INT_LIST, [], '禁止触发的QQ号'),
        'debug': Item(bool, None, False, '调试模式')
    }

    enable: bool
    use_proxy: bool
    proxy_url: str
    main_group: int
    admin_group: int
    mcsm_api_url: str
    mcsm_api_key: str
    mcsm_instances: dict[str, str]
    mcsm_instances_data: dict[str, McsmInstanceData]
    mcsm_instances_list: list[McsmInstanceData]
    active_days_threshold: int
    message_forwarding_format: str
    forbidden_users: list[int]
    debug: bool

    @property
    def active_threshold_timestamp(self) -> int:
        return self.active_days_threshold * 86400

    def __init__(self) -> None:
        super().__init__()
        self.proxy: Optional[Proxy] = None
        self._message_forwarding_format = '《"text":"[QQ] <{name}> {text}","color":"gray"》'

    def apply_yaml(self) -> None:
        super().apply_yaml()
        if self.use_proxy:
            self.proxy = Proxy(self.proxy_url)
        self._message_forwarding_format = self.message_forwarding_format.replace('{', '《').replace('}', '》').replace('【', '{').replace('】', '}')

    def create_mcsm_instances_data(self):
        self.mcsm_instances_data = {
            k: McsmInstanceData(
                k, *v.split(':', 2)
            )
            for k, v in self.mcsm_instances.items()
        }
        self.mcsm_instances_list = list(self.mcsm_instances_data.values())

    def apply_forwarding_format(self, name: str, text: str) -> str:
        return self._message_forwarding_format.format(name=name, text=text).replace('《', '{').replace('》', '}')


shared.plugin_config = PluginConfig()
start_async_client()
