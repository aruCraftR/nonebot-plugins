from typing import TYPE_CHECKING

from nonebot import logger as nb_logger
from nonebot.config import Config
from tiktoken import get_encoding as tiktoken_encoding

if TYPE_CHECKING:
    from . import config
    from loguru import Record

def __patcher(x: 'Record'):
    x['name'] = 'LLM'

nonebot_config: Config
plugin_config: 'config.PluginConfig'
tiktoken = tiktoken_encoding('cl100k_base')
logger = nb_logger.bind().patch(__patcher)