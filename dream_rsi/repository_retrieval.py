"""Deterministic issue-to-source context, using only a repository's tracked files.

The module also runs in prepared Python 3.6+ containers; keep its driver portable.
This is an engineering retrieval aid, not a learned policy or a correctness test.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from collections import Counter

EXTENSIONS = {'.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.rs', '.go', '.java', '.c', '.cpp', '.h'}
GENERIC = {'print', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'len',
           'range', 'super', 'isinstance', 'getattr', 'setattr', 'True', 'False', 'None'}


def queries(issue):
    if not isinstance(issue, str) or len(issue.encode('utf-8')) > 131072:
        raise ValueError('Expected issue text of at most 128 KiB')
    symbols = re.findall(r'\b([A-Za-z_][A-Za-z_0-9]{2,80})\s*\(', issue)
    symbols += re.findall(r'\b([A-Za-z][A-Za-z_0-9]*_[A-Za-z_0-9]+)\b', issue)
    symbols = [name for name, _ in Counter(symbols).most_common() if name not in GENERIC and len(name) <= 80][:16]
    paths = [name for name in dict.fromkeys(re.findall(r'[A-Za-z_0-9.-]+\.(?:py|pyi|js|jsx|ts|tsx|rs|go|java|cpp|c|h)\b', issue)) if len(name) <= 255][:10]
    code = []
    for line in issue.splitlines():
        match = re.match(r'^\s*(?:-+>)?\s*\d+\s+(.{8,160})$', line)
        if match and not match.group(1).lstrip().startswith(('#', '...')):
            code.append(match.group(1).strip())
    code = list(dict.fromkeys(code))[:12]
    return {'symbols':symbols, 'filenames':paths, 'trace_lines':code}


def rank_file(path, text, query):
    lines = text.splitlines()
    hits, matched = {}, []
    score = 25 if Path(path).name in query['filenames'] else 0
    patterns = [(name, re.compile(r'\b' + re.escape(name) + r'\b'),
                 re.compile(r'\b(?:def|class|function|fn|func)\s+' + re.escape(name) + r'\b'))
                for name in query['symbols']]
    for name, pattern, definition in patterns:
        positions = [index for index, line in enumerate(lines) if pattern.search(line)]
        if not positions:
            continue
        defined = [index for index in positions if definition.search(lines[index])]
        weight = 40 if defined else 3
        score += weight
        matched.append(name)
        for index in (defined or positions)[:3]:
            hits[index] = hits.get(index, 0) + weight
    for code in query['trace_lines']:
        positions = [index for index, line in enumerate(lines) if code in line.strip()]
        if positions:
            score += 50
            matched.append(code)
            for index in positions[:2]:
                hits[index] = hits.get(index, 0) + 50
    if not score:
        return None
    if not hits:
        hits[0] = 1
    chosen = sorted(hits, key=lambda index: (-hits[index], index))[:3]
    included = set()
    for index in chosen:
        included.update(range(max(0,index-12),min(len(lines),index+19)))
    snippet = '\n'.join('{}: {}'.format(index+1,lines[index]) for index in sorted(included))
    snippet = snippet.encode('utf-8')[:4000].decode('utf-8',errors='ignore')
    return {'path':path, 'score':score, 'matched_queries':matched,
            'sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(), 'excerpt':snippet}


def retrieve(root, issue, max_files=5000, max_bytes=20000000):
    root = Path(root).resolve()
    query = queries(issue)
    tracked = subprocess.check_output(['git','-C',str(root),'ls-files','-z']).split(b'\0')
    ranked, scanned, used = [], 0, 0
    truncated = False
    for raw in sorted(tracked):
        if not raw:
            continue
        try:
            name = raw.decode('utf-8')
            relative = Path(name)
            path = root/relative
            if (relative.is_absolute() or '..' in relative.parts or relative.suffix not in EXTENSIONS
                    or any(part.startswith('.') or part in ('tests','test','__tests__','node_modules','vendor') for part in relative.parts)
                    or relative.name.startswith('test_') or path.is_symlink() or root not in path.resolve().parents):
                continue
            size = path.stat().st_size
            if size > 262144 or not path.is_file():
                continue
            if scanned >= max_files or used + size > max_bytes:
                truncated = True
                break
            data = path.read_bytes()
            scanned += 1
            used += len(data)
            text = data.decode('utf-8')
        except (OSError, UnicodeError):
            continue
        row = rank_file(name,text,query)
        if row:
            ranked.append(row)
    ranked.sort(key=lambda row: (-row['score'],row['path']))
    document = {'method':'issue symbols, traceback lines, and filenames; no reference patches',
            'queries':query, 'files_scanned':scanned, 'bytes_scanned':used,
            'scan_truncated':truncated, 'files':ranked[:5],
            'warning':'Search hints only; ranking and excerpts do not establish a correct repair.'}
    while len(json.dumps(document).encode('utf-8')) > 60000 and document['files']:
        document['files'].pop()
        document['output_truncated'] = True
    return document


def context_for_workspace(workspace, issue):
    """Use the existing bounded Docker transport; never read the host repository."""
    source = Path(__file__).read_text()
    result = workspace._exec(['python','-I','-c',source], json.dumps({'issue':issue}).encode())
    if result['returncode']:
        raise RuntimeError('Repository retrieval failed: ' + result['stderr'][:2000])
    document = json.loads(result['stdout'])
    document['seconds'] = result['seconds']
    return document


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(retrieve('/testbed',request['issue'])))
