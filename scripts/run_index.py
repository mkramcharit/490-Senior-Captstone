import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def write_state(root, **values):
    target = root / 'supervisor.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'updated_unix': time.time(), **values}, indent=2), encoding='utf-8')
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--batch-size', type=int)
    args = parser.parse_args()
    import torch
    device = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device == 'cuda' and not torch.cuda.is_available():
        parser.error('CUDA is unavailable in this Python environment; use --device cpu')
    batch_size = args.batch_size or (64 if device == 'cuda' else 16)
    if batch_size < 1:
        parser.error('Batch size must be positive')
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
            raise OSError('Unable to prevent automatic system sleep')
    command = [sys.executable, '-u', '-B', '-m', 'landmark_ml.full_archive', str(root),
               '--batch-size', str(batch_size), '--threads', '4', '--device', device, '--model', args.model,
               '--prefetch', '2', '--download-workers', '2', '--preprocess-workers', '4']
    attempts = 0
    child = None
    try:
        while not (root / 'handoff-ready.json').is_file():
            attempts += 1
            with (root / 'supervised-build.log').open('ab', buffering=0) as log:
                child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                write_state(root, phase='running', process_id=child.pid, attempt=attempts, sleep_prevention=os.name == 'nt')
                started = time.time()
                last_progress = started
                last_stamp = None
                while child.poll() is None:
                    progress = root / 'activity.json'
                    try:
                        payload = json.loads(progress.read_text(encoding='utf-8'))
                        stamp = payload['updated_unix']
                        if stamp != last_stamp:
                            last_progress = time.time()
                            last_stamp = stamp
                        phase = payload.get('phase', '')
                    except (OSError, ValueError, KeyError):
                        phase = 'starting'
                    if phase == 'archive' and time.time() - last_progress > 1800:
                        write_state(root, phase='restarting_stalled_worker', process_id=child.pid, attempt=attempts)
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, check=False)
                        else:
                            child.kill()
                        child.wait()
                        break
                    time.sleep(15)
            if (root / 'handoff-ready.json').is_file():
                write_state(root, phase='complete', attempt=attempts)
                return
            write_state(root, phase='retrying_after_worker_exit', exit_code=child.returncode, attempt=attempts)
            time.sleep(60)
        write_state(root, phase='complete', attempt=attempts)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if os.name == 'nt':
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    main()
