# 茜特菈莉桌宠 · 高清完整待机版

![茜特菈莉桌宠封面](docs/images/cover.jpg)

从 [Releases](https://github.com/Light-w-m/desktop-pet/releases) 下载 **CitlaliDesktopPet.exe**，双击运行，无需安装 Python。默认站立，背景和窗口边框透明。EXE 内置全部播放素材。

[v1.3.0](https://github.com/Light-w-m/desktop-pet/releases/tag/v1.3.0) 使用无损动画差分压缩，EXE 约 229 MiB，五种动画共 2178 帧。主动作和拖动素材保持原像素，所有素材在压缩前后逐帧对比无差异；日常运行只需要 EXE。

源码仓库不包含大型 EXE、动画 WebP 和播放帧包。需要从源码运行或构建时，另下载同一版本的 **CitlaliDesktopPet-source-assets.zip**，解压到项目根目录。MP4 原始录屏不随仓库或 Release 分发。发布步骤见 [GitHub 发布说明](docs/PUBLISHING.md)。

- 左键双击角色：随机显示“有点烦”或“脸红”。
- 按住角色拖动：移动位置，同时播放抱着抱枕摇晃的拖动动画，并随机显示“不想面对”或“来了”。拖动开始与松手时采用短渐变，松手后继续此前的动作；同一次拖动只触发表情一次，轻微手抖不会触发。互动表情显示在右上角，5 秒后自动消失。
- 晃动小彩蛋：按住角色快速来回晃几下，晃动时仍播放原来的移动动作；停下约 0.24 秒或松手后，跺一次脚，同时在右上角显示专属生气表情。动作约 4.93 秒，保留原视频的抬脚、落脚、转正、收手和站稳，清理收腿时两脚之间误留的背景；最后约 0.6 秒对齐到站立首帧，再从待机下一帧继续；专属表情 5 秒后消失，不加入原来的九宫格。普通拖动、缓慢摆动和轻微手抖不会触发。判定窗口约 1.25 秒，需明显反向至少 4 次，同次拖动只触发一次，并有 2.5 秒冷却。横向、纵向和斜向都支持；再次拖动可中断跺脚，暂停主动画时仍可互动。
- 跺脚开始时，从“元素爆发·其一～其三”和“重受击·其一～其二”五条中文语音中随机播放一条，避免连续重复。沿用语音开关和音量；手动点播优先，跺脚语音不会被随后恢复的喝饮料语音打断。
- 右键 → **自由走动**：保持开始时的高度，沿水平线持续走动，遇到当前显示器的可用区域边缘直接切换方向，不停下来转身。点击、双击、拖动、打开右键菜单、换动作、暂停或缩放都会停止，需要再次选择才会继续。
- 连续走动约 25～40 秒后，依次说完“突破的感受·起、承、转、合”，每条实际播放完成后等待约 0.8 秒，整组结束再间隔 90～150 秒。沿用语音开关和音量，打断走动时取消剩余语音，手动点播优先。
- 鼠标滚轮：调整大小。
- 右键角色：选择站立、喝饮料、读书、自由走动、自动轮换、暂停、大小或退出。
- 右键菜单采用迷你浅粉色卡片，主菜单及表情面板约为上一版一半的宽高。弹窗放在人物旁边，右侧放不下时切到左侧；切换动作时重新避开人物，窄屏时自动适配可用空间。打开时动画继续播放，方向键或 Tab 选择、Enter 执行、Esc 收起，点击菜单外也会收起。
- 右键 → **表情**：九宫格展示慌张、睡了、怀疑、不想面对、刚醒、脸红、有点烦、来了和眨眼。点击后显示在桌宠右上角，5 秒后自动消失；再次选择任意表情会重新计时。暂停动画时也会正常到时消失。
- “表情”和“语音”并排显示。点击“语音”打开迷你分页列表，点击名称播放；上一页/下一页、左右方向键或滚轮翻页，点击“停止”结束播放。选择另一条会替换当前语音，关闭菜单后语音继续播放。
- 喝饮料动作每轮实际开始后延迟 0.5 秒播放“闲聊·喝酒”，等待切换时不会提前播放，暂停时延迟也随动画暂停。自由切换按“站立 → 喝饮料 → 站立 → 读书”轮换，两段站立各约 30 秒，长于另外两个动作；每段站立进入后 8～12 秒随机播放一次“闲聊·小说”或“闲聊·出神”。手动单独站立仍每隔 45～90 秒闲聊。两种模式都避免连续重复，暂停、静音或手动点播时暂不触发。
- 语音面板底部可切换“语音开 / 语音关”，并用 − / + 每次调整 10% 音量。关闭语音或调至 0% 会立即停止播放，手动与自动语音均静音；重新打开后等待下次触发。音量只影响桌宠，调节当前语音即时生效，偏好会保存到本机设置。
- 语音按当前保留的文件生成。删除原始语音后，再次打开列表即可隐藏；运行 `python work/prepare_voices.py` 可同步 CSV、校验清单和播放缓存。下载素材与生成的语音缓存全部由 Git 忽略。
- 表情会随桌宠拖动、缩放和切换动作调整位置；透明贴图不拦截鼠标，靠近屏幕边缘时保持在可见范围内。在表情面板点击“清除”即可收起。
- 空格：暂停或继续。Esc：退出。

程序置顶，透明区域可以点击到下面的窗口。位置、大小与语音偏好保存在本机的 `pet-settings.json`。

右键 → **DeepSeek 助手** 可打开本机官方 DeepSeek Harness，进行 API 对话和文件/命令操作。CLI、配置及缓存默认安装在 D 盘，API Key 在官方网页的“设置 → 模型”中填写。默认只配置 `deepseek-flash`，保留操作审批。安装、模型限制和当前能力见 [DeepSeek 接入说明](docs/DEEPSEEK.md)。

EXE 和窗口图标使用用户提供的抱枕图片，内置 16、24、32、48、64、128、256 像素七档图标。原图在 `assets/app-icon-source.jpg`，运行 `python work/prepare_app_icon.py` 可重新生成 `assets/app.ico`。

## 当前素材

三组动画使用用户提供的两段 **2560 × 1440、原生 60 FPS** OBS 录屏重新提取。人物、整个抱枕、包边和动作道具保留原来的相对位置；使用相同取景和缩放，排除游戏界面与地面倒影。透明素材为 **840 × 720 的无损 WebP**，默认显示为 560 × 480，大号显示从高分辨率素材缩放。画布上方及两侧留出动作收尾时抬升和摆动的空间，读书动作中的独立小伙伴，以及入场、收尾时缩小或独立移动的抱枕也完整保留。

读书和喝饮料都保留录屏中的起始动作和回到站立的过程。三组动画的起止帧使用同一站姿，以短过渡衔接轻微的呼吸相位差。动作主体使用录屏原生帧，不再补帧；快速动作保留源录屏已有的运动模糊。

| 动作 | 播放帧数 | 单次时长 |
| --- | ---: | ---: |
| 站立 | 153 | 2.55 秒 |
| 读书 | 816 | 13.6 秒 |
| 喝饮料 | 945 | 15.75 秒 |
| 拖动互动 | 186 | 3.10 秒 |
| 晃动后跺脚 | 296 | 4.93 秒 |

拖动互动使用用户提供的 71 帧 GIF，保留原本的局部取景和人物画面，去掉房间背景。通过运动补偿补至 60 FPS，加入循环过渡，并柔化素材底部已有的裁切边缘。拖动时暂存当前主动作的播放位置，松手后平滑恢复；暂停主动画时仍可播放拖动互动。GIF 原件和处理缓存保留在本机。

跺脚使用提供的 MP4，去掉双手前伸的开头，保留原视频约 1.13～6.07 秒，包含完整的抬脚、落脚、转正、收手和站稳。用双向光流补至 60 FPS；两组固定 RGB 校色基准与背景亮度跟踪共同消除录屏由暗到亮的光照变化，并受限锐化、清理背景光效。站稳后才开始 0.24 秒退出渐变；最后站姿与实际待机素材的头顶、鞋底和体型对齐，渐变前保留超过一秒的完整站姿。透明轮廓参考先通过特征匹配对齐再辅助跟踪抠图，生成图的 RGB 不进入动画。保留 0.20 秒入场，首帧与恢复帧提前准备。画面亮度及站姿对比见 `work/stomping-tone-comparison.jpg`，处理记录及内置抠图工具的提示词见 `assets/stomping/source.json`。

站立、喝饮料、读书之间切换时，当前动作先自然结束并回到站立，再进入所选动作。因此，切换可能需要等待当前动作的剩余时间；右键菜单会显示待切换动作。连续选择以最后一次为准，重新选择正在播放的动作会取消待切换请求并继续播放。走动单独控制，打断后停止。暂停时保持当前帧，恢复后继续衔接。

新版走动使用 `10月23日.mp4`：原录屏 120 FPS，多数行走区间每秒约 56～60 个有效画面。按 60 FPS 直接选择单个原始画面，固定校色与缩放；不混合相邻 RGB、不生成光流中间帧、不叠化循环接缝。碰边直接切换左右行走，提前预读反向画面，移除转身停顿。进出走动只淡出/淡入一个姿势，避免两个人影重叠。透明轮廓通过既有参考及新增的背面参考辅助抠图，生成图的 RGB 不进入动画。素材参数、内置 imagegen 提示词及校验值见 `assets/walking/source.json`，源视频和轮廓参考保留在本机 `local-media/walking-video-20261023`。

跺脚末尾使用与当前站立素材一致的精确终点，取消运行时的第二次收尾叠化和提前推进的站立时钟。脚间黑块、靴子保留及四档尺寸的终点比对见 `work/stomp-handoff-validation.json`，实际 EXE 的完整收尾与接续帧率见 `work/stomp-package-validation.json`。

站立服装两侧的粉色飘带按每帧真实布料轮廓抠图，修复旧追踪轮廓偏移时把青色背景留在飘带内的问题。喝饮料、读书的站立起止画面同步修复，全部 1914 个主动作帧的区域外可见像素、透明度与时序均验证一致；颜色与实际播放检查见 `work/standing-ribbon-validation.json` 和 `work/standing-package-validation.json`。

素材记录在 `references/obs-source.json`，帧数、时长和编码信息在 `assets/manifest.json`。完整取景参考保存在 `references/requested-full-framing.png`。以前的处理脚本和小型预览保留供历史对照，大型素材留在本机。

站立的两只鞋分别按实际鞋底轮廓跟踪，去掉原录屏的地面倒影；两条飘带保留浅色连接处，并跟随原动画摆动。动作起始和收尾的公共站姿使用同样的处理，避免切换时倒影重新闪现。

## 构建与验证

运行代码统一放在 `src/citlali_pet`，根目录的 `main.py` 只负责启动；`app.py` 连接各个功能，`animation` 管理帧流、动作时钟和互动，`ui` 管理原生窗口表面、菜单和表情，`audio` 管理语音库、播放和调度。九个 PNG 保存在 `assets/expressions` 并内置到 EXE；缩略图按需解码，最多缓存 18 张小图。程序优先加载旁边的 `assets`，没有外部素材时使用 EXE 内的素材包。

```text
main.py                  源码与 EXE 的启动入口
pyproject.toml           Python 包及命令入口配置
src/citlali_pet/
  app.py                 主程序
  paths.py               素材、设置与打包资源定位
  animation/             动画与交互
  ui/                    菜单、表情及透明绘图
  audio/                 语音播放与调度
assets/                  素材及校验表
work/                    构建、素材处理与验证工具
docs/                    说明文档
```

安装 `requirements.txt` 的依赖、准备好源码素材后，用 `python main.py` 启动。开发时也可运行 `python -m pip install -e .`，然后使用 `python -m citlali_pet` 或 `citlali-pet`。从其他工作目录启动源码时，素材和设置仍定位到本项目；独立 EXE 继续使用程序旁的设置和内置素材。

[drag_motion.py](src/citlali_pet/animation/drag_motion.py) 管理拖动的独立时钟和 0.16 秒渐变，拖动帧包保存在 `assets/dragging` 并与主动作共用一套受限缓存。Release 源码素材包含处理好的拖动帧包，直接构建不需要额外依赖；从原 GIF 重新处理时运行 `work/build_drag_assets.py`，需要 NumPy、OpenCV 和本地的原 GIF、透明轮廓参考。素材来源及校验值见 `assets/dragging/source.json`，拖动行为和打包帧率分别由 `work/test_dragging.py`、`work/analyze_dragging.py` 验证。

[shake_motion.py](src/citlali_pet/animation/shake_motion.py) 识别拖动中的明显反向，管理停下后的单次跺脚与站立恢复。帧包在 `assets/stomping`，专属表情在 `assets/easter-eggs`；两者内置到 EXE，跺脚和主动作、拖动动画共用受限帧缓存。`work/build_stomp_assets.py --extract` 用本地 MP4 和六个轮廓参考准备素材，需要 NumPy、OpenCV 和 ffmpeg。`work/test_shaking.py` 覆盖误触、松手/停下、站立恢复、暂停、缩放、重新拖动和冷却；`work/verify_packaged_stomping.py` 验证实际 EXE 内的素材、单次播放、完整收势后再渐变和站立恢复。

[voices.py](src/citlali_pet/audio/voices.py) 管理后台播放和语音面板，[voice_output.py](src/citlali_pet/audio/voice_output.py) 通过 WinMM 的独立播放句柄调节音量，[voice_actions.py](src/citlali_pet/audio/voice_actions.py) 在实际动画循环边界配对语音并安排站立闲聊；[voice_library.py](src/citlali_pet/audio/voice_library.py) 管理可用语音。内存中仅保留正在播放的一条 PCM WAV，结束或停止后释放。构建时仅内置仍保留的语音；如需从自己的 OGG 生成播放文件，需要 ffmpeg，`work/prepare_voices.py` 会保留原采样率，不重新下载已删除的文件。Release 源码素材包包含已准备好的 `assets/voices`，从该素材包构建不需要再次转换。缺少语音素材时，其他桌宠功能仍可使用。

所有语音共用自然收尾逻辑：原始 PCM 后附加 0.25 秒静音，等待设备完成整个缓冲区后直接释放，避免末尾发音被强制重置打断。手动停止、切换语音和静音仍可立即中断；原录音与磁盘上的 WAV 不做裁剪或改写。`work/test_voice_tail.py` 检查全部保留文件的 PCM 完整性、自然结束不重置，以及长短语音和动作语音的实际设备播放进度。

本次仅补回跺脚需要的五条中文语音，当前本地保留 34 条；其余已删除录音继续排除。`work/restore_stomp_voices.py` 按原始索引与 SHA256 明确恢复这五条，下载与播放缓存仍由 Git 忽略。`work/test_stomp_voices.py` 验证文件、随机选择及播放优先级；`work/test_frame_stream.py` 检查异步预读、缓存失效与内存上限。普通运行和构建不会自动下载语音。

播放器按需读取 `pet-frames.bin`，后台预读接下来 8 帧，显示帧缓存不超过 12 帧或 24 MiB。新版帧包保存主动作、拖动、跺脚、左右走动，仅保存 840 × 720 原生像素。主动作和拖动用无损 WebP 编码相邻帧差异，每 8 帧重新设置完整帧，随机读取最多追溯 7 帧；跺脚、走动及待机开头 24 帧采用每帧独立的无损 WebP，避免收尾与恢复待机同时读取时反复重建差分帧。原生帧缓存仍限于 12 帧或 16 MiB。所有显示尺寸使用相同的 Lanczos 缩放与预乘透明处理，命中检测复用当前帧的 alpha。

原始 WebP 与拖动、跺脚源帧包保留用于开发和素材检查；EXE 只包含合并后的紧凑帧包，避免重复存储默认尺寸和互动素材。菜单图像仍在后台绘制。运行时直接注册 WebP 解码器，并排除不用的 AVIF 库，避免首次播放加载无关格式。

播放器只缩放人物有效区域及 Lanczos 滤波需要的透明边缘，按原画布的有理数比例对齐采样，输出与完整画布缩放逐像素一致；原生尺寸直接使用原图块。[pixel_surface.py](src/citlali_pet/ui/pixel_surface.py) 将图块直接复制到映射的位图缓冲区，减少 Python 逐行绘图开销。帧率、素材及原有显示、原生解码缓存限制保持不变；另用最多 8 MiB 压缩缓存复用一部分待机帧，达到上限后停止加入，缩放时释放。其他动作继续按需读取。

`work/test_resizing.py` 检查透明边缘、画布边界及不同缩放比例，`work/test_pixel_surface.py` 对比新旧绘图缓冲区，`work/test_loop_cache.py` 检查待机复用、字节上限和缩放时的旧任务失效。CPU 实测使用 `work/benchmark_cpu.py` 分别运行旧、新 EXE 的同尺寸、同位置三动作周期，同时记录帧率和内存；结果在 `work/cpu-before.json` 与 `work/cpu-after.json`。测量时关闭其他桌宠实例，避免重叠的透明窗口影响结果。`work/verify_app_icon.py` 验证图标原图、全部尺寸与 EXE 的 Windows 图标资源。

本机 18 个逻辑处理器、1.3 倍尺寸的新版 EXE 实测：站立 CPU 约 3.7%，喝饮料约 5.7%，读书约 4.8%，三种动作均约 60 FPS；该轮程序工作集峰值约 76 MiB。占用会随系统负载与尺寸变化，完整测量数据保留了旧、新版本的帧率和内存。

帧包内置在可独立运行的 EXE 中，不在旁边重复保存。源码运行时会读取 `work/repaired-assets` 中生成的帧包；如需外部覆盖，也可把完整的帧包索引和数据放入 `assets`。

紧凑帧包的原生像素、默认尺寸、透明度和时序通过全部素材对比，并检查其他四种尺寸及随机跳帧；本次共 2556 帧。完整素材比对见 `work/compact-quality-validation.json`，跺脚实机播放见 `work/stomp-package-validation.json`，校色对比见 `work/stomp-colour-validation.json`，自由切换语音与时长见 `work/automatic-rotation-validation.json`。前一版主动作播放与内存测量见 `work/compact-runtime-validation.json`，菜单连续开关后的 GDI 检查见 `work/menu-validation.json`。

1. Windows x64 使用 Python 3.12，运行 `python -m pip install -r requirements-build.txt`。把 Release 源码素材包解压到根目录，再运行 `python work/prepare_assets.py`。也可用 `work/extract_obs.py` 从上述本地 OBS 文件重新提取素材，额外需要 NumPy、OpenCV 和 ffmpeg。
2. 运行 `work/validate_assets.py` 检查所有帧的轮廓边距、完整性、时长和公共站姿接缝。
   运行 `work/validate_standing_edges.py` 检查脚底倒影、鞋底边界稳定性和飘带连接处。
3. 运行 `work/test_playback.py` 检查动作中途切换、连续选择和自动轮换。
4. `work/prepare_assets.py` 自动调用 `work/build_compact_pack.py` 生成或复用紧凑无损帧包，无需再运行旧的 `work/build_frame_pack.py`。运行 `work/validate_compact_pack.py` 对照全部原素材，`work/validate_stream.py` 额外对照主动作 WebP。构建缓存匹配素材校验值时会直接复用。
5. 通过 `work/CitlaliDesktopPet.spec` 打包 EXE，再使用 `--qa-seconds 45` 实际验证三种动作的播放（自动 QA 不播放语音）。`work/test_pink_menu.py` 检查菜单交互和 GDI 资源释放，`work/test_expressions.py` 检查表情，`work/test_voices.py` 检查已删除语音过滤、后台播放、停止、音量、偏好保存及原生菜单交互，`work/test_voice_actions.py` 检查动作语音触发、随机间隔、暂停和手动点播优先级。

EXE、动画 WebP、播放帧包、MP4、构建缓存、日志、设置和本地备份由 `.gitignore` 排除。`work/prepare_release.py` 可以生成本地 Release 附件；`work/check_publish_repo.py` 检查所有可推送历史中的大文件。完成修改并验证后创建本地 Git 提交。角色与录屏内容属于原权利人，本程序用于个人桌面体验。
