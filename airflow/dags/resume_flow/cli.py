"""Run with python -m resume_flow.cli (the launcher sets PYTHONPATH)."""
import argparse
import json
import os
from pathlib import Path

from .storage import read_json, run_dir, inside


def main(argv=None):
    parser = argparse.ArgumentParser(description='从材料制作简历；offline 仅用于内置虚构样例')
    parser.add_argument('--workspace', type=Path,
                        default=Path(os.environ.get('RESUME_WORKSPACE', Path(__file__).resolve().parents[2] / 'resume_workspace')))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('sample', help='初始化虚构材料，不覆盖已有文件')
    prepare = commands.add_parser('prepare', help='本机执行材料整理；生产运行建议使用 DAG')
    prepare.add_argument('--case-id', required=True)
    prepare.add_argument('--run-key', required=True)
    prepare.add_argument('--target', default='')
    prepare.add_argument('--jd-file', type=Path)
    prepare.add_argument('--mode', choices=['deepseek', 'offline'], default='deepseek')
    for name in ('review', 'approve', 'export', 'status'):
        command = commands.add_parser(name)
        command.add_argument('--run-key', required=True)
        if name == 'review':
            command.add_argument('--port', type=int, default=0)
        if name == 'approve':
            command.add_argument('--confirm', action='store_true', required=True)
        if name == 'export':
            command.add_argument('--export-key', required=True)
    accept = commands.add_parser('accept')
    accept.add_argument('--export-key', required=True)
    accept.add_argument('--confirm-all-pages', action='store_true', required=True)
    ask = commands.add_parser('ask', help='自然语言选择并触发已有 Airflow 工作流')
    ask.add_argument('text')
    ask.add_argument('--request-id', help='相同请求重试时复用，防止重复提交')
    ask.add_argument('--dry-run', action='store_true', help='调用模型解析，但不请求 Airflow')
    chat = commands.add_parser('chat', help='交互式自然语言入口，输入 exit 结束')
    chat.add_argument('--dry-run', action='store_true')
    status = commands.add_parser('airflow-status', help='直接查询 Airflow 运行与任务状态，不调用模型')
    status.add_argument('--dag-id', required=True, choices=['resume_prepare', 'resume_export'])
    status.add_argument('--dag-run-id', required=True)
    args = parser.parse_args(argv)
    ws = args.workspace
    if args.command in ('ask', 'chat', 'airflow-status'):
        from .natural import parse_request, execute_request, workflow_status
        if args.command == 'airflow-status':
            from .airflow_api import AirflowClient
            print(json.dumps(workflow_status(ws, AirflowClient(), args.dag_id, args.dag_run_id), ensure_ascii=False, indent=2))
        elif args.command == 'ask':
            result = execute_request(ws, parse_request(ws, args.text), args.request_id, args.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            history = []
            print('输入需求；exit 结束。请求与案例标识发送给 DeepSeek，不发送材料正文。')
            while True:
                try:
                    request = input('你> ').strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if request.lower() in ('exit', 'quit'):
                    break
                if not request:
                    continue
                try:
                    plan = parse_request(ws, request, history=history)
                    result = execute_request(ws, plan, dry_run=args.dry_run)
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    history.extend([{'user': request}, {'result': result}])
                    history = history[-6:]
                except (ValueError, OSError) as error:
                    print('错误：' + str(error))
        return
    if args.command == 'sample':
        from .sample import SAMPLE_TEXT
        source = inside(ws, 'inputs', 'demo', 'profile.md')
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists() and source.read_text(encoding='utf-8') != SAMPLE_TEXT:
            raise ValueError('样例路径已有不同内容，拒绝覆盖')
        source.write_text(SAMPLE_TEXT, encoding='utf-8')
        print(json.dumps({'synthetic': True, 'input': str(source)}, ensure_ascii=False))
    elif args.command == 'prepare':
        from .incremental import prepare_version, finish_version
        from .extract import extract_run
        from .workflow import collect_facts, draft_resume
        from .review import prepare_review
        jd = args.jd_file.read_text(encoding='utf-8-sig') if args.jd_file else ''
        version = prepare_version(ws, args.case_id, args.run_key, args.target, jd, args.mode)
        if version['skip']:
            print(json.dumps(version, ensure_ascii=False))
            return
        extract_run(ws, args.run_key)
        collect_facts(ws, args.run_key, args.mode)
        draft_resume(ws, args.run_key, args.mode)
        prepare_review(ws, args.run_key)
        finish_version(ws, args.run_key)
        print(json.dumps({'run_key': args.run_key, 'review': str(inside(ws, 'reviews', args.run_key))}, ensure_ascii=False))
    elif args.command == 'review':
        from .review import make_server
        server, token = make_server(ws, args.run_key, args.port)
        print(f'http://127.0.0.1:{server.server_port}/#token={token}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == 'approve':
        from .review import approve
        print(json.dumps(approve(ws, args.run_key), ensure_ascii=False))
    elif args.command == 'export':
        from .export import export_resume
        print(export_resume(ws, args.run_key, args.export_key))
    elif args.command == 'accept':
        from .export import accept_visual
        print(json.dumps(accept_visual(ws, args.export_key), ensure_ascii=False))
    elif args.command == 'status':
        from .review import get_status
        print(json.dumps(get_status(ws, args.run_key), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(str(error)) from None
