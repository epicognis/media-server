import paramiko, sys, time

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
    if out: print('   ', out[:600])
    if err:
        lines = [l for l in err.splitlines() if l.strip() and '[sudo]' not in l]
        if lines and rc != 0:
            print('ERR', '\n    '.join(lines[:6]))
    return rc, out

def sudo(cmd, timeout=120):
    return run(f'echo {PASS} | sudo -S bash -c \'{cmd}\'', timeout=timeout)

# ── Mount NAS ─────────────────────────────────────────────────────────
print('\n=== NAS mount ===')
rc, _ = run('mountpoint -q /mnt/nas && echo ALREADY')
if 'ALREADY' not in _:
    sudo('mount -t cifs //MYCLOUD-YYUADJ/Public /mnt/nas '
         '-o guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0755,dir_mode=0755')

run('ls /mnt/nas')

# ── Patch paths in main.py using Python ───────────────────────────────
print('\n=== patch paths ===')
patch_script = r"""
import re
path = '/home/pi/home/media-server/main.py'
with open(path) as f:
    src = f.read()

replacements = [
    (r'Path(r"Z:\\Movies")',              'Path("/mnt/nas/Movies")'),
    (r'Path(r"Z:\\Music\\My Music")',     'Path("/mnt/nas/Music/My Music")'),
    ("Path(r\"Z:\\\\Music\\\\Lety's Collections\")", "Path(\"/mnt/nas/Music/Lety's Collections\")"),
    (r'Path(r"Z:\\Books")',               'Path("/mnt/nas/Books")'),
]

for old, new in replacements:
    src = src.replace(old, new)

with open(path, 'w') as f:
    f.write(src)
print('done')
"""
run(f"python3 -c \"{patch_script}\"")
run("grep -n 'MOVIES_DIR\\|MY_MUSIC_DIR\\|LETY_DIR\\|BOOKS_DIR' /home/pi/home/media-server/main.py | head -4")

# ── Create missing static dir ─────────────────────────────────────────
print('\n=== static dir ===')
run('mkdir -p /home/pi/home/media-server/static')

# ── Restart server ────────────────────────────────────────────────────
print('\n=== restart server ===')
run('pkill -f "uvicorn main:app" 2>/dev/null || true; sleep 2')
run('cd /home/pi/home/media-server && '
    'nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 '
    '> /tmp/media-server.log 2>&1 & echo launched')
time.sleep(5)
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/')
run('curl -s http://localhost:8000/api/movies | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{len(d)} movies\")" 2>/dev/null || echo movies-api-failed')
run('tail -8 /tmp/media-server.log')

client.close()
print('\nAll done.')
