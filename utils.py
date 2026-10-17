"""
you may be wondering what the point of this utils thing is
unfortunately, pillow does not have built-in async support
fortunately, there is a module named aioEasyPillow
unfortunately, aioEasyPillow is absolute dog shit
fortunately, there is a module named easy-pil
unfortunately, easy-pil does not make pillow easier to use
fortunately, i rewrote it to be slightly less dog shit
unfortunately, im too lazy to code gif support
if you want gifs use esmbot or notsobot they are better bots
"""

from __future__ import annotations
import aiohttp, asyncio, functools, io, inspect, time, os, platform, magic, cv2, re, base64, json, numpy as np, torch, random
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from typing import List, Union, Tuple, Literal
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from scipy import ndimage
from dotenv import dotenv_values
environ = dotenv_values(".env")

from photo2pixel.models.module_photo2pixel import Photo2PixelModel
from photo2pixel.utils import img_common_util

DIRECTORY = os.path.dirname(__file__)
TESTING = platform.system() == "Windows"
FFMPEG = TESTING and os.path.join(DIRECTORY, "assets/ffmpeg.exe") or "/home/slave/bin/ffmpeg"
YT_DLP = TESTING and os.path.join(DIRECTORY, "assets/yt-dlp.exe") or "/usr/bin/yt-dlp"
TEMP_FOLDER = os.path.join(DIRECTORY, "TEMP")

mime = magic.Magic(mime=True)

def buffer_to_mimetype(buffer: io.BytesIO) -> str:
    mimetype = mime.from_buffer(buffer.read())
    buffer.seek(0)
    return mimetype

async def run_in_executor(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    partial_func = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial_func)
    
class Errors:
    FileNotFound = Exception("File not found")
    FileLarge = Exception("File failed to upload")
    InvalidParameter = Exception("Invalid parameter")

timeout = aiohttp.ClientTimeout(total=None)

def is_html_string(text: str) -> bool:
    return bool(re.compile(r"<[^>]+>").search(text))

def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))

def valid_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")

class Downloader:
    @classmethod
    def get_methods(self) -> List:
        methods = [method for method, _ in inspect.getmembers(self, predicate=inspect.isfunction)]
        return methods
    
    """
    async def youtube(url: str) -> io.BytesIO:
        async with aiohttp.ClientSession() as session:
            data = {
                "url": url,
                "capture_all": "on"
            }
            await session.post(f"https://web.archive.org/save/{url}", data=data)
        return url # f"https://web.archive.org/{url}"
    """

    # i hate this stupid ass domain, this triggers urls like roblox.com
    async def xcom(url: str) -> io.BytesIO:
        if "https://x.com" in url or "twitter.com" in url:
            headers = {
                #"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                try:
                    # new_url = "https://fixupx.com/" + url.split("/",3)[-1]
                    new_url = "https://fixupx.com/" + url.split("/",3)[-1]
                    try:
                        print("newurl", new_url)
                        async with session.get(new_url, allow_redirects=False) as resp:
                            resp = await resp.text()
                            soup = BeautifulSoup(resp, "html.parser")
                            if soup.find("meta", property="og:video"):
                                async with session.get(soup.find("meta", property="og:video").get("content")) as resp:
                                    return io.BytesIO(await resp.read())
                            elif soup.find("meta", property="og:image"):
                                async with session.get(soup.find("meta", property="og:image").get("content")) as resp:
                                    return io.BytesIO(await resp.read())
                    except Exception:
                        import traceback
                        print(traceback.format_exc())
                        if "twitter.com" in url:
                            new_url = url.replace("twitter.com", "unavatar.io/x")
                        else:
                            new_url = url.replace("x.com", "unavatar.io/x")
                        async with session.get(new_url) as resp:
                            return io.BytesIO(await resp.read())
                except Exception:
                    return url
        return url
    
    async def instagram2(url: str) -> io.BytesIO:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
            "Accept-Encoding": "gzip, deflate, br",
        }
        async with aiohttp.ClientSession(headers=headers) as session:   
            try:
                new_url = url.replace("instagram.com", "instagramfix.com")
                print(url, "->", new_url)
                async with session.get(new_url, headers=headers, ssl=False) as resp:
                    print(await resp.text())
                    content_type = resp.headers.get("Content-Type")
                    if "html" in content_type:
                        return url
                    if "video" not in content_type:
                        return url
                    return io.BytesIO(await resp.read())
            except Exception as err:
                print("instagram error:", err)
                return url
        return url
    
    async def discord(url: str) -> io.BytesIO:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"""Bot {environ.get("TOKEN")}""",}
                data = {"attachment_urls": [url]}
                async with session.post("https://discord.com/api/v9/attachments/refresh-urls", headers=headers, json=data) as resp:
                    resp.raise_for_status()
                    resp = json.loads(await resp.text())
                    async with session.get(resp.get("refreshed_urls")[0].get("refreshed")) as respones:
                        return io.BytesIO(await respones.read())
        except Exception:
            return url
    
    async def tenor(url: str) -> io.BytesIO:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                resp = await response.text()
                soup = BeautifulSoup(resp, "html.parser")
                if soup.find("meta", property="og:url"):
                    async with session.get(soup.find("meta", property="og:url").get("content")) as resp:
                        return io.BytesIO(await resp.read())
    
    async def giphy(url: str) -> io.BytesIO:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                resp = await response.text()
                soup = BeautifulSoup(resp, "html.parser")
                async with session.get(soup.find_all("meta", attrs={"property": "og:image"})[-1].get("content")) as resp:
                    return io.BytesIO(await resp.read())
    
    async def pinterest(url: str) -> io.BytesIO:
        async with aiohttp.ClientSession() as session:
            for i in range(10):
                try:
                    async with session.get(url) as response:
                        resp = await response.text()
                        soup = BeautifulSoup(resp, "html.parser")
                        async with session.get(soup.find("meta", property="og:image").get("content")) as resp:
                            return io.BytesIO(await resp.read())
                except Exception:
                    await asyncio.sleep(0.5)
    
    async def roblox(url: str) -> io.BytesIO:
        pattern = r"/(?:catalog|library|asset)/(\d+)"
        match = re.search(pattern, url)
        assetId = match is not None and match.group(1) or 0
        url = f"https://thumbnails.roblox.com/v1/assets?assetIds={assetId}&returnPolicy=PlaceHolder&size=150x150&format=Png&isCircular=false"
        # cookies={".ROBLOSECURITY": environ.get("ROBLOX")}
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.roblox.com//") as response:
                headers = {"x-csrf-token": response.headers.get("x-csrf-token")}
                async with session.get(url, headers=headers) as response:
                    resp = json.loads(await response.text())
                    async with session.get(str(resp.get("data")[0].get("imageUrl")).replace("/150/150/", "/720/720/")) as resp:
                        return io.BytesIO(await resp.read())
    
    async def twitter(url: str) -> io.BytesIO:
        return await Downloader.xcom(url)

