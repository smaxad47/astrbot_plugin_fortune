"""今日运势（抽签）AstrBot 插件 —— 原版渲染移植 · 核心版（资源外置）。

移植自 nonebot_plugin_fortune v0.4.12
(https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)
原作者: KafCoppelia <k740677208@gmail.com>，MIT License。

分两版资源策略，避免插件仓库过大：
- 插件仓库只保留**代码**（+ 可选的小文件）。体积大的主题立绘 / 字体 / copywriting
  打包成一个 zip 放到 GitHub Release，安装后在 WebUI「插件 → 今日运势 → 资源管理」
  页面里点击下载，或首次抽签时按配置自动后台下载。
- 资源下载解压到 AstrBot 插件数据目录 `data/plugin_data/astrbot_plugin_fortune/resource/`，
  代码优先使用该目录；若那里还没有，则回退到插件自带的 `resource/`（便于本地开发）。

渲染方式保持与原插件一致：沿用原 `utils.drawing()` / `utils.decrement()` 的 Pillow 逻辑
（标题固定中心 (140,99)、45px #F5F5F5、Mamelon.otf；正文固定中心 (140,297)、25px #323232、
sakura.ttf、每列最多 9 字、竖排分栏），只把 nonebot2 接口换成 AstrBot 接口。

指令仅 `抽签`；默认全部主题启用、随机抽签；每群每人每天限 1 次。
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:  # 配置对象（存在 _conf_schema.json 时由 AstrBot 注入）
    from astrbot.api import AstrBotConfig
except Exception:  # pragma: no cover - 兼容无该导出的旧版本
    AstrBotConfig = dict  # type: ignore

# Pillow 为 AstrBot 核心自带依赖（pyproject: pillow>=11.2.1），本地出图、无需任何公共 API。
from PIL import Image, ImageDraw, ImageFont

__fortune_version__ = "v0.5.1"
PLUGIN_NAME = "astrbot_plugin_fortune"

# 资源包下载地址（已写死为该 Release 附件；仍可在插件配置 resource_url 里覆盖）。
RESOURCE_URL = "https://github.com/smaxad47/astrbot_plugin_fortune/releases/download/0.4.12/fortune_resource.zip"

"""
    抽签主题对应表：键为资源文件夹名，值为该主题的别名列表（第一个用于展示）。
