import discord, aiohttp, asyncio, logging, random, time, collections, io, platform, os, magic, re, json, hashlib, math, base64, qrcode, html, inspect, filetype, shutil, uvicorn
from discord import app_commands, ui # sku, Entitlement
from dotenv import dotenv_values
from database import SessionLocal, engine, check_and_add_column
from models import Base, User, SAMPLE_DATA, SAMPLE_STATS # type: ignore
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified
from utils import Editor, Errors, Downloader, run_in_executor, to_pixel_art, is_image, get_image_info, smart_format_image
from fastapi import FastAPI, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse, StreamingResponse
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urlparse, parse_qs, unquote
from typing import List, Union
from pathlib import Path
from email.message import Message
from email import policy
from email.parser import BytesParser
from datetime import datetime
from PIL import Image
from bs4 import BeautifulSoup, NavigableString

# stuff that i dont wanna redefine later
mime = magic.Magic(mime=True)
environ = dotenv_values(".env")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

cooldowns = {}

async def set_cooldown(key: str, seconds: float):
    cooldowns[key] = time.time() + seconds
    await asyncio.sleep(seconds)
    cooldowns.pop(key, None)

cooldown_length = 2

def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))

class Container(ui.LayoutView):
    container = ui.Container()
    def __init__(self, files: discord.File | str = None, title: str = None, description: str = None, footer: str = None):
        super().__init__()

        if title:
            self.container.add_item(ui.TextDisplay(title))
        
        if files:
            if not isinstance(files, list):
                files = [files]
            gallery = ui.MediaGallery(*[discord.MediaGalleryItem(file) for file in files])
            self.container.add_item(gallery)
            
        if description:
            self.container.add_item(ui.TextDisplay(description))
        
        if footer:
            self.container.add_item(ui.Separator())
            self.container.add_item(ui.TextDisplay(footer))

class Tree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command_id = interaction.data.get("id")
        user = interaction.user
        user_info = await get_data(user)
        if TESTING or user_info.data.get("whitelisted"):
            return True
        user_id = user.id
        for entitlement in interaction.entitlements:
            if entitlement.sku_id == 1458598471107088476 and entitlement.user_id == user_id:
                return True
        key = f"{user_id}-{command_id}"
        cooldown = cooldowns.get(key)
        if cooldown:
            await interaction.response.send_message(f"""You are on cooldown for **{max(round((cooldown - time.time()), 2), 0.01)}s**\n-# btw you can give me [$1](https://discord.com/discovery/applications/880143829376835585/store/1458598471107088476) to remove it""")
            return False
        asyncio.create_task(set_cooldown(key, cooldown_length))
        return True

tree = Tree(client)

# stupid constants
START_TIME = time.time()
DIRECTORY = os.path.dirname(__file__)
TEMP_FOLDER = os.path.join(DIRECTORY, "TEMP")
if not os.path.exists(TEMP_FOLDER):
    print("creating temp folder")
    os.makedirs(TEMP_FOLDER)
TESTING = platform.system() == "Windows"
FFMPEG = TESTING and r"""C:\Users\Max\AppData\Local\Microsoft\WinGet\Packages\yt-dlp.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-N-124716-g054dffd133-win64-gpl\bin\ffmpeg.exe""" or "/home/slave/bin/ffmpeg"
YT_DLP = TESTING and r"""C:\Users\Max\AppData\Local\Microsoft\WinGet\Packages\yt-dlp.yt-dlp_Microsoft.Winget.Source_8wekyb3d8bbwe\yt-dlp.exe""" or "/home/slave/bin/yt-dlp"
DENO_PATH = TESTING and "deno" or "/home/slave/.deno/bin/deno"
YT_KEY = environ.get("YTKEY")

YES = "<:greenTick:1380263952285569054>"
NO = "<:redTick:1380264006341758987>"
SUSPENDED = "(SUSPENDED)" # "🚫"

class PreviewView(discord.ui.View):
    def __init__(self, prompt: str, info: str):
        super().__init__()
        self.timeout = None
        self.add_item(self.PreviewButton(prompt, info))

    class PreviewButton(discord.ui.Button):
        def __init__(self, label: str, info: str):
            super().__init__(label=label, style=discord.ButtonStyle.gray)
            self.info = info

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_message(content=self.info, ephemeral=True)

async def check_inboxes():
    async with aiohttp.ClientSession(headers={"X-API-KEY": environ.get("SMTPAPIKEY")}) as session:
        while True:
            try:
                params = {
                    "page": 1
                }

                toDelete = []

                pages = None

                while True:
                    async with session.get("https://api.smtp.dev/accounts", params=params) as response:
                        resp = await response.json()
                        if not pages:
                            pages = math.ceil(resp.get("totalItems") / len(resp.get("member")))
                        for member in resp.get("member"):
                            created = datetime.fromisoformat(member.get("createdAt")).timestamp()
                            if member.get("used") == 0 and time.time() > created + (86400*3):
                                toDelete.append(member.get("id"))
                            elif member.get("address"):
                                numbers = re.findall(r'\d+', member.get("address").split("@")[0])
                                number = len(numbers) > 0 and int("".join(numbers))
                                if number and len(str(number)) >= 10 and (time.time() > (int(str(number)[:10]) + (24*72))):
                                    toDelete.append(member.get("id"))
                        params["page"] += 1
                        if pages and params["page"] > pages:
                            break
                
                for emailId in toDelete:
                    await session.delete(f"https://api.smtp.dev/accounts/{emailId}")
            except Exception:
                pass

            async with SessionLocal() as db_session:
                try:
                    query = await db_session.execute(select(User))
                    users = query.scalars().all()
                    for user in users:
                        newEmails = [i for i in (user.emails or []) if i.get("temp") == None or time.time() < i.get("temp")]
                        deleted = []
                        for email in newEmails:
                            try:
                                params = {
                                    "isActive": "true",
                                    "address": email.get("email"),
                                    "page": 1
                                }
                                async with session.get("https://api.smtp.dev/accounts", params=params) as resp:
                                    resp = await resp.json()
                                    member = len(resp.get("member"))
                                    if member == 0:
                                        deleted.append(email)
                                        continue
                                    mailboxes = resp.get("member")[0].get("mailboxes")
                                    for mailbox in mailboxes:
                                        async with session.get(f"https://api.smtp.dev{mailbox.get('@id')}/messages?page=1") as response:
                                            resp = await response.json()
                                            for message in resp.get("member"):
                                                if not message.get("isRead"):
                                                    try:
                                                        discordUser = await client.fetch_user(user.uid)
                                                        embed = discord.Embed(
                                                            title=message.get("subject"),
                                                            description=message.get("intro"),
                                                            color=discord.Color.blurple(),
                                                            # timestamp=datetime.fromisoformat(message.get("createdAt"))
                                                        )
                                                        author = message.get("from")
                                                        sender = author.get("address").lower()
                                                        if sender in user.blockedEmails:
                                                            await session.delete(f"https://api.smtp.dev{message.get('@id')}")
                                                            continue
                                                        embed.set_author(
                                                            name=f"From: {author.get('name')} ({author.get('address')})"
                                                        )
                                                        params = urlencode({"url": message.get('downloadUrl')})
                                                        embed.description = (embed.description or "") + f"\n[Open email](https://disuko.inkthirsty.xyz/view-email?{params})"
                                                        recipients = [i.get("address") for i in message.get("to") if i.get("address").split("@")[0].replace(".", "").lower() == email.get("email").split("@")[0].lower()]
                                                        embed.set_footer(text=len(recipients) > 0 and recipients[0] or email.get("email"))

                                                        class View(discord.ui.View):
                                                            def __init__(self, sender: str):
                                                                super().__init__()
                                                                self.sender = sender
                                                                self.timeout = None

                                                            @discord.ui.button(style=discord.ButtonStyle.grey, label="Block Sender", emoji="🚫")
                                                            async def blocklmao(self, interaction: discord.Interaction, button: discord.ui.Button):
                                                                if interaction.user == discordUser:
                                                                    async with SessionLocal() as db_local_session:
                                                                        individual = await get_data(discordUser)
                                                                        blocked = individual.blockedEmails.copy()
                                                                        if self.sender in blocked:
                                                                            await interaction.response.send_message(f"`{self.sender}` is already on your block list (how did you even get this to happen?)", ephemeral=True)
                                                                        else:
                                                                            individual.blockedEmails = (individual.blockedEmails + [self.sender]).copy()
                                                                            db_local_session.add(individual)
                                                                            await db_local_session.commit()
                                                                            await interaction.response.send_message(f"Added `{self.sender}` to block list (remove with /email unblock)", ephemeral=True)

                                                            """
                                                            @discord.ui.button(style=discord.ButtonStyle.red, label="Delete", emoji="🗑️")
                                                            async def deletemsg(self, interaction: discord.Interaction, button: discord.ui.Button):
                                                                if interaction.user == discordUser:
                                                                    async with aiohttp.ClientSession(headers={"X-API-KEY": environ.get("SMTPAPIKEY")}) as session:
                                                                        await session.delete(f"https://api.smtp.dev{message.get('@id')}")
                                                                        await interaction.delete_original_response()
                                                            """

                                                        await discordUser.send(embed=embed, view=View(sender))
                                                        await session.patch(f"https://api.smtp.dev{message.get('@id')}", json={"isRead":True}, headers={"Content-Type": "application/merge-patch+json", "X-API-KEY": environ.get("SMTPAPIKEY")})
                                                        await asyncio.sleep(1)
                                                    except Exception:
                                                        import traceback
                                                        print(traceback.format_exc())
                                                        pass
                            except Exception:
                                pass
                        newEmails = [i for i in newEmails if i.get("email") not in deleted]
                        if user.emails != newEmails:
                            user.emails = newEmails.copy()
                            flag_modified(user, "emails")
                            await db_session.commit()
                except Exception:
                    pass
            await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(api: FastAPI):
    await check_and_add_column()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    discord.utils.setup_logging(level=logging.INFO, root=False)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    asyncio.create_task(client.start(environ.get("TOKEN")))
    asyncio.create_task(clean())
    asyncio.create_task(check_inboxes())
    yield

async def clean():
    while True:
        now = time.time()
        for filename in os.listdir(TEMP_FOLDER):
            path = os.path.join(TEMP_FOLDER, filename)
            if os.path.exists(path):
                if os.path.getmtime(path) < now - (60):
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                        print(f"Deleted directory {path}")
                    else:
                        os.remove(path)
                        print(f"Deleted file {path}")
            pass
        await asyncio.sleep(1)

app = FastAPI(
    lifespan=lifespan,
    title="disuko",
    swagger_ui_parameters={
        "syntaxHighlight": True,
        "syntaxHighlight.theme": "obsidian",
        "displayRequestDuration": True,
        "useUnsafeMarkdown": True,
    },
    redoc_url=None,
    docs_url=None,
)


def custom_openapi():
    app.openapi_schema = get_openapi(title=app.title, version="1.0", routes=app.routes)
    for method_item in app.openapi_schema.get("paths").values():
        for param in method_item.values():
            responses = param.get("responses")
            if "422" in responses:
                del responses["422"]
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/", include_in_schema=False)
async def api_home():
    return RedirectResponse("/docs")

@app.get("/docs", include_in_schema=False)
async def api_docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title, swagger_favicon_url="/favicon.ico")

def generate_qr_with_logo_bytes(
    data: str,
    box_size: int = 16,
    border: int = 2,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF"
) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for logo overlay
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

@app.get("/qr", description="Generate a customizable QR code with optional logo")
async def api_qr(
    data: str,
    box_size: int = Query(16, ge=1, le=64, description="Size of each QR code box"),
    border: int = Query(2, ge=0, le=10, description="Width of the border"),
    fill_color: str = Query("#000000", pattern="^#(?:[0-9a-fA-F]{3}){1,2}$", description="Hex color for the QR code"),
    back_color: str = Query("#FFFFFF", pattern="^#(?:[0-9a-fA-F]{3}){1,2}$", description="Hex background color")
):
    buffer = await asyncio.to_thread(
        generate_qr_with_logo_bytes,
        data,
        box_size,
        border,
        fill_color,
        back_color
    )
    return StreamingResponse(buffer, media_type="image/png")

def linkify_urls_in_text(text: str) -> str:
    url_pattern = re.compile(
        r'(?<!href=["\'])'  # Ignore URLs already inside href attributes
        r'((https?://|ftp://|www\.)[^\s<>"]+)', re.IGNORECASE
    )
    
    def replace_url(match):
        url = match.group(1)
        href = url if url.startswith(('http://', 'https://', 'ftp://')) else 'http://' + url
        safe_url = html.escape(url)
        safe_href = html.escape(href)
        return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_url}</a>'
    
    return url_pattern.sub(replace_url, text)

def linkify_urls_in_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    allowed_tags = ['p', 'div', 'span', 'li', 'td', 'th', 'a']

    for tag in soup.find_all(allowed_tags):
        for content in tag.contents:
            if isinstance(content, NavigableString):
                new_html = linkify_urls_in_text(str(content))
                content.replace_with(BeautifulSoup(new_html, 'html.parser'))

    return str(soup)

def clean_html(body: str) -> str:
    soup = BeautifulSoup(body, "html.parser")

    # Remove inline styles completely (keeps text readable)
    for tag in soup.find_all(style=True):
        del tag['style']

    # Remove <font> tags but keep text
    for tag in soup.find_all('font'):
        tag.unwrap()

    return str(soup)

