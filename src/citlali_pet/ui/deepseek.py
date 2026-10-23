"""Text-only DeepSeek client: fixed HTTPS endpoint, no agent or tool executor."""
import base64
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path

MODEL = 'deepseek-flash'
MAX_INPUT = 2000
MAX_OUTPUT_TOKENS = 1024
MAX_HISTORY_CHARS = 10000
MAX_RESPONSE_BYTES = 1024 * 1024
SYSTEM_PROMPT = (
    '你是陪伴用户的茜特菈莉桌宠，用自然、温和、简短的中文聊天并回答简单问题。'
    '你只能进行文字问答，没有电脑操作能力，不能访问或修改文件、执行命令、'
    '运行程序、浏览网页或控制鼠标键盘。用户要求操作电脑时，说明无法执行，'
    '不要声称已经完成操作。只根据用户主动输入的对话作答。')


class ChatError(Exception):
    """An error safe to show without request bodies, headers or credentials."""


def installation_root():
    return Path(os.environ.get('CITLALI_DEEPSEEK_ROOT', r'D:\AI\DeepSeek')).resolve()


def settings_path():
    return installation_root()/'data/pet-chat.json'


class DATA_BLOB(C.Structure):
    _fields_ = [('size', W.DWORD), ('data', C.POINTER(C.c_ubyte))]


def _dpapi(value, decrypt=False):
    """Bind stored credentials to the current Windows account, without a dialog."""
    crypt = C.WinDLL('crypt32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    call = getattr(crypt, 'CryptUnprotectData' if decrypt else 'CryptProtectData')
    call.argtypes = [C.POINTER(DATA_BLOB), C.c_void_p, C.c_void_p, C.c_void_p,
                     C.c_void_p, W.DWORD, C.POINTER(DATA_BLOB)]
    call.restype = W.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [C.c_void_p], C.c_void_p
    buffer = (C.c_ubyte * len(value)).from_buffer_copy(value)
    source, output = DATA_BLOB(len(value), buffer), DATA_BLOB()
    if not call(C.byref(source), None, None, None, None, 1, C.byref(output)):
        raise ChatError('无法读取或保存 API Key，请在设置中重新填写。')
    try:
        return C.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def validate_key(value):
    value = value.strip()
    if not 12 <= len(value) <= 256 or not all(c.isascii() and (c.isalnum() or c in '-_.') for c in value):
        raise ChatError('API Key 格式不正确，请检查后重试。')
    return value


def save_api_key(value, path=None):
    value = validate_key(value)
    path = path or settings_path()
    encrypted = base64.b64encode(_dpapi(value.encode('utf-8'))).decode('ascii')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'version': 1, 'api_key_dpapi': encrypted}), encoding='utf-8')
    temporary.replace(path)


def load_api_key(path=None):
    path = path or settings_path()
    if path.is_file():
        try:
            record = json.loads(path.read_text(encoding='utf-8-sig'))
            encrypted = base64.b64decode(record['api_key_dpapi'], validate=True)
            return validate_key(_dpapi(encrypted, decrypt=True).decode('utf-8'))
        except (OSError, ValueError, KeyError, TypeError):
            raise ChatError('本机 API Key 无法读取，请在聊天设置中重新保存。') from None
    value = os.environ.get('DEEPSEEK_API_KEY', '')
    if value:
        return validate_key(value)
    raise ChatError('请先点“设置”，填写 DeepSeek API Key。')


def build_request(question, history=()):
    question = question.strip()
    if not question:
        raise ChatError('先输入想说的话吧。')
    if len(question) > MAX_INPUT:
        raise ChatError(f'每条消息最多 {MAX_INPUT} 个字，请缩短后再发送。')
    # Rebuild text-only history. Caller-controlled fields cannot become tools,
    # function calls, attachments or actions. Keep whole user/assistant pairs.
    pairs, size = [], len(question)
    for user_text, reply in reversed(list(history)[-8:]):
        if not isinstance(user_text, str) or not isinstance(reply, str):
            continue
        if size + len(user_text) + len(reply) > MAX_HISTORY_CHARS:
            break
        pairs.append((user_text, reply))
        size += len(user_text) + len(reply)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for user_text, reply in reversed(pairs):
        messages.extend([{'role': 'user', 'content': user_text}, {'role': 'assistant', 'content': reply}])
    messages.append({'role': 'user', 'content': question})
    return {'model': MODEL, 'messages': messages, 'max_tokens': MAX_OUTPUT_TOKENS,
            'thinking': {'type': 'disabled'}, 'stream': False,
            'tools': [], 'tool_choice': 'none'}


