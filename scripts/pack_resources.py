#!/usr/bin/env python3
"""把 resource/ 下的图片/字体/文案打包成一个资源 zip。

用法：
    python scripts/pack_resources.py
    python scripts/pack_resources.py --resource resource --out dist/fortune_resource.zip

生成的 zip 结构（解压后即为一个资源根目录）：
    img/<主题>/*.png|jpg
    fortune/copywriting.json
    font/Mamelon.otf
    font/sakura.ttf

把这个 zip 作为 GitHub Release 的附件上传，然后把下载直链填到
插件配置 resource_url，或在插件「资源管理」页面里填写。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import zipfile
from pathlib import Path


def human_size(n: int) -> str:
    v = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if v < 1024 or u == "GB":
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} GB"


def build(resource_dir: Path, out_zip: Path, compress: bool = False) -> None:
    include = ["img", "fortune", "font"]
    missing = [d for d in include if not (resource_dir / d).exists()]
    if missing:
        print(f"[warn] 缺少目录（会被跳过）: {', '.join(missing)}")

    # 图片本身已是压缩格式，默认仅存储（ZIP_STORED），打包更快、体积几乎相同。
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if compress:
        zf_ctx = zipfile.ZipFile(out_zip, "w", compression=compression, compresslevel=6)
    else:
        zf_ctx = zipfile.ZipFile(out_zip, "w", compression=compression)
    with zf_ctx as zf:
        for top in include:
            base = resource_dir / top
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    arc = Path(top) / path.relative_to(base)
                    zf.write(path, arc.as_posix())
                    count += 1
    size = out_zip.stat().st_size
    sha = hashlib.sha256(out_zip.read_bytes()).hexdigest()
    print(f"打包完成: {out_zip}")
    print(f"  文件数: {count}")
    print(f"  体积  : {human_size(size)} ({size} bytes)")
    print(f"  sha256: {sha}")


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="打包 astrbot_plugin_fortune 资源")
    ap.add_argument("--resource", default=str(here / "resource"), help="资源目录（含 img/fortune/font）")
    ap.add_argument("--out", default=str(here / "dist" / "fortune_resource.zip"), help="输出 zip 路径")
    ap.add_argument("--compress", action="store_true", help="使用 Deflate 压缩（默认仅存储，打包更快）")
    args = ap.parse_args()
    build(Path(args.resource), Path(args.out), compress=args.compress)


if __name__ == "__main__":
    main()