@app.get("/view-email", response_class=HTMLResponse)
async def api_view_email(url: str):
    async with aiohttp.ClientSession(
        headers={"X-API-KEY": environ.get("SMTPAPIKEY")}
    ) as session:
        async with session.get(f"https://api.smtp.dev{url}") as resp:
            raw = await resp.read()

    msg = BytesParser(policy=policy.default).parsebytes(raw)

    subject = msg.get("subject", "No Subject")
    from_addr = msg.get("from", "Unknown")
    to_addr = msg.get("to", "Unknown")

    body = ""
    inline_images = {}

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()

            if ctype == "text/html":
                body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8",
                    errors="replace"
                )

            elif ctype.startswith("image/"):
                cid = part.get("Content-ID")
                if cid:
                    inline_images[cid.strip("<>")] = (
                        part.get_payload(decode=True),
                        ctype
                    )
    else:
        body = msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8",
            errors="replace"
        )

    # Replace CID images
    for cid, (data, ctype) in inline_images.items():
        encoded = base64.b64encode(data).decode()
        body = body.replace(
            f"cid:{cid}",
            f"data:{ctype};base64,{encoded}"
        )

    # --- SANITIZE SAFELY (don’t destroy layout) ---
    soup = BeautifulSoup(body, "html.parser")

    # Remove dangerous tags
    for tag in soup(["script", "iframe", "object", "embed"]):
        tag.decompose()

    # Remove JS event handlers
    for tag in soup.find_all():
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]

    clean_body = str(soup)

    # --- FINAL HTML ---
    html_out = f"""
    <html>
    <head>
        <title>{html.escape(subject)}</title>
        <style>
            body {{
                margin: 0;
                background: #121212;
                font-family: system-ui, sans-serif;
            }}

            .email-wrapper {{
                padding: 30px;
            }}

            .email-body {{
                white-space: pre-wrap;
                word-wrap: break-word;
            }}

            .email-container {{
                max-width: 800px;
                margin: auto;
                background: #ffffff;
                color: #000;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 10px 25px rgba(0,0,0,.3);
            }}

            @media (prefers-color-scheme: dark) {{
                .email-container {{
                    background: #1e1e1e;
                    color: #e0e0e0;
                }}
            }}

            img {{
                max-width: 100%;
                height: auto;
            }}

            a {{
                color: #4ea1ff;
                word-break: break-word;
            }}

            .meta {{
                font-size: 14px;
                color: #aaa;
                margin-bottom: 15px;
                border-bottom: 1px solid #444;
                padding-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="email-container">
                <div class="meta">
                    <div><strong>From:</strong> {html.escape(from_addr)}</div>
                    <div><strong>To:</strong> {html.escape(to_addr)}</div>
                    <div><strong>Subject:</strong> {html.escape(subject)}</div>
                </div>
                <div class="email-body">
                    {clean_body}
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html_out)

def buffer_to_mimetype(buffer: io.BytesIO) -> str:
    mimetype = mime.from_buffer(buffer.read())
    buffer.seek(0)
    return mimetype

def guess_format(mimetype: str) -> str:
    with open(os.path.join(DIRECTORY, "assets/formats.json")) as file:
        data = json.load(file)
    for key, value in data.items():
        if key in mimetype.lower():
            return value
    return

def is_html_string(text: str) -> bool:
    return bool(re.compile(r"<[^>]+>").search(text))

def valid_url(url: str) -> bool:
    url = str(url)
    return url.startswith("http://") or url.startswith("https://")

def make_hash(text: str):
    sha256 = hashlib.sha256()
    sha256.update(text.encode("utf-8"))
    return sha256.hexdigest()

def estimate_eta(file_size_bytes):
    mbps = 480
    file_size_mb = file_size_bytes / (1000 * 1000)
    upload_speed = mbps * 0.125
    upload_time_without_delay = file_size_mb / upload_speed
    
    # time, size
    factors = [
        (40, 282.72),
    ]
    
    closest_factor = min(factors, key=lambda x: abs(file_size_mb - x[0]))
    delay_factor = (closest_factor[0] - (closest_factor[1] / upload_speed)) / closest_factor[1]
    
    total_eta = upload_time_without_delay + (file_size_mb * delay_factor)
    return total_eta * 4

def reformat_youtube_url(url):
    match = re.search(
        r'(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/))([a-zA-Z0-9_-]{11})',
        url
    )
    return match and f'https://www.youtube.com/watch?v={match.group(1)}'

def extract_real_url(google_redirect_url):
    parsed = urlparse(google_redirect_url)
    query = parse_qs(parsed.query)
    encoded_url = query.get("url", [None])[0]
    return encoded_url and unquote(encoded_url)

MAX_FILE_SIZE = 1024 * 1024 * 1024 * 20 # 1GB

async def upload_file(
    content: Union[Editor, str, io.BytesIO], 
    file_format: str = "png", 
    file_name: str = None,
    short_url: bool = False, 
    # vault: bool = False,
    interaction: discord.Interaction = None,
    text: str = None,
) -> str:
    if not file_name:
        if isinstance(content, str):
            file_name = os.path.basename(urlparse(content).path)
        else:
            file_name = f"upload_{int(time.time())}.{file_format}"

    if not file_name.endswith(f".{file_format}"):
        pathlike = Path(file_name)
        file_name = f"{pathlike.stem}{pathlike.suffix}.{file_format}"
    
    timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=60)
    CDN_URL = "https://vault.inkthirsty.xyz"
    API_KEY = environ.get("CDN")
    
    # Get file size and content type
    if isinstance(content, str):
        async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=5)) as temp_session:
            async with temp_session.head(content) as resp:
                file_size = int(resp.headers.get('content-length', 0))
                if file_size == 0:
                    raise ValueError("Could not determine file size")
                content_type = resp.headers.get('content-type', 'application/octet-stream')
    elif isinstance(content, Editor):
        buffer = content.image_bytes
        buffer.seek(0, 2)
        file_size = buffer.tell()
        buffer.seek(0)
        content_type = filetype.guess_mime(buffer) or 'application/octet-stream'
        buffer.seek(0)
    else:
        buffer = content
        buffer.seek(0, 2)
        file_size = buffer.tell()
        buffer.seek(0)
        content_type = filetype.guess_mime(buffer) or 'application/octet-stream'
        buffer.seek(0)
    
    async with aiohttp.ClientSession(
        timeout=timeout,
        cookies={"api_key": API_KEY},
        connector=aiohttp.TCPConnector(limit=5, limit_per_host=2)
    ) as session:
        try:
            # Step 1: Start upload
            async with session.post(
                f"{CDN_URL}/upload/start",
                json={
                    "name": file_name,
                    "size": file_size,
                    "content_type": content_type,
                    "size_limit": (10 * 1_000_000) - 28
                }
            ) as resp:
                resp.raise_for_status()
                session_data = await resp.json()
                session_id = session_data["session_id"]
                total_chunks = session_data["total_chunks"]
                upload_map = session_data["upload_map"]
                print(f"Created upload session: {session_id} ({total_chunks} chunks)")
            
            # Step 2: Upload chunks with progress updates
            async def upload_chunk(session, session_id, chunk, chunk_index, total_chunks, interaction, text, CDN_URL):
                for attempt in range(3):
                    try:
                        async with session.patch(
                            f"{CDN_URL}/upload/chunk/{session_id}",
                            data=chunk,
                            headers={"Content-Type": "application/octet-stream"}
                        ) as upload_resp:
                            upload_resp.raise_for_status()
                            
                            if interaction:
                                await interaction.edit_original_response(
                                    content=f"{text}\n-# Upload progress: {chunk_index + 1}/{total_chunks}"
                                )
                            print(f"Uploaded chunk {chunk_index + 1}/{total_chunks}")
                            break
                    except Exception as e:
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                        else:
                            raise

            # Then both branches:
            if isinstance(content, str):
                async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=5)) as download_session:
                    async with download_session.get(content) as resp:
                        resp.raise_for_status()
                        for chunk_index, chunk_size in enumerate(upload_map):
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                raise ValueError(f"Stream ended early at chunk {chunk_index}")
                            await upload_chunk(session, session_id, chunk, chunk_index, total_chunks, interaction, text, CDN_URL)
            else:
                buffer.seek(0)
                for chunk_index, chunk_size in enumerate(upload_map):
                    chunk = buffer.read(chunk_size)
                    if not chunk:
                        raise ValueError(f"Buffer ended early at chunk {chunk_index}")
                    await upload_chunk(session, session_id, chunk, chunk_index, total_chunks, interaction, text, CDN_URL)
            
            # Step 3: Finalize
            async with session.post(f"{CDN_URL}/upload/finish/{session_id}") as resp:
                resp.raise_for_status()
                resp_json = await resp.json()
                url = short_url and resp_json.get("short_url") or resp_json.get("url")
                print(f"Upload finalized: {url}")
            
            return valid_url(url) and url

        except Exception as e:
            print(f"Failed to upload to CDN: {e}")
            import traceback
            print(traceback.format_exc())
            
            # Fallback to Discord
            try:
                if isinstance(content, str):
                    async with aiohttp.ClientSession(timeout=timeout) as temp_session:
                        async with temp_session.get(content) as resp:
                            buffer = io.BytesIO(await resp.read())
                else:
                    buffer = content if isinstance(content, io.BytesIO) else content.image_bytes
                
                buffer.seek(0)
                channel = await client.fetch_channel(environ.get("IMAGE_CHANNEL"))
                message = await channel.send(file=discord.File(buffer, f"fallback.{file_format}"))
                url = message.attachments[0].url
                return valid_url(url) and url
            except Exception as fallback_error:
                print(f"Fallback failed: {fallback_error}")
                import traceback
                print(traceback.format_exc())
                return None

async def insta_proxy(url):
    """
    try:
        print("pre-test")
        pretest = await Downloader.instagram2(url)
        print("url", pretest)
        soup = BeautifulSoup(html, 'html.parser')
        script = soup.find('script', {'id': 'discord:component-embed'})
        data = json.loads(script.string)
        new_url = data['component']['components'][1]['items'][0]['media']['url']
        print("newurl:", new_url)
        return new_url
    except Exception as err:
        import traceback
        print("ERRORFUCK", traceback.format_exc())
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
        "Accept-Encoding": "gzip, deflate, br",
    }
    async with aiohttp.ClientSession(headers=headers) as session:   
        try:
            new_url = url.replace("instagram.com", "instagramfix.com")
            print(url, "->", new_url)
            async with session.get(new_url, headers=headers, ssl=False) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                script = soup.find('script', {'id': 'discord:component-embed'})
                data = json.loads(script.string)
                new_url = data['component']['components'][1]['items'][0]['media']['url']
                print("newurl:", new_url)
                return new_url
        except Exception as err:
            import traceback
            print("ERRORFUCK", traceback.format_exc())
    async with aiohttp.ClientSession() as session:
        async def get_new_url(url):
            try:
                parsed = urlparse(url)
                path = parsed.path + ("?" + parsed.query if parsed.query else "")
                
                webhooks = environ.get("WEBHOOKS").strip().split(" ")
                proxies = ["instagramfix.com", "kirkstagram.com",] * 5 + ["kkinstagram.com"]

                messages = {}
                
                for i in range(5):
                    for proxy in proxies:
                        separator = "&" if "?" in path else "?"
                        if i < 1:
                            test_url = f"https://{proxy}{path}"
                        else:
                            test_url = f"https://{proxy}{path}{separator}adamisgay={time.time()}"
                        try:
                            webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                            message = messages.get(proxy)
                            if not message:
                                message = await webhook.send(test_url, wait=True)
                            await asyncio.sleep(1)
                            new_msg = await webhook.fetch_message(message.id)
                            # print(test_url, new_msg.embeds)
                            for embed in new_msg.embeds:
                                print(embed, embed.image, embed.video, embed.url, embed.thumbnail, embed.provider)
                                video = embed.video
                                if video and video.proxy_url:
                                    print("Video proxy:", proxy, video.proxy_url)
                                    return video.proxy_url
                                
                                thumbnail = embed.thumbnail
                                if thumbnail and thumbnail.proxy_url:
                                    print("Thumbnail proxy:", proxy, thumbnail.proxy_url)
                                    return thumbnail.proxy_url
                        except Exception:
                            pass
                    await asyncio.sleep(1)
            except Exception:
                return url
        for i in range(5):
            attempt = await get_new_url(url)
            if attempt is not None and attempt != url:
                try:
                    async with session.get(attempt) as resp:
                        try:
                            json.loads(await resp.text())
                            continue
                        except Exception:
                            pass
                        return io.BytesIO(await resp.read())
                except Exception:
                    pass
            await asyncio.sleep(1)
    return url

async def attempt_embed(url):
    async with aiohttp.ClientSession() as session:
        async def get_new_url(url):
            try:                
                webhooks = environ.get("WEBHOOKS").strip().split(" ")
                message = None
                for i in range(5):
                    try:
                        webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                        if not message:
                            message = await webhook.send(url, wait=True)
                        await asyncio.sleep(1)
                        new_msg = await webhook.fetch_message(message.id)
                        for embed in new_msg.embeds:
                            thumbnail = embed.thumbnail
                            if thumbnail and thumbnail.proxy_url:
                                print("Thumbnail:", thumbnail.proxy_url, thumbnail.url)
                                return thumbnail.proxy_url
                            
                            video = embed.video
                            if video and video.proxy_url:
                                print("Video:", video.proxy_url, video.url)
                                return video.proxy_url
                    except Exception:
                        pass
            except Exception:
                return url
        attempt = await get_new_url(url)
        if attempt is not None and attempt != url:
            async with session.get(attempt) as resp:
                return io.BytesIO(await resp.read())
    return url

Downloader.instagram = insta_proxy
Downloader.klipy = attempt_embed

