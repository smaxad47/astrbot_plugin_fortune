# astrbot_plugin_fortune 今日运势（抽签）· 精简版

将 [nonebot_plugin_fortune](https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)（v0.4.12）
移植到 [AstrBot](https://astrbot.app) 的精简版插件。抽签！占卜你的今日运势🙏

> 原插件作者：KafCoppelia <k740677208@gmail.com>，MIT License。
> 抽签图片、文案等资源版权归原作者及各位贡献者所有，详见原项目 README。

## 特点（精简版）

- **依赖极少**：直接使用 AstrBot 内置的文转图 `html_render` 出图，不再依赖 `Pillow` / `httpx`。
- **指令极少**：只保留 `抽签` 与 `主题列表`。可选 `抽签 <主题>` 指定主题。
- **零设置**：默认全部主题启用、随机抽签，无需设置群主题 / 指定签底等操作。
- **每人每天限一次**：按“群 + 用户”记录，跨天自动刷新（基于日期字符串判断）。

## 安装

1. 将 `astrbot_plugin_fortune` 目录放入 AstrBot 的 `data/plugins/` 下（或通过 WebUI 安装）。
2. 在 WebUI「插件」页重载插件。
3. 确保 AstrBot 已配置可用的**文转图（t2i）渲染服务**（WebUI -> 其他 -> 文转图）。
   `html_render` 通过该服务把 HTML 渲染成图片；若使用官方默认端点则无需额外配置。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/抽签`（别名 `/今日运势` `/运势`） | 随机抽一张今日运势 |
| `/抽签 <主题>` | 指定主题抽签，如 `/抽签 pcr`、`/抽签 原神`、`/抽签 碧蓝` |
| `/主题列表` | 查看所有可选主题 |

说明：`抽签` 的参数按主题别名精确或模糊匹配；留空即随机。每人每天限一次，
重复抽签会提示“今天已经抽过啦”。

## 出图说明

- 通过 `self.html_render(_TMPL, data, return_url=False, umo=...)` 渲染一张 480×480 的运势卡：
  以该主题随机一张立绘为底图（内联为 base64 data URI，避免渲染端读不到本地文件）。
- 主题底图本身自带左侧「签面框」和顶部标题框，因此**不叠加白卡**：标题写进顶部框、正文以
  **竖排、从右向左、水平居中**写进签面框，还原原 Pillow 版式。
- 版式按「签面框」定位：`_DEFAULT_BOX = (left, top, right, bottom)` 覆盖绝大多数主题；
  `_THEME_BOX` 用于个别签面不同的主题（已预置 `summer_pockets`、`warship_girls_r`）。
  若某主题仍有偏移，只需给该主题加一行 `_THEME_BOX["xxx"] = (l, t, r, b)` 即可，无需改模板。
- 文案过长会顶出签面，故自动优先挑选 ≤13 字的文案。
- 若你的 t2i 服务对请求体积有限制，可改用底图 URL 而非 data URI（需图床）。

## 资源

- `resource/img/<主题>/`：各主题立绘（约 239MB，随插件自带）。
- `resource/fortune/copywriting.json`：19 类运势 + 700+ 条文案。
- 运行时数据写入 AstrBot `data/plugin_data/astrbot_plugin_fortune/fortune_data.json`，
  不污染插件目录，便于更新。

## 与原 nonebot 版本的差异

- 出图从 Pillow 绘制改为 `html_render`（HTML+CSS），模板可自行调整样式。
- 移除 httpx 自动下载、群主题设置、指定签底、每日定时清图任务。
- 指令从一整套精简为 `抽签` / `主题列表`。
