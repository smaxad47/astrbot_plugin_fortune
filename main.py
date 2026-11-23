"""今日运势（抽签）AstrBot 插件 —— 本地渲染 · 完全独立版。

移植自 nonebot_plugin_fortune (https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)
原作者: KafCoppelia <k740677208@gmail.com>，MIT License。

设计目标（v0.5.0）：
- **完全本地化**：不再使用 AstrBot 的 `html_render`（其默认走公共 t2i 接口），
  而是直接用 Pillow 在本地绘制 480x480 运势卡，运行期不访问任何公共 API / 网络。
- **自带资源**：主题立绘、文案、字体（Mamelon.otf / sakura.ttf）全部随插件打包，
  仅依赖 AstrBot 核心已内置的 Pillow（pyproject: pillow>=11.2.1）。
- **指令精简**：只保留 `抽签`（一般抽签）、可选 `抽签 <主题>`、`主题列表`。
- 每群每人每天限抽 1 次，跨天自动刷新（基于日期字符串判断）。
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from datetime import date
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# Pillow 是 AstrBot 核心依赖（pyproject 中声明 pillow>=11.2.1），这里直接本地出图，
# 不经过任何在线文转图（t2i）服务，也不依赖公共 API。
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
# 本地出图（Pillow）配置
# ---------------------------------------------------------------------- #
_FONT_DIR = Path(__file__).parent / "resource" / "font"
TITLE_FONT_FILE = _FONT_DIR / "Mamelon.otf"
TEXT_FONT_FILE = _FONT_DIR / "sakura.ttf"

# 主题底图（resource/img/<主题>/*，均为 480x480）自带左侧「签面框」与顶部标题框。
# 版式按「签面框」定位：_DEFAULT_BOX = (left, top, right, bottom)，
# 各主题签面位置基本一致，个别主题在 _THEME_BOX 中覆盖即可。
_DEFAULT_BOX = (45, 61, 221, 452)

# 个别主题签面框不同则在此覆盖 (left, top, right, bottom)。
_THEME_BOX: dict[str, tuple[int, int, int, int]] = {
    "summer_pockets": (35, 110, 262, 455),  # 黄色描边框，偏宽、偏下、无白底
}

# 少数主题版式差异较大，直接给出完整布局（标题/正文坐标）。
_LAYOUT_OVERRIDES: dict[str, dict] = {
    "warship_girls_r": {
        "center_x": 143,
        "title_y": 110,       # 顶部米色标题条
        "text_top": 205,      # 「今日运势」标签之下
        "text_bottom": 400,
        "max_chars": 6,
    },
}

_TITLE_SIZE = 30
_TEXT_SIZE = 24
_TEXT_GAP = 6          # 竖排时字与字之间的垂直间距
_COL_GAP = 16          # 两列之间的水平间距
_MAX_CHARS = 9         # 每列最多字数（默认版式）
_INK_THRESHOLD = 147   # 背景亮度阈值：>= 用深色字，否则用浅色字
_PUNCT = set("，。！？、；：…—,.!?;:")

# 字体缓存（避免每次渲染都重新加载 20MB 字体）。
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    key = (str(path), size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


def _mean_luma(img: Image.Image, box: tuple[int, int, int, int]) -> float:
    """返回指定区域的平均亮度（0~255），用于自适应文字颜色。"""
    region = img.crop(box).convert("L")
    hist = region.histogram()
    total = sum(hist)
    if not total:
        return 255.0
    return sum(i * c for i, c in enumerate(hist)) / total


def _split_columns(text: str, max_chars: int) -> list[str]:
    """把文案按每列最多 max_chars 字切成若干列（尽量均分，避免标点掉到列首）。"""
    if not text:
        return [""]
    max_chars = max(1, max_chars)
    n = max(1, math.ceil(len(text) / max_chars))
    per = math.ceil(len(text) / n)
    cols: list[str] = []
    i = 0
    while i < len(text):
        end = min(len(text), i + per)
        # 若切分点落在标点上，把标点并入当前列，避免下一列以标点开头
        while end < len(text) and text[end] in _PUNCT:
            end += 1
        cols.append(text[i:end])
        i = end
    return cols


def _compute_layout(theme: str) -> dict:
    """由主题名推导标题与正文的绘制布局。"""
    if theme in _LAYOUT_OVERRIDES:
        return dict(_LAYOUT_OVERRIDES[theme])

    left, top, right, bottom = _THEME_BOX.get(theme, _DEFAULT_BOX)
    cx = (left + right) // 2
    return {
        "center_x": cx,
        # 标题：签面顶部自带的标题框（约 top+12 起，高 48），垂直中心 top+36
        "title_y": top + 36,
        # 正文：「运势」字样及其下方波浪线之后开始，到框底留白
        "text_top": top + 105,
        "text_bottom": bottom - 8,
        "max_chars": _MAX_CHARS,
    }


def _draw_card(
    base_path: Path, title: str, text: str, theme: str, out_path: Path
) -> Path:
    """在本地用 Pillow 绘制一张运势卡并保存到 out_path。"""
    img = Image.open(base_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    layout = _compute_layout(theme)
    cx = layout["center_x"]

    # ---------- 标题（写进顶部标题框，水平居中） ----------
    title_font = _load_font(TITLE_FONT_FILE, _TITLE_SIZE)
    title_w = draw.textlength(title, font=title_font)
    band = (
        int(cx - title_w / 2),
        layout["title_y"] - 18,
        int(cx + title_w / 2) + 1,
        layout["title_y"] + 18,
    )
    band_luma = _mean_luma(img, band)
    if band_luma >= _INK_THRESHOLD:
        title_fill, title_stroke = (45, 45, 45), (255, 255, 255)
    else:
        title_fill, title_stroke = (252, 252, 252), (35, 35, 35)
    draw.text(
        (cx, layout["title_y"]),
        title,
        font=title_font,
        fill=title_fill,
        anchor="mm",
        stroke_width=1,
        stroke_fill=title_stroke,
    )

    # ---------- 正文（竖排、从右向左、居中） ----------
    text_top = layout["text_top"]
    text_bottom = layout["text_bottom"]
    box_h = text_bottom - text_top
    cell = _TEXT_SIZE + _TEXT_GAP
    text_font = _load_font(TEXT_FONT_FILE, _TEXT_SIZE)

    cols = _split_columns(text, layout.get("max_chars", _MAX_CHARS))
    n = len(cols)
    pitch = _TEXT_SIZE + _COL_GAP
    total_w = n * pitch

    body_band = (
        int(cx - total_w / 2),
        text_top,
        int(cx + total_w / 2) + 1,
        text_bottom,
    )
    body_luma = _mean_luma(img, body_band)
    if body_luma >= _INK_THRESHOLD:
        body_fill, body_stroke, body_sw = (48, 48, 48), None, 0
    else:
        body_fill, body_stroke, body_sw = (248, 248, 248), (25, 25, 25), 1

    for ci, col in enumerate(cols):
        # 第一列在最右（竖排从右向左阅读）
        col_left = cx + total_w / 2 - (ci + 1) * pitch
        xc = col_left + pitch / 2
        col_h = len(col) * cell
        start_y = text_top + (box_h - col_h) / 2
        for j, ch in enumerate(col):
            if ch == " ":
                continue
            yc = start_y + (j + 0.5) * cell
            draw.text(
                (xc, yc),
                ch,
                font=text_font,
                fill=body_fill,
                anchor="mm",
                stroke_width=body_sw,
                stroke_fill=body_stroke,
            )

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
    "抽签！占卜你的今日运势🙏（本地 Pillow 出图，完全独立）",
    __fortune_version__,
    "https://github.com/MinatoAquaCrews/nonebot_plugin_fortune",
)
class FortunePlugin(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.resource_dir = Path(__file__).parent / "resource"
        self.img_dir = self.resource_dir / "img"
        self.copywriting_file = self.resource_dir / "fortune" / "copywriting.json"

        self.data_dir = _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / "fortune_data.json"
        self.out_dir = self.data_dir / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._dump_json(self.data_file, {})

        self._copywriting: list[dict] = self._load_copywriting()
        self._check_resources()

    # ------------------------------------------------------------------ #
    # 资源与数据
    # ------------------------------------------------------------------ #
    def _check_resources(self) -> None:
        if not self.img_dir.exists():
            logger.error(f"运势图片资源缺失: {self.img_dir}")
        if not self.copywriting_file.exists():
            logger.error(f"运势文案资源缺失: {self.copywriting_file}")
        if not TITLE_FONT_FILE.exists():
            logger.error(f"标题字体资源缺失: {TITLE_FONT_FILE}")
        if not TEXT_FONT_FILE.exists():
            logger.error(f"正文字体资源缺失: {TEXT_FONT_FILE}")

    def _load_copywriting(self) -> list[dict]:
        try:
            with open(self.copywriting_file, "r", encoding="utf-8") as f:
                return json.load(f).get("copywriting", [])
        except Exception as e:  # noqa: BLE001
            logger.error(f"读取运势文案失败: {e}")
            return []

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
        data = self._load_data()
        rec = data.get(gid, {}).get(uid)
        return bool(rec) and rec.get("last_sign_date") == date.today().isoformat()

    def _mark_drawn(self, gid: str, uid: str) -> None:
        data = self._load_data()
        data.setdefault(gid, {})[uid] = {"last_sign_date": date.today().isoformat()}
        self._dump_json(self.data_file, data)

    # ------------------------------------------------------------------ #
    # 主题与抽签
    # ------------------------------------------------------------------ #
    def _available_themes(self) -> list[str]:
        return [
            t
            for t in FortuneThemesDict
            if t != "random" and (self.img_dir / t).is_dir()
        ]

    def _random_theme(self) -> str:
        return random.choice(self._available_themes())

    def _resolve_theme(self, arg: str) -> tuple[str | None, str | None]:
        """根据用户输入解析主题，返回 (主题目录名, 错误信息)。

        arg 为空或“随机”时随机选一个主题；否则按别名精确或子串匹配。
        """
        if not arg or arg in FortuneThemesDict["random"]:
            return self._random_theme(), None
        for theme, aliases in FortuneThemesDict.items():
            if theme != "random" and arg in aliases:
                return theme, None
        for theme, aliases in FortuneThemesDict.items():
            if theme != "random" and any(arg in a for a in aliases):
                return theme, None
        return None, "还没有这种抽签主题哦~"

    def _pick_image(self, theme: str) -> Path:
        folder = self.img_dir / theme
        images = [p for p in folder.iterdir() if p.is_file()]
        return random.choice(images)

    def _get_copywriting(self) -> tuple[str, str]:
        """随机取一条运势（标题 + 文案）。

        签面宽度有限，过长文案会顶出签面，因此优先选择 ≤13 字的文案；
        若该分类没有则退而求其次选 ≤16 字，保证实际绘制的文案不会过长。
        """
        if not self._copywriting:
            return "今日运势", "运势不错"

        # 只从“至少有一条 ≤16 字文案”的分类里挑，避免出现超长文案
        valid = [
            luck
            for luck in self._copywriting
            if any(len(t) <= 16 for t in luck.get("content", []))
        ]
        luck = random.choice(valid or self._copywriting)
        texts = luck.get("content", []) or ["运势不错"]
        short = [t for t in texts if len(t) <= 13]
        mid = [t for t in texts if len(t) <= 16]
        pool = short or mid or texts
        text = random.choice(pool)
        return luck.get("good-luck", "今日运势"), text

    # ------------------------------------------------------------------ #
    # 本地渲染
    # ------------------------------------------------------------------ #
    def _render_sync(self, theme: str) -> str:
        """同步渲染（在线程池中执行，避免阻塞事件循环）。"""
        title, text = self._get_copywriting()
        base = self._pick_image(theme)
        out_name = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}.png"
        out_path = self.out_dir / out_name
        _draw_card(base, title, text, theme, out_path)
        self._cleanup_out_dir()
        return str(out_path)

    def _cleanup_out_dir(self, max_age_seconds: int = 86400) -> None:
        """清理 1 天前的临时图片，避免占用过多磁盘。"""
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

    async def _render_card(self, event: AstrMessageEvent, theme: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._render_sync, theme)

    # ------------------------------------------------------------------ #
    # 指令
    # ------------------------------------------------------------------ #
    @filter.command("抽签", alias={"今日运势", "运势"})
    async def divine(self, event: AstrMessageEvent, arg: str = ""):
        """抽签：抽一张今日运势。可带主题，如 /抽签 pcr。每人每天限一次。"""
        gid = event.get_group_id() or event.get_session_id()
        uid = event.get_sender_id() or "unknown"

        if self._already_drawn(gid, uid):
            yield event.plain_result(
                "你今天抽过签了，贪心的人是不会有好运的🤗 明天再来吧～"
            )
            return

        theme, err = self._resolve_theme(arg.strip())
        if err:
            yield event.plain_result(err)
            return

        try:
            img_path = await self._render_card(event, theme)
        except Exception as e:  # noqa: BLE001
            logger.error(f"今日运势生成出错: {e}")
            yield event.plain_result("今日运势生成出错……请稍后再试")
            return

        self._mark_drawn(gid, uid)
        logger.info(f"User {uid} | Group {gid} 占卜了今日运势（{theme}）")

        yield event.chain_result(
            [
                _at(event.get_sender_id()),
                _plain("✨今日运势✨\n"),
                _image(img_path),
            ]
        )

    @filter.command("主题列表")
    async def themes_list(self, event: AstrMessageEvent):
        """查看可选的抽签主题。"""
        msg = "可选抽签主题"
        for theme, aliases in FortuneThemesDict.items():
            if theme != "random" and (self.img_dir / theme).is_dir():
                msg += f"\n{aliases[0]}"
        yield event.plain_result(msg)

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