async def download_file(url: str, mbLimit: float = None, get_filename: bool = False, forced_format: str = None) -> io.BytesIO:
    def check(yep: str):
        return "".join(yep.split("/")[2].split("."))

    def maybe_return(buffer, name=None):
        return (buffer, name) if get_filename else buffer

    def maybe_return_none():
        return (None, None) if get_filename else None

    async def run_yt_dlp(command: list):
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode().strip(), stderr.decode().strip(), proc.returncode

    timeout = aiohttp.ClientTimeout(total=1800)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        url = extract_real_url(url) or url
        url = reformat_youtube_url(url) or url
        redirect = extract_real_url(url) or reformat_youtube_url(url)

        #if "instagram.com" in check(url).lower()

        methods = [i for i in Downloader.get_methods() if i in check(url).lower() or (redirect and i in check(redirect).lower())]
        method = len(methods) > 0 and getattr(Downloader, methods[0])
        print(methods, "METHOD", method)

        if method:
            buffer = await method(url)
            if isinstance(buffer, io.BytesIO):
                return maybe_return(buffer, None)
            else:
                redirect = buffer

        mimetype = None
        extracheck = any(site in url for site in ["fandom.com", "roblox.com", "tenor"])

        # --- Direct HTTP download with retries ---
        path = None
        for attempt in range(3):
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    size = int(resp.headers.get("Content-Length", 0))
                    print(f"Content-Length: {size}")

                    if size >= MAX_FILE_SIZE or (mbLimit and size > mbLimit * 1000 * 1000):
                        print("File too large, aborting.")
                        return maybe_return_none()

                    content_type = resp.headers.get("Content-Type", "")
                    cd = resp.headers.get("Content-Disposition")

                    if cd:
                        msg = Message()
                        msg["Content-Disposition"] = cd
                        filename = msg.get_filename()
                        path = filename if filename else os.path.basename(urlparse(url).path)

                    print(f"URL: {url} | Path: {path} | Content-Type: {content_type}")

                    # Direct image — stream in chunks
                    if "image" in content_type:
                        print(f"Direct image detected ({content_type}), streaming...")
                        buffer = io.BytesIO()
                        bytes_read = 0
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            bytes_read += len(chunk)
                            if bytes_read > MAX_FILE_SIZE or (mbLimit and bytes_read > mbLimit * 1000 * 1000):
                                print("Image exceeded size limit mid-stream, aborting.")
                                return maybe_return_none()
                            buffer.write(chunk)
                        
                        buffer.seek(0)
                        
                        # Async image processing
                        img_path = path or os.path.basename(urlparse(url).path) or "download.webp"
                        
                        if not await is_image(buffer):
                            print(f"Invalid image: {img_path}")
                            return maybe_return_none()
                        
                        img_info = await get_image_info(buffer)
                        
                        if img_info['is_animated']:
                            print(f"Animated: {img_info['frames']} frames, converting to WEBP...")
                            buffer, fmt, _ = await smart_format_image(buffer, prefer_format="webp")
                            img_path = f"{os.path.splitext(img_path)[0]}.{fmt}"
                        else:
                            print(f"Static image: {img_info['format']}")
                        
                        return maybe_return(buffer, img_path)

                    # Direct video/other — stream in chunks
                    if "video" in content_type or "application/octet-stream" in content_type:
                        print(f"Direct file detected ({content_type}), streaming...")
                        buffer = io.BytesIO()
                        bytes_read = 0
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            bytes_read += len(chunk)
                            if bytes_read > MAX_FILE_SIZE or (mbLimit and bytes_read > mbLimit * 1000 * 1000):
                                print("File exceeded size limit mid-stream, aborting.")
                                return maybe_return_none()
                            buffer.write(chunk)
                        buffer.seek(0)
                        file_path = path or os.path.basename(urlparse(url).path) or "download.mp4"
                        return maybe_return(buffer, file_path)

                    http_success = True
                    break  # got a response, fall through to yt-dlp

            except Exception as e:
                print(f"HTTP attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    print("All HTTP attempts failed, falling through to yt-dlp...")

        # --- yt-dlp with proxy -> no-proxy fallback ---
        print("Attempting yt-dlp...")
        proxy = environ.get("PROXY")

        size_filter = (
            f"bv[filesize_approx<{mbLimit}M]+ba / b[filesize_approx<{mbLimit}M] / best"
            if mbLimit else
            "bv[filesize_approx<1G]+ba / b[filesize_approx<1G] / best"
        )
        output_template = (
            os.path.join(TEMP_FOLDER, path) if path
            else os.path.join(TEMP_FOLDER, "%(title).60s.%(ext)s")
        )
        format_args = (
            ["--recode-video", forced_format] if forced_format
            else ["--merge-output-format", "mp4"]
        )

        def build_command(use_proxy: bool = False, use_cookies: bool = False) -> list:
            return [
                YT_DLP,
                *(["--proxy", proxy] if use_proxy else []),
                "-f", size_filter,
                "--ffmpeg-location", os.path.dirname(FFMPEG),
                "--restrict-filenames",
                "--print", "after_move:filepath",
                "-o", output_template,
                # "--cookies-from-browser", "chrome",
                #"--cookies", os.path.join(DIRECTORY, "assets", "cookies.txt"),
                *(["--cookies", os.path.join(DIRECTORY, "assets", "cookies.txt")] if use_cookies else []),
                "--extractor-args", "youtube:player_client=default,web_embedded",
                "--no-playlist", "--abort-on-error", "--no-check-certificate", "-k",
                "-S", "res:2160,filesize",
                *(["--js-runtimes", f"deno:{DENO_PATH}"] if not TESTING else []),
                *format_args,
                redirect or url,
            ]

        yt_dlp_attempts = [
            ("without cookies", build_command(use_cookies=False)),
            ("with cookies",    build_command(use_cookies=True)),
            # ("with proxy",    build_command(use_proxy=not TESTING)),
            # ("without proxy", build_command(use_proxy=False)),
        ] * 2

        output_file_path = None
        for label, command in yt_dlp_attempts:
            print(f"yt-dlp attempt {label}:")
            print("COMMAND ->", " ".join(command))
            stdout_str, stderr_str, returncode = await run_yt_dlp(command)
            print("stdout:", stdout_str)
            print("stderr:", stderr_str)

            if returncode == 0 and os.path.exists(stdout_str):
                output_file_path = stdout_str
                break

            print(f"yt-dlp failed {label} (rc={returncode}), trying next...")

        if output_file_path:
            video_filename = os.path.basename(output_file_path)
            print(f"Captured: {video_filename}")
            with open(output_file_path, "rb") as f:
                buffer = io.BytesIO(f.read())
            try:
                os.remove(output_file_path)
            except Exception as e:
                print("Cleanup failed:", e)
            return maybe_return(buffer, str(video_filename).replace(" ", "_"))

        # --- Final fallback: embed scraping (Instagram, Reddit, etc.) ---
        if extracheck or (mimetype and "text/html" in mimetype):
            channel = await client.fetch_channel(environ.get("IMAGE_CHANNEL"))
            replacements = {
                "reddit.com": "rxddit.com",
            }
            pattern = re.compile(r'(?<=://)(?:www\.)?(instagram\.com|reddit\.com)(?=/|$)')

            def replace_domain(u: str) -> str:
                def repl(match):
                    domain = match.group(1)
                    prefix = "www." if match.group(0).startswith("www.") else ""
                    return prefix + replacements[domain]
                return pattern.sub(repl, u)

            url = replace_domain(url)
            tasks = await asyncio.gather(*[
                asyncio.create_task(session.head(url, allow_redirects=False, params=i and {"x": time.time(), "i": i}))
                for i in range(5)
            ])
            message = await channel.send("Investigating embed fallback\n" + "\n".join(str(t.url) for t in tasks))
            for _ in range(5):
                new_msg = await channel.fetch_message(message.id)
                try:
                    test_url = new_msg.embeds[0].thumbnail.url or new_msg.embeds[0].image.url
                    async with session.get(test_url) as resp:
                        return maybe_return(io.BytesIO(await resp.read()), None)
                except Exception:
                    await asyncio.sleep(1)

        return maybe_return_none()
        
def display_bytes(number: int) -> tuple[int, str]:
    number = int(number)
    if number == 0 or number < 0:
        return 0, "B"
    suffixes = ["B", "KB", "MB", "GB"]
    base = 1000
    index = 0
    
    while number >= base and index < len(suffixes) - 1:
        number /= base
        index += 1
    
    return round(number, 2), suffixes[index]

def present_download(url: str, size: float | int, unit: str) -> str:
    return f"-# {url} ({size} {unit})"
    # return f"[Download ({size} {unit})](<{url}>)"


def invisible_link(url: str) -> str:
    return f"[󠀀]({url})"

def create_embed(user: discord.User = None, title: str = None, description: str = None) -> discord.Embed:
    embed = discord.Embed(
        title=title or None,
        description=description or None
    )
    if user:
        # embed.set_footer(text=f"Command executed by {user.name}", icon_url=user.avatar.url)
        pass
    return embed

def calculate_mode(data):
    counter = collections.Counter(data)
    mode = counter.most_common(1)[0][0]
    return mode

def rgb_to_hex(rgb: tuple) -> str:
    return "{:02x}{:02x}{:02x}".format(*[int(round(x)) for x in rgb]).upper()

def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def admin_check(user: discord.User):
    whitelist = [726440141391921284]
    return user.id in whitelist

def calculate_uptime():
    total_seconds = int(round(time.time() - START_TIME))

    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    components = []

    if days > 0:
        components.append(f"{int(days)} days")
    if hours > 0:
        components.append(f"{int(hours)} hours")
    if minutes > 0:
        components.append(f"{int(minutes)} minutes")
    if seconds > 0:
        components.append(f"{int(seconds)} seconds")

    time_string = ", ".join(components)
    return time_string

async def register(user: discord.User):
    user_id = str(user.id)  # Ensure user_id is a string (from discord.User.id)
    async with SessionLocal() as db_session:
        # Query to check if the user already exists
        query = await db_session.execute(select(User).filter_by(uid=user_id))
        result = query.scalar_one_or_none()
        
        # If no result, create and add a new user
        if not result:
            new_user = User(uid=user_id)
            db_session.add(new_user)
            await db_session.commit()  # Commit to save the new user
            print(f"Created data for {user}")

async def get_data(user: discord.User):
    user_id = str(user.id)  # Ensure user_id is a string
    async with SessionLocal() as db_session:
        query = await db_session.execute(select(User).filter_by(uid=user_id))
        result = query.scalar_one_or_none()

        # If the user exists, return the result
        if result:
            stats = result.stats.copy()  # Assuming stats is a dict
            data = result.data.copy()  # Assuming data is a dict
            
            # Update stats and data with defaults
            for key, value in SAMPLE_STATS.items():
                stats[key] = stats.get(key, value)
            for key, value in SAMPLE_DATA.items():
                data[key] = data.get(key, value)
            
            result.stats = stats  # Update the stats
            result.data = data  # Update the data
            await db_session.commit()  # Commit to save the updated data
            return result
        
        # If the user doesn't exist, register the user and then return their data
        else:
            await register(user)
            return await get_data(user)  # Recursive call to get data after registration


async def CMD_error(interaction: discord.Interaction, error: Exception = None, extra: str = None):
    content = f"Command error```yaml\n{error or traceback.format_exc()}\n```"
    if extra:
        content = f"{content}\n\n{extra}"
    await interaction.followup.send(content=content)

@tree.command(name="invite", description="Bot invite link")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_say(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(content=f"https://discord.com/oauth2/authorize?client_id={client.user.id}")

@tree.command(name="test", description="i made this for testing things without doing a complete overhaul just for it to break")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_test(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(content="hey wait i got a new complaint")
    await interaction.edit_original_response(content="forever in debt to your priceless advice")

@tree.command(name="stats", description="Check the bot's stats.")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_stats(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    
    async with SessionLocal() as db_session:  # One session for both fetching and updating
        try:
            # Fetch all users from the database
            result = await db_session.execute(select(User))
            users = result.scalars().all()
            
            # Sum up the commands used by all users, defaulting to 0 if missing
            global_commands = sum([user.stats.get("Commands used", 0) for user in users])
            
            # Sum up the cash from all users, defaulting to 0 if missing
            global_cash = int(sum([user.data.get("Cash", 0) for user in users]))
            
            jsonified = [i.__dict__ for i in users]
            storage = sum([int(user.storage or 0) for user in users])

            # Prepare the data dictionary
            data = {
                "Created": f"<t:{int(client.user.created_at.timestamp())}:f>",
                "Online since": f"<t:{int(START_TIME)}:R>",
                "Operating system": platform.system(),
                "Servers": f"{len(client.guilds):,}",
                "Users": f"{len(users):,}",
                "Commands used": f"{global_commands:,}",
                # "Total cash": f"${global_cash:,}",
                "Storage wasted": "%s %s" % display_bytes(io.BytesIO(str(jsonified).encode()).getbuffer().nbytes + storage),
            }
            
            # Create the embed to display stats
            embed = discord.Embed(
                title="Awesome stats",
                description="\n".join(f"{name}: {value}" for name, value in data.items()),
            )
            
            # Send the embed with the stats
            await interaction.followup.send(embed=embed)
        except Exception as error:
            # If an error occurs, print it to the console for debugging
            print(f"Error fetching stats: {error}")
            await interaction.followup.send(content=":warning: An error occurred while fetching stats.")

# GENERATION COMMANDS

'''
@tree.command(name="save", description="Download and upload most files to the cloud (1GB limit)")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_save(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, file_name: str = None, file_ext: str = None, proxy_check: bool = True, short_url: bool = False):
    original_response = await interaction.response.defer(thinking=True)

    file_format = file_ext
    start_time = time.time()
    source_url = None
    try:
        print("BEFORE | URL:", url, "File:", file)
        if file is None and url is None:
            try:
                urls = []
                channel = interaction.channel
                history = channel.history(limit=20)
                async for i in history:
                    attachments = [attachment.url for attachment in i.attachments]
                    images = [embed.image and embed.image.url for embed in i.embeds]
                    thumbnails = [embed.thumbnail and embed.thumbnail.url for embed in i.embeds]
                    links = re.findall(r"(https?://[^\s,!?]+|www\.[^\s,!?]+|ftp://[^\s,!?]+)", i.content)
                    urls.extend([url for url in attachments + images + thumbnails + links if valid_url(url)])
                    print("Urls:", urls)
                    if len(urls) > 0:
                        break
                url = urls
            except Exception:
                raise Errors.FileNotFound
        if file is not None and url is None:
            url = file.url
        if proxy_check:
            try:
                original_url, _ = get_proxy_url(url, return_both=True)
                if original_url is not None:
                    url = original_url
            except Exception:
                pass
        if url is not None:
            if isinstance(url, list):
                for lol_url in url:
                    try:
                        file, filename = await download_file(lol_url, get_filename=True)
                        if file is not None:
                            url = lol_url
                            break
                    except Exception:
                        pass
            else:
                file, filename = await download_file(url, get_filename=True)
        source_url = url
        download_time = time.time() - start_time
        print("AFTER | URL:", url, "File:", file)
        if file is None:
            raise filename or Errors.FileNotFound
        if isinstance(file, tuple):
            file_format = file_format or file[1]
            file = file[0]
        nbytes = file.getbuffer().nbytes
        async with SessionLocal() as db_session:
            user = await get_data(user=interaction.user)
            user.storage = int(user.storage or 0) + nbytes
            db_session.add(user)
            await db_session.commit()
            
        file_size, unit = display_bytes(nbytes)
        eta = estimate_eta(nbytes)
        content = f"-# {file_size} {unit} downloaded <t:{int(time.time())}:R>\n-# Expected completion: <t:{math.ceil(time.time() + eta)}:R>"
        await interaction.followup.send(content)
        mimetype = buffer_to_mimetype(file)
        if file_format is None:
            file_format = guess_format(mimetype)
            if file_format is None:
                file_format = os.path.basename(urlparse(url).path).split(".")[-1]
        if not filename:
            filename = unquote(urlparse(url).path.split("/")[-1])
        file_name = file_name or filename
        if file_name:
            file_name = file_name[:250]
        start_time = time.time()
        url = await upload_file(file, file_format or guess_format(mimetype), file_name=file_name, interaction=interaction, text=content, short_url=short_url)
        if url is None:
            raise Errors.FileLarge
        upload_time = time.time() - start_time
        try:
            content=f"""-# **{file_size} {unit}｜↓ {round(download_time, 2)}s｜↑ {round(upload_time, 2)}s｜[Source](<{source_url}>) **\n**{url} **"""
            await interaction.edit_original_response(content=content)
            if interaction.channel.type not in (discord.ChannelType.private, discord.ChannelType.group):
                for i in range(5):
                    await asyncio.sleep(10)
                    message = await interaction.channel.fetch_message(original_response.message_id)
                    if len(message.embeds) == 0:
                        await interaction.edit_original_response(content=f"""{content}{" " * (i + 1)}""")
                    else:
                        break
            # await interaction.followup.send(content=f"""-# **{file_size} {unit}｜↓ {round(download_time, 2)}s｜↑ {round(upload_time, 2)}s｜[Source](<{source_url}>)**\n-# **{url}**""")
            # await interaction.delete_original_response()
        except Exception:
            import traceback
            print(traceback.format_exc())
            await interaction.user.send(content=url)
    except Exception as error:
        import traceback
        # error = traceback.format_exc()
        # print(error)
        await CMD_error(interaction=interaction, error=error, extra=source_url and f"URL: <{source_url}>")
'''

@tree.command(name="save", description="Download and upload most files to the cloud (1GB limit)")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_save(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, file_name: str = None, short_url: bool = False):
    original_response = await interaction.response.defer(thinking=True)

    file_format = None
    start_time = time.time()
    source_url = None
    try:
        print("BEFORE | URL:", url, "File:", file)
        if file is None and url is None:
            try:
                urls = []
                channel = interaction.channel
                history = channel.history(limit=20)
                async for i in history:
                    attachments = [attachment.url for attachment in i.attachments]
                    images = [embed.image and embed.image.url for embed in i.embeds]
                    thumbnails = [embed.thumbnail and embed.thumbnail.url for embed in i.embeds]
                    links = re.findall(r"(https?://[^\s,!?]+|www\.[^\s,!?]+|ftp://[^\s,!?]+)", i.content)
                    urls.extend([url for url in attachments + images + thumbnails + links if valid_url(url)])
                    print("Urls:", urls)
                    if len(urls) > 0:
                        break
                url = urls
            except Exception:
                raise Errors.FileNotFound
        if file is not None and url is None:
            url = file.url
        if url is not None:
            if isinstance(url, list):
                for lol_url in url:
                    try:
                        file, filename = await download_file(lol_url, get_filename=True)
                        if file is not None:
                            url = lol_url
                            break
                    except Exception:
                        pass
            else:
                file, filename = await download_file(url, get_filename=True)
        source_url = url
        download_time = time.time() - start_time
        print("AFTER | URL:", url, "File:", file)
        if file is None:
            raise filename or Errors.FileNotFound
        if isinstance(file, tuple):
            file_format = file_format or file[1]
            file = file[0]
        nbytes = file.getbuffer().nbytes
        async with SessionLocal() as db_session:
            user = await get_data(user=interaction.user)
            user.storage = int(user.storage or 0) + nbytes
            db_session.add(user)
            await db_session.commit()
            
        file_size, unit = display_bytes(nbytes)
        eta = estimate_eta(nbytes)
        content = f"-# {file_size} {unit} downloaded <t:{int(time.time())}:R>\n-# Expected completion: <t:{math.ceil(time.time() + eta)}:R>"
        await interaction.followup.send(content)
        mimetype = buffer_to_mimetype(file)
        if file_format is None:
            file_format = guess_format(mimetype)
            if file_format is None:
                file_format = os.path.basename(urlparse(url).path).split(".")[-1]
        if not filename:
            filename = unquote(urlparse(url).path.split("/")[-1])
        file_name = file_name or filename
        if file_name:
            file_name = file_name[:250]
        start_time = time.time()
        url = await upload_file(file, file_format or guess_format(mimetype), file_name=file_name, interaction=interaction, text=content, short_url=short_url)
        if url is None:
            raise Errors.FileLarge
        upload_time = time.time() - start_time
        try:
            content=f"""-# **{file_size} {unit}｜↓ {round(download_time, 2)}s｜↑ {round(upload_time, 2)}s｜[Source](<{source_url}>) **\n**{url} **"""
            await interaction.edit_original_response(content=content)
            if interaction.channel.type not in (discord.ChannelType.private, discord.ChannelType.group):
                for i in range(5):
                    await asyncio.sleep(10)
                    message = await interaction.channel.fetch_message(original_response.message_id)
                    if len(message.embeds) == 0:
                        await interaction.edit_original_response(content=f"""{content}{" " * (i + 1)}""")
                    else:
                        break
        except Exception:
            import traceback
            print(traceback.format_exc())
            await interaction.user.send(content=url)
    except Exception as error:
        import traceback
        await CMD_error(interaction=interaction, error=error, extra=source_url and f"URL: <{source_url}>")
        
"""
@tree.command(name="container", description="Make a cool container")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_container(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
    await interaction.response.defer(thinking=True)
    if file is not None and url is None:
        url = file.url
    await interaction.followup.send(view=Container(files=url))
"""

@tree.command(name="ghost", description="sends a message that poofs. I mainly made this to keep threads alive")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_container(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(":ghost:")
    await asyncio.sleep(5)
    await interaction.delete_original_response()

@tree.command(name="revive", description="message in all threads")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def CMD_container(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("u dont got perms bru")
        return

    for thread in interaction.guild.threads:
        message = await thread.send(content="HI")
        await message.delete()
    await interaction.followup.send("done lol")
    
@tree.command(name="availability", description="Checks websites to see where a name is available, even for websites no one uses, sherlock command?")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_availability(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    async with aiohttp.ClientSession() as session:
        try:
            name = name.lower().strip().replace(" ", "")
            webhooks = environ.get("WEBHOOKS").strip().split(" ")

            class Checker():
                @staticmethod
                async def instagram():
                    start = time.time()
                    url = f"https://www.instagram.com/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        new_msg = await webhook.fetch_message(message.id)
                        taken = len(new_msg.embeds) > 0 and new_msg.embeds[0]
                        if taken:
                            break
                        await asyncio.sleep(0.5)
                    displayName = taken and " ".join(taken.description.split(" ")[13:]).strip()
                    display = displayName and f"[`{displayName}`](https://www.instagram.com/{name})"
                    return {
                        "message": f"<:instagram:1389281520891465789> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def twitter():
                    start = time.time()
                    async with session.get(f"https://vxtwitter.com/{name}") as response:
                        resp = await response.text()
                        soup = BeautifulSoup(resp, "html.parser")
                        suspended = "User has been suspended." in resp
                        taken = soup.find("meta", attrs={"name": "og:title"})
                        display = (suspended and f"`{name} {SUSPENDED}`") or (taken and f"[`{taken.get('content')}`](https://x.com/{name})")
                        return {
                            "message": f"<:twitter:1389281191957631047> {display or ''}",
                            "taken": bool(taken or suspended),
                            "time": time.time() - start
                        }
                
                @staticmethod
                async def youtube():
                    start = time.time()
                    params = {
                        "part": "id,snippet,statistics,contentDetails,topicDetails",
                        "forHandle": name,
                        "type": "channel",
                        "key": YT_KEY
                    }
                    async with session.get(f"https://www.googleapis.com/youtube/v3/channels", params=params) as response:
                        resp = await response.json()
                        taken = resp.get("items")
                        details = taken and taken[0]
                        snippet = details and details.get("snippet")
                        display = taken and f"[`{snippet.get('title')} ({snippet.get('customUrl')})`](https://www.youtube.com/channel/{details.get('id')})"
                        return {
                            "message": f"<:youtube:1389298081811533969> {display or ''}",
                            "taken": bool(taken),
                            "time": time.time() - start
                        }
                
                @staticmethod
                async def roblox():
                    start = time.time()
                    body = {"usernames": [name], "excludeBannedUsers": False}
                    async with session.post("https://users.roblox.com/v1/usernames/users", json=body) as response:
                        resp = await response.json()
                        details = resp.get("data")
                        taken = len(details) > 0
                        details = taken and details[0]
                        suspended = False
                        if taken:
                            userId = details.get("id")
                            async with session.get(f"https://www.roblox.com/users/{userId}/profile") as response:
                                suspended = response.status == 404
                        display = (suspended and f"`{details.get('name')} {SUSPENDED}`") or (taken and f"[`{details.get('name')}`](https://www.roblox.com/users/{userId}/profile)")
                        # display = taken and f"[{snippet.get('title')} ({snippet.get('customUrl')})]({newUrl})" or f"@{name}"
                        return {
                            "message": f"<:roblox:1389282531513339944> {display or ''}",
                            "taken": bool(taken),
                            "time": time.time() - start
                        }
                
                @staticmethod
                async def twitch():
                    start = time.time()
                    url = f"https://twitch.tv/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        loaded = len(new_msg.embeds) > 0 and new_msg.embeds[0].title
                        if loaded:
                            break
                    divider = " - Twitch"
                    taken = loaded and divider in loaded
                    displayName = taken and loaded.split(divider)[0]
                    display = displayName and f"[`{displayName}`](https://twitch.tv/{name})"
                    return {
                        "message": f"<:twitch:1389723439702741032> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def reddit():
                    start = time.time()
                    url = f"https://reddit.com/user/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        taken = len(new_msg.embeds) > 0 and new_msg.embeds[0].title
                        if taken:
                            break
                    match = taken and re.search(r"Check out (.+?)[’']s Reddit profile", taken)
                    displayName = match and match.group(1)
                    display = displayName and f"[`{displayName}`](https://www.reddit.com/u/{name})"
                    return {
                        "message": f"<:reddit:1389721901282103326> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def lastfm():
                    start = time.time()
                    url = f"https://last.fm/user/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        taken = len(new_msg.embeds) > 0 and new_msg.embeds[0].title
                        if taken:
                            break
                    match = taken and re.search(r"(.+?)’s Music Profile", taken)
                    displayName = match and match.group(1)
                    display = displayName and f"[`{displayName}`](https://last.fm/user/{name})"
                    return {
                        "message": f"<:lastfm:1389724180269764760> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def anilist():
                    start = time.time()
                    url = f"https://anilist.co/user/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        loaded = len(new_msg.embeds) > 0
                        if loaded:
                            break
                    taken = loaded and new_msg.embeds[0].title
                    display = taken and f"[`{taken}`](https://anilist.co/user/{name})"
                    return {
                        "message": f"<:anilist:1389734362357960856> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def duolingo():
                    start = time.time()
                    async with session.get(f"https://duolingo.com/profile/{name}", allow_redirects=True) as response:
                        resp = await response.text()
                        soup = BeautifulSoup(resp, "html.parser")
                        title = soup.find("meta", attrs={"property": "og:title"})
                        taken = title and re.match(r"^(.*?) on Duolingo$", title.get("content"))
                        displayName = taken and taken.group(1)
                        username = str(response.url).split("/")[-1]
                        display = displayName and f"[`{displayName} (@{username})`]({response.url})"
                        return {
                            "message": f"<:duolingo:1389734314102489168> {display or ''}",
                            "taken": bool(taken),
                            "time": time.time() - start
                        }
                
                @staticmethod
                async def minecraft():
                    start = time.time()
                    url = f"https://crafty.gg/@{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        loaded = len(new_msg.embeds) > 0 and new_msg.embeds[0]
                        if loaded:
                            break
                    taken = loaded and re.match(r"^(.*?) Minecraft Player Profile", loaded.title)
                    displayName = taken and taken.group(1)
                    display = displayName and f"[`{displayName}`](https://crafty.gg/@{displayName})"
                    return {
                        "message": f"<:minecraft:1389743548756131962> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }
                
                @staticmethod
                async def myanimelist():
                    start = time.time()
                    url = f"https://myanimelist.net/profile/{name}?{start}"
                    webhook = discord.Webhook.from_url(url=random.choice(webhooks), session=session)
                    message = await webhook.send(url, wait=True)
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        new_msg = await webhook.fetch_message(message.id)
                        loaded = len(new_msg.embeds) > 0
                        if loaded:
                            break
                    taken = loaded and re.match(r"^(.*?)['’]s Profile", new_msg.embeds[0].title)
                    displayName = taken and taken.group(1)
                    display = displayName and f"[`{displayName}`](https://myanimelist.net/profile/{name})"
                    return {
                        "message": f"<:myanimelist:1389751756451352742> {display or ''}",
                        "taken": bool(taken),
                        "time": time.time() - start
                    }

            functions = [getattr(Checker, attr) for attr in dir(Checker) if isinstance(inspect.getattr_static(Checker, attr), staticmethod)]
            tasks = [asyncio.create_task(func()) for func in functions]
            info = await asyncio.gather(*tasks)

            statuses = [
                {"title": "No matches", "empty": "None :("},
                {"title": "Results", "empty": "None :D", "join": "\n", "prefix": ""}
            ]

            embed = discord.Embed(
                title=f"Search for @{name}",
                description=""
            )

            batch = sorted([i for i in info if i is not None], key=lambda d: d["time"])

            for i, v in enumerate(statuses):
                pool = [f"{j.get('prefix') or ''}{j.get('message')}" for j in batch if i == int(bool(j.get("taken")))]
                embed.add_field(name=v.get("title"), value=len(pool) > 0 and v.get("join", " ").join(pool) or v.get("empty", ""), inline=False)
            embed.set_footer(text="⚠️ Results may be inaccurate due to banned accounts or rate limits")
            await interaction.followup.send(embed=embed)
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

PROXY_MAP = {
    "instagram.com": ["instagramfix.com", "kirkstagram.com", "kkinstagram.com", "eeinstagram.com"],
    "x.com": ["fixupx.com", "fxtwitter.com", "vxtwitter.com", "fixvx.com", "twitter.com", "hitlerx.com"],
    "tiktok.com": ["tiktokfix.com", "vxtiktok.com", "fixtiktok.com", "tiktokfixer.com"],
}

TRACKING_PARAMS = {"igsh", "igsi", "si", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid", "t", "s", "stkn"}

REVERSE_PROXY_MAP = {proxy: original for original, proxies in PROXY_MAP.items() for proxy in proxies}

def get_proxy_url(url: str, return_both: bool = False, refresh: bool = False):
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    domain = parsed.netloc.replace("www.", "")
    
    if domain in PROXY_MAP:
        original = domain
    elif domain in REVERSE_PROXY_MAP:
        original = REVERSE_PROXY_MAP[domain]
    else:
        raise ValueError("Unknown service")
    
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {k: v for k, v in query_params.items() if k not in TRACKING_PARAMS}
    new_query = urlencode(filtered_params, doseq=True)
    path = parsed.path + ("?" + new_query if new_query else "")
    
    original_url = f"https://{original}{path}"
    primary_proxy = PROXY_MAP[original][0]
    proxy_url = f"https://{primary_proxy}{path}"
    if refresh:
        separator = "&" if "?" in path else "?"
        proxy_url += f"{separator}lol={int(time.time())}"
    
    return (original_url, proxy_url) if return_both else proxy_url

@tree.command(name="fix", description="Finds an embed proxy for a social media URL with tracking params stripped")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_proxy(interaction: discord.Interaction, url: str, both: bool = False, hide: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=hide)
    async with aiohttp.ClientSession() as session:
        try:
            original_url, proxy_url = get_proxy_url(url, return_both=True)
            async with session.get(proxy_url) as response:
                html = await response.text()

                soup = BeautifulSoup(html, 'html.parser')
                
                has_video = soup.find('meta', property='og:video')
                if not has_video:
                    og_image = soup.find('meta', property='og:image') or soup.find('meta', property='twitter:image')
                    if og_image:
                        image_url = og_image.get('content', '')
                        if image_url and 'tweet_video_thumb' in image_url:
                            proxy_url = proxy_url.replace("https://fixupx.com/", "https://fixvx.com/")

            output = both and f"Original: <{original_url}>\nProxied: {proxy_url}" or proxy_url
            print(original_url, proxy_url)
            await interaction.followup.send(output)
            
        except ValueError as e:
            await interaction.followup.send(str(e))
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

@tree.command(name="unfix", description="Finds the original social media URL with tracking params stripped")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_proxy2(interaction: discord.Interaction, url: str, both: bool = False, hide: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=hide)
    async with aiohttp.ClientSession() as session:
        try:
            original_url, proxy_url = get_proxy_url(url, return_both=True)
            async with session.get(proxy_url) as response:
                html = await response.text()

                soup = BeautifulSoup(html, 'html.parser')
                
                has_video = soup.find('meta', property='og:video')
                if not has_video:
                    og_image = soup.find('meta', property='og:image') or soup.find('meta', property='twitter:image')
                    if og_image:
                        image_url = og_image.get('content', '')
                        if image_url and 'tweet_video_thumb' in image_url:
                            proxy_url = proxy_url.replace("https://fixupx.com/", "https://fixvx.com/")

            output = both and f"Original: <{original_url}>\nProxied: {proxy_url}" or original_url
            print(original_url, proxy_url)
            await interaction.followup.send(output)
            
        except ValueError as e:
            await interaction.followup.send(str(e))
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)
            
@tree.command(name="favicon", description="Fetch favicon from (almost) any website")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_favicon(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "sz": "256",
                "domain_url": url
            }
            async with session.get("https://www.google.com/s2/favicons", params=params) as response:
                response.raise_for_status()
                embed = discord.Embed(
                    description=f"https://www.google.com/s2/favicons?{urlencode(params)}"
                )
                embed.set_image(url=str(response.url))
        await interaction.followup.send(embed=embed)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="gif", description="Resend image as a fake gif")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_gif(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            try:
                urls = []
                channel = interaction.channel
                history = channel.history(limit=20)
                async for i in history:
                    attachments = [attachment.url for attachment in i.attachments]
                    images = [embed.image and embed.image.url for embed in i.embeds]
                    thumbnails = [embed.thumbnail and embed.thumbnail.url for embed in i.embeds]
                    links = re.findall(r"(https?://[^\s,!?]+|www\.[^\s,!?]+|ftp://[^\s,!?]+)", i.content)
                    urls.extend([url for url in attachments + images + thumbnails + links if valid_url(url)])
                    if len(urls) > 0:
                        break
                url = urls[0]
            except Exception:
                raise Errors.FileNotFound
        if file is not None:
            url = file.url
        file = await download_file(url, mbLimit=8)
        upload_file = discord.File(file, filename="lol.gif")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

if TESTING:
    @tree.command(name="say")
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def CMD_download(interaction: discord.Interaction, text: str):
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(text)
        for _ in range(20):
            await asyncio.sleep(1)
            message = await interaction.original_response()
            for embed in message.embeds:
                print(embed, embed.image.url, embed.thumbnail.url, embed.video.url, embed.provider.url)
    # https://kirkstagram.com/reel/Ddc4yMasAu2/

@tree.command(name="download", description="Download files (/save is also better)")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_download(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, file_name: str = None, file_format: str = None):
    await interaction.response.defer(thinking=True)
    start_time = time.time()
    try:
        if file is None and url is None:
            try:
                urls = []
                channel = interaction.channel
                history = channel.history(limit=20)
                async for i in history:
                    attachments = [attachment.url for attachment in i.attachments]
                    images = [embed.image and embed.image.url for embed in i.embeds]
                    thumbnails = [embed.thumbnail and embed.thumbnail.url for embed in i.embeds]
                    links = re.findall(r"(https?://[^\s,!?]+|www\.[^\s,!?]+|ftp://[^\s,!?]+)", i.content)
                    urls.extend([url for url in attachments + images + thumbnails + links if valid_url(url)])
                    if len(urls) > 0:
                        break
                url = urls[0]
            except Exception:
                raise Errors.FileNotFound
        if file is not None:
            url = file.url
        file, filename = await download_file(url, mbLimit=8, get_filename=True)
        download_time = time.time() - start_time

        if not file:
            await interaction.followup.send(content="file too big or failed to download, try /save instead :D")
            return
            
        mimetype = buffer_to_mimetype(file)
        if file_format is None:
            file_format = guess_format(mimetype)
            if file_format is None:
                file_format = os.path.basename(urlparse(url).path).split(".")[-1]
            
        if not filename:
            file_name = unquote(urlparse(url).path.split("/")[-1])
        file_name = file_name or filename
        if file_name:
            file_name = file_name[:250]
        else:
            file_name = f"untitled.{file_format}"
        
        if not Path(file_name).suffix:
            file_name = f"{file_name}.{file_format}"
        print("filename:", file_name, "format:", file_format)
        
        upload_file = discord.File(file, filename=file_name)

        nbytes = file.getbuffer().nbytes
        file_size, unit = display_bytes(nbytes)

        #path = Path(file_name.replace("_", " ")).stem
        view = Container(title=file_name.replace("_", " "), files=upload_file)
        container = view.container
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"""{file_size} {unit} ｜ {mimetype} ｜ Download: {round(download_time, 2)}s"""))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("Use /save for better quality. Files over 500MB may fail."))
        
        await interaction.followup.send(view=view, file=upload_file)
        #await interaction.followup.send(content="Want better quality? Use /save for large files\n-# no limit but files larger than 500MB can fail", file=discord.File(file, filename=file_name), view=Container())
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="trim", description="Trim whitespace around a transparent image")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(square="Crop the image 1:1")
@app_commands.describe(whitespace="Whitespace area: 1-1000")
@app_commands.describe(sharpen="honestly i probably got this backwards but I recommend leaving it None/False")
@app_commands.describe(size="resizes base image to whatever you put here bruh (cant be larger than actual image)")
async def CMD_trim(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, square: bool = False, sharpen: bool = False, whitespace: int = None, size: int = None):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file, ignore_recolor=not sharpen)
        start2 = time.time()
        await file.trim()
        if size:
            await file.thumbnail((size, size))
        if square:
            size = tuple(max(file.image.size) for _ in range(2))
            blank: Editor = Editor()
            await blank.convert("RGBA")
            await blank.resize(size=size)
            blank_width, blank_height = blank.image.size
            file_width, file_height = file.image.size

            center_x = (blank_width - file_width) // 2
            center_y = (blank_height - file_height) // 2
            center = (center_x, center_y)

            await blank.paste(file, position=center)
            file = blank
        if whitespace:
            whitespace = clamp(whitespace, 1, 1000)
            size = tuple(i + whitespace for i in file.image.size)
            blank: Editor = Editor()
            await blank.convert("RGBA")
            await blank.resize(size=size)
            blank_width, blank_height = blank.image.size
            file_width, file_height = file.image.size

            center_x = (blank_width - file_width) // 2
            center_y = (blank_height - file_height) // 2
            center = (center_x, center_y)

            await blank.paste(file, position=center)
            file = blank
        
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="bleed", description="Bleed opaque pixels into transparent areas")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_bleed(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file)
        await file.bleed()
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="resize", description="Resize image")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_resize(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, width: int = None, height: int = None):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file)
        start2 = time.time()
        await file.thumbnail((width or height or 512, height or width or 512))
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="whitespace", description="Add whitespace to an image")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(whitespace="Whitespace area: 1-1000 (10 by default)")
async def CMD_whitespace(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, whitespace: int = 10):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file, ignore_recolor=True)
        start2 = time.time()
        if whitespace:
            whitespace = clamp(whitespace, 1, 1000)
            size = tuple(i + whitespace for i in file.image.size)
            blank: Editor = Editor()
            await blank.convert("RGBA")
            await blank.resize(size=size)
            blank_width, blank_height = blank.image.size
            file_width, file_height = file.image.size

            center_x = (blank_width - file_width) // 2
            center_y = (blank_height - file_height) // 2
            center = (center_x, center_y)

            await blank.paste(file, position=center)
            file = blank
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="circle", description="Make an image circular")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def CMD_circle(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, trim: bool = False):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file)
        start2 = time.time()
        if trim:
            await file.trim()
        size = tuple(min(file.image.size) for _ in range(2))
        await file.resize(size=size, crop=True)
        await file.circle()
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="blur", description="Make an image blurry")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.choices(mode=[
    app_commands.Choice(name="Box (default)", value="box"),
    app_commands.Choice(name="Gaussian", value="gaussian")
])
@app_commands.describe(radius="Strength of the blur")
@app_commands.describe(mode="What blur algorithm should be used")
async def CMD_blur(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, mode: app_commands.Choice[str] = None, radius: int = 10):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        if mode is None:
            mode = "box"
        else:
            mode = mode.value
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file)
        start2 = time.time()
        await file.blur(mode=mode, radius=radius)
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