class Driver:
    def __init__(self) -> Driver:
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        # driver = webdriver.Firefox(options=options)
        if platform.system() == "Windows":
            driver = webdriver.Firefox(options=options)
        else:
            driver = webdriver.Firefox(executable_path="/usr/bin/geckodriver", options=options)
        self.driver = driver
    
    async def get(self, url: str):
        return await run_in_executor(self.__get, url)
    
    def __get(self, url: str):
        self.driver.get(url)
    
    async def quit(self):
        return await run_in_executor(self.__quit)
    
    def __quit(self):
        self.driver.quit()
    
    async def find(self, by: By, name: str):
        start = time.time()
        while True:
            if time.time() - start > 10:
                element = None
                break
            element = await run_in_executor(self.__find, by, name)
            if element:
                break
            await asyncio.sleep(0)
        return element

    def __find(self, by: By, name: str):
        element = self.driver.find_element(by, name)
        return element
    
    async def send_keys(self, element, value: str):
        return await run_in_executor(self.__send_keys, element, value)

    def __send_keys(self, element, value: str):
        element.send_keys(value)
    
    async def click(self, element):
        return await run_in_executor(self.__click, element)

    def __click(self, element):
        element.click()


class Canvas:
    def __init__(
        self,
        size: Tuple[float, float] = None,
        width: float = None,
        height: float = None,
        color: Union[Tuple[int, int, int], str, int] = None,
    ) -> None:
        if not size and not width and not height:
            raise ValueError('size, width, and height cannot all be None')

        if width and height:
            size = (width, height)

        self.size = size
        self.color = color

        self.image: Image.Image = Image.new("RGBA", size, color=color)


