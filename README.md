# astrbot_plugin_fortune 今日运势（抽签）· 完全独立版

将 [nonebot_plugin_fortune](https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)（v0.4.12）
移植到 [AstrBot](https://astrbot.app) 的插件。抽签！占卜你的今日运势🙏

> 原插件作者：KafCoppelia <k740677208@gmail.com>，MIT License。
> 抽签图片、文案、字体等资源版权归原作者及各位贡献者所有，详见原项目 README。

## 特点

- **完全本地化，不依赖公共 API**：直接用 **Pillow** 在本地绘制 480×480 运势卡，
  不使用 AstrBot 的 `html_render`（其默认会请求公共文转图服务），运行期**不访问任何网络 / 公共接口**。
- **资源全自带**：主题立绘、文案 `copywriting.json`、字体 `Mamelon.otf` / `sakura.ttf`
  都随插件一起打包，安装后开箱即用，无需图床或外部渲染服务。
- **指令极少**：只保留 `抽签` 与 `主题列表`，可选 `抽签 <主题>` 指定主题。
- **零设置**：默认全部主题启用、随机抽签，无需设置群主题 / 指定签底。
- **每人每天限一次**：按“群 + 用户”记录，跨天自动刷新（基于日期字符串判断）。

## 安装

1. 将 `astrbot_plugin_fortune` 目录放入 AstrBot 的 `data/plugins/` 下（或通过 WebUI 安装）。
2. 在 WebUI「插件」页重载插件。
3. 无需配置任何文转图（t2i）服务或公共接口；Pillow 为 AstrBot 核心自带依赖。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/抽签`（别名 `/今日运势` `/运势`） | 随机抽一张今日运势 |
| `/抽签 <主题>` | 指定主题抽签，如 `/抽签 pcr`、`/抽签 原神`、`/抽签 碧蓝` |
| `/主题列表` | 查看所有可选主题 |

说明：`抽签` 的参数按主题别名精确或模糊匹配；留空即随机。每人每天限一次，
重复抽签会提示“今天已经抽过啦”。

## 出图说明（本地 Pillow）

- 以该主题随机一张立绘（480×480）为底图，用 Pillow 绘制：
  - **标题**（如「大吉」「金運」）写进签面顶部的标题框，水平居中；
  - **正文**以**竖排、从右向左、居中**写进签面正文框，还原原 Pillow 版式。
- 文字颜色会根据背景亮度**自适应**（深色底用浅字、浅色底用深字），保证各主题可读性。
- 版式按「签面框」定位：`_DEFAULT_BOX = (left, top, right, bottom)` 覆盖绝大多数主题；
  `_THEME_BOX` / `_LAYOUT_OVERRIDES` 用于个别签面不同的主题
  （已预置 `summer_pockets`、`warship_girls_r`）。
- 为适配签面宽度，文案自动优先挑选 ≤13 字（兜底 ≤16 字），并按每列最多 9 字自动分栏。
- 生成的图片写入 AstrBot 数据目录 `data/plugin_data/astrbot_plugin_fortune/out/`，
  超过 1 天的临时图会在下次出图时自动清理。

## 资源

- `resource/img/<主题>/`：各主题立绘（约 239MB，随插件自带）。
- `resource/fortune/copywriting.json`：19 类运势 + 600+ 条文案。
- `resource/font/Mamelon.otf`、`resource/font/sakura.ttf`：标题 / 正文所用中日文字体。
- 运行时数据写入 AstrBot `data/plugin_data/astrbot_plugin_fortune/fortune_data.json`，
  不污染插件目录，便于更新。

## 与原 nonebot 版本的差异

- 出图沿用原插件的 **Pillow 本地绘制**思路（字体同样使用 Mamelon + sakura），
  而非改为依赖在线文转图服务；未引入任何公共 API 依赖。
- 移除 httpx 自动下载、群主题设置、指定签底、每日定时清图任务。
- 指令从一整套精简为 `抽签` / `主题列表`。
