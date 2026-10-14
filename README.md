# 茜特菈莉桌宠 · 完整待机版

双击 **CitlaliDesktopPet.exe** 运行，无需安装 Python。默认正常站立，背景和窗口边框透明。

- 按住角色拖动：移动位置。
- 鼠标滚轮：调整大小。
- 右键角色：选择站立、喝饮料、读书、自动轮换、暂停、大小或退出。
- 空格：暂停或继续。Esc：退出。

程序置顶，透明区域可以点击到下面的窗口。位置和大小保存在本机的 `pet-settings.json`。

## 完整画面与动作

三组动画来自[新衣装完整待机实机展示](https://www.bilibili.com/video/BV1pUTo6HE8X/)，作者为「你们怎么都给给的QwQ」。人物和整个抱枕一起从实机画面中提取，保留抱枕底部、两侧和蓝色包边，并保持人物与抱枕原本的位置关系。

读书和喝饮料包含动作开始、持续待机和回到站立的过程。三组动画统一使用 400 × 420 的透明画布和相同缩放比例，每帧留有安全边距。原视频为 720p、30 FPS，帧间插值到约 60 FPS，末尾补上短循环过渡；播放器按实际帧时长调度。

| 动作 | 帧数 | 循环时长 |
| --- | ---: | ---: |
| 站立 | 149 | 2.483 秒 |
| 读书 | 857 | 14.283 秒 |
| 喝饮料 | 1079 | 17.983 秒 |

动作过程沿用原实机画面，快速动作保留源视频的运动模糊；补帧可能有少量光流形变。素材来源与截取范围分别记录在 `references/full-idles-source.json` 和 `assets/manifest.json`。用户要求的完整取景参考保存在 `references/requested-full-framing.png`。

## 预览与构建

`动作修复预览.mp4` 对比上一版与当前完整待机版。MP4 下载素材和预览只保存在本机，由 `.gitignore` 排除。构建缓存、日志、设置和备份也不进入 Git。完成修改并验证后创建本地 Git 提交。

`desktop_pet.py` 是播放器源码，直接运行需 Windows、Python 和 Pillow。程序优先加载旁边的 `assets`；没有外部素材时加载 EXE 内打包的动画。

重建流程：

1. 用 `work/download_full_idles.py` 下载实机视频到 `work/sources/full-idles.mp4`。
2. 用 `work/extract_full_idles.py` 提取完整透明动画到 `work/repaired-assets`。
3. 用 `work/validate_assets.py` 校验，再通过 `work/CitlaliDesktopPet.spec` 打包 EXE。

素材处理脚本需要 Pillow、NumPy、OpenCV；下载使用 Windows 的 curl。旧版处理脚本和生成参考保留供历史对照，当前动画由实机视频重建。

旧版备份在 `backups/before-full-idles`。角色与原始素材属于其原权利人，本程序用于个人桌面体验。
