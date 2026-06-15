import paramiko, time

HOST = '192.168.1.21'
USER = 'pi'
PASS = 'Dr0wssap!'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdin.close()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    rc  = stdout.channel.recv_exit_status()
    print(f'[{rc}] {cmd[:90]}')
    if out: print('   ', out[:800])
    if err:
        lines = [l for l in err.splitlines() if l.strip() and '[sudo]' not in l]
        if lines:
            print('ERR', '\n    '.join(lines[:8]))
    return rc, out

def sudo(cmd, timeout=120):
    return run(f"echo {PASS} | sudo -S bash -c '{cmd}'", timeout=timeout)

# ── Upload patch script via SFTP ──────────────────────────────────────
print('\n=== upload patch script ===')
sftp = client.open_sftp()
sftp.put(r'C:\home\media_server\patch_paths.py', '/tmp/patch_paths.py')
sftp.close()
print('   uploaded patch_paths.py')

# ── Run the patch script ───────────────────────────────────────────────
print('\n=== patch paths ===')
rc, _ = run('python3 /tmp/patch_paths.py')
if rc != 0:
    print('PATCH FAILED — aborting')
    client.close()
    exit(1)

# ── Verify paths were replaced ─────────────────────────────────────────
print('\n=== verify paths ===')
run("grep -n 'MOVIES_DIR\\|MY_MUSIC_DIR\\|LETY_DIR\\|BOOKS_DIR' /home/pi/home/media-server/main.py | head -6")

# ── Kill any running uvicorn ───────────────────────────────────────────
print('\n=== restart server ===')
run("pkill -f 'uvicorn main:app' || true")
time.sleep(2)

# ── Start server ───────────────────────────────────────────────────────
run('cd /home/pi/home/media-server && '
    'nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 '
    '> /tmp/media-server.log 2>&1 & echo launched')
time.sleep(6)

# ── Verify ────────────────────────────────────────────────────────────
print('\n=== verify server ===')
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/')
run('curl -s http://localhost:8000/api/movies | python3 -c '
    '"import sys,json; d=json.load(sys.stdin); print(f\'{len(d)} movies\')" '
    '2>/dev/null || echo movies-api-failed')
run('curl -s http://localhost:8000/api/books | python3 -c '
    '"import sys,json; d=json.load(sys.stdin); print(f\'{len(d)} book categories\')" '
    '2>/dev/null || echo books-api-failed')
run('tail -10 /tmp/media-server.log')

client.close()
print('\nDone.')
