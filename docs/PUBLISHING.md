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
   - `CitlaliDesktopPet-source-assets.zip`：开发者重新构建所需的三组原始无损动画。
   - `SHA256SUMS.txt`：上述两个附件的校验值。
6. 把 `release/RELEASE_NOTES.md` 的内容复制到发布说明中，核对后自行发布。

`release` 整个目录已经忽略，不会随代码推送。MP4、设置、日志和备份也保持本地。用 Git 或 GitHub Desktop 推送源码；网页选择 Release 附件时只需选择上面三个文件。

## 以后重新打包

在 Windows x64、Python 3.12 环境中：

```powershell
python -m pip install -r requirements-build.txt
python work/prepare_assets.py
python work/build_frame_pack.py
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

## 本地历史备份

首次整理前的完整 Git 历史保存在 `backups/github-history-before-cleanup-*.bundle`。本机 EXE 和所有动画仍保留原位置。旧对象与恢复记录也可能仍占用本机 `.git` 空间；正常推送只传输分支可达的整理后历史。

需要查阅原历史时，可以用 `git bundle verify` 检查对应备份，再用 `git clone <备份文件路径> <另一个空目录>` 恢复到独立目录。此次本地整理会改变旧提交的哈希；代码内容和提交说明保留。