"""
FortuneThemesDict: dict[str, list[str]] = {
    "random": ["随机"],
    "amazing_grace": ["奇异恩典"],
    "arknights": ["明日方舟", "方舟", "arknights", "鹰角", "Arknights", "舟游"],
    "asoul": ["Asoul", "asoul", "a手", "A手", "as", "As"],
    "azure": ["碧蓝航线", "碧蓝", "azure", "Azure"],
    "dc4": ["dc4", "DC4", "Dc4"],
    "einstein": ["爱因斯坦携爱敬上", "爱因斯坦", "einstein", "Einstein"],
    "genshin": ["原神", "Genshin Impact", "genshin", "Genshin", "op", "原批"],
    "granblue_fantasy": ["碧蓝幻想", "Granblue Fantasy", "granblue fantasy", "幻想"],
    "hololive": ["Hololive", "hololive", "Vtb", "vtb", "管人", "Holo", "holo", "管人痴"],
    "hoshizora": ["星空列车与白的旅行", "星空列车"],
    "liqingge": ["李清歌", "清歌"],
    "onmyoji": ["阴阳师", "yys", "Yys", "痒痒鼠"],
    "pcr": ["PCR", "公主链接", "公主连结", "Pcr", "pcr"],
    "pretty_derby": ["赛马娘", "马", "马娘", "赛马"],
    "punishing": ["战双", "战双帕弥什"],
    "sakura": ["樱色之云绯色之恋", "樱云之恋", "樱云绯恋", "樱云"],
    "summer_pockets": ["夏日口袋", "夏兜", "sp", "SP"],
    "sweet_illusion": ["灵感满溢的甜蜜创想", "甜蜜一家人", "富婆妹"],
    "touhou": ["东方", "touhou", "Touhou", "车万"],
    "touhou_lostword": ["东方归言录", "东方lostword", "touhou lostword"],
    "touhou_old": ["旧东方", "旧版东方", "老东方", "老版东方", "经典东方"],
    "warship_girls_r": ["战舰少女R", "舰r", "舰R", "wsgr", "WSGR", "战舰少女r"],
}

# ---------------------------------------------------------------------- #
# 资源路径（可在“插件自带资源”和“下载到 data 目录的资源”之间切换）
# ---------------------------------------------------------------------- #
BUNDLED_RESOURCE_DIR = Path(__file__).parent / "resource"

_RESOURCE_ROOT: Path = BUNDLED_RESOURCE_DIR

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def set_resource_root(path: Path) -> None:
    """切换当前使用的资源根目录（img/ fortune/ font/ 都在其下）。"""
    global _RESOURCE_ROOT
    _RESOURCE_ROOT = Path(path)


def get_resource_root() -> Path:
    return _RESOURCE_ROOT


def _img_dir() -> Path:
    return _RESOURCE_ROOT / "img"


def _copywriting_path() -> Path:
    return _RESOURCE_ROOT / "fortune" / "copywriting.json"


def _font_path(name: str) -> Path:
    return _RESOURCE_ROOT / "font" / name


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = _font_path(name)
    key = (str(path), size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


def is_resource_ready(base: Path) -> bool:
    """判断某个资源根目录是否可用（有 img 主题图 + copywriting + 两套字体）。"""
    base = Path(base)
    img = base / "img"
    if not img.is_dir():
        return False
    if not (base / "fortune" / "copywriting.json").exists():
        return False
    if not (base / "font" / "Mamelon.otf").exists():
        return False
    if not (base / "font" / "sakura.ttf").exists():
        return False
    for d in img.iterdir():
        if d.is_dir() and any(p.is_file() for p in d.iterdir()):
            return True
    return False


def count_resource_stats(base: Path) -> tuple[int, int]:
    """返回 (主题数, 图片数)。"""
    img = Path(base) / "img"
    themes = images = 0
    if img.is_dir():
        for d in img.iterdir():
            if d.is_dir():
                n = sum(1 for p in d.iterdir() if p.is_file())
                if n:
                    themes += 1
                    images += n
    return themes, images


# ---------------------------------------------------------------------- #
# 原 nonebot_plugin_fortune 的绘制逻辑（保持原样，仅改用可切换的资源根目录）
# ---------------------------------------------------------------------- #
def get_copywriting() -> tuple[str, str]:
    """原 utils.get_copywriting：读取 copywriting.json，随机取一条运势（标题 + 文案）。"""
    with open(_copywriting_path(), "r", encoding="utf-8") as f:
        content = json.load(f).get("copywriting")
    luck = random.choice(content)
    return luck.get("good-luck"), random.choice(luck.get("content"))


def random_basemap(theme: str) -> Path:
    """原 utils.random_basemap：theme 为 random 时在所有主题目录中随机选一张底图。"""
    if theme == "random":
        base = _img_dir()
        themes: list[str] = [f.name for f in base.iterdir() if f.is_dir()]
        base = base / random.choice(themes)
    else:
        base = _img_dir() / theme
    images: list[Path] = [i for i in base.iterdir() if i.is_file()]
    return random.choice(images)


def decrement(text: str) -> tuple[int, list[str]]:
    """原 utils.decrement：把文案切成若干列（每列最多 9 字，两列时用空格补齐对齐）。"""
    length: int = len(text)
    result: list[str] = []
    cardinality = 9
    if length > 4 * cardinality:
        raise ValueError("运势文案过长")

    col_num: int = 1
    while length > cardinality:
        col_num += 1
        length -= cardinality

    space = " "
    length = len(text)

    if col_num == 2:
        if length % 2 == 0:
            fill_in = space * int(9 - length / 2)
            return col_num, [
                text[: int(length / 2)] + fill_in,
                fill_in + text[int(length / 2):],
            ]
        else:
            fill_in = space * int(9 - (length + 1) / 2)
            return col_num, [
                text[: int((length + 1) / 2)] + fill_in,
                fill_in + space + text[int((length + 1) / 2):],
            ]

    for i in range(col_num):
        if i == col_num - 1 or col_num == 1:
            result.append(text[i * cardinality:])
        else:
            result.append(text[i * cardinality:(i + 1) * cardinality])
    return col_num, result


def drawing(gid: str, uid: str, theme: str, out_dir: Path) -> Path:
    """原 utils.drawing：在一张随机主题底图上绘制标题与竖排正文，保存后返回路径。"""
    img_path: Path = random_basemap(theme)
    img: Image.Image = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    title, text = get_copywriting()

    # 标题（固定中心 140,99；45px；#F5F5F5；Mamelon.otf）
    font_size = 45
    color = "#F5F5F5"
    image_font_center = [140, 99]
    ttfront = _load_font("Mamelon.otf", font_size)
    bbox = ttfront.getbbox(title)
    font_length = (bbox[2] - bbox[0], bbox[3] - bbox[1])
    draw.text(
        (
            image_font_center[0] - font_length[0] / 2,
            image_font_center[1] - font_length[1] / 2,
        ),
        title,
        fill=color,
        font=ttfront,
    )

    # 正文（固定中心 140,297；25px；#323232；sakura.ttf；竖排分栏）
    font_size = 25
    color = "#323232"
    image_font_center = [140, 297]
    ttfront = _load_font("sakura.ttf", font_size)
    slices, result = decrement(text)

    for i in range(slices):
        font_height: int = len(result[i]) * (font_size + 4)
        text_vertical: str = "\n".join(result[i])
        x: int = int(
            image_font_center[0]
            + (slices - 2) * font_size / 2
            + (slices - 1) * 4
            - i * (font_size + 4)
        )
        y: int = int(image_font_center[1] - font_height / 2)
        draw.text((x, y), text_vertical, fill=color, font=ttfront)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path: Path = out_dir / f"{_safe_name(gid)}_{_safe_name(uid)}.png"
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------- #
# 资源下载 / 解压
# ---------------------------------------------------------------------- #
def _safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(name)) or "unknown"


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """安全解压（防止路径穿越）。"""
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest_dir / member.filename).resolve()
            if not (target == dest_dir or str(target).startswith(str(dest_dir) + os.sep)):
                raise RuntimeError(f"压缩包包含非法路径: {member.filename}")
        zf.extractall(dest_dir)


def _normalize_resource_layout(path: Path) -> Path:
    """若 zip 内多套了一层目录，则下探到真正包含 img/ 的那层。"""
    if (path / "img").is_dir():
        return path
    for child in path.iterdir():
        if child.is_dir() and (child / "img").is_dir():
            return child
    return path


def _default_data_dir() -> Path:
    """AstrBot 插件数据目录；不可用时回退到插件目录下 data。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        return Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME
    except Exception:  # noqa: BLE001
        return Path(__file__).parent / "data"


