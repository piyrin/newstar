"""Read selected local dotenv values without executing or expanding their contents."""
import os
from pathlib import Path

KEYS = {'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'AIRFLOW_API_URL', 'AIRFLOW_API_USERNAME',
        'AIRFLOW_API_PASSWORD', 'AIRFLOW_API_TOKEN'}
ALIASES = {'_AIRFLOW_WWW_USER_USERNAME': 'AIRFLOW_API_USERNAME',
           '_AIRFLOW_WWW_USER_PASSWORD': 'AIRFLOW_API_PASSWORD'}


def load_env(path: Path):
    if not path.is_file():
        return
    direct, aliases = {}, {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        mapped = ALIASES.get(key, key)
        if mapped not in KEYS:
            continue
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('本机 .env 配置引号未闭合')
            value = value[1:-1]
        else:
            value = value.split(' #', 1)[0].rstrip()
        (aliases if key in ALIASES else direct)[mapped] = value
    for key, value in {**aliases, **direct}.items():
        os.environ.setdefault(key, value)