class Editor:
    def __init__(self, image: Union[Image.Image, str, io.BytesIO, Editor, Canvas] = None) -> None:
        if image is None:
            self.image: Image.Image = Image.new("RGBA", (1, 1))
        else:
            if isinstance(image, str) or isinstance(image, io.BytesIO):
                self.image: Image.Image = Image.open(image)
            elif isinstance(image, Canvas) or isinstance(image, Editor):
                self.image: Image.Image = image.image
            else:
                self.image: Image.Image = image
            self.image: Image.Image = self.image.convert("RGBA")

    @property
    def image_bytes(self) -> io.BytesIO:
        buffer = io.BytesIO()
        self.image.save(buffer, format="png")
        buffer.seek(0)
        return buffer
    
    @property
    def b64(self) -> str:
        buffer = self.image_bytes
        img_byte_data = buffer.getvalue()
        base64_encoded = base64.b64encode(img_byte_data)
        base64_string = base64_encoded.decode("utf-8")
        return base64_string
    
    @property
    def palette(self) -> List[List[int, int, int]]:
        palette = self.image.getpalette()
        return [palette[i:i+3] for i in range(0, len(palette), 3)]

    async def convert(self, mode: str) -> Editor:
        return await run_in_executor(self.__convert, mode)

    def __convert(self, mode: str) -> Editor:
        self.image = self.image.convert(mode)
        return self

    async def copy(self, image: Union[Image.Image, str, io.BytesIO, Editor, Canvas]) -> Editor:
        return await run_in_executor(self.__copy, image)

    def __copy(self, image: Union[Image.Image, Editor, Canvas]) -> Editor:
        if isinstance(image, Editor):
            image = image.image
        self.image = image.copy()
        return self
    
    async def load(self, source: str | io.BytesIO, color: Tuple[int, int, int, int] = None, ignore_recolor: bool = False) -> Editor:
        async with aiohttp.ClientSession() as session:
            if isinstance(source, str):
                if valid_url(source):
                    async with session.get(source) as resp:
                        buffer = io.BytesIO(await resp.read())
                        mimetype = buffer_to_mimetype(buffer)
                        if "video" in mimetype:
                            buffer = await self.capture(source)
                else:
                    if source.startswith("data:") and "base64" in source:
                        source = source.split(",", 1)[1]
                    decoded = base64.b64decode(source)
                    buffer = io.BytesIO(decoded)
            else:
                buffer = source
            return await run_in_executor(self.__load, buffer, color, ignore_recolor)

    def __load(self, buffer: Union[io.BytesIO], color: Tuple[int, int, int, int] = None, ignore_recolor: bool = False) -> Editor:
        overlay = Image.open(buffer).convert("RGBA")
        with Image.new("RGBA", size=overlay.size, color=color or (0, 0, 0, 0)) as blank:
            if ignore_recolor == False:
                for x in range(overlay.width):
                    for y in range(overlay.height):
                        pixel = overlay.getpixel((x, y))
                        if 0 < pixel[-1] < 255:
                            overlay.putpixel((x, y), pixel[:3] + (255,))
            blank.paste(overlay, (0, 0), overlay)
        self.image = blank
        return self
    
    async def sidebyside(self, sources: List[Editor]) -> Editor:
        try:
            height = min([source.image.height for source in sources])
            for source in sources:
                await source.thumbnail((height, height))
            widths = [source.image.width for source in sources]
            width = sum(widths)
            await self.resize((width, height))
            position = 0
            for source in sources:
                index = sources.index(source)
                await self.paste(source, (position, 0))
                position = position + widths[index]
            return self
        except Exception as err:
            print("ERROR LOL", err)

    
    async def capture(self, source: str, replace: bool = False):
        return await run_in_executor(self.__capture, source, replace)
    
    def __capture(self, source: str, replace: bool = False):
        capture = cv2.VideoCapture(source)
        success, frame = capture.read()
        capture.release()
        
        if not success:
            raise Exception("Failed to read the first frame")

        buffer = io.BytesIO(cv2.imencode(".jpg", frame)[1])
        
        if replace:
            self = self.__load(buffer)
        else:
            return buffer
    
    async def paste(
            self,
            image: Union[Image.Image, Editor, Canvas],
            position: Tuple[float, float] = (0,0),
            mask: Union[Image.Image, Editor] = None
    ) -> Editor:
        return await run_in_executor(self.__paste, image, position, mask)

    def __paste(
            self,
            image: Union[Image.Image, Editor, Canvas],
            position: Tuple[float, float] = (0,0),
            mask: Union[Image.Image, Editor] = None
    ) -> Editor:
        blank = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        if isinstance(image, Editor) or isinstance(image, Canvas):
            image = image.image
        if mask and isinstance(mask, Editor):
            mask = mask.image
        blank.paste(image, position, mask)
        self.image = Image.alpha_composite(self.image, blank)
        return self

    async def show(self):
        await run_in_executor(self.__show)

    def __show(self):
        self.image.show()

    async def save(self, fp, format: str = None, **params):
        await run_in_executor(self.__save, fp, format, **params)

    def __save(self, fp, format: str = "png", **params):
        self.image.save(fp, format, **params)

    async def resize(self, size: Tuple[float, float], crop: bool = False, resample: bool = True) -> Editor:
        return await run_in_executor(self.__resize, size, crop=crop, resample=resample)

    def __resize(self, size: Tuple[float, float], crop=False, resample: bool = True) -> Editor:
        if not crop:
            if resample:
                self.image = self.image.resize(size, resample=0)
            else:
                self.image = self.image.resize(size)
        else:
            width, height = self.image.size
            ideal_width, ideal_height = size

            aspect = width / float(height)
            ideal_aspect = ideal_width / float(ideal_height)

            if aspect > ideal_aspect:
                new_width = int(ideal_aspect * height)
                offset = (width - new_width) / 2
                resize = (offset, 0, width - offset, height)
            else:
                new_height = int(width / ideal_aspect)
                offset = (height - new_height) / 2
                resize = (0, offset, width, height - offset)
            if resample:
                self.image = self.image.crop(resize).resize((ideal_width, ideal_height), resample=0)
            else:
                self.image = self.image.crop(resize).resize((ideal_width, ideal_height))
        return self

    async def crop(self, region: Tuple[float, float, float, float]) -> Editor:
        return await run_in_executor(self.__crop, region)

    def __crop(self, region: Tuple[float, float, float, float]) -> Editor:
        if len(region) > 2:
            self.image = self.image.crop(region)
        else:
            left = (self.image.width - region[0]) // 2
            top = (self.image.height - region[1]) // 2
            right = (self.image.width + region[0]) // 2
            bottom = (self.image.height + region[1]) // 2
            self.image = self.image.crop((left, top, right, bottom))
        return self

    async def thumbnail(self, size: Tuple[int, int]) -> Editor:
        return await run_in_executor(self.__thumbnail, size)

    def __thumbnail(self, size: Tuple[int, int]) -> Editor:
        self.image.thumbnail(size)
        return self

    async def trim(self) -> Editor:
        return await run_in_executor(self.__trim)

    def __trim(self) -> Editor:
        self.image = self.image.crop(self.image.getbbox())
        return self

    async def bleed(self) -> Editor:
        return await run_in_executor(self.__bleed)

    def __bleed(self) -> Editor:
        img_arr = np.array(self.image)
        rgba = img_arr.copy()
        alpha = rgba[..., 3]
        opaque_mask = (alpha >= 254)
        if np.any(opaque_mask):
            dist, indices = ndimage.distance_transform_edt(~opaque_mask, return_indices=True)
            for y in range(alpha.shape[0]):
                for x in range(alpha.shape[1]):
                    if alpha[y, x] < 254:
                        ny, nx = indices[0, y, x], indices[1, y, x]
                        rgba[y, x, :3] = rgba[ny, nx, :3]
                        rgba[y, x, 3] = 255
        self.image = Image.fromarray(rgba, "RGBA")
        return self

    async def rounded_corners(self, radius: int = 10, offset: int = 2) -> Editor:
        return await run_in_executor(self.__rounded_corners, radius, offset)

    def __rounded_corners(self, radius: int = 10, offset: int = 2) -> Editor:
        background = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        holder = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        mask = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (offset, offset) + (self.image.size[0] - offset, self.image.size[1] - offset),
            radius=radius,
            fill="black",
        )
        holder.paste(self.image, (0, 0))
        self.image = Image.composite(holder, background, mask)
        return self


    async def circle(self) -> Editor:
        return await run_in_executor(self.__circle)

    def __circle(self) -> Editor:
        background = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        holder = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        mask = Image.new("RGBA", size=self.image.size, color=(255, 255, 255, 0))
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0) + self.image.size, fill="black")
        holder.paste(self.image, (0, 0))
        self.image = Image.composite(holder, background, mask)
        return self

    async def rotate(self, deg: float = 0, expand: bool = False) -> Editor:
        return await run_in_executor(self.__rotate, deg, expand)

    def __rotate(self, deg: float = 0, expand: bool = False) -> Editor:
        self.image = self.image.rotate(angle=deg, expand=expand)
        return self


    async def blur(self, mode: Literal['box', 'gaussian'] = 'box', radius: float = 1) -> Editor:
        return await run_in_executor(self.__blur, mode, radius)

    def __blur(self, mode: Literal['box', 'gaussian'] = 'box', radius: float = 1) -> Editor:
        if mode == 'box':
            self.image = self.image.filter(ImageFilter.BoxBlur(radius=radius))
        if mode == 'gaussian':
            self.image = self.image.filter(ImageFilter.GaussianBlur(radius=radius))
        return self


    async def blend(
            self, image: Union[Image.Image, Editor, Canvas], alpha: float = 0.0, on_top: bool = False
    ) -> Editor:
        return await run_in_executor(self.__blend, image, alpha, on_top)

    def __blend(
            self, image: Union[Image.Image, Editor, Canvas], alpha: float = 0.0, on_top: bool = False
    ) -> Editor:
        if isinstance(image, Editor) or isinstance(image, Canvas):
            image = image.image
        if image.size != self.image.size:
            image = Editor(image).resize(self.image.size, crop=True).image
        if on_top:
            self.image = Image.blend(self.image, image, alpha=alpha)
        else:
            self.image = Image.blend(image, self.image, alpha=alpha)
        return self


    async def pixelate(self, width: int = None, height: int = None, resample: bool = True) -> Editor:
        return await run_in_executor(self.__pixelate, width, height, resample)

    def __pixelate(self, width: int = 16, height: int = None, resample: bool = True) -> Editor:
        if height is None:
            height = width
        width = clamp(width, 1, 256)
        height = clamp(height, 1, 256)
        
        if resample == True:
            self.image = self.image.resize((width, height), Image.Resampling.NEAREST)
        else:
            self.image = self.image.resize((width, height))
        self.image = self.image.resize((width * 5, height * 5), resample=0)
        
        original_width, original_height = self.image.size
        aspect_ratio = original_width / original_height
        
        if original_width > 512 or original_height > 512:
            if original_width > original_height:
                new_width = 512
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = 512
                new_width = int(new_height * aspect_ratio)
            self.image = self.image.resize((new_width, new_height), resample=0)
        return self
    
    async def reduce_colors(self, colors: int = None):
        return await run_in_executor(self.__reduce_colors, colors)
    
    def __reduce_colors(self, colors: int = 10):
        # self.image = ImageEnhance.Brightness(self.image).enhance(enhancement)
        self.image = self.image.convert("P", palette=Image.ADAPTIVE, colors=colors)
        return self
    
    # Async wrapper
    async def stroke(self, threshold: int = 0, thickness: int = 10, color: tuple = (0,0,0)) -> 'Editor':
        return await run_in_executor(self.__stroke, threshold, thickness, color)

    # Synchronous implementation
    def __stroke(self, threshold: int = 0, thickness: int = 10, color: tuple = (0,0,0)) -> 'Editor':
        img = np.array(self.image)
        h, w, _ = img.shape
        padding = thickness + 50
        alpha = img[:, :, 3]
        rgb_img = img[:, :, 0:3]

        bigger_img = cv2.copyMakeBorder(rgb_img, padding, padding, padding, padding, 
                                        cv2.BORDER_CONSTANT, value=(0,0,0))
        alpha = cv2.copyMakeBorder(alpha, padding, padding, padding, padding, 
                                cv2.BORDER_CONSTANT, value=0)
        bigger_img = cv2.merge((bigger_img, alpha))

        _, alpha_without_shadow = cv2.threshold(alpha, threshold, 255, cv2.THRESH_BINARY)
        alpha_without_shadow = 255 - alpha_without_shadow

        dist = cv2.distanceTransform(alpha_without_shadow, cv2.DIST_L2, cv2.DIST_MASK_3)

        stroke_matrix = np.ones(dist.shape)
        check_size = thickness
        stroke_matrix[dist > check_size] = 0
        border = (dist > thickness-1) & (dist <= check_size)
        stroke_matrix[border] = 1.0 - (dist[border] - (thickness-1))

        stroke_alpha = (stroke_matrix*255).astype(np.uint8)

        stroke_b = np.full((h+2*padding, w+2*padding), color[2], np.uint8)
        stroke_g = np.full((h+2*padding, w+2*padding), color[1], np.uint8)
        stroke_r = np.full((h+2*padding, w+2*padding), color[0], np.uint8)
        stroke_img = cv2.merge((stroke_b, stroke_g, stroke_r, stroke_alpha))

        stroke_img = Image.fromarray(stroke_img.astype("uint8"))
        bigger_img = Image.fromarray(bigger_img.astype("uint8"))

        result = Image.alpha_composite(stroke_img, bigger_img)
        result = result.crop((padding, padding, padding+w, padding+h))
        self.image = result
        return self
    
    async def to_tensor(self) -> torch.Tensor:
        return await run_in_executor(img_common_util.convert_image_to_tensor, self.image)

    # Converts a tensor back to Editor format
    @classmethod
    async def from_tensor(cls, tensor: torch.Tensor) -> 'Editor':
        img = await run_in_executor(img_common_util.convert_tensor_to_image, tensor)
        return cls(img)

    # Runs Photo2Pixel on this image
    async def run_photo2pixel(
            self,
            kernel_size: int = 8,
            pixel_size: int = 4,
            edge_threshold: int = 128,
            target_blocks: tuple[int,int] = (64,64),
            crop_to_target_ratio: bool = False,
            upscale: int = 4
        ) -> 'Editor':

        img = self.image.copy()

        # Crop to content
        img = img.crop(img.getbbox())

        orig_width, orig_height = img.size

        # Resize/crop to target
        if crop_to_target_ratio:
            target_ratio = target_blocks[0] / target_blocks[1]
            orig_ratio = orig_width / orig_height
            if orig_ratio > target_ratio:
                new_width = int(orig_height * target_ratio)
                left = (orig_width - new_width) // 2
                img = img.crop((left, 0, left + new_width, orig_height))
            else:
                new_height = int(orig_width / target_ratio)
                top = (orig_height - new_height) // 2
                img = img.crop((0, top, orig_width, top + new_height))
            new_blocks = target_blocks
        else:
            max_blocks = max(target_blocks)
            if orig_width >= orig_height:
                new_width = max_blocks * pixel_size
                new_height = int(orig_height / orig_width * new_width)
            else:
                new_height = max_blocks * pixel_size
                new_width = int(orig_width / orig_height * new_height)
            img = img.resize((new_width, new_height), Image.Resampling.NEAREST)
            new_blocks = (new_width // pixel_size, new_height // pixel_size)

        # Convert to tensor
        tensor_input = await run_in_executor(img_common_util.convert_image_to_tensor, img)

        # Run model
        model = Photo2PixelModel()
        model.eval()
        def model_forward():
            with torch.no_grad():
                return model(tensor_input, param_kernel_size=kernel_size,
                            param_pixel_size=pixel_size,
                            param_edge_thresh=edge_threshold)
        tensor_output = await run_in_executor(model_forward)

        # Convert back to Editor
        editor_output = await Editor.from_tensor(tensor_output)

        # Optional upscale
        if upscale > 1:
            editor_output.image = editor_output.image.resize(
                (new_blocks[0] * upscale, new_blocks[1] * upscale),
                Image.NEAREST
            )

        return editor_output


# ============================================================================
# IMPROVED PHOTO2PIXEL ALGORITHM (standalone, numpy + PIL only)
# ============================================================================

def _box_sum_strided(arr, k, stride):
    """Zero-padded box sum over k x k windows sampled every `stride` pixels."""
    pad = (k - 1) // 2
    ap = np.pad(arr, ((pad, pad), (pad, pad)), mode="constant")
    hp, wp = ap.shape
    ho = (hp - k) // stride + 1
    wo = (wp - k) // stride + 1
    out = np.zeros((ho, wo), dtype=np.float64)
    for dy in range(k):
        ys = dy + (ho - 1) * stride + 1
        for dx in range(k):
            xs = dx + (wo - 1) * stride + 1
            out += ap[dy:ys:stride, dx:xs:stride]
    return out


def _binary_erode(mask, k):
    """True only where the full k x k neighborhood is also True."""
    pad = (k - 1) // 2
    ap = np.pad(mask.astype(np.float64), ((pad, pad), (pad, pad)), mode="constant", constant_values=0)
    h, w = mask.shape
    out = np.zeros((h, w), dtype=np.float64)
    for dy in range(k):
        for dx in range(k):
            out += ap[dy:dy + h, dx:dx + w]
    return out >= k * k


def _binary_dilate(mask, k):
    """True if any pixel in the k x k neighborhood is True."""
    pad = (k - 1) // 2
    ap = np.pad(mask.astype(np.float64), ((pad, pad), (pad, pad)), mode="constant", constant_values=0)
    h, w = mask.shape
    out = np.zeros((h, w), dtype=np.float64)
    for dy in range(k):
        for dx in range(k):
            out += ap[dy:dy + h, dx:dx + w]
    return out > 0


def detect_outline_mask(arr_rgb, dark_threshold=60, open_kernel=3, max_saturation=40):
    """
    Separate thin outline strokes from real solid-black content using
    morphological opening. Outlines disappear under erosion (they're thin),
    solid black regions survive.

    dark_threshold: permissive brightness cutoff, catches outlines AND real blacks
    open_kernel: structuring element size in pixels, roughly the outline
                 stroke width (or slightly above it).
                 Too small -> thick outlines misclassified as real black.
                 Too large -> thin real-black details misclassified as outline.
    max_saturation: dark pixels with more color spread than this (max-min channel)
                 are treated as colored shading, not outline, even if dark.
                 Prevents dark navy/maroon/shadow areas from being eaten.
    """
    mean = arr_rgb.mean(axis=2)
    chan_max = arr_rgb.max(axis=2)
    chan_min = arr_rgb.min(axis=2)
    saturation_spread = chan_max - chan_min

    dark_mask = (mean < dark_threshold) & (saturation_spread < max_saturation)

    eroded = _binary_erode(dark_mask, open_kernel)   # kills anything thinner than open_kernel
    opened = _binary_dilate(eroded, open_kernel)      # restores surviving blobs to original size

    outline_mask = dark_mask & ~opened     # dark but didn't survive erosion = thin = outline
    solid_black_mask = dark_mask & opened  # dark and survived erosion = real black content
    return outline_mask, solid_black_mask


def compute_edge_proximity_mask(alpha, max_distance=2, alpha_threshold=128):
    """
    Boolean mask (same shape as alpha) marking opaque pixels within
    `max_distance` (8-connected) pixels of a transparent pixel. Only pixels
    near the silhouette edge are candidates for black-pixel correction,
    interior dark linework (eyes, nose, mouth, shading) is real content and
    should be left alone regardless of how dark it is.
    """
    transparent = alpha < alpha_threshold
    near_edge = transparent.copy()
    frontier = transparent.copy()
    h, w = alpha.shape
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    for _ in range(max_distance):
        if not frontier.any():
            break
        new_frontier = np.zeros_like(frontier)
        ys, xs = np.where(frontier)
        for y, x in zip(ys, xs):
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not near_edge[ny, nx]:
                    new_frontier[ny, nx] = True
                    near_edge[ny, nx] = True
        frontier = new_frontier

    return near_edge & ~transparent  # only opaque pixels within range count as "near edge"


def resize_premultiplied(img, target_size, resample=Image.Resampling.BILINEAR):
    """
    Resize an RGBA image without letting background color bleed into
    foreground edges. A normal resize blends RGB directly, so a fully
    transparent background pixel next to an opaque foreground pixel still
    contributes its raw color to the interpolated result, that's the
    source of the muddy edge fringe. Premultiplying RGB by alpha before
    resizing makes transparent pixels contribute zero regardless of what
    color they happen to store, then un-premultiplying afterward restores
    correct color for the pixels that are actually visible.
    """
    img = img.convert("RGBA")
    arr = np.array(img).astype(np.float64)

    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4]
    premultiplied_rgb = rgb * (alpha / 255.0)

    premult_img = Image.fromarray(
        np.concatenate([premultiplied_rgb, alpha], axis=2).astype(np.uint8), "RGBA"
    )
    resized = premult_img.resize(target_size, resample)

    r_arr = np.array(resized).astype(np.float64)
    r_rgb = r_arr[:, :, :3]
    r_alpha = r_arr[:, :, 3:4]

    safe_alpha = np.where(r_alpha < 1, 1, r_alpha)  # avoid divide-by-zero on fully transparent pixels
    unpremultiplied_rgb = np.clip(r_rgb / (safe_alpha / 255.0), 0, 255)
    # fully transparent pixels have no meaningful color, leave them black rather than noisy
    unpremultiplied_rgb = np.where(r_alpha < 1, 0, unpremultiplied_rgb)

    out = np.concatenate([unpremultiplied_rgb, r_alpha], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def pixel_effect(rgb, num_bins, kernel_size, pixel_size, outline_mask=None, low_alpha_mask=None, min_fraction=0.15):
    """
    Pixelate by box-averaging the dominant brightness bin in each window.

    Two kinds of pixels are excluded from the color vote entirely:
    - outline_mask: thin dark line-art strokes, so they can't hijack a
      window's dominant color.
    - low_alpha_mask: pixels with low opacity. After a bilinear resize,
      pixels right at a transparency boundary often carry leftover
      background color blended in even though they're mostly transparent.
      Counting them muddies the result with background color. Excluding
      them keeps the vote restricted to genuinely solid foreground pixels.

    A window only counts as genuinely "all outline" (true solid-black
    region) if every excluded pixel in it is outline (not low-alpha) and
    none of it is non-excluded. Anything in between, mostly excluded but
    with a handful of real pixels left, is flagged as low-confidence
    instead of trusting those few leftover pixels. Low-confidence cells
    get filled in later from neighboring grid cells.

    min_fraction: fraction of a window's pixels that must be valid
                  (non-excluded) before the color vote is trusted.
    """
    mean = rgb.mean(axis=2)
    idx = np.clip((mean / 256.0 * num_bins).astype(np.int64), 0, num_bins - 1)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    if outline_mask is None:
        outline_mask = np.zeros(mean.shape, dtype=bool)
    if low_alpha_mask is None:
        low_alpha_mask = np.zeros(mean.shape, dtype=bool)

    exclude_mask = outline_mask | low_alpha_mask
    not_excluded = (~exclude_mask).astype(np.float64)

    cnt, r_sum, g_sum, b_sum = [], [], [], []
    for bin_i in range(num_bins):
        m = (idx == bin_i).astype(np.float64) * not_excluded
        cnt.append(_box_sum_strided(m, kernel_size, pixel_size))
        r_sum.append(_box_sum_strided(r * m, kernel_size, pixel_size))
        g_sum.append(_box_sum_strided(g * m, kernel_size, pixel_size))
        b_sum.append(_box_sum_strided(b * m, kernel_size, pixel_size))

    cnt = np.stack(cnt)
    r_sum, g_sum, b_sum = np.stack(r_sum), np.stack(g_sum), np.stack(b_sum)

    total_valid = _box_sum_strided(not_excluded, kernel_size, pixel_size)
    window_size = float(kernel_size * kernel_size)

    arg = np.argmax(cnt, axis=0)
    yy, xx = np.indices(arg.shape)
    cmax = np.clip(np.maximum(cnt[arg, yy, xx], 1), 1, None)
    out_r = np.floor(r_sum[arg, yy, xx] / cmax + 0.5)
    out_g = np.floor(g_sum[arg, yy, xx] / cmax + 0.5)
    out_b = np.floor(b_sum[arg, yy, xx] / cmax + 0.5)
    grid = np.stack([out_r, out_g, out_b], axis=-1)

    # windows with zero valid pixels: if it's genuine solid-black outline content
    # (opaque, just dark), recover its color from the outline pixels alone, ignoring
    # any low-alpha background fringe so the fallback can't get muddied either
    all_excluded = total_valid < 1
    recovered_as_outline = np.zeros_like(all_excluded)
    if all_excluded.any():
        m = (outline_mask & ~low_alpha_mask).astype(np.float64)
        cnt_o = _box_sum_strided(m, kernel_size, pixel_size)
        r_o = _box_sum_strided(r * m, kernel_size, pixel_size)
        g_o = _box_sum_strided(g * m, kernel_size, pixel_size)
        b_o = _box_sum_strided(b * m, kernel_size, pixel_size)
        has_outline_color = cnt_o > 0
        use_fallback = all_excluded & has_outline_color
        cmax_o = np.clip(np.maximum(cnt_o, 1), 1, None)
        grid[use_fallback, 0] = np.floor(r_o[use_fallback] / cmax_o[use_fallback] + 0.5)
        grid[use_fallback, 1] = np.floor(g_o[use_fallback] / cmax_o[use_fallback] + 0.5)
        grid[use_fallback, 2] = np.floor(b_o[use_fallback] / cmax_o[use_fallback] + 0.5)
        recovered_as_outline = use_fallback

    # everything else with too little real signal (incl. windows that were all
    # low-alpha with no outline color to fall back on): flag for neighbor fill
    low_confidence = (total_valid < window_size * min_fraction) & ~recovered_as_outline

    return np.clip(grid, 0, 255), low_confidence


def fill_low_confidence_cells(grid, low_confidence, passes=6):
    """
    Replace flagged low-confidence cells with the average of their reliable
    neighbors, iterating outward so fills propagate sensibly instead of
    leaving (or creating) dark gaps.
    """
    if not low_confidence.any():
        return grid

    grid = grid.copy()
    unresolved = low_confidence.copy()
    h, w = unresolved.shape
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

    for _ in range(passes):
        if not unresolved.any():
            break
        ys, xs = np.where(unresolved)
        still_unresolved = np.zeros_like(unresolved)
        for y, x in zip(ys, xs):
            samples = []
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not unresolved[ny, nx]:
                    samples.append(grid[ny, nx])
            if samples:
                grid[y, x] = np.mean(samples, axis=0)
            else:
                still_unresolved[y, x] = True
        unresolved = still_unresolved

    return grid


def process_alpha_channel(alpha_small, gw, gh, target_w, target_h, threshold):
    """Process alpha like Lua does: sample from center of each grid cell, harden to binary."""
    alpha = np.array(alpha_small)
    pixel_size = target_w / gw
    
    alpha_out = np.zeros((gh, gw), dtype=np.uint8)
    for gy in range(gh):
        for gx in range(gw):
            sx = int(gx * pixel_size + pixel_size / 2)
            sy = int(gy * pixel_size + pixel_size / 2)
            sx = np.clip(sx, 0, target_w - 1)
            sy = np.clip(sy, 0, target_h - 1)
            
            sample = alpha[sy, sx] if sy < alpha.shape[0] and sx < alpha.shape[1] else 0
            alpha_out[gy, gx] = 255 if sample >= threshold else 0
    
    return alpha_out


def count_unique_colors(rgb, opaque):
    """Number of distinct RGB colours among the opaque pixels."""
    cols = rgb[opaque]
    if cols.shape[0] == 0:
        return 0
    return int(np.unique(cols.reshape(-1, 3), axis=0).shape[0])


_QUANT_METHODS = {
    "mediancut": Image.Quantize.MEDIANCUT,
    "maxcoverage": Image.Quantize.MAXCOVERAGE,
    "fastoctree": Image.Quantize.FASTOCTREE,
}


def limit_palette(grid8, opaque, n, dither=False, method="mediancut"):
    """Reduce the opaque pixels to at most `n` colours."""
    if n is None:
        return grid8
    cols = grid8[opaque]
    if cols.shape[0] == 0:
        return grid8
    if np.unique(cols.reshape(-1, 3), axis=0).shape[0] <= n:
        return grid8

    quant_method = _QUANT_METHODS.get(method, Image.Quantize.MEDIANCUT)

    pal_src = Image.fromarray(cols.reshape(-1, 1, 3), "RGB")
    pal = pal_src.quantize(colors=n, method=quant_method, dither=Image.Dither.NONE)

    work = grid8.copy()
    if (~opaque).any():
        work[~opaque] = cols.reshape(-1, 3).mean(axis=0).round().astype(np.uint8)
    mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quant = Image.fromarray(work, "RGB").quantize(palette=pal, dither=mode).convert("RGB")

    out = grid8.copy()
    out[opaque] = np.array(quant)[opaque]
    return out


def has_real_alpha(img):
    """True if the image actually carries transparency."""
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        return alpha.getextrema()[0] < 255
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False


def trim_border(img, transparent, tolerance):
    """Crop away the surrounding empty border."""
    if transparent:
        bbox = img.getchannel("A").getbbox()
    else:
        rgb = img.convert("RGB")
        bg = rgb.getpixel((0, 0))
        bg_img = Image.new("RGB", rgb.size, bg)
        diff = ImageChops.difference(rgb, bg_img)
        diff = ImageChops.add(diff, diff, scale=1.0, offset=-tolerance)
        bbox = diff.getbbox()

    return img.crop(bbox) if bbox else img


def resolve_grid_size(src_w, src_h, cfg):
    """Decide the art-grid (gw, gh) in art pixels from the config rules."""
    w, h = cfg.get("width"), cfg.get("height")
    aspect = src_w / src_h

    if w is not None and h is not None:
        gw, gh = w, h
    elif w is not None:
        gw, gh = w, int(w / aspect + 0.5)
    elif h is not None:
        gw, gh = int(h * aspect + 0.5), h
    else:
        long_edge = min(cfg.get("auto_long_edge"), max(src_w, src_h))
        if src_w >= src_h:
            gw, gh = long_edge, int(long_edge / aspect + 0.5)
        else:
            gw, gh = int(long_edge * aspect + 0.5), long_edge

    return max(1, int(gw)), max(1, int(gh))


def blend_blacks_from_source(pixelated_img, source_img, grid_size, edge_mask,
                              black_threshold=30, blend_strength=1.0):
    """
    Blend edge-adjacent black pixels using colors sampled from the original
    source image. Only touches pixels within `edge_mask` (near the
    transparent silhouette boundary), real interior dark linework and
    shading are left untouched. Source sampling also excludes near-black
    pixels so the average doesn't get dragged dark again.
    """
    pixelated_img = pixelated_img.convert("RGBA")
    source_img = source_img.convert("RGBA")

    pixelated_data = np.array(pixelated_img).astype(np.float64)
    source_data = np.array(source_img).astype(np.float64)

    gw, gh = grid_size
    src_h, src_w = source_data.shape[:2]
    pix_h, pix_w = pixelated_data.shape[:2]

    cell_w = src_w / gw
    cell_h = src_h / gh

    r, g, b, a = pixelated_data[:, :, 0], pixelated_data[:, :, 1], pixelated_data[:, :, 2], pixelated_data[:, :, 3]
    is_black = (r < black_threshold) & (g < black_threshold) & (b < black_threshold)

    blended_count = 0

    for y in range(pix_h):
        for x in range(pix_w):
            if not is_black[y, x] or a[y, x] < 128:
                continue

            # skip interior black content, only fix pixels near the silhouette edge
            if not edge_mask[y, x]:
                continue

            grid_y = min(int(y / pix_h * gh), gh - 1)
            grid_x = min(int(x / pix_w * gw), gw - 1)

            src_y_min = max(0, int(grid_y * cell_h))
            src_y_max = min(src_h, int((grid_y + 1) * cell_h))
            src_x_min = max(0, int(grid_x * cell_w))
            src_x_max = min(src_w, int((grid_x + 1) * cell_w))

            if src_y_max <= src_y_min or src_x_max <= src_x_min:
                continue

            region = source_data[src_y_min:src_y_max, src_x_min:src_x_max]
            region_a = region[:, :, 3]
            region_rgb = region[:, :, :3]

            opaque_mask = region_a >= 128
            non_black_mask = ~(
                (region_rgb[:, :, 0] < black_threshold)
                & (region_rgb[:, :, 1] < black_threshold)
                & (region_rgb[:, :, 2] < black_threshold)
            )
            combined_mask = opaque_mask & non_black_mask
            if not combined_mask.any():
                combined_mask = opaque_mask  # genuinely nothing but black/transparent here

            if combined_mask.any():
                opaque_pixels = region[combined_mask]
                avg_r = opaque_pixels[:, 0].mean()
                avg_g = opaque_pixels[:, 1].mean()
                avg_b = opaque_pixels[:, 2].mean()

                pixelated_data[y, x, 0] = r[y, x] * (1 - blend_strength) + avg_r * blend_strength
                pixelated_data[y, x, 1] = g[y, x] * (1 - blend_strength) + avg_g * blend_strength
                pixelated_data[y, x, 2] = b[y, x] * (1 - blend_strength) + avg_b * blend_strength

                blended_count += 1

    return Image.fromarray(pixelated_data.astype(np.uint8), "RGBA")


def cleanup_remaining_blacks(img, edge_mask, black_threshold=30):
    """Second pass: blend only edge-adjacent black pixels with neighboring non-black pixels."""
    img = img.convert("RGBA")
    data = np.array(img).astype(np.float64)

    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    is_black = (r < black_threshold) & (g < black_threshold) & (b < black_threshold)

    if not is_black.any():
        return img

    h, w = data.shape[:2]
    blended_count = 0

    neighbors = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)
    ]

    for y in range(h):
        for x in range(w):
            if not is_black[y, x] or a[y, x] < 128:
                continue

            if not edge_mask[y, x]:
                continue  # skip interior blacks like pupils, only fix near the silhouette edge

            non_black_colors = []
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    nr, ng, nb = r[ny, nx], g[ny, nx], b[ny, nx]
                    if (nr >= black_threshold or ng >= black_threshold or nb >= black_threshold) and a[ny, nx] >= 128:
                        non_black_colors.append([nr, ng, nb])

            if non_black_colors:
                non_black_colors = np.array(non_black_colors)
                avg_color = non_black_colors.mean(axis=0)

                data[y, x, 0] = avg_color[0]
                data[y, x, 1] = avg_color[1]
                data[y, x, 2] = avg_color[2]
                blended_count += 1

    return Image.fromarray(data.astype(np.uint8), "RGBA")

