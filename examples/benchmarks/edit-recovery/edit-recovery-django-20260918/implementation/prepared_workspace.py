"""Bounded local tools in a disposable, prepared repository image.

Commands execute inside Docker only. The writable container is suitable for
local experiments, not a hosted service for mutually untrusted users.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid

from .sandbox import SandboxUnavailable


def bounded_process(argv, *, payload=b'', timeout=60, limit=65536):
    """Bound both streams while consuming them, including a noisy child process."""
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(stream, buffer):
        while chunk := stream.read(4096):
            remaining = limit - len(buffer)
            buffer.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()
                process.kill()
                break

    def send():
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threads = [threading.Thread(target=drain, args=(stream, buffer), daemon=True)
               for stream, buffer in zip((process.stdout, process.stderr), buffers)]
    threads.append(threading.Thread(target=send, daemon=True))
    start = time.monotonic()
    status = 'completed'
    try:
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status = 'timeout'
            process.kill()
            process.wait(timeout=5)
    finally:
        for thread in threads:
            thread.join(timeout=2)
        process.stdout.close()
        process.stderr.close()
    if overflow.is_set():
        status = 'output_limit'
    return {'status': status, 'returncode': process.returncode,
            'stdout': buffers[0].decode(errors='replace'),
            'stderr': buffers[1].decode(errors='replace'),
            'seconds': time.monotonic() - start}


# Remove non-ancestral references and objects before model-directed commands.
# Preserve base ancestry/tags because packages may derive versions from Git.
INITIALIZE = r'''
set -eu
# Prepared images may retain the environment-setup revision at HEAD.
# Resolve only the registered task commit, before any model can inspect files.
git -c safe.directory=/testbed cat-file -e "$1^{commit}" 2>/dev/null || { echo 'Base commit unavailable' >&2; exit 1; }
git -c safe.directory=/testbed reset --hard "$1" >/dev/null
actual=$(git -c safe.directory=/testbed rev-parse HEAD)
[ "$actual" = "$1" ] || { echo 'Base commit mismatch' >&2; exit 1; }
git for-each-ref --merged="$1" --format='%(refname)' refs/tags > /tmp/dream-kept-refs
printf '%s\n' refs/heads/dream-baseline >> /tmp/dream-kept-refs
git update-ref refs/heads/dream-baseline "$1"
git symbolic-ref HEAD refs/heads/dream-baseline
git for-each-ref --format='%(refname)' | while IFS= read -r ref; do
    if ! grep -Fxq "$ref" /tmp/dream-kept-refs; then printf 'delete %s\n' "$ref"; fi
done | git update-ref --stdin
git remote | while IFS= read -r remote; do git remote remove "$remote"; done
git reflog expire --expire=now --all
git -c pack.threads=1 -c pack.windowMemory=64m gc --prune=now
rm /tmp/dream-kept-refs
'''

FILE_TOOL = r'''
import json, pathlib, subprocess, sys
request = json.load(sys.stdin)
root = pathlib.Path('/testbed')
name = request['path']
p = root / name
if (not name or name.startswith('/') or any(x in ('', '.', '..', '.git') for x in name.split('/'))
    or '\\' in name or any(ord(c) < 32 for c in name)):
    raise ValueError('Invalid repository path')
if root not in p.resolve().parents or p.is_symlink() or not p.is_file():
    raise ValueError('Expected an existing regular repository file')
subprocess.run(['git', 'ls-files', '--error-unmatch', '--', name], check=True, stdout=subprocess.DEVNULL)
if p.stat().st_size > 262144:
    raise ValueError('File exceeds 256 KiB')
content = p.read_text(encoding='utf-8')
if request['action'] == 'read':
    start = request.get('start', 1)
    end = request.get('end', start + 159)
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= start + 299:
        raise ValueError('Read 1-300 lines using positive line numbers')
    print('\n'.join(f'{i}: {line}' for i, line in enumerate(content.splitlines(), 1) if start <= i <= end))
elif request['action'] == 'replace':
    old, new = request['old'], request['new']
    if not isinstance(old, str) or not old or not isinstance(new, str):
        raise ValueError('Replacement needs nonempty old text and string new text')
    count = content.count(old)
    if count != 1:
        positions = []
        offset = 0
        for _ in range(min(count, 3)):
            offset = content.find(old, offset)
            positions.append(content.count('\n', 0, offset) + 1)
            offset += len(old)
        lines = content.splitlines()
        # For missing matches, show the current beginning; never reuse stale source.
        anchors = positions or [1]
        excerpts = []
        for line in anchors:
            start = max(1, line - 2)
            excerpts.append('\n'.join('%d: %s' % (i, lines[i-1][:300])
                for i in range(start, min(len(lines), start + 7) + 1)))
        print(json.dumps({'error': 'missing_match' if count == 0 else 'ambiguous_match',
            'matches': count, 'match_lines': positions, 'current_excerpts': excerpts,
            'next_step': 'Read the current file around the intended location, then include enough surrounding text to match exactly once.'}))
        sys.exit(1)
    changed = content.replace(old, new, 1)
    if len(changed.encode()) > 262144:
        raise ValueError('Changed file exceeds 256 KiB')
    p.write_text(changed, encoding='utf-8')
    print('Replaced one occurrence')
else:
    raise ValueError('Unknown file action')
'''


class PreparedWorkspace:
    """One disposable image layer, no host mounts, network, or Docker socket."""
    def __init__(self, image, base_commit, *, timeout=60, output_limit=65536):
        if not re.fullmatch(r'[0-9a-f]{40}', base_commit):
            raise ValueError('Expected a complete base commit')
        if not 1 <= timeout <= 120 or not 1024 <= output_limit <= 1048576:
            raise ValueError('Invalid execution bounds')
        self.image, self.base_commit = image, base_commit
        self.timeout, self.output_limit = timeout, output_limit
        self.name = 'dream-prepared-' + uuid.uuid4().hex
        self.active = False
        self.image_id = None

    def __enter__(self):
        inspect = subprocess.run(['docker', 'image', 'inspect', self.image, '--format', '{{.Id}}'],
                                 capture_output=True, text=True, timeout=15)
        if inspect.returncode or not re.fullmatch(r'sha256:[a-f0-9]{64}', inspect.stdout.strip()):
            raise SandboxUnavailable('Prepared image must already be available locally')
        self.image_id = inspect.stdout.strip()
        command = ['docker', 'run', '-d', '--pull=never', '--name', self.name,
                   '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                   '--pids-limit=128', '--memory=2g', '--memory-swap=2g', '--cpus=2',
                   '--log-driver=none', '--user=0:0', '--workdir=/testbed',
                   '--env=HOME=/tmp/dream-home', '--env=GIT_CONFIG_NOSYSTEM=1',
                   '--env=GIT_CONFIG_GLOBAL=/dev/null', '--env=PYTHONDONTWRITEBYTECODE=1',
                   '--env=LANG=C.UTF-8', '--env=LC_ALL=C.UTF-8',
                   '--env=PATH=/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/bin:/usr/bin:/bin',
                   '--entrypoint=/bin/sh', self.image_id, '-c', 'while :; do sleep 3600; done']
        self.active = True  # Also clean up an uncertain/timed-out Docker launch.
        try:
            launch = bounded_process(command, timeout=30)
            if launch['status'] != 'completed' or launch['returncode']:
                raise SandboxUnavailable('Could not start prepared workspace: ' + launch['stderr'])
            initialized = self._exec(['/bin/sh', '-c', INITIALIZE, 'initialize', self.base_commit], timeout=120)
            if initialized['returncode']:
                raise SandboxUnavailable('Prepared workspace initialization failed: ' + initialized['stderr'])
        except BaseException:
            self.close()
            raise
        return self

    def _exec(self, argv, payload=b'', timeout=None):
        if not self.active:
            raise SandboxUnavailable('Prepared workspace is closed')
        result = bounded_process(['docker', 'exec', '-i', '--workdir=/testbed', self.name, *argv],
                                 payload=payload, timeout=timeout or self.timeout, limit=self.output_limit)
        if result['status'] != 'completed':
            # Killing docker exec does not stop its child. Destroy the workspace.
            self.close()
            raise SandboxUnavailable('Prepared command exceeded ' + result['status'] + '; workspace removed')
        return result

    def run(self, command):
        if not isinstance(command, str) or not command.strip() or len(command.encode()) > 16384:
            raise ValueError('Command must contain 1–16384 bytes')
        return self._exec(['/bin/bash', '-c', command])

    def file_action(self, request):
        payload = json.dumps(request).encode()
        if len(payload) > 524288:
            raise ValueError('File request exceeds 512 KiB')
        return self._exec(['python', '-I', '-c', FILE_TOOL], payload)

    def patch(self):
        # Include new files written by an issue reproducer or model command.
        result = self.run('git add -N -- . && git diff --no-ext-diff --binary HEAD -- .')
        if result['returncode']:
            raise SandboxUnavailable('Could not export repository patch')
        return result['stdout']

    def close(self):
        if not self.active:
            return
        removed = subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True, text=True, timeout=20)
        if removed.returncode and 'No such container' not in removed.stderr:
            raise SandboxUnavailable('Could not confirm workspace removal: ' + self.name)
        self.active = False

    def __exit__(self, *args):
        self.close()
