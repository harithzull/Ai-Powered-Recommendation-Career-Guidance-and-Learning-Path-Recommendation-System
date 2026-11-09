import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from resume.constants import ERRORS, MAX_FILE_BYTES, MAX_TEXT_CHARS, WORKER_WALL_SECONDS
from .limits import windows_job


def failed(code):
    return {'valid': False, 'status': 'failed', 'text': '', 'error_code': code}


def extract_text(data, file_type):
    if not data or len(data) > MAX_FILE_BYTES or file_type not in ('pdf', 'docx'):
        return failed('resource_limit')
    keys = ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LANG', 'LC_ALL')
    env = {k: os.environ[k] for k in keys if k in os.environ}
    command = [sys.executable, '-I', '-B', str(Path(__file__).with_name('worker.py'))]
    process, close_job = None, lambda: None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name == 'posix')
        close_job = windows_job(process)
        payload = json.dumps({'type': file_type, 'data': base64.b64encode(data).decode('ascii')}).encode('ascii')
        output, _ = process.communicate(payload, timeout=WORKER_WALL_SECONDS)
        if process.returncode or len(output) > 1024*1024:
            return failed('resource_limit')
        result = json.loads(output)
        if (set(result) != {'valid', 'status', 'text', 'error_code'} or type(result['valid']) is not bool
                or result['status'] not in ('completed', 'failed', 'no_extractable_text')
                or not isinstance(result['text'], str) or len(result['text']) > MAX_TEXT_CHARS
                or result['error_code'] not in ('', *ERRORS)):
            return failed('extraction_failed')
        return result
    except subprocess.TimeoutExpired:
        return failed('processing_timeout')
    except Exception:
        return failed('worker_unavailable')
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate()
        close_job()