def to_pixel_art(img, cfg, source_img=None):
    """Run the full photo2pixel pipeline on a PIL image.
    
    Returns (raw_image, upscaled_image, stats) where stats is a dict with the
    grid size and the colour counts before/after any palette limit.
    """
    transparent = has_real_alpha(img)
    img = img.convert("RGBA")

    if cfg.get("trim"):
        img = trim_border(img, transparent, cfg.get("trim_tolerance"))

    src_w, src_h = img.size
    gw, gh = resolve_grid_size(src_w, src_h, cfg)
    print(f"Before trim - Grid: {gw}x{gh}, Source: {src_w}x{src_h}")

    p = max(2, int(cfg.get("sample_size")))
    k = int(cfg.get("kernel_size"))
    if k % 2 == 0:
        k += 1

    target = (gw * p, gh * p)
    # premultiplied resize keeps background color from bleeding into
    # foreground edges during the bilinear downscale
    resized = resize_premultiplied(img, target, Image.Resampling.BILINEAR)

    arr = np.array(resized).astype(np.float64)

    # shape-based outline detection at the working resolution
    outline_mask, solid_black_mask = detect_outline_mask(
        arr[:, :, :3],
        dark_threshold=cfg.get("outline_dark_threshold", 60),
        open_kernel=cfg.get("outline_open_kernel", 3),
        max_saturation=cfg.get("outline_max_saturation", 40),
    )

    # pixels too transparent to trust their color, after resize these can
    # still carry leftover background color at low opacity, so the color
    # vote shouldn't count them as real foreground content
    low_alpha_mask = arr[:, :, 3] < int(cfg.get("alpha_threshold"))

    grid_rgb, low_confidence = pixel_effect(
        arr[:, :, :3], int(cfg.get("num_bins")), k, p,
        outline_mask=outline_mask, low_alpha_mask=low_alpha_mask,
        min_fraction=cfg.get("outline_min_fraction", 0.15)
    )
    grid_rgb = fill_low_confidence_cells(grid_rgb, low_confidence)
    grid8 = grid_rgb.astype(np.uint8)

    alpha_full = resized.getchannel("A")
    alpha_out = process_alpha_channel(alpha_full, gw, gh, target[0], target[1], int(cfg.get("alpha_threshold")))

    opaque = alpha_out >= 255
    colors_before = count_unique_colors(grid8, opaque)
    grid8 = limit_palette(grid8, opaque, cfg.get("palette"), cfg.get("palette_dither"), cfg.get("palette_method"))
    colors_after = count_unique_colors(grid8, opaque)

    rgba = np.dstack([grid8, alpha_out])
    raw = Image.fromarray(rgba, "RGBA")

    if cfg.get("trim_final"):
        raw = trim_border(raw, True, 0)

    if cfg.get("square"):
        w, h = raw.size
        if w != h:
            size = max(w, h)
            padded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            offset_x = (size - w) // 2
            offset_y = (size - h) // 2
            padded.paste(raw, (offset_x, offset_y), raw)
            raw = padded

    # Shape-aware blending from source image, restricted to pixels near the
    # transparent silhouette edge so interior linework/shading isn't touched
    if source_img is not None and cfg.get("blend_from_source", True) and has_real_alpha(source_img):
        raw_alpha = np.array(raw.convert("RGBA"))[:, :, 3]
        edge_mask = compute_edge_proximity_mask(
            raw_alpha,
            max_distance=cfg.get("edge_distance", 2),
            alpha_threshold=int(cfg.get("alpha_threshold")),
        )
        raw = blend_blacks_from_source(
            raw, source_img, (gw, gh), edge_mask,
            cfg.get("black_threshold", 30), cfg.get("blend_strength", 1.0)
        )
        # Clean up any remaining edge blacks
        raw = cleanup_remaining_blacks(raw, edge_mask, cfg.get("black_threshold", 30))

    factor = max(1, int(cfg.get("upscale")))
    upscaled = raw.resize((raw.width * factor, raw.height * factor), Image.Resampling.NEAREST)

    stats = {
        "grid": (gw, gh),
        "colors_before": colors_before,
        "colors_after": colors_after,
        "palette": cfg.get("palette"),
    }
    print(f"After trim - Final: {raw.width}x{raw.height}")
    return raw, upscaled, stats


