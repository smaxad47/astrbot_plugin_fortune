"""今日运势（抽签）AstrBot 插件 —— 精简版。

移植自 nonebot_plugin_fortune (https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)
原作者: KafCoppelia <k740677208@gmail.com>，MIT License。

设计目标（精简版）：
- 依赖极少：仅用 AstrBot 内置的文转图 `html_render`，不依赖 Pillow / httpx。
- 指令极少：只保留 `抽签`（一般抽签）与 `主题列表`；可选 `抽签 <主题>` 指定主题。
- 不做任何“设置/重置群主题”的功能：默认全部主题启用，随机抽签。
- 每群每人每天限抽 1 次，跨天自动刷新（基于日期字符串判断）。
"""

from __future__ import annotations

import base64
import json
import random
from datetime import date
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

__fortune_version__ = "v0.4.12"

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

# html_render 的 HTML 模板。
# 主题底图（resource/img/<主题>/*，480x480）本身自带左侧"签面框"与顶部标题框，
# 因此只把标题写进顶部框、正文以【竖排、从右向左、居中】写进签面框即可，
# 无需叠加白色卡片——还原原插件用 Pillow 绘制的版式。
#
# 版式按「签面框」定位：_DEFAULT_BOX = (left, top, right, bottom)，
# 各主题底图的签面位置基本一致，个别主题在 _THEME_BOX 中覆盖即可。
_TMPL = """
<div style="
    width:480px;height:480px;position:relative;
    background-image:url('{{ bg }}');
    background-size:cover;background-position:center;
    font-family:'Mamelon','Sakura','PingFang SC','Microsoft YaHei',sans-serif;
    overflow:hidden;">
  <div style="
      position:absolute;left:{{ title_x }}px;top:{{ title_y }}px;
      width:{{ title_w }}px;height:{{ title_h }}px;
      display:flex;align-items:center;justify-content:center;
      color:{{ title_color }};font-size:{{ title_size }}px;font-weight:bold;
      letter-spacing:2px;text-shadow:0 0 5px rgba(255,255,255,.95),
      0 0 2px rgba(255,255,255,.95);">{{ title }}</div>
  <div style="
      position:absolute;left:{{ text_x }}px;top:{{ text_y }}px;
      width:{{ text_w }}px;height:{{ text_h }}px;
      display:flex;flex-direction:row;justify-content:center;
      align-items:flex-start;">
    <div style="
        writing-mode:vertical-rl;text-orientation:upright;
        letter-spacing:{{ text_spacing }}px;
        color:{{ text_color }};font-size:{{ text_size }}px;
        line-height:{{ text_lineheight }}px;">{{ text }}</div>
  </div>
</div>
"""

# 默认签面框 (left, top, right, bottom)，适用于多数 480x480 主题。
_DEFAULT_BOX = (45, 61, 221, 452)

# 个别主题签面框不同则在此覆盖 (left, top, right, bottom)。
_THEME_BOX: dict[str, tuple[int, int, int, int]] = {
    "summer_pockets": (35, 110, 262, 455),  # 黄色描边框，偏宽、偏下、无白底
    "warship_girls_r": (52, 175, 192, 447),  # 灰白面板，顶部有预印「今日运势」红框
}


def _layout_from_box(box: tuple[int, int, int, int]) -> dict:
    """由签面框推导标题框与正文框的绝对坐标（标题/正文均水平居中于签面）。"""
    left, top, right, bottom = box
    width = right - left
    cx = (left + right) // 2

    # 标题：签面内顶部自带的标题框（约 top+12 起，高 48），水平居中
    title_w = int(width * 0.9)
    title_h = 48
    title_x = cx - title_w // 2
    title_y = top + 12

    # 正文：从「运势」字样及其下方波浪线之后开始（约 top+105），到框底留白
    text_w = int(width * 0.9)
    text_x = cx - text_w // 2
    text_y = top + 105
    text_h = bottom - text_y - 8

    return {
        "title_x": title_x,
        "title_y": title_y,
        "title_w": title_w,
        "title_h": title_h,
        "title_size": 30,
        "title_color": "#333333",
        "text_x": text_x,
        "text_y": text_y,
        "text_w": text_w,
        "text_h": text_h,
        "text_size": 23,
        "text_lineheight": 27,
        "text_spacing": 9,
        "text_color": "#3a3a3a",
    }


# 兼容旧命名的默认布局（dc4 等常见主题）。
_DEFAULT_LAYOUT = _layout_from_box(_DEFAULT_BOX)


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
    "抽签！占卜你的今日运势🙏（精简版，html_render 出图）",
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
        if not self.data_file.exists():
            self._dump_json(self.data_file, {})

        self._check_resources()

    # ------------------------------------------------------------------ #
    # 资源与数据
    # ------------------------------------------------------------------ #
    def _check_resources(self) -> None:
        if not self.img_dir.exists():
            logger.error(f"运势图片资源缺失: {self.img_dir}")
        if not self.copywriting_file.exists():
            logger.error(f"运势文案资源缺失: {self.copywriting_file}")

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
    def _random_theme(self) -> str:
        themes = [
            t
            for t in FortuneThemesDict
            if t != "random" and (self.img_dir / t).is_dir()
        ]
        return random.choice(themes)

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
        """随机取一条运势。

        签面可容纳约两列、每列 9 字左右，过长的文案会顶出签面，
        因此优先挑选长度适中（<= 13 字）的文案；兜底再放宽到 16 字。
        """
        with open(self.copywriting_file, "r", encoding="utf-8") as f:
            content = json.load(f).get("copywriting")
        # 优先 <=13 字
        for _ in range(16):
            luck = random.choice(content)
            text = random.choice(luck.get("content"))
            if len(text) <= 13:
                return luck.get("good-luck"), text
        # 放宽到 <=16
        for _ in range(16):
            luck = random.choice(content)
            text = random.choice(luck.get("content"))
            if len(text) <= 16:
                return luck.get("good-luck"), text
        # 兜底
        return luck.get("good-luck"), text

    @staticmethod
    def _img_data_uri(path: Path) -> str:
        """把本地图片转成 data URI，供 HTML 模板内联使用（无需额外依赖）。"""
        ext = path.suffix.lower().lstrip(".")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:image/{mime};base64,{b64}"

    async def _render_card(self, event: AstrMessageEvent, theme: str) -> str:
        title, text = self._get_copywriting()
        box = _THEME_BOX.get(theme) or _DEFAULT_BOX
        # 占位用的 (0,0,0,0) 视为无效 -> 回退默认框
        if box == (0, 0, 0, 0):
            box = _DEFAULT_BOX
        layout = _layout_from_box(box)
        data = {
            "bg": self._img_data_uri(self._pick_image(theme)),
            "title": title,
            "text": text,
            **layout,
        }
        # return_url=False -> 返回本地文件路径，可直接用于 image_result
        return await self.html_render(
            _TMPL, data, return_url=False, umo=event.unified_msg_origin
        )

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
        """插件卸载时调用（本精简版无后台任务）。"""


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
