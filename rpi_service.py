import paramiko, time

HOST = '192.168.1.21'
USER = 'pi'
PASS = 'Dr0wssap!'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdin.close()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    rc = stdout.channel.recv_exit_status()
    print(f'[{rc}] {cmd[:80]}')
    if out: print('   ', out[:600])
    if err:
        lines = [l for l in err.splitlines() if l.strip() and '[sudo]' not in l]
        if lines: print('ERR', '\n    '.join(lines[:4]))
    return rc, out

def sudo(cmd, timeout=30):
    return run(f"echo {PASS} | sudo -S bash -c '{cmd}'", timeout=timeout)

SERVICE = (
    '[Unit]\n'
    'Description=Media Server\n'
    'After=network-online.target\n'
    'Wants=network-online.target\n'
    '\n'
    '[Service]\n'
    'User=pi\n'
    'WorkingDirectory=/home/pi/home/media-server\n'
    'ExecStart=/home/pi/home/media-server/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080\n'
    'Restart=on-failure\n'
    'RestartSec=5\n'
    '\n'
    '[Install]\n'
    'WantedBy=multi-user.target\n'
)

# Write service file via SFTP
sftp = client.open_sftp()
with sftp.open('/tmp/media-server.service', 'w') as f:
    f.write(SERVICE)
sftp.close()
print('service file uploaded')

sudo('cp /tmp/media-server.service /etc/systemd/system/media-server.service')
sudo('systemctl daemon-reload')
sudo('systemctl enable media-server')

# Hand off from nohup to systemd
run('pkill -f "uvicorn main:app" || true')
time.sleep(2)
sudo('systemctl start media-server')
time.sleep(5)

run('systemctl is-active media-server')
run('systemctl status media-server --no-pager -l')
run('curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8080/')

client.close()
print('\nDone.')