# ============================================================================
# ASYNC IMAGE PROCESSING - Animated image detection and formatting
# ============================================================================

async def is_image(buffer: io.BytesIO) -> bool:
    """
    Detect if buffer contains a valid image asynchronously.
    
    Args:
        buffer: BytesIO object containing image data
        
    Returns:
        True if buffer is a valid image, False otherwise
    """
    buffer.seek(0)
    
    def _check():
        buffer.seek(0)
        try:
            with Image.open(buffer) as img:
                _ = img.size
                return True
        except Exception:
            return False
        finally:
            buffer.seek(0)
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _check)
    buffer.seek(0)
    return result


async def get_frame_count(buffer: io.BytesIO) -> int:
    """
    Get frame count from image asynchronously.
    
    Args:
        buffer: BytesIO object containing image data
        
    Returns:
        Number of frames (1 for static, n for animated)
    """
    buffer.seek(0)
    
    def _count():
        buffer.seek(0)
        try:
            with Image.open(buffer) as img:
                return getattr(img, 'n_frames', 1)
        except Exception:
            return 1
        finally:
            buffer.seek(0)
    
    loop = asyncio.get_running_loop()
    frame_count = await loop.run_in_executor(None, _count)
    buffer.seek(0)
    return frame_count


async def get_image_info(buffer: io.BytesIO) -> dict:
    """
    Get comprehensive image information asynchronously.
    
    Args:
        buffer: BytesIO object containing image data
        
    Returns:
        Dictionary with: is_image, format, frames, width, height, size_bytes, is_animated
    """
    buffer.seek(0)
    
    def _info():
        buffer.seek(0)
        try:
            with Image.open(buffer) as img:
                frame_count = getattr(img, 'n_frames', 1)
                return {
                    'is_image': True,
                    'format': img.format.lower() if img.format else 'unknown',
                    'frames': frame_count,
                    'width': img.width,
                    'height': img.height,
                    'size_bytes': len(buffer.getvalue()),
                    'is_animated': frame_count > 1,
                }
        except Exception as e:
            print(f"Error getting image info: {e}")
            return {
                'is_image': False,
                'format': None,
                'frames': 0,
                'width': None,
                'height': None,
                'size_bytes': len(buffer.getvalue()),
                'is_animated': False,
            }
        finally:
            buffer.seek(0)
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _info)
    buffer.seek(0)
    return result


