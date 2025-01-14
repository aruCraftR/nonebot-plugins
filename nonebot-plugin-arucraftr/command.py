
from traceback import print_exc
from uuid import UUID

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, Message
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg

from .permission import permission_admin_group
from .api import AsyncMojangAPI, refresh_async_client
from .functions import get_whitelist_json, update_admin_id_set, update_member_data
from . import shared


CMD_PREFIX = 'op'

HELP_MSG = \
"""aruCraftR插件命令列表(标有*的为管理员命令)
[...]: 选择其一 | <...>: 填入文本

{cmd} help | 获取帮助信息
{cmd} reload | 重载配置文件
{cmd} refresh | 刷新全部数据缓存
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


cmd_refresh = on_command(
    (CMD_PREFIX, 'refresh'),
    permission=ADMIN_PERMISSION
)

@cmd_refresh.handle()
async def refresh_data(bot):
    try:
        await update_admin_id_set(bot)
        await update_member_data(bot)
    except Exception as e:
        await cmd_refresh.finish(f'数据刷新失败: {repr(e)}')
    else:
        await cmd_refresh.finish('数据刷新成功')


cmd_get_uuid = on_command(
    (CMD_PREFIX, 'get', 'uuid'),
    aliases={(CMD_PREFIX, 'g', 'u')},
    permission=ADMIN_PERMISSION
)

@cmd_get_uuid.handle()
async def get_uuid(args: Message = CommandArg()):
    if name := args.extract_plain_text():
        player_info = await AsyncMojangAPI.get_online_uuid(name)
        await cmd_get_uuid.finish(f'玩家 {player_info.name} 的UUID为 {UUID(player_info.id)}')
    else:
        await cmd_get_uuid.finish('请在命令末尾提供玩家名')


cmd_get_whitelist = on_command(
    (CMD_PREFIX, 'get', 'whitelist'),
    aliases={(CMD_PREFIX, 'g', 'w')},
    permission=ADMIN_PERMISSION
)

@cmd_get_whitelist.handle()
async def get_whitelist(args: Message = CommandArg()):
    indent = None
    if user_indent := args.extract_plain_text():
        if user_indent.isdigit():
            indent = int(user_indent)
    await cmd_get_whitelist.send('正在从MojangAPI获取正版玩家信息, 请耐心等待')
    try:
        json, success, failure = await get_whitelist_json(indent)
    except Exception as e:
        print_exc()
        await cmd_get_whitelist.finish(f'出现错误: {repr(e)}')
    if success + failure == 0:
        await cmd_get_whitelist.finish('当前没有任何活跃玩家')
    if success == 0:
        await cmd_get_whitelist.finish('无法访问MojangAPI')
    await cmd_get_whitelist.finish(f'{json}\n包含了{success}个玩家, {failure}个玩家获取失败)')
