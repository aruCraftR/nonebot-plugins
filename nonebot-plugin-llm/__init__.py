
import asyncio
from time import time

from nonebot import get_driver
# from pymilvus import MilvusClient

from . import shared
from . import config

if shared.plugin_config.enable:
    from . import command
    from . import message
    from .database import init_collection
    from .chat import get_chat_instances

    driver = get_driver()
    shared.nonebot_config = driver.config


    @driver.on_shutdown
    async def on_shutdown():
        shared.logger.info("正在保存数据，完成前请勿强制结束！")
        for i in get_chat_instances():
            i.history.save_pickle()
        shared.logger.info("保存完成！")


    @driver.on_startup
    async def on_startup():
        asyncio.run_coroutine_threadsafe(timed_storage(), asyncio.get_running_loop())


    async def timed_storage():
        while True:
            await asyncio.sleep(5)
            current_timestamp = time()
            for i in get_chat_instances():
                i.history.check_auto_save(current_timestamp)


# shared.db_client = MilvusClient(shared.plugin_config.milvus_server, timeout=shared.plugin_config.milvus_timeout)
# init_collection()
