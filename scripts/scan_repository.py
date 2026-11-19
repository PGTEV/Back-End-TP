"""Scan reachable git blobs for known credential formats without printing matched values.

Heuristic aid, not a guarantee: provider configuration and revoked credentials
still require operational review. Scans history, not only the current checkout.
"""
import re
import subprocess
import sys

PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
    re.compile(rb'gh[pousr]_[0-9A-Za-z]{36,255}'),
    re.compile(rb'github_pat_[0-9A-Za-z_]{60,255}'),
    re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{40,255}'),
]

objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all']).splitlines()
found = []
for entry in objects:
    parts = entry.split(b' ', 1)
    oid = parts[0].decode('ascii')
    if subprocess.check_output(['git', 'cat-file', '-t', oid]).strip() != b'blob':
        continue
    content = subprocess.check_output(['git', 'cat-file', 'blob', oid])
    if any(pattern.search(content) for pattern in PATTERNS):
        found.append((oid, parts[1].decode('utf-8', errors='replace') if len(parts) > 1 else '(blob)'))
for oid, path in found:
    print(f'Potential credential: {path} (blob {oid[:12]}); value withheld.')
print(f'Known-format scan: {len(objects)} reachable objects, {len(found)} flagged blobs.')
sys.exit(bool(found))