def _encode_to_gif(buffer: io.BytesIO) -> io.BytesIO:
    """Sync helper for GIF encoding."""
    buffer.seek(0)
    output = io.BytesIO()
    
    try:
        with Image.open(buffer) as img:
            frames = []
            durations = []
            
            try:
                for i in range(img.n_frames):
                    img.seek(i)
                    frame = img.convert("RGBA")
                    frames.append(frame)
                    duration = img.info.get('duration', 100)
                    durations.append(duration)
            except (AttributeError, EOFError):
                frames = [img.convert("RGBA")]
                durations = [100]
            
            if frames:
                frames[0].save(
                    output,
                    format='GIF',
                    save_all=len(frames) > 1,
                    append_images=frames[1:] if len(frames) > 1 else [],
                    duration=durations,
                    loop=0,
                    optimize=False
                )
        
        output.seek(0)
        return output
        
    except Exception as e:
        print(f"Error encoding to GIF: {e}")
        buffer.seek(0)
        return buffer


async def encode_to_gif(buffer: io.BytesIO) -> io.BytesIO:
    """
    Encode image to GIF format with animation support asynchronously.
    
    Args:
        buffer: BytesIO object containing image data
        
    Returns:
        New BytesIO object with GIF-encoded data
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _encode_to_gif, buffer)


def _encode_to_webp(buffer: io.BytesIO) -> io.BytesIO:
    """Sync helper for WEBP encoding."""
    buffer.seek(0)
    output = io.BytesIO()
    
    try:
        with Image.open(buffer) as img:
            frames = []
            durations = []
            
            try:
                for i in range(img.n_frames):
                    img.seek(i)
                    frame = img.convert("RGBA")
                    frames.append(frame)
                    duration = img.info.get('duration', 100)
                    durations.append(duration)
            except (AttributeError, EOFError):
                frames = [img.convert("RGBA")]
                durations = [100]
            
            if frames:
                frames[0].save(
                    output,
                    format='WEBP',
                    save_all=len(frames) > 1,
                    append_images=frames[1:] if len(frames) > 1 else [],
                    duration=durations,
                    loop=0,
                    method=6
                )
        
        output.seek(0)
        return output
        
    except Exception as e:
        print(f"Error encoding to WEBP: {e}")
        buffer.seek(0)
        return buffer


async def encode_to_webp(buffer: io.BytesIO) -> io.BytesIO:
    """
    Encode image to WEBP format with animation support asynchronously.
    
    Args:
        buffer: BytesIO object containing image data
        
    Returns:
        New BytesIO object with WEBP-encoded data
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _encode_to_webp, buffer)


