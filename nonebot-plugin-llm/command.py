
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, Message
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg

from .config import DEFAULT
from .chat import get_chat_instance, get_chat_instances
from . import shared
from .rule import rule_forbidden_id


CMD_PREFIX = 'llm'

HELP_MSG = \
"""LLM插件命令列表(标有*的为管理员命令)
{cmd} new | 重置当前会话记录

{cmd} help | *获取帮助信息
{cmd} reload | *重载全部配置文件
{cmd} info chat | *查看当前会话的记录情况
{cmd} change bot <bot_name> | *更改当前会话的机器人预设为<bot_name>
{cmd} discard bot <bot_name> | *将当前会话的机器人预设恢复为默认
{cmd} change model <model_name> | *更改当前会话的模型改为<model_name>
{cmd} discard model <model_name> | *将当前会话的模型恢复为默认
[注意: 全局操作仅对已加载的聊天实例生效]
{cmd} global new | *重置全部会话记录
{cmd} global info chat | *重置全部会话记录""".format(cmd=CMD_PREFIX)

NORMAL_PERMISSION = PRIVATE_FRIEND | GROUP


cmd_help = on_command(
    (CMD_PREFIX, 'help'),
    aliases={(CMD_PREFIX, 'h')},
    permission=SUPERUSER
)

@cmd_help.handle()
async def print_help():
    await cmd_help.finish(HELP_MSG)


cmd_reload = on_command(
    (CMD_PREFIX, 'reload'),
    aliases={(CMD_PREFIX, 'r')},
    permission=SUPERUSER
)

@cmd_reload.handle()
async def reload_config():
    try:
        shared.plugin_config.load_yaml()
        for i in get_chat_instances():
            i.config.load_yaml()
    except Exception as e:
        await cmd_reload.finish(f'LLM插件配置重载失败: {repr(e)}')
    else:
        await cmd_reload.finish('LLM插件配置重载成功')


cmd_clear_history = on_command(
    (CMD_PREFIX, 'new'),
    aliases={(CMD_PREFIX, 'n')},
    rule=rule_forbidden_id,
    permission=NORMAL_PERMISSION
)

@cmd_clear_history.handle()
async def clear_history(event: MessageEvent, bot: Bot):
    chat_instance = await get_chat_instance(cmd_clear_history, event, bot)
    chat_instance.clear_history()
    await cmd_clear_history.finish('已清除当前会话的历史记录')


cmd_global_new = on_command(
    (CMD_PREFIX, 'global', 'new'),
    aliases={(CMD_PREFIX, 'g', 'n')},
    permission=SUPERUSER
)

@cmd_global_new.handle()
async def global_new():
    count = 0
    for i in get_chat_instances():
        count += 1
        i.clear_history()
    await cmd_global_new.finish(f'已清除 {count} 个会话的历史记录')


cmd_change_bot = on_command(
    (CMD_PREFIX, 'change', 'bot'),
    aliases={(CMD_PREFIX, 'c', 'b')},
    permission=SUPERUSER
)

@cmd_change_bot.handle()
async def change_bot_name(event: MessageEvent, bot: Bot, args: Message = CommandArg()):
    chat_instance = await get_chat_instance(cmd_change_bot, event, bot)
    bot_name = args.extract_plain_text()
    if bot_name not in shared.plugin_config.system_prompts:
        await cmd_change_bot.finish(f'系统提示词预设 {bot_name} 不存在\n当前可用预设: {', '.join(shared.plugin_config.system_prompts.keys())}')
    chat_instance.config.set_value('bot_name', bot_name)
    await cmd_change_bot.finish(f'已切换到系统提示词预设 {bot_name}\n提示词内容: {chat_instance.config.system_prompt}')


cmd_discard_bot = on_command(
    (CMD_PREFIX, 'discard', 'bot'),
    aliases={(CMD_PREFIX, 'd', 'b')},
    permission=SUPERUSER
)

@cmd_discard_bot.handle()
async def discard_bot_name(event: MessageEvent, bot: Bot):
    chat_instance = await get_chat_instance(cmd_discard_bot, event, bot)
    chat_instance.config.set_value('bot_name', DEFAULT)
    await cmd_discard_bot.finish(f'已切换到默认系统提示词预设 {chat_instance.config.bot_name}\n提示词内容: {chat_instance.config.system_prompt}')


cmd_change_model = on_command(
    (CMD_PREFIX, 'change', 'model'),
    aliases={(CMD_PREFIX, 'c', 'm')},
    permission=SUPERUSER
)

@cmd_change_model.handle()
async def change_model_name(event: MessageEvent, bot: Bot, args: Message = CommandArg()):
    chat_instance = await get_chat_instance(cmd_change_model, event, bot)
    model_name = args.extract_plain_text()
    if model_name not in shared.plugin_config.models:
        await cmd_change_model.finish(f'模型名 {model_name} 不存在\n当前可用模型: {', '.join(shared.plugin_config.models.keys())}')
    chat_instance.config.set_value('bot_name', model_name)
    await cmd_change_model.finish(f'已切换到模型 {model_name}\n模型标识名: {chat_instance.config.model_identifier}')


cmd_discard_model = on_command(
    (CMD_PREFIX, 'discard', 'model'),
    aliases={(CMD_PREFIX, 'd', 'm')},
    permission=SUPERUSER
)

@cmd_discard_model.handle()
async def discard_model_name(event: MessageEvent, bot: Bot):
    chat_instance = await get_chat_instance(cmd_discard_model, event, bot)
    chat_instance.config.set_value('model_name', DEFAULT)
    await cmd_discard_model.finish(f'已切换到默认模型 {chat_instance.config.model_name}\n模型标识名: {chat_instance.config.model_identifier}')


cmd_info_chat = on_command(
    (CMD_PREFIX, 'info', 'chat'),
    aliases={(CMD_PREFIX, 'i', 'c')},
    permission=SUPERUSER
)

@cmd_info_chat.handle()
async def info_chat(event: MessageEvent, bot: Bot):
    chat_instance = await get_chat_instance(cmd_info_chat, event, bot)
    await cmd_info_chat.finish(
        f'对话标识符: {chat_instance.chat_key}\
        \n对话条数: {len(chat_instance.history.chat_history)}\
        \n对话Token数: {chat_instance.history.chat_history_token_count} / {chat_instance.history.chat_context_token_limit}\
        \n上下文条数: {len(chat_instance.history.other_history)}\
        \n上下文Token数: {chat_instance.history.other_history_token_count} / {chat_instance.history.other_context_token_limit}'
    )


cmd_global_info_chat = on_command(
    (CMD_PREFIX, 'global', 'info', 'chat'),
    aliases={(CMD_PREFIX, 'g', 'i', 'c')},
    permission=SUPERUSER
)

@cmd_global_info_chat.handle()
async def global_info_chat():
    msg = [
        f'{i.chat_key}: 对话数{len(i.history.chat_history)} {\
            f"上下文数{len(i.history.other_history)}" if i.is_group else "无上下文"\
        }' for i in get_chat_instances()
    ]
    msg.append(f'总计 {len(msg)} 个已加载会话')
    await cmd_global_info_chat.finish('\n'.join(msg))
