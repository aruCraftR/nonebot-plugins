
import base64
from io import BytesIO

import httpx
from PIL import Image
from PIL.ImageFile import ImageFile

from . import shared


class QQImage:
    clinet = httpx.AsyncClient()
    def __init__(self, url: str) -> None:
        self.url = url
        self._image = None
        self._base64 = None

    async def get_image(self) -> ImageFile:
        if self._image is None:
            self._image = Image.open(await self._get())
        return self._image

    async def _get(self) -> bytes:
        try:
            response = await self.clinet.get(self.url)
            return await response.aread()
        except Exception as e:
            shared.logger.error('图像下载失败')
            raise e
        finally:
            response.close()

    async def get_base64(self):
        if self._base64 is None:
            image = await self.get_image()
            image.thumbnail(shared.plugin_config.image_size_limit)
            bytes_io = BytesIO()
            image.save(bytes_io, 'jpeg', quality=shared.plugin_config.image_quality, subsampling=shared.plugin_config.image_subsampling)
            self._base64 = f'data:image/jpeg;base64,{base64.b64encode(bytes_io.getbuffer()).decode('utf-8')}'
        return self._base64
