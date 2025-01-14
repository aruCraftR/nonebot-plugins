
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, Message
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg

from .config import DEFAULT
from .permission import permission_admin_group
from .api import AsyncMojangAPI, refresh_async_client
from . import shared


CMD_PREFIX = 'op'

HELP_MSG = \
"""aruCraftR插件命令列表(标有*的为管理员命令)
[...]: 选择其一 | <...>: 填入文本

{cmd} help | 获取帮助信息
{cmd} reload | 重载配置文件
{cmd} get uuid <玩家名> | 获取指定玩家的正版UUID""".format(cmd=CMD_PREFIX)

NORMAL_PERMISSION = PRIVATE_FRIEND | GROUP
ADMIN_PERMISSION = SUPERUSER | permission_admin_group


cmd_help = on_command(
    (CMD_PREFIX, 'help'),
    aliases={(CMD_PREFIX, 'h')},
    permission=ADMIN_PERMISSION
)

@cmd_help.handle()
async def print_help():
    await cmd_help.finish(HELP_MSG)


cmd_reload = on_command(
    (CMD_PREFIX, 'reload'),
    aliases={(CMD_PREFIX, 'r')},
    permission=ADMIN_PERMISSION
)

@cmd_reload.handle()
async def reload_config():
    try:
        shared.plugin_config.load_yaml()
        await refresh_async_client()
    except Exception as e:
        await cmd_reload.finish(f'aruCraftR插件配置重载失败: {repr(e)}')
    else:
        await cmd_reload.finish('ruCraftR插件配置重载成功')


cmd_get_uuid = on_command(
    (CMD_PREFIX, 'get', 'uuid'),
    aliases={(CMD_PREFIX, 'g', 'u')},
    permission=NORMAL_PERMISSION
)

@cmd_get_uuid.handle()
async def get_uuid(args: Message = CommandArg()):
    if name := args.extract_plain_text():
        player_info = await AsyncMojangAPI.get_online_uuid(name)
        await cmd_get_uuid.finish(f'玩家 {player_info.name} 的UUID为 {player_info.id}')
    else:
        await cmd_get_uuid.finish('请在命令末尾提供玩家名')
