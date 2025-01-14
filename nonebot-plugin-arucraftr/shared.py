from typing import TYPE_CHECKING

from nonebot import logger as nb_logger
from nonebot.config import Config
from tiktoken import get_encoding as tiktoken_encoding

if TYPE_CHECKING:
    from . import config
    from loguru import Record
    from .utils import MemberInfo

def __patcher(x: 'Record'):
    x['name'] = 'aruCraftR'

nonebot_config: Config
plugin_config: 'config.PluginConfig'
logger = nb_logger.bind().patch(__patcher)
admin_id_set = {}
member_info: dict[int, 'MemberInfo'] = {}
