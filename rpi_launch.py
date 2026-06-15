import paramiko, time, json

HOST = '192.168.1.21'
USER = 'pi'
PASS = 'Dr0wssap!'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=15):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdin.close()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    rc = stdout.channel.recv_exit_status()
    print(f'[{rc}] {cmd[:80]}')
    if out: print('   ', out[:800])
    if err:
        lines = [l for l in err.splitlines() if l.strip() and '[sudo]' not in l]
        if lines: print('ERR', '\n    '.join(lines[:4]))
    return rc, out

# Check what's on 8080
run('ss -tlnp | grep 8080 || echo port-8080-free')

# Start media server on 8080
run('cd /home/pi/home/media-server && '
    'nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 '
    '> /tmp/media-server-8080.log 2>&1 & echo launched')

time.sleep(8)

run('tail -6 /tmp/media-server-8080.log')
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8080/')

rc, out = run('curl -s http://localhost:8080/api/movies')
if out.startswith('['):
    print(f'   MOVIES: {len(json.loads(out))} items')
else:
    print(f'   MOVIES resp: {out[:150]}')

rc, out = run('curl -s http://localhost:8080/api/books')
print(f'   BOOKS resp: {out[:300]}')

client.close()
print('\nDone. Media server at http://192.168.1.21:8080')