def parse_response(body):
    try:
        choice = json.loads(body)['choices'][0]
        message = choice['message']
        if message.get('tool_calls') or message.get('function_call') or choice.get('finish_reason') in ('tool_calls', 'function_call'):
            raise ChatError('收到不支持的操作请求，已拦截。这里只能文字聊天。')
        content = message['content']
        if not isinstance(content, str) or not content.strip():
            raise ChatError('这次没有收到文字回答，请稍后重试。')
        return content.strip()[:8000] + ('\n（本次回答已达到长度上限。）' if choice.get('finish_reason') == 'length' else '')
    except (ValueError, KeyError, IndexError, TypeError):
        raise ChatError('服务返回的回答格式不正确，请稍后重试。') from None


def post_chat(payload, key):
    """Use Windows TLS/certificate verification; never follow redirects with a key."""
    api = C.WinDLL('winhttp', use_last_error=True)

    def function(name, result, *arguments):
        call = getattr(api, name)
        call.restype, call.argtypes = result, arguments
        return call

    handle, ptr = W.HANDLE, C.c_void_p
    open_session = function('WinHttpOpen', handle, W.LPCWSTR, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD)
    connect = function('WinHttpConnect', handle, handle, W.LPCWSTR, W.WORD, W.DWORD)
    open_request = function('WinHttpOpenRequest', handle, handle, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, ptr, W.DWORD)
    set_option = function('WinHttpSetOption', W.BOOL, handle, W.DWORD, ptr, W.DWORD)
    timeouts = function('WinHttpSetTimeouts', W.BOOL, handle, C.c_int, C.c_int, C.c_int, C.c_int)
    send = function('WinHttpSendRequest', W.BOOL, handle, W.LPCWSTR, W.DWORD, ptr, W.DWORD, W.DWORD, C.c_size_t)
    receive = function('WinHttpReceiveResponse', W.BOOL, handle, ptr)
    headers = function('WinHttpQueryHeaders', W.BOOL, handle, W.DWORD, W.LPCWSTR, ptr, C.POINTER(W.DWORD), ptr)
    available = function('WinHttpQueryDataAvailable', W.BOOL, handle, C.POINTER(W.DWORD))
    read = function('WinHttpReadData', W.BOOL, handle, ptr, W.DWORD, C.POINTER(W.DWORD))
    close = function('WinHttpCloseHandle', W.BOOL, handle)
    handles = []

    def check(value):
        if not value:
            code = C.get_last_error()
            raise ChatError('连接超时，请稍后重试。' if code == 12002 else f'暂时无法连接 DeepSeek（网络错误 {code}）。')
        return value

    try:
        session = check(open_session('CitlaliPetChat/1.0', 4, None, None, 0))
        handles.append(session)
        check(timeouts(session, 5000, 10000, 10000, 30000))
        connection = check(connect(session, 'api.deepseek.com', 443, 0))
        handles.append(connection)
        request = check(open_request(connection, 'POST', '/chat/completions', None, None, None, 0x00800000))
        handles.append(request)
        disabled = W.DWORD(1 | 2 | 4)  # cookies, redirects, automatic Windows authentication
        check(set_option(request, 63, C.byref(disabled), C.sizeof(disabled)))
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        buffer = C.create_string_buffer(body)
        header = 'Content-Type: application/json\r\nAuthorization: Bearer ' + validate_key(key) + '\r\n'
        check(send(request, header, len(header), buffer, len(body), len(body), 0))
        check(receive(request, None))
        status, size = W.DWORD(), W.DWORD(C.sizeof(W.DWORD))
        check(headers(request, 19 | 0x20000000, None, C.byref(status), C.byref(size), None))
        if status.value != 200:
            errors = {401: 'API Key 无效或已过期，请在设置中更新。', 402: 'DeepSeek 账户余额不足。',
                      429: '请求太频繁，请稍等一会儿再发送。'}
            raise ChatError(errors.get(status.value, f'DeepSeek 暂时无法回答（HTTP {status.value}），请稍后重试。'))
        chunks, total = [], 0
        while True:
            count = W.DWORD()
            check(available(request, C.byref(count)))
            if not count.value:
                break
            if total + count.value > MAX_RESPONSE_BYTES:
                raise ChatError('回答数据过大，本次接收已停止。')
            buffer = C.create_string_buffer(count.value)
            received = W.DWORD()
            check(read(request, buffer, count.value, C.byref(received)))
            if not received.value:
                break
            chunks.append(buffer.raw[:received.value])
            total += received.value
        return b''.join(chunks)
    finally:
        for item in reversed(handles):
            close(item)


def ask(question, history=()):
    return parse_response(post_chat(build_request(question, history), load_api_key()))
