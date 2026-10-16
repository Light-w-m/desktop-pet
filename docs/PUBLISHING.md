# GitHub 发布

Git 仓库保存源码、构建脚本、校验值和小型预览；EXE、动画 WebP、播放帧包和 MP4 保留本机，作为需要的 Release 附件分发。

GitHub 普通 Git 仓库阻止超过 100 MiB 的单文件；Release 每个附件需要小于 2 GiB。本项目的两个发布文件都在 Release 限制内。参见 [大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) 和 [Release 附件限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)。本项目无需 Git LFS。

## 这次发布

1. 在项目目录运行 `python work/check_publish_repo.py`，确认 `ready` 为 `true`。
2. 确认 GitHub 上的 `Light-w-m/desktop-pet` 仓库已经创建，并且当前 Git 账号有写入权限。可用 `git remote -v` 检查地址。
3. 自行执行 `git push -u origin main`。也可在 GitHub Desktop 中推送当前仓库。
4. 在 GitHub 仓库的 **Releases → Draft a new release** 中，自行选择版本标签和标题。
5. 从本机 `release` 目录选择以下三个附件：
   - `CitlaliDesktopPet.exe`：普通用户下载的独立程序。
   - `CitlaliDesktopPet-source-assets.zip`：开发者重新构建所需的主动作、拖动帧包和语音素材。
   - `SHA256SUMS.txt`：上述两个附件的校验值。
6. 把 `release/RELEASE_NOTES.md` 的内容复制到发布说明中，核对后自行发布。

`release` 整个目录已经忽略，不会随代码推送。MP4、设置、日志和备份也保持本地。用 Git 或 GitHub Desktop 推送源码；网页选择 Release 附件时只需选择上面三个文件。

## 以后重新打包

在 Windows x64、Python 3.12 环境中：

```powershell
python -m pip install -r requirements-build.txt
python work/prepare_assets.py
python work/validate_compact_pack.py
python work/validate_stream.py
python -m PyInstaller --noconfirm --distpath work/dist --workpath work/pyinstaller-build work/CitlaliDesktopPet.spec
```

构建结果位于 `work/dist/CitlaliDesktopPet.exe`。按 README 完成动画、菜单与实际启动验证后，可重新生成发布附件：

```powershell
python work/prepare_release.py --exe work/dist/CitlaliDesktopPet.exe
python work/check_publish_repo.py
```

发布脚本只生成本地文件，不推送代码、不创建 GitHub Release、不上传附件。它会生成源码素材校验表 `assets/source-checksums.json`，并检查复制后的 EXE 和素材 ZIP 的 SHA-256。更新素材后，将新的校验表一起提交。

## 源码素材

新克隆的仓库没有动画文件。下载同一版本 Release 中的 `CitlaliDesktopPet-source-assets.zip`，解压到项目根目录，得到 `assets/standing-obs.webp`、`assets/reading-obs.webp` 和 `assets/drinking-obs.webp`。运行 `python work/prepare_assets.py` 会检查 SHA-256，并准备本机的构建目录。

v1.2.0 还包含 `assets/dragging/pet-frames.json` 和 `pet-frames.bin`，提供已处理好的透明拖动动画。`assets/dragging/source.json` 随源码保存处理说明和校验值；`work/prepare_assets.py` 同时检查拖动帧包。使用准备好的素材包构建不需要重新抠图或补帧，拖动动画与主动作共用受限帧缓存。

带语音的版本还会在源码素材包中提供 `assets/voices/catalog.json` 和 PCM WAV；这些文件同样保持 Git 忽略。使用本地原始语音时，先按需要删除 `local-media/citlali-voices-zh-cn` 中的 OGG，再运行 `python work/prepare_voices.py` 同步索引并转换保留的文件，转换需要 ffmpeg。EXE 只内置当前保留的语音，运行时使用 Windows 原生接口，无需 ffmpeg。

## 本地历史备份

本次按用户选择，只保留最近一版的独立 EXE、Git bundle 和设置快照，放在 `backups/before-compact-*`。更早的备份已移入 Windows 回收站，可从回收站恢复；原始动画与语音素材仍保留。旧的不可达 Git 对象在保留备份后清理，分支和已有提交不改写。

需要查阅备份时，可以用 `git bundle verify` 检查对应 bundle，再用 `git clone <备份文件路径> <另一个空目录>` 恢复到独立目录。需要更早的历史时，先从回收站恢复当时的 bundle。

`work/compact_cleanup.ps1` 默认只预览可重建缓存的清理计划。显式使用 `-Apply` 执行；清理旧备份还需要 `-RecycleOlderBackups -KeepBackup backups/<要保留的快照目录>`。它检查目标留在项目目录内，不遍历目录链接；原始素材不在清理列表中。
