
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot

from . import shared
from . import config

if shared.plugin_config.enable:
    from . import command
    from . import event
    from .functions import update_admin_id_set, update_member_data

    driver = get_driver()
    shared.nonebot_config = driver.config


    @driver.on_bot_connect
    async def on_bot_connect(bot: Bot):
        await update_admin_id_set(bot)
        await update_member_data(bot)