@tree.command(name="stroke", description="Add a cool stroke to an image (make sure its transparent tho or it just wont work lol)")
@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(whitespace="Whitespace area: 1-1000")
@app_commands.describe(thickness="Stroke thickness (default: 5)")
@app_commands.describe(hex_color="color in hex format (you know what i mean)")
async def CMD_stroke(interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, thickness: int = 5, hex_color: str = "#ffffff", whitespace: int = None, trim: bool = False):
    await interaction.response.defer(thinking=True)
    try:
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        embed = create_embed(user=interaction.user)
        start = time.time()
        temp_file = await download_file(url)
        file: Editor = Editor()
        await file.load(source=temp_file)
        start2 = time.time()
        await file.stroke(thickness=thickness, color=hex_to_rgb(hex_color))
        if trim:
            await file.trim()
        if whitespace:
            whitespace = clamp(whitespace, 1, 1000)
            size = tuple(i + whitespace for i in file.image.size)
            blank: Editor = Editor()
            await blank.convert("RGBA")
            await blank.resize(size=size)
            blank_width, blank_height = blank.image.size
            file_width, file_height = file.image.size

            center_x = (blank_width - file_width) // 2
            center_y = (blank_height - file_height) // 2
            center = (center_x, center_y)

            await blank.paste(file, position=center)
            file = blank
        upload_file = discord.File(file.image_bytes, filename="image.png")
        view = Container(files=upload_file)
        await interaction.followup.send(view=view, file=upload_file)
    except Exception as error:
        import traceback
        print(traceback.format_exc())
        await CMD_error(interaction=interaction, error=error)

    

