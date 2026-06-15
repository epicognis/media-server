# Media Server — Claude Code Context

FastAPI media server that streams and downloads Movies, Music, and Audiobooks
from a WD My Cloud NAS. Built on Windows; this document covers porting to a
Raspberry Pi on the same LAN.

---

## What this app does

- `main.py` — FastAPI app, all routes, streaming with HTTP Range support, zip downloads
- `templates/index.html` — Single-page UI (vanilla JS, no build step)
- `static/` — Reserved for static assets (currently empty)

Run with:
```
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## File server — WD My Cloud NAS

### Windows (current)
The media files live on a **WD My Cloud NAS** mounted as `Z:\` on the Windows host.

| Detail | Value |
|--------|-------|
| Protocol | SMB / CIFS |
| Hostname | `MYCLOUD-YYUADJ` |
| Share | `Public` |
| Windows mount | `Z:\` → `\\MYCLOUD-YYUADJ\Public` |

Top-level folders inside the `Public` share that this app uses:

```
\\MYCLOUD-YYUADJ\Public\
├── Movies\          ← flat directory of .mpg files
├── Music\
│   ├── My Music\    ← Artist → Album → mp3
│   └── Lety's Collections\  ← folders of mp3s
└── Books\
    ├── fiction_by_author\          (Author → Book → parts)
    ├── non_fiction_by_author\
    ├── non_fiction_by_title\       (Book → parts, no author folder)
    ├── philosophy_health_by_author\
    ├── philosophy_health_by_title\
    └── to_be_filed\
```

### Raspberry Pi — mount the same share via CIFS

**1. Install the CIFS tools:**
```bash
sudo apt update && sudo apt install -y cifs-utils
```

**2. Create the mount point:**
```bash
sudo mkdir -p /mnt/nas
```

**3. Mount (ad-hoc, for testing):**
```bash
sudo mount -t cifs //MYCLOUD-YYUADJ/Public /mnt/nas \
  -o guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0755,dir_mode=0755
```

If hostname resolution fails, substitute the NAS IP address (find it via
`arp -a | grep -i mycloud` or your router's DHCP table).

**4. Make it persist across reboots** — add to `/etc/fstab`:
```
//MYCLOUD-YYUADJ/Public  /mnt/nas  cifs  guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0755,dir_mode=0755,_netdev,x-systemd.automount  0  0
```
`_netdev` tells systemd to wait for the network before mounting.

---

## Path changes required in main.py

The app currently uses Windows absolute paths. On the RPi, change the six
path constants at the top of `main.py`:

| Windows path | RPi path |
|---|---|
| `Z:\Movies` | `/mnt/nas/Movies` |
| `Z:\Music\My Music` | `/mnt/nas/Music/My Music` |
| `Z:\Music\Lety's Collections` | `/mnt/nas/Music/Lety's Collections` |
| `Z:\Books` | `/mnt/nas/Books` |

Replace the block:
```python
MOVIES_DIR   = Path(r"Z:\Movies")
MY_MUSIC_DIR = Path(r"Z:\Music\My Music")
LETY_DIR     = Path(r"Z:\Music\Lety's Collections")
BOOKS_DIR    = Path(r"Z:\Books")
```

With:
```python
MOVIES_DIR   = Path("/mnt/nas/Movies")
MY_MUSIC_DIR = Path("/mnt/nas/Music/My Music")
LETY_DIR     = Path("/mnt/nas/Music/Lety's Collections")
BOOKS_DIR    = Path("/mnt/nas/Books")
```

---

## Python environment on the RPi

```bash
sudo apt install -y python3-pip python3-venv
cd ~/media_server
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn jinja2 python-multipart
```

---

## Run on boot (systemd)

Create `/etc/systemd/system/media-server.service`:
```ini
[Unit]
Description=Media Server
After=network-online.target mnt-nas.mount
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/media_server
ExecStart=/home/pi/media_server/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable media-server
sudo systemctl start media-server
```

---

## Key app architecture notes

- **Streaming**: `range_response()` in `main.py` handles HTTP Range requests so
  seek works in the browser's audio/video player. NAS latency may affect large
  video files — test `.mpg` playback over the network.
- **Zip downloads**: Written to a temp file, streamed, then deleted via
  `BackgroundTask`. Temp dir on RPi defaults to `/tmp` — ensure enough space.
- **Book categories**: Auto-discovered at startup by scanning `Z:\Books`
  (→ `/mnt/nas/Books`). Structure detection (by_author vs by_title) reads the
  first subdirectory to determine depth.
- **Search**: Live filesystem scan on every query — no index. Acceptable for
  this collection size; may be slow on a heavily loaded NAS over WiFi.
- **No auth**: The server has no login. Run it on a private LAN only, or add
  HTTP Basic Auth middleware if exposed externally.

---

## Quick troubleshooting

| Symptom | Check |
|---------|-------|
| 404 on all media | NAS not mounted — run `ls /mnt/nas` |
| Filenames with `'` break | Confirm `iocharset=utf8` in mount options |
| Slow video seek | Normal over SMB; try wired Ethernet instead of WiFi |
| Port 8000 blocked | `sudo ufw allow 8000` or use port 80 with `--port 80` (needs `sudo`) |
