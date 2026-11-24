"""今日运势（抽签）AstrBot 插件 —— 原版渲染移植 · 核心版。

移植自 nonebot_plugin_fortune v0.4.12
(https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)
原作者: KafCoppelia <k740677208@gmail.com>，MIT License。

本版说明：
- **保留原插件的绘制方式**：直接沿用原 `utils.drawing()` / `utils.decrement()` 的
  Pillow 绘制逻辑——固定标题中心 (140, 99)、正文字中心 (140, 297)，标题 45px `#F5F5F5`
  （Mamelon.otf），正文 25px `#323232`（sakura.ttf）、竖排分栏。只是把 nonebot2 的接口
  换成 AstrBot 的接口，渲染结果与原插件一致。
- **只做核心内容**：仅 `抽签` 一条指令；默认全部主题启用、随机抽签。
- 每群每人每天限抽 1 次（同日再抽会返回当天已生成的同一张签，与原插件一致）。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import date
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# Pillow 为 AstrBot 核心自带依赖（pyproject: pillow>=11.2.1），本地出图、无需任何公共 API。
from PIL import Image, ImageDraw, ImageFont

__fortune_version__ = "v0.5.0"

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
# 资源路径
# ---------------------------------------------------------------------- #
RESOURCE_DIR = Path(__file__).parent / "resource"
IMG_DIR = RESOURCE_DIR / "img"
COPYWRITING_FILE = RESOURCE_DIR / "fortune" / "copywriting.json"
FONT_DIR = RESOURCE_DIR / "font"
TITLE_FONT_FILE = FONT_DIR / "Mamelon.otf"
TEXT_FONT_FILE = FONT_DIR / "sakura.ttf"

# 字体按 (路径, 字号) 缓存，避免每次出图都重复加载 20MB 字体（不影响绘制结果）。
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    key = (str(path), size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


def _safe_name(name: str) -> str:
    """把群号/用户号收敛为安全的文件名片段。"""
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(name)) or "unknown"


# ---------------------------------------------------------------------- #
# 以下是原 nonebot_plugin_fortune 的绘制逻辑（保持原样，仅改用本插件的资源路径）
# ---------------------------------------------------------------------- #
def get_copywriting() -> tuple[str, str]:
    """原 utils.get_copywriting：读取 copywriting.json，随机取一条运势（标题 + 文案）。"""
    with open(COPYWRITING_FILE, "r", encoding="utf-8") as f:
        content = json.load(f).get("copywriting")
    luck = random.choice(content)
    return luck.get("good-luck"), random.choice(luck.get("content"))


def random_basemap(theme: str) -> Path:
    """原 utils.random_basemap：theme 为 random 时在所有主题目录中随机选一张底图。"""
    if theme == "random":
        base = IMG_DIR
        # 每个子文件夹是一个主题；本版默认全部主题启用
        themes: list[str] = [f.name for f in base.iterdir() if f.is_dir()]
        base = base / random.choice(themes)
    else:
        base = IMG_DIR / theme
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

    # 针对两列做补空格对齐
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
    # 1. 随机选一张底图
    img_path: Path = random_basemap(theme)
    img: Image.Image = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 2. 随机取一条运势
    title, text = get_copywriting()

    # 3. 绘制标题（固定中心 140,99；45px；#F5F5F5；Mamelon.otf）
    font_size = 45
    color = "#F5F5F5"
    image_font_center = [140, 99]
    ttfront = _load_font(TITLE_FONT_FILE, font_size)
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

    # 4. 绘制正文（固定中心 140,297；25px；#323232；sakura.ttf；竖排分栏）
    font_size = 25
    color = "#323232"
    image_font_center = [140, 297]
    ttfront = _load_font(TEXT_FONT_FILE, font_size)
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

    # 5. 保存
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path: Path = out_dir / f"{_safe_name(gid)}_{_safe_name(uid)}.png"
    img.save(out_path)
    return out_path


def _default_data_dir() -> Path:
    """AstrBot 插件数据目录；不可用时回退到插件目录下 data。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        return Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_fortune"
    except Exception:  # noqa: BLE001
        return Path(__file__).parent / "data"


@register(
    "astrbot_plugin_fortune",
    "KafCoppelia (nonebot 原作者) / AstrBot 移植",
    "抽签！占卜你的今日运势🙏（原版 Pillow 渲染）",
    __fortune_version__,
    "https://github.com/MinatoAquaCrews/nonebot_plugin_fortune",
)
class FortunePlugin(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.data_dir = _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = self.data_dir / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / "fortune_data.json"
        if not self.data_file.exists():
            self._dump_json(self.data_file, {})
        self._check_resources()

    # ------------------------------------------------------------------ #
    # 资源与数据
    # ------------------------------------------------------------------ #
    def _check_resources(self) -> None:
        if not IMG_DIR.is_dir():
            logger.error(f"运势图片资源缺失: {IMG_DIR}")
        if not COPYWRITING_FILE.exists():
            logger.error(f"运势文案资源缺失: {COPYWRITING_FILE}")
        if not TITLE_FONT_FILE.exists():
            logger.error(f"标题字体资源缺失: {TITLE_FONT_FILE}")
        if not TEXT_FONT_FILE.exists():
            logger.error(f"正文字体资源缺失: {TEXT_FONT_FILE}")

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

    # ------------------------------------------------------------------ #
    # 出图
    # ------------------------------------------------------------------ #
    def _draw_sync(self, gid: str, uid: str) -> str:
        """同步出图（在线程池中执行，避免阻塞事件循环）。"""
        out_path = drawing(gid, uid, "random", self.out_dir)
        self._cleanup_out_dir()
        return str(out_path)

    def _cleanup_out_dir(self, max_age_seconds: int = 2 * 86400) -> None:
        """清理 2 天前的旧图，避免持续占用磁盘。"""
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

    # ------------------------------------------------------------------ #
    # 指令：抽签（核心，仅此一条）
    # ------------------------------------------------------------------ #
    @filter.command("抽签", alias={"今日运势", "运势"})
    async def divine(self, event: AstrMessageEvent):
        """抽签：占卜今日运势。默认全部主题随机。每人每天限一次。"""
        gid = event.get_group_id() or event.get_session_id()
        uid = event.get_sender_id() or "unknown"

        # 当天已抽过：返回当天已生成的同一张签
        cached = self._cached_path(gid, uid)
        if self._already_drawn(gid, uid) and cached.exists():
            yield event.chain_result(
                [
                    _at(event.get_sender_id()),
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
                _at(event.get_sender_id()),
                _plain("✨今日运势✨\n"),
                _image(img_path),
            ]
        )

    async def terminate(self) -> None:
        """插件卸载时调用（本插件无后台任务）。"""


# ---------------------------------------------------------------------- #
# 消息组件小工具（延迟导入）
# ---------------------------------------------------------------------- #
def _at(qq: str):
    import astrbot.api.message_components as Comp

    return Comp.At(qq=qq)


def _plain(text: str):
    import astrbot.api.message_components as Comp

    return Comp.Plain(text)


def _image(path: str):
    import astrbot.api.message_components as Comp

    return Comp.Image.fromFileSystem(path)