async def smart_format_image(
    buffer: io.BytesIO,
    prefer_format: str = "webp",
    force_reformat: bool = False
) -> tuple:
    """
    Smart image formatter that auto-detects and converts to best format.
    
    Args:
        buffer: BytesIO object containing image data
        prefer_format: "webp" or "gif" for animated images
        force_reformat: If True, converts static images too
        
    Returns:
        Tuple of (buffer, format_string, frame_count)
    """
    if not await is_image(buffer):
        print("Not a valid image")
        buffer.seek(0)
        return buffer, "unknown", 0
    
    img_info = await get_image_info(buffer)
    print(f"Image: {img_info['format']}, {img_info['frames']} frames")
    
    # Animated - convert to best format
    if img_info['is_animated']:
        print(f"Animated image detected ({img_info['frames']} frames)")
        
        if prefer_format.lower() == "webp":
            result = await encode_to_webp(buffer)
            return result, "webp", img_info['frames']
        else:
            result = await encode_to_gif(buffer)
            return result, "gif", img_info['frames']
    
    # Static - reformat if requested
    elif force_reformat:
        print(f"Static image, reformatting to {prefer_format}")
        
        if prefer_format.lower() == "webp":
            result = await encode_to_webp(buffer)
            return result, "webp", 1
        else:
            result = await encode_to_gif(buffer)
            return result, "gif", 1
    
    # Keep original
    else:
        buffer.seek(0)
        return buffer, img_info['format'] or "unknown", 1