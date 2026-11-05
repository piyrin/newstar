"""Small DeepSeek HTTP adapter with bounded requests and redacted errors."""
import json
import os
import time
import urllib.error
import urllib.request


class DeepSeekClient:
    def __init__(self, retries=2, backoff=2):
        self.key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not self.key:
            raise ValueError('未配置 DEEPSEEK_API_KEY；离线样例请显式选择 offline')
        self.model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')
        self.retries, self.backoff = retries, backoff

    def complete(self, system: str, payload: dict) -> dict:
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 70000:
            raise ValueError('模型单次输入超过 70000 字符，请拆分材料')
        body = json.dumps({'model': self.model,
                           'messages': [{'role': 'system', 'content': system},
                                        {'role': 'user', 'content': encoded}],
                           'response_format': {'type': 'json_object'},
                           'thinking': {'type': 'disabled'}, 'max_tokens': 6000,
                           'stream': False}, ensure_ascii=False).encode('utf-8')
        for attempt in range(self.retries + 1):
            request = urllib.request.Request('https://api.deepseek.com/chat/completions', body,
                         {'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('模型响应超过大小限制')
                answer = json.loads(raw)['choices'][0]
                content = answer['message']['content']
                if answer.get('finish_reason') != 'stop' or not content.strip():
                    raise ValueError('模型返回空白或未完成的 JSON')
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError('模型必须返回 JSON 对象')
                return value
            except urllib.error.HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504):
                    raise ValueError(f'DeepSeek HTTP {error.code}，请检查账户和配置') from None
                reason = f'DeepSeek 临时 HTTP {error.code}'
            except (urllib.error.URLError, TimeoutError, OSError):
                reason = 'DeepSeek 网络连接失败或超时'
            except (ValueError, KeyError, IndexError, TypeError):
                reason = 'DeepSeek 返回空白、截断或无效 JSON'
            if attempt < self.retries:
                time.sleep(self.backoff * (attempt + 1))
        raise ValueError(reason + '；有限重试已耗尽')
