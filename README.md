# 茜特菈莉桌宠 · 高清完整待机版

从 [Releases](https://github.com/Light-w-m/desktop-pet/releases) 下载 **CitlaliDesktopPet.exe**，双击运行，无需安装 Python。默认站立，背景和窗口边框透明。EXE 内置全部播放素材。

源码仓库不包含大型 EXE、动画 WebP 和播放帧包。需要从源码运行或构建时，另下载同一版本的 **CitlaliDesktopPet-source-assets.zip**，解压到项目根目录。MP4 原始录屏不随仓库或 Release 分发。发布步骤见 [GitHub 发布说明](docs/PUBLISHING.md)。

- 按住角色拖动：移动位置。
- 鼠标滚轮：调整大小。
- 右键角色：选择站立、喝饮料、读书、自动轮换、暂停、大小或退出。
- 右键菜单采用浅粉色卡片、细线图标和选中提示；打开时动画继续播放。方向键或 Tab 选择、Enter 执行、Esc 收起，点击菜单外也会收起。
- 右键 → **表情**：九宫格展示慌张、睡了、怀疑、不想面对、刚醒、脸红、有点烦、来了和眨眼。点击后显示在桌宠右上角，5 秒后自动消失；再次选择任意表情会重新计时。暂停动画时也会正常到时消失。
- 表情会随桌宠拖动、缩放和切换动作调整位置；透明贴图不拦截鼠标，靠近屏幕边缘时保持在可见范围内。在表情面板点击“清除表情”即可收起。
- 空格：暂停或继续。Esc：退出。

程序置顶，透明区域可以点击到下面的窗口。位置和大小保存在本机的 `pet-settings.json`。

## 当前素材

三组动画使用用户提供的两段 **2560 × 1440、原生 60 FPS** OBS 录屏重新提取。人物、整个抱枕、包边和动作道具保留原来的相对位置；使用相同取景和缩放，排除游戏界面与地面倒影。透明素材为 **840 × 720 的无损 WebP**，默认显示为 560 × 480，大号显示从高分辨率素材缩放。画布上方及两侧留出动作收尾时抬升和摆动的空间，读书动作中的独立小伙伴，以及入场、收尾时缩小或独立移动的抱枕也完整保留。

读书和喝饮料都保留录屏中的起始动作和回到站立的过程。三组动画的起止帧使用同一站姿，以短过渡衔接轻微的呼吸相位差。动作主体使用录屏原生帧，不再补帧；快速动作保留源录屏已有的运动模糊。

| 动作 | 原生帧数 | 单次时长 |
| --- | ---: | ---: |
| 站立 | 153 | 2.55 秒 |
| 读书 | 816 | 13.6 秒 |
| 喝饮料 | 945 | 15.75 秒 |

选择另一个动作时，当前动作先自然结束并回到站立，再进入所选动作。因此，切换可能需要等待当前动作的剩余时间；右键菜单会显示待切换动作。连续选择以最后一次为准，重新选择正在播放的动作会取消待切换请求并继续播放。暂停时保持当前帧，恢复后继续衔接。

素材记录在 `references/obs-source.json`，帧数、时长和编码信息在 `assets/manifest.json`。完整取景参考保存在 `references/requested-full-framing.png`。以前的处理脚本和小型预览保留供历史对照，大型素材留在本机。

站立的两只鞋分别按实际鞋底轮廓跟踪，去掉原录屏的地面倒影；两条飘带保留浅色连接处，并跟随原动画摆动。动作起始和收尾的公共站姿使用同样的处理，避免切换时倒影重新闪现。

## 构建与验证

`desktop_pet.py` 是 Windows 播放器源码，直接运行需要 Python 和 Pillow；`playback.py` 管理动作切换，`pet_menu.py` 和 `menu_view.py` 绘制粉色菜单，`expressions.py` 管理表情面板和透明贴图。九个 PNG 保存在 `assets/expressions` 并内置到 EXE；缩略图按需解码，最多缓存 18 张小图。程序优先加载旁边的 `assets`，没有外部素材时使用 EXE 内的素材包。

播放器按需读取 `pet-frames.bin`，后台预读接下来 8 帧，已解压帧缓存不超过 12 帧或 24 MiB，不再把 1914 帧全部放进内存。素材包同时保存原生分辨率与默认尺寸的无损帧：默认尺寸提前完成缩放，其他尺寸仍从 840 × 720 原图缩放。透明命中检测复用当前帧的 alpha，省去另一份遮罩。原 WebP 保留用于素材检查，EXE 只包含播放需要的索引和帧包。

两种尺寸的无损数据会增加磁盘体积，用于减少运行时的内存和解码开销。菜单图像也在后台绘制，鼠标悬停时不会阻塞动画播放。

帧包内置在可独立运行的 EXE 中，不在旁边重复保存。源码运行时会读取 `work/repaired-assets` 中生成的帧包；如需外部覆盖，也可把完整的帧包索引和数据放入 `assets`。

本机 45 秒后台回归中，默认尺寸的进程组工作集峰值为 45.0 MiB，大号为 72.4 MiB；旧版默认尺寸约 546.5 MiB。默认三组动作约 60 FPS，大号约 58–59 FPS。1914 帧默认尺寸均与原版显示像素一致，其他尺寸抽查也一致；菜单连续开关后 GDI 句柄数不变。记录保存在 `work/memory-*.json`、`work/exe-playback-*-validation.json`、`work/stream-quality-validation.json` 和 `work/menu-validation.json`。

1. Windows x64 使用 Python 3.12，运行 `python -m pip install -r requirements-build.txt`。把 Release 源码素材包解压到根目录，再运行 `python work/prepare_assets.py`。也可用 `work/extract_obs.py` 从上述本地 OBS 文件重新提取素材，额外需要 NumPy、OpenCV 和 ffmpeg。
2. 运行 `work/validate_assets.py` 检查所有帧的轮廓边距、完整性、时长和公共站姿接缝。
   运行 `work/validate_standing_edges.py` 检查脚底倒影、鞋底边界稳定性和飘带连接处。
3. 运行 `work/test_playback.py` 检查动作中途切换、连续选择和自动轮换。
4. 用 `work/build_frame_pack.py` 生成无损帧包，再运行 `work/validate_stream.py` 对照原 WebP 逐帧检查默认尺寸，以及抽查其他尺寸和任意跳帧。
5. 通过 `work/CitlaliDesktopPet.spec` 打包 EXE，再使用 `--qa-seconds 45` 实际验证三种动作的播放。`work/test_pink_menu.py` 检查菜单交互和 GDI 资源释放，`work/test_expressions.py` 检查九个表情的选择、清除、跟随位置、透明命中和重复开关。

EXE、动画 WebP、播放帧包、MP4、构建缓存、日志、设置和本地备份由 `.gitignore` 排除。`work/prepare_release.py` 可以生成本地 Release 附件；`work/check_publish_repo.py` 检查所有可推送历史中的大文件。完成修改并验证后创建本地 Git 提交。角色与录屏内容属于原权利人，本程序用于个人桌面体验。
