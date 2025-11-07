import argparse
import json
import os
from datetime import datetime
from pathlib import Path

research = Path.cwd() / 'Research'
research.mkdir(exist_ok=True)
log_path = research / 'decision_log.md'


def append_entry(step: str, status: str, summary: str, artifacts: list[str], env: dict[str, str]) -> None:
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    lines = []
    lines.append(f'## {ts} — {step} — {status}')
    if summary:
        lines.append(summary)
    if artifacts:
        lines.append('Artifacts:')
        for a in artifacts:
            p = Path(a)
            lines.append(f'- {a} {"(exists)" if p.exists() else "(missing)"}')
    if env:
        lines.append('Env: ' + json.dumps(env, sort_keys=True))
    lines.append('')
    with log_path.open('a', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--step', required=True)
    ap.add_argument('--status', choices=['pass','fail','partial'], required=True)
    ap.add_argument('--summary', default='')
    ap.add_argument('--artifact', action='append', default=[])
    ap.add_argument('--env', default='')
    args = ap.parse_args()

    env_info = {
        'platform': os.name,
        'system': os.getenv('OS',''),
        'dal': os.getenv('EAR_DAL','false'),
        'tacc': os.getenv('EAR_TACC','false'),
        'windows': 'true' if os.name == 'nt' else 'false',
    }
    # merge JSON override if provided
    if args.env:
        try:
            env_info.update(json.loads(args.env))
        except Exception:
            pass

    append_entry(args.step, args.status, args.summary, args.artifact, env_info)

if __name__ == '__main__':
    main()
