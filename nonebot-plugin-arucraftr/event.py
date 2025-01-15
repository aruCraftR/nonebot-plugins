
from nonebot.plugin import on_message, on_notice, on_request
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, GroupIncreaseNoticeEvent, NoticeEvent, GroupDecreaseNoticeEvent, GroupRequestEvent, RequestEvent

from .rule import rule_forbidden_id, rule_available_message, rule_from_admin_group, rule_from_main_group
from .functions import update_admin_id_set, update_member_data
from .permission import permission_admin_group, permission_main_group
from .api import AsyncMcsmAPI
from . import shared
from .utils import get_user_name, uniform_chat_text


main_group_message = on_message(
    rule=rule_from_main_group & rule_forbidden_id & rule_available_message
)

admin_group_message = on_message(
    rule=rule_from_admin_group & rule_forbidden_id & rule_available_message
)

main_group_notice = on_notice(permission=permission_main_group, priority=5000, block=False)
main_group_request = on_request(permission=permission_main_group, priority=5000, block=False)
admin_group_notice = on_notice(permission=permission_admin_group, priority=5000, block=False)

@main_group_message.handle()
async def main_group_message_handler(event: MessageEvent, bot: Bot):
    if not (text := (await uniform_chat_text(event, bot)).text):
        return
    sender_name = await get_user_name(event, bot, event.user_id)
    json = shared.plugin_config.apply_forwarding_format(sender_name, text, group='QQ')
    if shared.plugin_config.debug:
        shared.logger.info(f'正在转发消息: {json}')
    for i in shared.plugin_config.mcsm_instances_list:
        try:
            await AsyncMcsmAPI.send_command(i, f'tellraw @a {json}')
        except Exception as e:
            shared.logger.warning(f'转发消息至{i.instance_aliase}时出现问题: {repr(e)}')


@admin_group_message.handle()
async def admin_group_message_handler(event: MessageEvent, bot: Bot):
    if not (text := (await uniform_chat_text(event, bot)).text):
        return
    sender_name = await get_user_name(event, bot, event.user_id)
    json = shared.plugin_config.apply_forwarding_format(sender_name, text, group='管理群')
    if shared.plugin_config.debug:
        shared.logger.info(f'正在转发消息: {json}')
    for i in shared.plugin_config.mcsm_instances_list:
        try:
            await AsyncMcsmAPI.send_command(i, f'tellraw @a[tag=admin] {json}')
        except Exception as e:
            shared.logger.warning(f'转发消息至{i.instance_aliase}时出现问题: {repr(e)}')


@main_group_notice.handle()
async def main_group_notice_handler(event: NoticeEvent, bot: Bot):
    if isinstance(event, (GroupIncreaseNoticeEvent, GroupDecreaseNoticeEvent)): # 群成员增加通知
        await update_member_data(bot)


@main_group_request.handle()
async def main_group_request_handler(event: RequestEvent):
    if isinstance(event, GroupRequestEvent):
        for i in shared.plugin_config.mcsm_instances_list:
            try:
                await AsyncMcsmAPI.send_command(i, [
                    'title @a[tag=admin] title "提醒"',
                    'title @a[tag=admin] subtitle "有新的入群申请待审批"',
                    'tellraw @a[tag=admin] {"text":"[QQ提醒] 有新的入群申请待审批","bold":true,"underlined":true,"color":"red"}'
                ])
            except Exception as e:
                shared.logger.warning(f'提醒入群申请到{i.instance_aliase}时出现问题: {repr(e)}')


@admin_group_notice.handle()
async def admin_group_notice_handler(event: NoticeEvent, bot: Bot):
    if isinstance(event, (GroupIncreaseNoticeEvent, GroupDecreaseNoticeEvent)): # 群成员增加通知
        await update_admin_id_set(bot)