# i wanted the command to look like /pixel art so ya lol

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class PixelGroup(app_commands.Group, name="pixel", description="pixel commands"):
    @app_commands.command(name="art_old", description="Convert an image into decent pixel art")
    @app_commands.describe(simple="(FALSE BY DEFAULT) - the pixel art's palette will be simpler, I had no idea what to call this but you will see what i mean if you check this")
    @app_commands.describe(colors_to_keep="(48 BY DEFAULT) - if simple is true, how many colors to keep in image")
    @app_commands.describe(stretch="(FALSE BY DEFAULT) - stretch image to fit")
    @app_commands.describe(trim="(TRUE BY DEFAULT) - whitespace will be trimmed before conversion")
    @app_commands.describe(background_color="(NONE BY DEFAULT) - background color for an image, will be transparent if color is invalid")
    @app_commands.describe(remove_translucent="(TRUE BY DEFAULT) - translucent pixels will be removed")
    async def CMD_pixelart(self, interaction: discord.Interaction, file: discord.Attachment = None, url: str = None, grid_size: int = None, stretch: bool = False, trim: bool = False, simple: bool = False, colors_to_keep: int = 48, background_color: str = None, crop: bool = False, remove_translucent: bool = True, upscale: bool = False):
        await interaction.response.defer(thinking=True)
        async with aiohttp.ClientSession() as session:
            try:
                if file is None and url is None:
                    url = interaction.user.avatar.url
                    # raise Errors.FileNotFound
                if file is not None:
                    url = file.url
                if grid_size is None:
                    grid_size = 128
                else:
                    grid_size = clamp(grid_size, 1, 256)
                start = time.time()
                file: Editor = Editor()
                source = await download_file(url)
                start2 = time.time()
                if background_color is not None:
                    background_color = hex_to_rgb(background_color) + (255,) # python is weird and u need a comma here for some reason
                await file.load(source=source, color=background_color)

                if remove_translucent == True:
                    px = file.image.load()
                    for y in range(file.image.size[1]):
                        for x in range(file.image.size[0]):
                            r, g, b, a = px[x, y]
                            # if remove_black == True and r + g + b < 25*3: px[x, y] = (0, 0, 0, 0)
                            if a < 255: px[x, y] = (0, 0, 0, 0)

                if crop == False:
                    size = tuple(max(file.image.size) for _ in range(2))
                    new: Editor = Editor(Image.new("RGBA", size))
                    overlay_size = file.image.size
                    x = (size[0] - overlay_size[0]) // 2
                    y = (size[1] - overlay_size[1]) // 2
                    await new.paste(file, (x, y), file)
                    await file.load(source=new.image_bytes)
                if trim == True:
                    await file.trim()
                if stretch == False:
                    size = tuple(min(file.image.size) for _ in range(2))
                    await file.resize(size=size, crop=True)
                if simple == True:
                    await file.reduce_colors(colors=colors_to_keep)

                await file.pixelate(width=grid_size, height=grid_size, resample=True)
                if upscale == True:
                    await file.resize((512, 512), False)
                    await file.thumbnail((512, 512))
                else:
                    await file.thumbnail((grid_size, grid_size))
                new = Editor()
                await new.load(file.image_bytes)
                await file.crop(new.image.getbbox())

                upload_file = discord.File(file.image_bytes, filename="image.png")
                view = Container(files=upload_file)
                await interaction.followup.send(view=view, file=upload_file)
            except Exception as error:
                import traceback
                print(traceback.format_exc())
                await CMD_error(interaction=interaction, error=error)

    @app_commands.command(name="art", description="Generates pixel art from an image")
    @app_commands.describe(file="Image file (optional, uses your avatar if not provided)")
    @app_commands.describe(url="Image URL (optional, uses your avatar if not provided)")
    @app_commands.describe(size="Max pixels for longest edge when width/height not set (Default: 128, range: 1-512)")
    @app_commands.describe(upscale="Upscale to at least 1024px on any side (Default: True)")
    @app_commands.describe(square="Pad to square with transparent background (Default: False)")
    async def CMD_photo2pixel(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment = None,
        url: str = None,
        size: int = 128,
        upscale: bool = True,
        square: bool = False
    ):
        await interaction.response.defer(thinking=True)
        try:
            if not file and not url:
                url = interaction.user.avatar.url
            if file:
                url = file.url

            source_bytes = await download_file(url)
            # Instead of Editor().load(), do this:
            overlay = Image.open(source_bytes).convert("RGBA")
            blank = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
            blank.paste(overlay, (0, 0), overlay)
            img = blank

            limit = 512
            img = img.crop(img.getbbox())
            img.thumbnail((limit, limit))

            size = clamp(size, 1, limit)

            cfg = {
                "width": None,
                "height": None,
                "auto_long_edge": size,
                "trim": True,
                "trim_tolerance": 12,
                "sample_size": 8,
                "kernel_size": 11,
                "num_bins": 4,
                "palette_dither": False,
                "palette_method": "maxcoverage",
                "alpha_threshold": 128,
                "edges": {                    # ADD THIS
                    "enabled": False,
                    "threshold": 100,
                    "thickness": 1,
                },
                "upscale": 1,
                "trim_final": True,
                "square": square,

                "blend_from_source": True,
                "black_threshold": 30,
                "blend_strength": 1.0,
            }

            raw, _, stats = await run_in_executor(to_pixel_art, img, cfg, img)

            if upscale:
                w, h = raw.size
                min_side = min(w, h)
                if min_side < 1024:
                    scale = 1024 / min_side
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    raw = raw.resize((new_w, new_h), Image.Resampling.NEAREST)

            img_bytes = io.BytesIO()
            raw.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            upload_file = discord.File(img_bytes, filename="pixel_art.png")
            view = Container(files=upload_file, footer=f"""Size: {size}｜Grid: {stats['grid'][0]}x{stats['grid'][1]}｜Colors: {stats["colors_after"]:,}｜[Source](<{url}>)""")
            await interaction.followup.send(view=view, file=upload_file)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=e)
            
tree.add_command(PixelGroup())

