# astrbot_plugin_fortune 今日运势（抽签）· 核心版

将 [nonebot_plugin_fortune](https://github.com/MinatoAquaCrews/nonebot_plugin_fortune)（v0.4.12）
移植到 [AstrBot](https://astrbot.app) 的插件。抽签！占卜你的今日运势🙏

> 原插件作者：KafCoppelia <k740677208@gmail.com>，MIT License。
> 抽签图片、文案、字体等资源版权归原作者及各位贡献者所有，详见原项目 README。

## 特点

- **保留原版渲染方式**：直接沿用原插件 `utils.drawing()` / `utils.decrement()` 的 Pillow 逻辑——
  标题固定中心 `(140,99)`、45px `#F5F5F5`（`Mamelon.otf`）；正文固定中心 `(140,297)`、
  25px `#323232`（`sakura.ttf`）、每列最多 9 字、竖排分栏。只是把 nonebot2 接口换成 AstrBot 接口。
- **只做核心内容**：仅 `抽签` 一条指令；默认**全部主题启用**、随机抽签；每群每人每天限 1 次。
- **资源可外置**：主题立绘 / 字体 / 文案可打包成 zip 放到 GitHub Release，
  插件仓库只保留代码；运行时从 WebUI「资源管理」页面或自动下载到本地数据目录。

## 两种部署方式

### 方式 A：连资源一起安装（简单，但体积大 ~240MB）
直接让 `resource/` 与代码一起打包进插件即可，无需下载。

### 方式 B：资源外置（推荐，插件仓库只留代码）

1. **打包资源**（在插件目录执行）：
   ```bash
   python scripts/pack_resources.py
   # -> dist/fortune_resource.zip（结构：img/ + fortune/ + font/）
   ```
2. **上传到 GitHub Release**：在仓库新建一个 Release/Tag，把 `dist/fortune_resource.zip` 作为附件上传。
   > 代码里已把默认地址**写死**为 `.../releases/download/0.4.12/fortune_resource.zip`，只要 Release 的 tag 用 `0.4.12` 即可直接使用；否则在下一步覆盖。
3. **（可选）填写地址**：默认无需配置；如需使用其它地址，打开 WebUI →「插件」→ 今日运势 →「插件配置」，把直链填到 `resource_url`。
4. **下载资源**：打开 WebUI →「插件」→ 今日运势 →「资源管理」页面，点击「下载 / 更新资源」，等待进度完成。
   - 或把配置项 `auto_download` 设为 `true`，首次抽签时自动后台下载。
5. 完成后发送 `/抽签` 即可。

> 下载得到的资源保存在 `data/plugin_data/astrbot_plugin_fortune/resource/`，插件更新不会丢。
> 代码会**优先使用**该下载目录；没有时才回退到插件自带的 `resource/`。

#### 让仓库真正“只留代码”
打包并上传 Release 之后，可以把资源从 Git 仓库中剔除（本地文件保留即可，用于重新打包）：
```bash
git rm -r --cached resource/img resource/font resource/fortune
printf 'resource/img/\nresource/font/\nresource/fortune/\n' >> .gitignore
git commit -m "externalize resources to release asset"
```

## 资源包结构

```
fortune_resource.zip
├─ img/<主题>/*.png|jpg      # 各主题立绘
├─ fortune/copywriting.json  # 运势文案
└─ font/
   ├─ Mamelon.otf            # 标题字体
   └─ sakura.ttf             # 正文字体
```

## 指令

| 指令 | 说明 |
| --- | --- |
| `/抽签`（别名 `/今日运势` `/运势`） | 随机抽一张今日运势 |

## 目录结构

```
astrbot_plugin_fortune/
├─ main.py                  # 插件主体（原版渲染 + 资源下载）
├─ metadata.yaml
├─ requirements.txt
├─ _conf_schema.json        # resource_url / auto_download 配置
├─ views/resources/         # 「资源管理」WebUI 页面
├─ scripts/pack_resources.py
├─ .astrbot-plugin/i18n/    # 视图标题等国际化
└─ resource/                # 资源（可按方式 B 从仓库剔除）
```

- 运行时数据：`data/plugin_data/astrbot_plugin_fortune/`（`fortune_data.json`、`out/` 生成的签到图、`resource/` 下载的资源）。
