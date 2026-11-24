# astrbot_plugin_fortune 今日运势（抽签）· 核心版

将 [nonebot_plugin_fortune](https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)（v0.4.12）
移植到 [AstrBot](https://astrbot.app) 的插件。抽签！占卜你的今日运势🙏

> 原插件作者：KafCoppelia <k740677208@gmail.com>，MIT License。
> 抽签图片、文案、字体等资源版权归原作者及各位贡献者所有，详见原项目 README。

## 说明

- **保留原版渲染方式**：直接沿用原插件的 `utils.drawing()` / `utils.decrement()` 的 Pillow 绘制逻辑——
  标题固定中心 `(140, 99)`、45px `#F5F5F5`（`Mamelon.otf`）；正文固定中心 `(140, 297)`、
  25px `#323232`（`sakura.ttf`）、每列最多 9 字、竖排分栏。**只是把 nonebot2 的接口换成 AstrBot 的接口**，
  出图效果与原插件一致。
- **只做核心内容**：仅 `抽签` 一条指令；默认**全部主题启用**、随机抽签。
- 每群每人每天限抽 1 次（当天再抽会返回当天已生成的同一张签，与原插件一致）。
- 完全本地渲染，不依赖任何在线文转图 / 公共 API；Pillow 为 AstrBot 核心自带依赖。

## 安装

1. 将 `astrbot_plugin_fortune` 目录放入 AstrBot 的 `data/plugins/` 下（或通过 WebUI 安装）。
2. 在 WebUI「插件」页重载插件即可，无需配置文转图服务。

## 指令

| 指令 | 说明 |
| --- | --- |
| `/抽签`（别名 `/今日运势` `/运势`） | 随机抽一张今日运势 |

## 资源

- `resource/img/<主题>/`：各主题立绘（480×480，随插件自带）。
- `resource/fortune/copywriting.json`：运势文案。
- `resource/font/Mamelon.otf`、`resource/font/sakura.ttf`：标题 / 正文所用字体（随插件自带）。
- 运行数据（`fortune_data.json` 与生成的签到图 `out/`）写入 AstrBot
  `data/plugin_data/astrbot_plugin_fortune/`，不污染插件目录。
