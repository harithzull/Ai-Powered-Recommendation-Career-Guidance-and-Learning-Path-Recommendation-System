"""Private parser worker: pipes only, no Django/settings/credentials/file paths."""
import base64
import json
import logging
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from resume.constants import MAX_FILE_BYTES  # noqa: E402


def main():
    logging.disable(logging.CRITICAL)
    def offline(*a, **kw):
        raise RuntimeError('Network is disabled')
    socket.socket.connect = socket.socket.connect_ex = offline
    socket.create_connection = socket.getaddrinfo = offline
    result = {'valid': False, 'status': 'failed', 'text': '', 'error_code': 'worker_unavailable'}
    try:
        from resume.services.limits import posix_limits
        posix_limits()
        # On Windows the parent assigns its Job Object before supplying stdin.
        payload = sys.stdin.buffer.read(7*1024*1024+1)
        if len(payload) > 7*1024*1024:
            raise ValueError()
        request = json.loads(payload)
        data = base64.b64decode(request['data'], validate=True)
        if len(data) > MAX_FILE_BYTES or request['type'] not in ('pdf', 'docx'):
            raise ValueError()
        from resume.services.parsing import Rejected, extract
        try:
            result = extract(data, request['type'])
        except Rejected as exc:
            result['error_code'] = exc.code
    except MemoryError:
        result['error_code'] = 'resource_limit'
    except Exception:
        pass
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    main()
