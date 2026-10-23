# DeepSeek 助手

桌宠右键菜单的 **DeepSeek 助手** 打开官方 DeepSeek Harness（`dsh`）本地网页。也可运行程序旁的 `CitlaliDesktopPet.exe --deepseek`，单独打开助手。对话目前显示在官方网页中。

## 本机安装

本机已安装官方 npm 包 `@deepseek-ai/dsh@0.2.1-rc.2`，需要 Node.js 22.19+ 或 24+。默认目录为 `D:\AI\DeepSeek`：

| 目录 | 内容 |
| --- | --- |
| `cli` | 官方 CLI 和依赖 |
| `data` | 配置、密钥和会话 |
| `cache`、`tmp` | npm/pnpm 缓存与临时文件 |
| `workspace/files` | 文件操作目录 |
| `workspace/.runtime-temp` | 与文件操作目录分开的沙箱临时目录 |
| `logs` | 本地服务日志，包含本机访问令牌，不要分享 |
| `bin` | 带 D 盘环境配置的 `dsh.cmd` |

源码安装：在项目根目录运行 `powershell -ExecutionPolicy Bypass -File work/install_deepseek.ps1`。支持 `-InstallRoot D:\其他目录\DeepSeek`；安装脚本不覆盖已有配置。自定义目录通过用户环境变量 `CITLALI_DEEPSEEK_ROOT` 告知桌宠；修改后重启桌宠。

安装器只给此 CLI 配置 D 盘缓存，不改变其他软件的 npm 全局设置。Windows、现有浏览器和系统组件仍可能使用自身目录。

## 配置 Key 与使用

1. 打开桌宠右键菜单 → **DeepSeek 助手**。
2. 官方网页 **设置 → 模型**，在 DeepSeek 卡片填入自己的 API Key 并保存。无需发到聊天或写入源码。
3. 添加工作区，先选 `D:\AI\DeepSeek\workspace\files`，创建会话。不要选择它的父目录，以免与沙箱临时目录重叠。
4. 可以日常聊天，也可以要求打开程序、查找文件、执行命令。文件与命令操作走 Harness 的工具和权限流程。

当前模型菜单只配置 `deepseek-flash`，关闭思考，单次默认输出量 4096 tokens，声明上下文 65536 tokens。模型目录、输出及默认值保存在 `data/cordis.patch.yml`。这是可编辑的本机默认配置，不是强制模型白名单、服务端账号限制或硬性费用预算；调用其他模型和覆盖请求参数仍需额外的网关校验才能硬性禁止。API 按实际用量计费。

默认权限为 `workspace-write`，需要审批的操作在官方网页中确认。权限边界以 Harness 的实现为准，不能视为完整系统隔离。启动入口只监听 `127.0.0.1:3080`，重复点击复用本地服务；退出桌宠后服务继续运行。需要停止时，可按 `data/pet-service.json` 中记录的 PID 停止对应 Node 进程。服务不自动开机启动。

本次接入包含文本对话和文件/命令工具。鼠标点击、屏幕识别、跨应用界面操作尚未接入；这些需要另配桌面操作工具。未填 Key 前只验证安装和启动，不代表已验证真实 API 推理。

本机安装已实际通过 API 对话与 `Write-Output DESKTOP_PET_TOOL_OK` 工具调用，后者保持“工作区内修改”模式，未提权。Windows 沙箱要求新建临时子目录继承当前用户的完整控制权限；本机使用 `workspace/.runtime-temp` 与 `workspace/files` 两个独立目录解决该问题。只修复父目录本身的权限不一定能解决子目录继承问题。官方诊断脚本的备份、验证报告及按顺序排列的恢复命令保存在 `D:\AI\DeepSeek\recovery\20261023-tmp\README.md`。

## 来源

- [DeepSeek 官方仓库](https://github.com/deepseek-ai/deepseek-harness)
- [官方 Web UI 使用指南](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/index.zh.md)
- [官方模型配置说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.zh.md)
- [DeepSeek API 模型说明](https://api-docs.deepseek.com/quick_start/pricing/)

官方 Harness 仍处于开发预览期。本项目把它作为本机独立依赖，不把 CLI、密钥、会话或日志打进桌宠 EXE 或 Git。
