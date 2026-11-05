"""Portable local entry point; run with the documented Python environment."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dags'))
from resume_flow.cli import main
from resume_flow.config import load_env

if __name__ == '__main__':
    try:
        load_env(Path(__file__).resolve().parents[1] / '.env')
        # Defaults match this repository's official Compose initializer.
        os.environ.setdefault('AIRFLOW_API_USERNAME', 'airflow')
        os.environ.setdefault('AIRFLOW_API_PASSWORD', 'airflow')
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(str(error)) from None
