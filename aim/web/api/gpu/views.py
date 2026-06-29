import json
import subprocess
import time

from aim.web.api.runs.utils import get_project_repo
from aim.web.api.utils import APIRouter


gpu_router = APIRouter()


@gpu_router.get('/')
async def gpu_status_api():
    try:
        result = subprocess.run(
            ['tailscale', 'status', '--json'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ts_data = json.loads(result.stdout)
        peers = ts_data.get('Peer', {})
        machines = [
            {
                'hostname': p['HostName'],
                'ip': p['TailscaleIPs'][0] if p.get('TailscaleIPs') else None,
            }
            for p in peers.values()
            if p.get('HostName', '').startswith('ml-') and p.get('Online', False)
        ]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return {'tailscale_available': False}

    repo = get_project_repo()
    repo._prepare_runs_cache()
    now = time.time()
    active_runs = []
    for run_hash in repo.list_active_runs():
        try:
            run = repo.get_run(run_hash)
            if not run or not run.active:
                continue
            try:
                hostname = run['hostname']
            except Exception:
                hostname = None
            try:
                tags = [tag.name for tag in run.props.tags_obj]
            except Exception:
                tags = []
            active_runs.append(
                {
                    'hash': run.hash,
                    'name': run.name,
                    'experiment': run.experiment,
                    'creation_time': run.creation_time,
                    'duration': int(now - run.creation_time),
                    'hostname': hostname,
                    'tags': tags,
                }
            )
        except Exception:
            continue

    return {
        'tailscale_available': True,
        'machines': machines,
        'active_runs': active_runs,
    }
