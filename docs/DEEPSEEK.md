# 桌宠文字聊天

右键人物 → **和她聊天**，或人物获得焦点后按 **Enter**，在人物右侧打开独立对话框。在输入框打字后按 Enter 或点击“发送”；Shift+Enter 换行，Esc 或右上角 × 收起对话框。屏幕右侧空间不足时自动切到左侧，保持面板可见并避开人物。拖动人物、缩放或切换动作时，面板跟随；请求在后台完成，动画继续播放。

## 仅文字问答

桌宠直接调用 DeepSeek 官方 HTTPS 文字对话接口，不启动或连接 CLI、浏览器、本地智能体服务。模型固定为 `deepseek-flash`，关闭思考，每条输入最多 2000 字，每次输出最多 1024 tokens。

请求固定传入空工具列表和 `tool_choice: none`。运行路径没有命令执行器、文件操作工具、浏览器工具、鼠标键盘控制工具、插件或 MCP。即使服务意外返回工具调用或旧式 function call，客户端也会拒绝该回答，不执行操作。回答显示在原生只读文本框中，代码和链接也是普通文字，不会运行或打开。

只把用户主动输入的消息、最近最多 8 组文字问答和固定聊天提示词发给 API。不会发送文件、截图、目录内容、运行程序列表或电脑信息。消息仅保存在内存，“清空”删除当前对话，退出桌宠后不保留；关闭并重新打开面板可以继续当前会话。API 仍按实际 token 用量计费。

## API Key

点击面板右上角 **设置**，输入 DeepSeek API Key 并保存。已保存的密钥不会回填到输入框；留空保存会继续使用原密钥。无 Key、Key 无效、余额不足或网络超时会在界面中提示。

设置默认保存在 `D:\AI\DeepSeek\data\pet-chat.json`，使用 Windows DPAPI 加密，绑定当前 Windows 账号。密钥不写入源码、EXE、聊天内容或日志。也支持启动环境中的 `DEEPSEEK_API_KEY`，优先使用加密设置。已有的本机 DeepSeek Key 已迁移到这个独立的聊天配置。

本机的旧 Harness 服务已停止，桌宠不再启动或连接它。旧的 `--deepseek` 启动参数也只打开原生文字聊天面板。独立聊天入口是 `CitlaliDesktopPet.exe --chat`，`D:\AI\DeepSeek\Open Chat.cmd` 和原有的 `Open DeepSeek.cmd` 均指向该入口。再次打开入口会唤起当前桌宠的面板，不会再启动一只桌宠。

如需在其他位置保存设置，可以在启动前设置 `CITLALI_DEEPSEEK_ROOT`。源码准备脚本为 `python work/prepare_chat.py`；它只创建本机配置目录和快捷启动文件，不安装 CLI 或智能体。

## 验证

- `work/test_deepseek.py`：空工具请求、固定模型及输出上限、输入和上下文限制、工具调用拦截、纯文本响应、密钥加密与注入字符拦截。
- `work/test_chat_ui.py`：原生输入与回答、异步请求时动画继续、跟随人物、清空、关闭后重开、密钥输入框不暴露已保存的 Key。
- `work/verify_text_chat.py`：真实 API 问答和操作请求的文字拒绝、原生面板截图及验证记录。
- `work/verify_packaged_chat.py`：在实际 EXE 中输入问题，验证原生窗口、加密密钥读取及真实 API 回答。

[DeepSeek Chat Completion 参数说明](https://api-docs.deepseek.com/api/create-chat-completion/) 中的 `tool_choice: none` 表示模型不调用工具。客户端同时没有任何接收并执行模型动作的代码路径。
