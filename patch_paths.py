path = '/home/pi/home/media-server/main.py'
with open(path) as f:
    src = f.read()

src = src.replace(
    r'Path(r"Z:\Movies")',
    'Path("/mnt/nas/Movies")'
).replace(
    r'Path(r"Z:\Music\My Music")',
    'Path("/mnt/nas/Music/My Music")'
).replace(
    "Path(r\"Z:\\Music\\Lety's Collections\")",
    "Path(\"/mnt/nas/Music/Lety's Collections\")"
).replace(
    r'Path(r"Z:\Books")',
    'Path("/mnt/nas/Books")'
)

with open(path, 'w') as f:
    f.write(src)

# Verify
import re
for line in src.splitlines()[14:19]:
    print(line)