# ai commands

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class AiGroup(app_commands.Group, name="ai", description="ai commands"):
    @app_commands.command(name="image", description="Generate images using AI")
    async def CMD_ai_image(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        async with aiohttp.ClientSession() as session:
            try:
                embed = create_embed(user=interaction.user)
                start = time.time()
                file: Editor = Editor()

                data = {
                    "context_id": "idk what this is used for but api works if you put any thing",
                    "imageSize": "square",
                    "numImages": 1, # new endpoint
                    "num_candidates": 1, # old endpoint
                    "prompt": prompt
                }
                headers = {
                    "Authorization": f"Token {environ.get('AI')}"
                }
                async with session.post("https://plus.character.ai/chat/character/generate-avatar-options", json=data, headers=headers) as resp:
                    resp = json.loads(await resp.text())
                    print("ai resp", resp)
                    result = resp.get("result")[0]
                source = await download_file(result)
                await file.load(source=source)

                upload_file = discord.File(file.image_bytes, filename="image.png")
                view = Container(files=upload_file)
                await interaction.followup.send(view=view, file=upload_file)
            except Exception as error:
                import traceback
                print(traceback.format_exc())
                await CMD_error(interaction=interaction, error=error)

            
tree.add_command(AiGroup())

# search/find COMMANDS

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class FindGroup(app_commands.Group, name="find", description="commands for finding stuff from a search, like google but for bad things"):
    @app_commands.command(name="album", description="Find any album cover from apple music")
    async def CMD_album(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        async with aiohttp.ClientSession() as session:
            try:
                if query is None:
                    raise Errors.InvalidParameter
                params = {
                    "term": query,
                    "country": "us",
                    "entity": "album",
                    "limit": 25
                }
                async with session.get("https://itunes.apple.com/search", params=params) as resp:
                    # this silly api is allergic to content-type: application/json
                    resp = json.loads(await resp.text())
                source = resp.get("results")[0]
                title = f"""{source.get("artistName")} - {source.get("collectionName")}"""
                url = source.get("artworkUrl100").replace("100x100bb.jpg", "500x500bb.jpg")

                embed = create_embed(user=interaction.user, title=title[:256])
                start = time.time()
                temp_file = await download_file(url)
                file: Editor = Editor()
                await file.load(source=temp_file)
                await file.trim()

                upload_file = discord.File(file.image_bytes, filename="image.png")
                view = Container(files=upload_file)
                await interaction.followup.send(view=view, file=upload_file)
            except Exception as error:
                import traceback
                print(traceback.format_exc())
                await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="anime", description="search for an anime based on a screenshot")
    async def CMD_searchanime(self, interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
        await interaction.response.defer(thinking=True)
        async with aiohttp.ClientSession() as session:
            try:
                if file is None and url is None:
                    url = interaction.user.avatar.url
                if file is not None:
                    url = file.url
                params = {
                    "url": url
                }
                async with session.get("https://api.trace.moe/search?anilistInfo&cutBorders", params=params, headers={"User-Agent": "Mozilla"}) as resp:
                    resp = json.loads(await resp.text()) # await resp.json()
                    temp = resp.get("result")[0]
                    params = {
                        "size": "l"
                    }
                    titles = [i for i in list(reversed(temp.get("anilist").get("title").values())) if i is not None]
                    title = f"""[{titles[0]}](<https://anilist.co/anime/{temp.get("anilist").get("id")}>)"""
                    # minutes, seconds = int(taken // 60), int(taken % 60)
                    start = temp.get("from")
                    finish = temp.get("to")
                    start_minutes = int(start // 60)
                    start_seconds = int(start % 60)
                    finish_minutes = int(finish // 60)
                    finish_seconds = int(finish % 60)
                    similarity = round(temp.get("similarity")*100, 2)
                    stats = {
                        "Anime": title,
                        "Episode": temp.get("episode") or "Unknown",
                        "Timestamp": f"{start_minutes}:{start_seconds:02} - {finish_minutes}:{finish_seconds:02}",
                        "Similarity": f"""{similarity}%"""
                    }
                    extra = ""
                    video_url = f"""{temp.get("video")}?size=l"""
                    print(video_url)
                    if similarity <= 95:
                        extra = ":warning: Try cropping your image or reverse image searching for better accuracy\n"
                    try:
                        copy = stats.copy()
                        # title = copy.pop("Anime", "???")
                        info = " ｜ ".join([f"{k}: {v}" for k, v in copy.items()])
                        file = discord.File(await download_file(video_url), f"{titles[0]}.mp4")
                        view = Container(files=file, description=f"{info}\n{extra}")
                        await interaction.followup.send(view=view, file=file)
                    except Exception:
                        info = "\n".join([f"{k}: {v}" for k, v in stats.items()])
                        await interaction.followup.send(content=f"{info}\n{extra}\nURL: {video_url}-# Credit to [trace.moe](<https://trace.moe>)")
            except Exception as error:
                import traceback
                print(traceback.format_exc())
                await CMD_error(interaction=interaction, error=error)

            
tree.add_command(FindGroup())


@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class FormatGroup(app_commands.Group, name="format", description="commands for formatting text"):
    @app_commands.command(name="wikipedia", description="Convert a string to match the Wikipedia title format")
    async def CMD_wikipedia(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
                "x-requested-with": "XMLHttpRequest",
                "Cookie": "styleA=false; styleB=false; styleC=false; styleD=false; styleM=false; styleN=false; styleP=false; styleW=false; styleS=true; styleL=false; styleU=false; optionSE=false; optionPC=true; optionML=true; optionHC=false; optionCP=false; optionSQ=false",
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                data = {
                    "preserveAllCaps": True,
                    "styleW": True,
                    "title": message
                }
                async with session.post("https://titlecaseconverter.com/tcc/", json=data) as resp:
                    resp = await resp.json()
                joints = " ".join([i.get("word") for i in resp[0].get("title")])
                new_message = re.sub(r"[\ue000-\uf8ff]", "", joints).replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="nytimes", description="Convert a string to match the New York Times title format")
    async def CMD_NYtimes(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
                "x-requested-with": "XMLHttpRequest",
                "Cookie": "styleA=false; styleB=false; styleC=false; styleD=false; styleM=false; styleN=false; styleP=false; styleW=false; styleS=true; styleL=false; styleU=false; optionSE=false; optionPC=true; optionML=true; optionHC=false; optionCP=false; optionSQ=false",
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                data = {
                    "preserveAllCaps": True,
                    "styleN": True,
                    "title": message
                }
                async with session.post("https://titlecaseconverter.com/tcc/", json=data) as resp:
                    resp = await resp.json()
                joints = " ".join([i.get("word") for i in resp[0].get("title")])
                new_message = re.sub(r"[\ue000-\uf8ff]", "", joints).replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="sentence", description="Convert a string to match generic sentence format")
    async def CMD_sentence(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
                "x-requested-with": "XMLHttpRequest",
                "Cookie": "styleA=false; styleB=false; styleC=false; styleD=false; styleM=false; styleN=false; styleP=false; styleW=false; styleS=true; styleL=false; styleU=false; optionSE=false; optionPC=true; optionML=true; optionHC=false; optionCP=false; optionSQ=false",
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                data = {
                    "styleS": True,
                    "title": message
                }
                async with session.post("https://titlecaseconverter.com/scc1/", json=data) as resp:
                    resp = json.loads(await resp.text())
                joints = resp[0].get("title")
                new_message = re.sub(r"[\ue000-\uf8ff]", "", joints).replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="uppercase", description="Convert a string to UPPER CASE")
    async def CMD_uppercase(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            joints = message.upper()
            new_message = joints.replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="lowercase", description="Convert a string to lower case")
    async def CMD_lowercase(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            joints = message.lower()
            new_message = joints.replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="random", description="Convert a string to rANdOm CasE")
    async def CMD_randomcase(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            joints = "".join([random.choice([i.upper(), i.lower()]) for i in message])
            new_message = joints.replace("@", "@\u200B")
            await interaction.followup.send(content=new_message)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
    
    @app_commands.command(name="alternating", description="Convert a string to AlTeRnAtInG cAsE")
    async def CMD_altcase(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        def alternating_case(text):
            result = ""
            toggle = True
            for char in text:
                if char.isalpha():
                    if toggle:
                        result += char.lower()
                    else:
                        result += char.upper()
                    toggle = not toggle
                else:
                    result += char
            return result
        try:
            joints = alternating_case(message)
            new_message = joints.replace("@", "@\u200B")
            await interaction.followup.send(content=f"{new_message}")
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)
            
tree.add_command(FormatGroup())

# USER COMMANDS

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class UserGroup(app_commands.Group, name="user", description="user commands"):
    @app_commands.command(name="avatar", description="Gets the avatar of a user")
    async def CMD_avatar(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        try:
            if user is not None:
                user = await client.fetch_user(user.id)
            else:
                user = await client.fetch_user(interaction.user.id)
            embed = create_embed(
                user=interaction.user,
                title=f"{user.name}",
            )
            try:
                url = user.avatar.url
            except Exception:
                url = "https://cdn.discordapp.com/embed/avatars/1.png"
            embed.set_image(url=url)
            temp_file = await download_file(url)
            file_size, unit = display_bytes(temp_file.getbuffer().nbytes)
            download = present_download(url, file_size, unit)
            embed.description = download
            await interaction.followup.send(embed=embed)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)

    @app_commands.command(name="banner", description="Gets the banner of a user")
    async def CMD_banner(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        try:
            if user is not None:
                user = await client.fetch_user(user.id)
            else:
                user = await client.fetch_user(interaction.user.id)
            embed = create_embed(
                user=interaction.user,
                title=f"{user.name}",
            )
            url = user.banner.url
            file = Editor()
            await file.load(source=url)
            embed.set_image(url=url)
            temp_file = await download_file(url)
            file_size, unit = display_bytes(temp_file.getbuffer().nbytes)
            download = present_download(url, file_size, unit)
            embed.description = download
            await interaction.followup.send(embed=embed)
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)


    @app_commands.command(name="info", description="Gets info about a user")
    async def CMD_info(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        try:
            if user is not None:
                user = await client.fetch_user(user.id)
            else:
                user = await client.fetch_user(interaction.user.id)
            badge_emojis = {
                "hypesquad_bravery": "<:_:1302653703811108914>",
                "hypesquad_balance": "<:_:1302653655203188867>",
                "hypesquad_brilliance": "<:_:1302653751328243813>",
                "active_developer": "<:_:1302656999389003836>",
                "discord_certified_moderator": "<:_:1303502360022093896>",
                "early_supporter": "<:_:1303502419313033270>",
                "nitro": "<:_:1303500898273595503>",
                "verified_bot": "<:_:1303506660421013535><:_:1303506695246319688>",
                "app": "<:_:1303507953667670137><:_:1303507983157821471>"
            }
            try:
                nitro = any([user.avatar.is_animated(), user.banner]) and not client.user.bot
            except Exception:
                nitro = False
            url = f"https://canary.discord.com/api/v10/users/{user.id}"
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bot {environ.get('TOKEN')}",
                }
                async with session.get(url, headers=headers) as resp:
                    resp = await resp.json()
                    print(resp)
            public_flags = resp.get("public_flags", 0)
            user_flags = sorted(discord.enums.UserFlags, key=lambda x: x.value, reverse=True)
            flags = []
            while public_flags != 0:
                for item in user_flags:
                    if public_flags >= item.value:
                        flags.append(item.name)
                        public_flags = public_flags - item.value
            badges = [badge_emojis.get(badge) or badge for badge in flags]
            if nitro:
                badges.append(badge_emojis.get("nitro"))
            if user.bot and badge_emojis.get("verified_bot") not in badges:
                badges.append(badge_emojis.get("app"))
            print(f"{user.name}'s badges: {badges}")
            data = {
                "Badges": None,
                "Created": f"<t:{int(user.created_at.timestamp())}:D>",
            }
            if len(badges) > 0:
                data["Badges"] = "".join(badges)
            else:
                data["Badges"] = "None"
            badges = "\n".join(f"{name}: {value}" for name, value in data.items())
            title = (user.display_name.lower() == user.name.lower() and user.display_name) or (user.display_name.lower() != user.name.lower() and f"{user.display_name} ({user.name})") or "?"
            embed = create_embed(
                user=interaction.user,
                title=title,
                description=f"<@!{user.id}>\n{badges}"
            )
            embed.set_thumbnail(url=url)
            await interaction.followup.send(embed=embed)
        except Exception as error:
            await CMD_error(interaction=interaction, error=error)

tree.add_command(UserGroup())

# ECONOMY COMMANDS

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class EconomyGroup(app_commands.Group, name="economy", description="economy commands"):
    @app_commands.command(name="profile", description="Check a user's profile")
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def CMD_profile(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(thinking=True)
        try:
            if user is not None:
                user = await client.fetch_user(user.id)
            else:
                user = await client.fetch_user(interaction.user.id)
            result = await get_data(user=user)
            jsonified = {k: v for k, v in result.__dict__.items() if k in dir(User)}
            data = result.data.copy()
            data.update(result.stats)

            stats = {
                # "Level": f"{int(data.get('Level', 0)):,}",
                "Cash": f"${int(data.get('Cash', 0)):,}",
                "Commands": f"{int(data.get('Commands used', 0)):,}",
                "Storage wasted": "%s %s" % display_bytes(io.BytesIO(str(jsonified).encode()).getbuffer().nbytes + int(result.storage or 0)),
            }

            embed = create_embed(
                user=interaction.user,
                title=user.name,
                description="\n".join(f"{name}: {value}" for name, value in stats.items())
            )
            file = Editor()
            try:
                url = user.avatar.url
                await file.load(source=url)
            except Exception:
                url = "https://cdn.discordapp.com/embed/avatars/1.png"
                await file.load(source=url)
            mode = calculate_mode(list(file.image.getdata()))[:3]
            embed.color = discord.Color.from_rgb(*mode)
            embed.set_thumbnail(url=url)
            await interaction.followup.send(embed=embed)
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

    @app_commands.command(name="slot", description="Bet any amount of money")
    @app_commands.describe(bid="Amount of cash to bid")
    @app_commands.describe(reels="3-10 - i only added this cuz i wanted to watch the numbers go up faster lol")
    async def CMD_slot(self, interaction: discord.Interaction, bid: int, reels: int = 3):
        await interaction.response.defer(thinking=True)
        async with SessionLocal() as database:
            try:
                user = interaction.user
                result = await get_data(user=user)

                data = result.data.copy()
                
                if bid < 1:
                    await interaction.followup.send(content=":warning: You must bid at least $1!")
                    return
                
                current_cash = data.get("Cash", 0)
                
                if bid > current_cash:
                    await interaction.followup.send(content=":warning: You don't have enough cash!")
                    return

                symbols = [":cherries:", ":lemon:", ":pineapple:", ":watermelon:", ":tangerine:", ":apple:", ":grapes:", ":seven:"]
                
                choices = random.choices(symbols, k=clamp(reels, 3, 10))
                display = "｜".join(choices)
                
                counter = {symbol: quantity for symbol, quantity in collections.Counter(choices).items() if quantity > 1}

                if counter:
                    reward = 0
                    outcome_parts = []
                    for symbol, quantity in counter.items():
                        multiplier = 2 ** (quantity - 1)  # 2 for 2-of-a-kind, 4 for 3-of-a-kind, etc.
                        if symbol == ":seven:":
                            multiplier *= 2
                        symbol_reward = int(bid * multiplier)
                        reward += symbol_reward
                        outcome_parts.append(f"{quantity}× {symbol} (${symbol_reward:,})")
                    
                    data["Cash"] = current_cash + reward
                    outcome = f":tada: You won ${reward:,}! " + " + ".join(outcome_parts)
                else:
                    data["Cash"] = current_cash - bid
                    outcome = "lol you won nothing brokie"

                result.data = data
                database.add(result)

                await database.commit()

                await interaction.followup.send(content=f"# **{display}**\n-# {outcome}")

            except Exception as e:
                await database.rollback()
                print(f"Error in CMD_slot: {e}")
                await interaction.followup.send(content=f":warning: An error occurred while processing your bet: {e}")



    global work_cooldowns
    work_cooldowns = {}
    @app_commands.command(name="work", description="Earn some money")
    @app_commands.choices(risk=[
        app_commands.Choice(name="Low", value="1"),
        app_commands.Choice(name="Medium", value="2"),
        app_commands.Choice(name="High", value="3"),
        app_commands.Choice(name="Extreme", value="4"),
        app_commands.Choice(name="Impossible", value="5"),
    ])
    @app_commands.describe(risk="Higher risk = higher payout")
    async def CMD_work(self, interaction: discord.Interaction, risk: app_commands.Choice[str] = None):
        await interaction.response.defer(thinking=True)

        value = int(risk.value) if risk else 1
        risk_multiplier = value
        risk_factor = 1 * (2 ** (value - 1))

        try:
            user = interaction.user
            current_time = time.time()
            cooldown = work_cooldowns.get(user.id, current_time)

            if current_time < cooldown:
                await interaction.followup.send(content=f"You may work again <t:{int(cooldown)}:R>")
                return

            work_cooldowns[user.id] = current_time + 5

            messages = [
                {"success": "You sold \"Class A\" drugs for ${reward:,}", "fail": "You got caught trying to sell drugs, but you were let off with just a warning"},
                {"success": "You got paid ${reward:,} to eat a rock", "fail": "You were dared to eat a rock but couldn't eat it whole. Your money went to hospital bills."},
                {"success": "You earned ${reward:,} from a mysterious job", "fail": "You got ratted out... those damn rats!"},
                {"success": "You blackmailed a model and earned ${reward:,}", "fail": "You attempted blackmail but got beaten up by her bodyguards."},
                {"success": "You convinced a billionaire to pay you ${reward:,} for flattery", "fail": "You flattered a billionaire, but all you got was a mug."},
                {"success": "You uploaded an epic prank and earned ${reward:,} from ad revenue", "fail": "Your prank went wrong, and you owe for damages."},
                {"success": "You sold a rare item for ${reward:,} after a hard-fought negotiation", "fail": "Your negotiation skills didn’t pan out, and you now owe money."},
                {"success": "You discovered a hidden talent and earned ${reward:,}", "fail": "You discovered a talent for awkwardness, but it cost you."}
            ]

            message = random.choice(messages)
            chance = random.random()
            odds = 1 / risk_factor
            info = f"\n-# Chance: 1 in {risk_factor} ({round(odds * 100, 1)}%)｜Outcome: {int(chance * risk_factor) + 1}"

            if chance > odds:
                await interaction.followup.send(content=message["fail"] + info)
                return
            async with SessionLocal() as database:
                result = await get_data(user=user)
                data = result.data.copy()
                reward = int(random.randint(126, 788) * risk_multiplier)
                current_cash = data.get("Cash", 0)
                data["Cash"] = current_cash + reward
                result.data = data

                database.add(result)
                await database.commit()
                await interaction.followup.send(content=message["success"].format(reward=reward) + info)

        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

# tree.add_command(EconomyGroup())

# ROBLOX COMMANDS

def process_image(image_bytes):
    """This stays a regular sync function for Pillow"""
    with Image.open(io.BytesIO(image_bytes)) as img:
        output = io.BytesIO()
        # Doing the conversion here
        img.convert("RGBA").save(output, format="PNG", optimize=True)
        return output.getvalue()

async def get_image_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                raw_bytes = await response.read()
                
                # Get the current event loop
                loop = asyncio.get_event_loop()
                
                # Run the CPU-bound Pillow work in a thread pool
                # This prevents the 'freeze'
                processed_bytes = await loop.run_in_executor(None, process_image, raw_bytes)
                return processed_bytes

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class RobloxGroup(app_commands.Group, name="roblox", description="roblox commands"):
    @app_commands.command(name="upload", description="Upload an image to Roblox (please don't get me banned)")
    async def CMD_robloxupload(self, interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
        await interaction.response.defer(thinking=True)

        user = await get_data(interaction.user)
        if not user.data.get("whitelisted", False):
            await interaction.followup.send("sorry u need to be whitelisted for this")
            return

        with open(os.path.join(DIRECTORY, "assets", "proxies.txt"), "r") as f:
            PROXIES = [line for line in f.read().splitlines() if line]

        try:
            if file is not None:
                url = file.url

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params={"ignore": "1"}) as response:
                    url = str(response.url)
                    data = aiohttp.FormData()
                    
                    # file: Editor = Editor()
                    # await file.load(source=url, ignore_recolor=True)
                    # content = file.image_bytes.read()
                    
                    # content = await response.read()
                    #data.add_field("fileContent", content, filename="image.png", content_type="image/png")
            
                    data = aiohttp.FormData()
                    content = await get_image_data(url)
                    data.add_field("fileContent", content, filename="image.png", content_type="image/png")

            with open(os.path.join(DIRECTORY, "assets/robloxkeys.txt")) as f:
                keys = [line.split(" ") for line in f.read().splitlines() if line]
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5), cookies={".ROBLOSECURITY": environ.get("ROBLOX")}) as session:
                random.shuffle(PROXIES)
                proxy = None
                for test in PROXIES:
                    ip, port, username, password = test.split(":")
                    proxy_test = f"http://{username}:{password}@{ip}:{port}"
                    try:
                        async with session.get("https://www.roblox.com", proxy=proxy_test) as resp:
                            if resp.ok:
                                proxy = proxy_test
                                break
                    except Exception:
                        pass
                if proxy is None:
                    await interaction.followup.send(content="no working proxies :(")
                    return
                print("chosen proxy:", proxy)

                success = True
                for user_id, api_key in keys:
                    async with session.post("https://auth.roblox.com/v1/login", proxy=proxy) as resp:
                        headers = {"x-api-key": api_key, "x-csrf-token": resp.headers.get("x-csrf-token")}
                    try:
                        data.add_field("request", f"""
                            {{
                                "assetType": "Image",
                                "displayName": "Hallo",
                                "description": "-",
                                "creationContext": {{
                                    "creator": {{
                                        "userId": "{user_id}"
                                    }}
                                }}
                            }}""")
                        print("silly headers:", headers)
                        async with session.post("https://apis.roblox.com/assets/v1/assets", data=data, headers=headers, proxy=proxy) as resp:
                            resp.raise_for_status()
                            resp = json.loads(await resp.text())
                            path = resp.get("operationId")
                            if path is None:
                                await asyncio.sleep(0.1)
                                continue
                            while True:
                                await asyncio.sleep(0.1)
                                async with session.get(f"https://apis.roblox.com/assets/v1/operations/{path}", headers=headers, proxy=proxy) as resp:
                                    resp = json.loads(await resp.text())
                                    if resp.get("done"):
                                        try:
                                            asset_id = resp.get("response").get("assetId")
                                        except Exception:
                                            asset_id = resp
                                        break
                            async with session.get(f"https://www.roblox.com/library/{asset_id}", allow_redirects=True, proxy=proxy) as resp:
                                asset_url = str(resp.url)
                            embed = create_embed(
                                user=interaction.user,
                                title="click for url",
                                description=f"```yaml\nrbxassetid://{asset_id}```",
                            )
                            embed.url = asset_url
                            # embed.set_footer(text="i didnt wanna clutter the embed")
                            embed.set_thumbnail(url=f"{url}")
                            await interaction.followup.send(embed=embed)
                            success = True
                            break
                    except Exception:
                        import traceback
                        print(traceback.format_exc())
                        pass
                    await asyncio.sleep(0)
                if not success:
                    raise Exception("Unable to upload due to either rate limits, incorrect file type, or all accounts got banned >:(")
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

            
tree.add_command(RobloxGroup())

# EMAIL COMMANDS

domains = [
    "inkthirsty.xyz"
    # "inkthirsty.xyz", "disuko.duckdns.org", "adamisgay.duckdns.org", "disuko.inkthirsty.xyz",
]
temp_domains = [
    "collectingdomainslol.duckdns.org", "limpbizkit.duckdns.org",
    "ultraviolence.duckdns.org", "please-donate-domains.duckdns.org", "my-chemical-romance.duckdns.org",
    "twenty-one-pilots.duckdns.org", "duckdns-domains-dont-get-flagged-as-spam.duckdns.org", "russian-roulette-is-rigged.duckdns.org"
]

async def create_email_address(email: str):
    headers = {"X-API-KEY": environ.get("SMTPAPIKEY")}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://api.smtp.dev/accounts", json={"address":email,"password":environ.get("EMAILPASSWORD")}) as resp:
            resp = await resp.json()

def alphanumeric_only(input_string: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '', input_string)

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class EmailGroup(app_commands.Group, name="email", description="email commands"):
    @app_commands.command(name="create", description="Create an email address")
    @app_commands.choices(domain=[app_commands.Choice(name=i, value=i) for i in list(sorted(domains))])
    async def CMD_create(self, interaction: discord.Interaction, name: str, domain: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True)
        name = alphanumeric_only(name).lower()
        if len(name) > 30 or len(name) == 0:
            await interaction.followup.send("30 char limit cuz i said so")
            return
        email = f"{name}@{domain.value}".lower()
        async with SessionLocal() as db_session:
            query = await db_session.execute(select(User))
            users = query.scalars().all()
            emails = []
            for user in users:
                emails.extend([i.get("email").lower() for i in user.emails or {}])
                if email.lower() in emails:
                    await interaction.followup.send(f"Sorry bro `{email}` is taken")
                    return
        async with SessionLocal() as db_session:
            user = await get_data(interaction.user)
            if user:
                user.emails = (user.emails or []) + [{"email": email}]
                db_session.add(user)
                await db_session.commit()
        await create_email_address(email)
        await interaction.followup.send(f"Created email `{email}`")

    lengths = {
        "15 minutes": 60*15,
        "30 minutes": 60*30,
        "1 hour": 60*60,
        "2 hours": 60*60*2,
        "6 hours": 60*60*6,
        "12 hours": 60*60*12,
        "24 hours": 60*60*24,
        "48 hours": 60*60*48,
        "72 hours": 60*60*72,
    }
    
    @app_commands.choices(expiration=[app_commands.Choice(name=k, value=v) for k, v in lengths.items()])
    @app_commands.choices(domain=[app_commands.Choice(name=i, value=i) for i in sorted(temp_domains)])
    @app_commands.command(name="temp", description="Create a temp email")
    async def CMD_temp(
        self, 
        interaction: discord.Interaction, 
        expiration: int = None, 
        name: str = None, 
        domain: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)

        expiration = time.time() + (expiration or 60*60)

        if name:
            name = alphanumeric_only(name).lower()[:30]
            if len(name) == 0:
                await interaction.followup.send("Name must contain valid alphanumeric characters!")
                return
        else:
            name = str(int(time.time()*1e6)) 

        domains_to_try = [domain.value] if domain else list(temp_domains)
        random.shuffle(domains_to_try)

        async with SessionLocal() as db_session:
            query = await db_session.execute(select(User))
            users = query.scalars().all()
            existing_emails = set()
            for user in users:
                existing_emails.update([i.get("email").lower() for i in user.emails or []])

        email = None
        for dom in domains_to_try:
            candidate = f"{name}@{dom}"
            if candidate.lower() not in existing_emails:
                email = candidate
                break

        if not email:
            await interaction.followup.send("Sorry bro, that email is taken on all available domains!")
            return
        async with SessionLocal() as db_session:
            user = await get_data(interaction.user)
            if user:
                user.emails = (user.emails or []) + [{"email": email, "temp": expiration}]
                db_session.add(user)
                # flag_modified(user, "emails")
                await db_session.commit()
        await create_email_address(email)

        view = PreviewView(prompt="Copy Address", info=email)
        await interaction.followup.send(f"Created email `{email}`\n-# expires: <t:{int(expiration)}:R>", view=view)

    @app_commands.command(name="list", description="List your email addresses")
    async def CMD_list(self, interaction: discord.Interaction):
        original_user = interaction.user
        await interaction.response.defer(thinking=True)
        embed = discord.Embed(title="Your Emails", description="no emails and no friends :(")
        embed.set_footer(text="Please donate domains :D")
        async with SessionLocal() as db_session:
            user = await get_data(original_user)
            if user:
                emails = user.emails
                if emails and len(emails) > 0:
                    lines = []
                    for idx, i in enumerate(emails, start=1):
                        line = f"{idx}. `{i.get('email')}`"
                        if i.get("temp"):
                            line += f" (expires <t:{int(i.get('temp'))}:R>)"
                        lines.append(line)

                    limit = 30

                    class Preview(discord.ui.View):
                        def __init__(self):
                            super().__init__()
                            self.page = 1
                            self.timeout = None

                        async def update(self, _interaction: discord.Interaction = None):
                            buttons = [button for button in self.children if isinstance(button, discord.ui.Button)]
                            buttons[0].disabled = self.page == 1
                            buttons[1].disabled = self.page == math.ceil(len(lines) / limit)
                            embed.description = "\n".join(lines[(self.page-1)*limit:self.page*limit])
                            if _interaction:
                                await _interaction.response.edit_message(embed=embed, view=self)

                        @discord.ui.button(style=discord.ButtonStyle.grey, emoji="⬅️")
                        async def scroll_left(self, interaction: discord.Interaction, button: discord.ui.Button):
                            self.page -= 1
                            await self.update(interaction)

                        @discord.ui.button(style=discord.ButtonStyle.grey, emoji="➡️")
                        async def scroll_right(self, interaction: discord.Interaction, button: discord.ui.Button):
                            self.page += 1
                            await self.update(interaction)

                        @discord.ui.button(style=discord.ButtonStyle.red, emoji="🗑️")
                        async def button_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
                            if interaction.user != original_user:
                                await interaction.response.send_message("fuck off this aint ur message", ephemeral=True)
                                return
                            class Other(discord.ui.View):
                                def __init__(self):
                                    super().__init__()
                                    self.timeout = None

                                @discord.ui.button(style=discord.ButtonStyle.grey, emoji="✅")
                                async def button1(otherself, interaction2: discord.Interaction, button: discord.ui.Button):
                                    await interaction2.response.send_message("deleted emails lol", ephemeral=True)
                                    await interaction.delete_original_response()
                                    user.emails = []
                                    db_session.add(user)
                                    await db_session.commit()
                                    await self.update(interaction)

                                @discord.ui.button(style=discord.ButtonStyle.grey, emoji="❌")
                                async def button2(self, interaction2: discord.Interaction, button: discord.ui.Button):
                                    await interaction2.response.send_message("Your emails are safe... for now...", ephemeral=True)
                                    await interaction.delete_original_response()
                            await interaction.response.send_message(content="Are you sure you want to delete all saved emails?", ephemeral=True, view=Other())
                    
                    view = Preview()
                    await view.update()
                    await interaction.followup.send(embed=embed, view=view)
                    return
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="delete", description="Delete an email address")
    async def CMD_delete(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(thinking=True)
        async with SessionLocal() as db_session:
            user = await get_data(interaction.user)
            if user:
                emails = [i.get("email").lower() for i in user.emails]
                if email.lower() in emails:
                    try:
                        async with aiohttp.ClientSession(headers={"X-API-KEY": environ.get("SMTPAPIKEY")}) as session:
                            params = {"address": email}
                            async with session.get("https://api.smtp.dev/accounts", params=params) as response:
                                resp = await response.json()
                                emailId = resp.get("member")[0].get("id")
                            await session.delete(f"https://api.smtp.dev/accounts/{emailId}")
                    except Exception:
                        pass
                    user.emails = [i for i in user.emails if i.get("email") != email]
                    db_session.add(user)
                    await db_session.commit()
                    await interaction.followup.send(f"Deleted `{email}`")
                    return
        await interaction.followup.send(f"Could not find `{email}`")

    @CMD_delete.autocomplete("email")
    async def find_email(
        self,
        interaction: discord.Interaction,
        email: str = None
    ) -> List[app_commands.Choice[str]]:
        async with SessionLocal() as db_session:
            try:
                user = await get_data(interaction.user)
                if user:
                    emails = user.emails
                    return [app_commands.Choice(
                        name=f"[{emails.index(i)+1}] {i.get('email')}",
                        value=i.get("email")
                    ) for i in emails if email.lower().strip() in i.get('email').lower()][:25]
                return
            except Exception:
                return

    @app_commands.command(name="block", description="Block an email address")
    async def CMD_block(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(thinking=True)
        email = email.lower()
        verify = bool(re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$").match(email))
        if verify:
            async with SessionLocal() as db_session:
                user = await get_data(interaction.user)
                if user:
                    blocked = user.blockedEmails.copy()
                    if email in blocked:
                        await interaction.followup.send(f"`{email}` is already on your block list (remove with /email unblock)")
                        return
                    else:
                        blocked.append(email)
                    user.blockedEmails = blocked
                    db_session.add(user)
                    await db_session.commit()
            await interaction.followup.send(f"Added `{email}` to block list (remove with /email unblock)")
        else:
            await interaction.followup.send(f"Invalid email.")

    @app_commands.command(name="unblock", description="Unblock an email address")
    async def CMD_unblock(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(thinking=True)
        async with SessionLocal() as db_session:
            user = await get_data(interaction.user)
            if user:
                user.blockedEmails = [i for i in user.blockedEmails if i != email]
                db_session.add(user)
                await db_session.commit()
        await interaction.followup.send(f"Deleted `{email}`")

    @app_commands.command(name="blocklist", description="Check your list of blocked emails")
    async def CMD_blocklist(self, interaction: discord.Interaction):
        original_user = interaction.user
        await interaction.response.defer(thinking=True)
        embed = discord.Embed(title="Blocked Emails", description="no opps ^_^")
        async with SessionLocal() as db_session:
            user = await get_data(original_user)
            if user:
                emails = user.blockedEmails
                if emails and len(emails) > 0:
                    lines = []
                    for idx, i in enumerate(emails, start=1):
                        line = f"{idx}. `{i}`"
                        lines.append(line)

                    limit = 10

                    class Preview(discord.ui.View):
                        def __init__(self):
                            super().__init__()
                            self.page = 1
                            self.timeout = None

                        async def update(self, _interaction: discord.Interaction = None):
                            buttons = [button for button in self.children if isinstance(button, discord.ui.Button)]
                            buttons[0].disabled = self.page == 1
                            buttons[1].disabled = self.page == math.ceil(len(lines) / limit)
                            embed.description = "\n".join(lines[(self.page-1)*limit:self.page*limit])
                            if _interaction:
                                await _interaction.response.edit_message(embed=embed, view=self)

                        @discord.ui.button(style=discord.ButtonStyle.grey, emoji="⬅️")
                        async def scroll_left(self, interaction: discord.Interaction, button: discord.ui.Button):
                            self.page -= 1
                            await self.update(interaction)

                        @discord.ui.button(style=discord.ButtonStyle.grey, emoji="➡️")
                        async def scroll_right(self, interaction: discord.Interaction, button: discord.ui.Button):
                            self.page += 1
                            await self.update(interaction)

                        @discord.ui.button(style=discord.ButtonStyle.red, emoji="🗑️")
                        async def button_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
                            if interaction.user != original_user:
                                await interaction.response.send_message("fuck off this aint ur message", ephemeral=True)
                                return
                            class Other(discord.ui.View):
                                def __init__(self):
                                    super().__init__()
                                    self.timeout = None

                                @discord.ui.button(style=discord.ButtonStyle.grey, emoji="✅")
                                async def button1(otherself, interaction2: discord.Interaction, button: discord.ui.Button):
                                    await interaction2.response.send_message("deleted emails lol", ephemeral=True)
                                    await interaction.delete_original_response()
                                    user.blockedEmails = []
                                    db_session.add(user)
                                    await db_session.commit()
                                    await self.update(interaction)

                                @discord.ui.button(style=discord.ButtonStyle.grey, emoji="❌")
                                async def button2(self, interaction2: discord.Interaction, button: discord.ui.Button):
                                    await interaction2.response.send_message("Your emails are safe... for now...", ephemeral=True)
                                    await interaction.delete_original_response()
                            await interaction.response.send_message(content="Are you sure you want to clear your blocked email list?", ephemeral=True, view=Other())
                    
                    view = Preview()
                    await view.update()
                    await interaction.followup.send(embed=embed, view=view)
                    return
            await interaction.followup.send(embed=embed)

    @CMD_unblock.autocomplete("email")
    async def find_email(
        self,
        interaction: discord.Interaction,
        email: str = None
    ) -> List[app_commands.Choice[str]]:
        async with SessionLocal() as db_session:
            try:
                user = await get_data(interaction.user)
                if user:
                    emails = user.blockedEmails
                    return [app_commands.Choice(
                        name=f"[{emails.index(i)+1}] {i}",
                        value=i
                    ) for i in emails if email.lower().strip() in i.lower()][:25]
                return
            except Exception:
                return

            
# tree.add_command(EmailGroup())




# QR COMMANDS

currencies = {
    "litecoin": {
        "name": "Litecoin",
        "symbol": "LTC",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/2.png",
        "color": "#345d9d"
    },
    "bitcoin": {
        "name": "Bitcoin",
        "symbol": "BTC",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/1.png",
        "color": "#f7931a"
    },
    "ethereum": {
        "name": "Ethereum",
        "symbol": "ETH",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/1027.png",
        "color": "#eceff0"
    },
    "solana": {
        "name": "Solana",
        "symbol": "SOL",
        "icon": "https://asset-metadata-service-production.s3.amazonaws.com/asset_icons/b658adaf7913c1513c8d120bcb41934a5a4bf09b6adbcb436085e2fbf6eb128c.png",
        "color": "#1cf3a2"
    },
    "tether": {
        "name": "Tether",
        "symbol": "USDT",
        "icon": "https://i.ibb.co/5xwYhpVz/image.png",
        "color": "#53ae94"
    },
    "usdc": {
        "name": "USDC",
        "symbol": "USDC",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/3408.png",
        "color": "#2775ca"
    },
    "xrp": {
        "name": "XRP",
        "symbol": "XRP",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/52.png",
        "color": "#fdfefe"
    },
    "bnb": {
        "name": "BNB",
        "symbol": "BNB",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/1839.png",
        "color": "#f0b90b"
    },
    "dogecoin": {
        "name": "Dogecoin",
        "symbol": "DOGE",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/74.png",
        "color": "#ba9f33"
    },
    "bitcoin_cash": {
        "name": "Bitcoin Cash",
        "symbol": "BCH",
        "icon": "https://s2.coinmarketcap.com/static/img/coins/128x128/1831.png",
        "color": "#8dc351"
    }
}

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class QRGroup(app_commands.Group, name="qr", description="qr commands"):
    def __init__(self):
        super().__init__()
        for currency, info in currencies.items():
            currency_lower = currency.lower()
            cmd = self.make_cmd(currency_lower, info)
            self.command(name=currency_lower, description=f"Prompt {info.get('name')} ({info.get('symbol')}) wallet")(cmd)

    def make_cmd(self, currency: str, info: dict):
        async def cmd(interaction: discord.Interaction, amount: float = 1.0, address: str = None):
            await interaction.response.defer(thinking=True)
            amount = round(amount, 2)
            symbol = info.get("symbol")
            name = info.get("name")
            try:
                user = interaction.user
                async with SessionLocal() as db_session:
                    user = await get_data(user=user)
                    data = user.data.copy()
                    wallets = data.get("wallets", {}).copy()
                    addy = wallets.get(currency, address)
                    if not addy:
                        await interaction.followup.send(content=f"No wallet found - add an address and it will be remembered for future commands!")
                        return

                    if addy:
                        wallets[currency] = addy
                        data["wallets"] = wallets
                        user.data = data
                        db_session.add(user)
                        await db_session.commit()
                    
                    headers = {"X-CMC_PRO_API_KEY": random.choice(environ.get("COINMARKET").split(";"))}
                    params = {
                        "symbol": symbol,
                        "convert": "USD"
                    }
                    async with aiohttp.ClientSession(headers=headers) as session:
                        try:
                            async with session.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest", params=params) as response:
                                response.raise_for_status()
                                resp = await response.json()
                                conversion = resp.get("data").get(symbol).get("quote").get("USD").get("price")
                                source = ["CoinMarketCap", "https://coinmarketcap.com/"]
                        except Exception:
                            params = {
                                "ids": currency,
                                "vs_currencies": "usd"
                            }
                            async with session.get("https://api.coingecko.com/api/v3/simple/price", params=params) as response:
                                resp = await response.json()
                                conversion = resp.get(currency).get("usd")
                                source = ["CoinGecko", "https://www.coingecko.com/"]
                        value = format(round(amount / conversion, 8), ".8f")

                        embed = discord.Embed(
                            color=discord.Color.from_str("#" + info.get("color", "ffffff")[-6:])
                        )
                        embed.set_author(
                            name=f"{name} ({symbol})",
                            icon_url=info.get("icon")
                        )
                        params = urlencode({"data": addy})
                        embed.set_image(url=f"https://disuko.inkthirsty.xyz/qr?{params}&")
                        embed.add_field(name="Address", value=f"```\n{addy}```", inline=False)
                        embed.add_field(name="Amount", value=f"`${float(value)*conversion:.2f}` `({value})`", inline=False)
                        embed.set_footer(text=source[0], icon_url=f"https://www.google.com/s2/favicons?sz=256&domain_url={source[1]}")

                    class Preview(discord.ui.View):
                        def __init__(self):
                            super().__init__()
                            self.timeout = None

                        @discord.ui.button(label="Copy Address", style=discord.ButtonStyle.gray)
                        async def copy_address(self, interaction: discord.Interaction, button: discord.ui.Button):
                            await interaction.response.send_message(content=addy, ephemeral=True)

                        @discord.ui.button(label="Copy Amount", style=discord.ButtonStyle.gray)
                        async def open_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
                            await interaction.response.send_message(content=value, ephemeral=True)

                    view = Preview()
                    await interaction.followup.send(embed=embed, view=view)
            except Exception as error:
                import traceback
                print(traceback.format_exc())
                await CMD_error(interaction=interaction, error=error)
        return cmd

# tree.add_command(QRGroup())


# ADMIN ONLY

@app_commands.allowed_installs(users=True, guilds=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class AdminGroup(app_commands.Group, name="admin", description="ADMIN ONLY"):
    @app_commands.command(name="sync", description="ADMIN ONLY")
    async def CMD_sync2(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        await tree.sync()
        await interaction.followup.send(content="Synced! (why do we have do to this)")

    @app_commands.command(name="edit", description="ADMIN ONLY")
    async def CMD_edit(self, interaction: discord.Interaction, message_id: str, channel_id: str = None, content: str = None):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        channel = await client.fetch_channel(channel_id or interaction.channel_id)
        message = await channel.fetch_message(message_id)

        await message.edit(content=content or f"{message.content} ")
        await interaction.followup.send(content="changed yuh maybe idk)")

    @app_commands.command(name="status", description="ADMIN ONLY")
    async def CMD_status(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        activity = discord.Activity(type = discord.ActivityType.custom, name = "filler", state = message)
        await client.change_presence(status=discord.Status.online, activity=activity)
        await interaction.followup.send(content=f"Status has been changed -> {message}")

    @app_commands.command(name="setavatar", description="ADMIN ONLY")
    async def CMD_setavatar(self, interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        file: io.BytesIO = await download_file(url)
        await client.user.edit(avatar=file.read())
        await interaction.followup.send(content=f"Avatar has been changed -> {url}")

    @app_commands.command(name="setbanner", description="ADMIN ONLY")
    async def CMD_setbanner(self, interaction: discord.Interaction, file: discord.Attachment = None, url: str = None):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        if file is None and url is None:
            raise Errors.FileNotFound
        if file is not None:
            url = file.url
        file: io.BytesIO = await download_file(url)
        await client.user.edit(banner=file.read())
        await interaction.followup.send(content=f"Banner has been changed -> {url}")

    @app_commands.command(name="execute", description="ADMIN ONLY")
    async def CMD_execute(self, interaction: discord.Interaction, command: str):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        try:
            exec(command)
            await interaction.followup.send(content="https://tenor.com/bsUWw.gif")
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

    @app_commands.command(name="terminal", description="ADMIN ONLY")
    async def CMD_terminal(self, interaction: discord.Interaction, command: str):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        try:
            proc = await asyncio.create_subprocess_exec(command, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            await interaction.followup.send(content="https://tenor.com/bsUWw.gif")
        except Exception as error:
            import traceback
            print(traceback.format_exc())
            await CMD_error(interaction=interaction, error=error)

    @app_commands.command(name="restart", description="ADMIN ONLY")
    async def CMD_restart(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return
        if TESTING:
            await interaction.followup.send(content="this only works on ubuntu you silly goose")
            return
        await interaction.followup.send(content="https://tenor.com/bxOlR.gif")
        exit()

    @app_commands.command(name="whitelist", description="ADMIN ONLY")
    async def CMD_whitelist(self, interaction: discord.Interaction, member: discord.User = None):
        await interaction.response.defer(thinking=True)

        # Check if the user is an admin
        if not admin_check(interaction.user):
            await interaction.followup.send(content="ur not admin lil bro")
            return

        async with SessionLocal() as db_session:
            try:
                if member:
                    user = await get_data(user=member)
                    data = user.data.copy()
                    data["whitelisted"] = not data.get("whitelisted", False)

                    user.data = data

                    db_session.add(user)
                    await db_session.commit()

                    await interaction.followup.send(content=f"Set <@!{member.id}> to {data['whitelisted']}")
                else:
                    query = await db_session.execute(select(User))
                    users = query.scalars().all()
                    whitelist = "\n".join([f"<@!{user.uid}>" for user in users if user.data.get("whitelisted", False)])

                    await interaction.followup.send(content=f"Whitelist:\n{whitelist}")
            except Exception as e:
                print(f"Error in CMD_whitelist: {e}")
                await interaction.followup.send(content=f":warning: An error occurred while updating whitelist status: {e}")


tree.add_command(AdminGroup())

@client.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.commands.Command):
    try:
        async with aiohttp.ClientSession() as session:
            async with SessionLocal() as database:
                result = await get_data(user=interaction.user)
                
                if result is None:
                    await interaction.followup.send(content="Error: User data not found!")
                    return

                stats = result.stats.copy()
                stats["Commands used"] = stats.get("Commands used", 0) + 1
                result.stats = stats

                database.add(result)

                await database.commit()

                webhook = discord.Webhook.from_url(environ.get("LOGS"), session=session)
                embed = discord.Embed(
                    description=f"{interaction.user.name} <@{interaction.user.id}> used command {command.name}",
                    color=discord.Color.green()
                )

                await webhook.send(embed=embed)

    except Exception as error:
        print(f"Error in on_app_command_completion: {error}")
        await interaction.followup.send(content="An error occurred while processing the command.")


@client.event
async def on_ready():
    await client.wait_until_ready()
    await tree.sync()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=41900)
    # asyncio.run(main())