# ---------------------------------------------------------------------- #
# 插件
# ---------------------------------------------------------------------- #
@register(
    PLUGIN_NAME,
    "KafCoppelia (nonebot 原作者) / AstrBot 移植",
    "抽签！占卜你的今日运势🙏（原版 Pillow 渲染，资源可外置下载）",
    __fortune_version__,
    "https://github.com/MinatoAquaCrews/nonebot_plugin_fortune",
)
class FortunePlugin(Star):
    def __init__(self, context: Context, config: "AstrBotConfig | None" = None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config if config is not None else {}
        self.data_dir = _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = self.data_dir / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / "fortune_data.json"
        if not self.data_file.exists():
            self._dump_json(self.data_file, {})

        self.external_dir = self.data_dir / "resource"
        self._resolve_resource_root()

        # 下载进度状态
        self._dl_task: asyncio.Task | None = None
        self._dl_state: dict = {
            "status": "idle",  # idle / downloading / done / error
            "downloaded": 0,
            "total": 0,
            "message": "",
        }

        self._register_web_apis()
        self._check_resources()

    # -------------------------- 资源根目录 -------------------------- #
    def _resolve_resource_root(self) -> None:
        if is_resource_ready(self.external_dir):
            set_resource_root(self.external_dir)
        elif is_resource_ready(BUNDLED_RESOURCE_DIR):
            set_resource_root(BUNDLED_RESOURCE_DIR)
        else:
            set_resource_root(self.external_dir)  # 等待下载

    def _resources_ready(self) -> bool:
        return is_resource_ready(get_resource_root()) or is_resource_ready(self.external_dir) \
            or is_resource_ready(BUNDLED_RESOURCE_DIR)

    def _resource_url(self) -> str:
        try:
            url = self.config.get("resource_url", "") if self.config else ""
        except Exception:  # noqa: BLE001
            url = ""
        return (url or RESOURCE_URL or "").strip()

    def _check_resources(self) -> None:
        if not self._resources_ready():
            logger.warning(
                "今日运势资源尚未安装：请在 WebUI「插件 → 今日运势 → 资源管理」中下载，"
                "或在插件配置里填写 resource_url 后点击下载。"
            )

    # -------------------------- 数据 -------------------------- #
    @staticmethod
    def _dump_json(path: Path, data) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _load_data(self) -> dict:
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _already_drawn(self, gid: str, uid: str) -> bool:
        rec = self._load_data().get(gid, {}).get(uid)
        return bool(rec) and rec.get("last_sign_date") == date.today().isoformat()

    def _mark_drawn(self, gid: str, uid: str) -> None:
        data = self._load_data()
        data.setdefault(gid, {})[uid] = {"last_sign_date": date.today().isoformat()}
        self._dump_json(self.data_file, data)

    # -------------------------- 下载 -------------------------- #
    def _start_download(self, url: str) -> bool:
        if self._dl_task and not self._dl_task.done():
            return False
        self._dl_state.update(
            status="downloading", downloaded=0, total=0, message="开始下载…"
        )
        self._dl_task = asyncio.create_task(self._do_download(url))
        return True

    def _download_to_file(self, url: str, dest: Path) -> None:
        """用标准库 urllib 分块下载到文件，并持续更新进度（在线程中执行）。"""
        import urllib.request

        req = urllib.request.Request(
            url, headers={"User-Agent": "astrbot-plugin-fortune"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            status = getattr(resp, "status", 200)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            total = int(resp.headers.get("Content-Length") or 0)
            self._dl_state["total"] = total
            self._dl_state["message"] = "下载中…"
            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    self._dl_state["downloaded"] = done

    async def _do_download(self, url: str) -> None:
        tmp = Path(tempfile.mkdtemp(prefix=".res_dl_", dir=str(self.data_dir)))
        zip_path = tmp / "resource.zip"
        try:
            self._dl_state["message"] = "连接下载地址…"
            await asyncio.to_thread(self._download_to_file, url, zip_path)

            self._dl_state["message"] = "解压中…"
            extract_dir = tmp / "extracted"
            await asyncio.to_thread(_extract_zip, zip_path, extract_dir)
            candidate = _normalize_resource_layout(extract_dir)

            if not is_resource_ready(candidate):
                raise RuntimeError("资源包结构不完整：应包含 img/、fortune/、font/")

            # 原子替换到 external_dir
            if self.external_dir.exists():
                shutil.rmtree(self.external_dir, ignore_errors=True)
            await asyncio.to_thread(shutil.move, str(candidate), str(self.external_dir))

            set_resource_root(self.external_dir)
            themes, images = count_resource_stats(self.external_dir)
            self._dl_state.update(
                status="done",
                message=f"完成：{themes} 个主题、{images} 张图片",
            )
            logger.info(f"今日运势资源下载完成：{themes} 主题 / {images} 图片")
        except Exception as e:  # noqa: BLE001
            self._dl_state.update(status="error", message=f"下载失败：{e}")
            logger.error(f"今日运势资源下载失败: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _status(self) -> dict:
        ready = self._resources_ready()
        root = get_resource_root()
        themes, images = count_resource_stats(root if is_resource_ready(root) else self.external_dir)
        if is_resource_ready(self.external_dir):
            source = "downloaded"
        elif is_resource_ready(BUNDLED_RESOURCE_DIR):
            source = "bundled"
        else:
            source = "missing"
        return {
            "ready": ready,
            "source": source,
            "resource_dir": str(root),
            "themes": themes,
            "images": images,
            "url": self._resource_url(),
            "downloading": self._dl_state.get("status") == "downloading",
            "state": self._dl_state,
        }

    # -------------------------- Web API -------------------------- #
    def _register_web_apis(self) -> None:
        try:
            context = self.context
            context.register_web_api(
                f"/{PLUGIN_NAME}/status", self.api_status, ["GET"], "资源状态"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/download", self.api_download, ["POST"], "下载/更新资源"
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/progress", self.api_progress, ["GET"], "下载进度"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册插件 Web API 失败（可能是 AstrBot 版本较旧）: {e}")

    async def api_status(self):
        from astrbot.api.web import json_response

        return json_response(self._status())

    async def api_progress(self):
        from astrbot.api.web import json_response

        return json_response(self._dl_state)

    async def api_download(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        url = (payload.get("url") or self._resource_url() or "").strip()
        if not url:
            return error_response(
                "未配置资源地址：请在插件配置 resource_url 填写，或在页面输入框填写 zip 直链。",
                status_code=400,
            )
        if not (url.startswith("https://") or url.startswith("http://")):
            return error_response("仅支持 http(s) 资源地址", status_code=400)

        # 允许页面直接保存地址到插件配置
        if payload.get("save") and hasattr(self.config, "__setitem__"):
            try:
                self.config["resource_url"] = url
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
            except Exception:  # noqa: BLE001
                pass

        started = self._start_download(url)
        return json_response(
            {"started": started, "message": "开始下载" if started else "已在下载中"}
        )

    # -------------------------- 出图 -------------------------- #
    def _draw_sync(self, gid: str, uid: str) -> str:
        out_path = drawing(gid, uid, "random", self.out_dir)
        self._cleanup_out_dir()
        return str(out_path)

    def _cleanup_out_dir(self, max_age_seconds: int = 2 * 86400) -> None:
        now = time.time()
        try:
            for p in self.out_dir.iterdir():
                if p.is_file() and now - p.stat().st_mtime > max_age_seconds:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    def _cached_path(self, gid: str, uid: str) -> Path:
        return self.out_dir / f"{_safe_name(gid)}_{_safe_name(uid)}.png"

    # -------------------------- 指令 -------------------------- #
    @filter.command("抽签", alias={"今日运势", "运势"})
    async def divine(self, event: AstrMessageEvent):
        """抽签：占卜今日运势。默认全部主题随机。每人每天限一次。"""
        gid = event.get_group_id() or event.get_session_id()
        uid = event.get_sender_id() or "unknown"

        # 资源未就绪：引导到 WebUI 下载，或按配置后台自动下载
        if not self._resources_ready():
            url = self._resource_url()
            auto = bool(self.config.get("auto_download", False)) if self.config else False
            if self._dl_state.get("status") == "downloading":
                yield event.plain_result("运势资源正在下载中，稍等片刻后再发送「抽签」哦～")
                return
            if auto and url:
                self._start_download(url)
                yield event.plain_result(
                    "首次使用，正在后台下载运势资源，完成后再次发送「抽签」即可～"
                )
                return
            yield event.plain_result(
                "运势资源尚未安装。请打开 WebUI →「插件」→「今日运势」→「资源管理」，"
                "点击「下载资源」后再试～"
            )
            return

        cached = self._cached_path(gid, uid)
        if self._already_drawn(gid, uid) and cached.exists():
            yield event.chain_result(
                [
                    _plain("你今天抽过签了，再给你看一次哦🤗\n"),
                    _image(str(cached)),
                ]
            )
            return

        try:
            loop = asyncio.get_running_loop()
            img_path = await loop.run_in_executor(None, self._draw_sync, gid, uid)
        except Exception as e:  # noqa: BLE001
            logger.error(f"今日运势生成出错: {e}")
            yield event.plain_result("今日运势生成出错……")
            return

        self._mark_drawn(gid, uid)
        logger.info(f"User {uid} | Group {gid} 占卜了今日运势")

        yield event.chain_result(
            [
                _plain("✨今日运势✨\n"),
                _image(img_path),
            ]
        )

    async def terminate(self) -> None:
        """插件卸载时调用。"""
        if self._dl_task and not self._dl_task.done():
            self._dl_task.cancel()


# ---------------------------------------------------------------------- #
# 消息组件小工具（延迟导入）
# ---------------------------------------------------------------------- #
def _plain(text: str):
    import astrbot.api.message_components as Comp

    return Comp.Plain(text)


def _image(path: str):
    import astrbot.api.message_components as Comp

    return Comp.Image.fromFileSystem(path)
