import os
import re
import mimetypes
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

# ── Paths ──────────────────────────────────────────────────────────────────
MOVIES_DIR   = Path(r"Z:\Movies")
MY_MUSIC_DIR = Path(r"Z:\Music\My Music")
LETY_DIR     = Path(r"Z:\Music\Lety's Collections")
BOOKS_DIR    = Path(r"Z:\Books")

AUDIO_EXTS = {".mp3", ".m4a", ".ogg", ".flac", ".wav", ".aac"}
VIDEO_EXTS = {".mpg", ".mpeg", ".mp4", ".mkv", ".avi", ".mov"}

# ── Auto-discover book categories ──────────────────────────────────────────
def _detect_book_type(cat_path: Path) -> str:
    """'by_author' if first-level dirs contain sub-dirs; else 'by_title'."""
    for sub in cat_path.iterdir():
        if not sub.is_dir():
            continue
        has_subdir = any(s.is_dir() for s in sub.iterdir())
        has_audio  = any(f.suffix.lower() in AUDIO_EXTS
                         for f in sub.iterdir() if f.is_file())
        if has_subdir and not has_audio:
            return "by_author"
        return "by_title"
    return "by_title"

def _display_name(folder: str) -> str:
    n = folder.replace("_", " ").replace("by author", "· by Author") \
              .replace("by title", "· by Title")
    n = re.sub(r"\bphilosophy health\b", "Philosophy & Health", n, flags=re.I)
    n = re.sub(r"\bnon fiction\b", "Non-Fiction", n, flags=re.I)
    n = re.sub(r"\bfiction\b", "Fiction", n, flags=re.I)
    n = re.sub(r"\bto be filed\b", "To Be Filed", n, flags=re.I)
    return n.strip().title().replace("& Health", "& Health") \
                            .replace("· By ", "· by ") \
                            .replace("Non-Fiction", "Non-Fiction")

BOOK_CATEGORIES: dict[str, dict] = {}
if BOOKS_DIR.is_dir():
    for _d in sorted(BOOKS_DIR.iterdir()):
        if _d.is_dir() and not _d.name.startswith(".") \
                        and _d.name not in ("fictionList.txt",):
            _type = _detect_book_type(_d)
            BOOK_CATEGORIES[_d.name] = {
                "path":    _d,
                "type":    _type,
                "display": _display_name(_d.name),
            }

app = FastAPI(title="Media Collection")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Helpers ────────────────────────────────────────────────────────────────
def clean_movie_title(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"\s+\d{8}\s*\[.*?\]$", "", name)
    name = re.sub(r"\s*\[.*?\]$", "", name)
    return name.strip()


def iter_range(path: Path, start: int, end: int, chunk: int = 1 << 20):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = f.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def range_response(path: Path, request: Request):
    size = path.stat().st_size
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    range_header = request.headers.get("range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else size - 1
            end   = min(end, size - 1)
            headers = {
                "Content-Range":  f"bytes {start}-{end}/{size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(end - start + 1),
                "Content-Type":   mime,
            }
            return StreamingResponse(iter_range(path, start, end),
                                     status_code=206, headers=headers)
    return StreamingResponse(
        open(path, "rb"),
        headers={"Accept-Ranges": "bytes", "Content-Length": str(size),
                 "Content-Type": mime},
    )


def make_zip(files: list[tuple[str, Path]], zip_name: str) -> FileResponse:
    """Write files into a temp zip, return as FileResponse with auto-cleanup."""
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
        for arcname, path in files:
            zf.write(str(path), arcname)
    return FileResponse(
        tmp.name, filename=zip_name, media_type="application/zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )


def audio_files(directory: Path) -> list[Path]:
    return sorted(f for f in directory.iterdir()
                  if f.is_file() and f.suffix.lower() in AUDIO_EXTS)


# ── Page ───────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


# ── Movies ─────────────────────────────────────────────────────────────────
@app.get("/api/movies")
async def list_movies():
    return [
        {"title": clean_movie_title(f.name), "filename": f.name}
        for f in sorted(MOVIES_DIR.iterdir())
        if f.suffix.lower() in VIDEO_EXTS
    ]


@app.get("/stream/movie/{filename:path}")
async def stream_movie(filename: str, request: Request):
    path = MOVIES_DIR / filename
    if not path.is_file():
        raise HTTPException(404)
    return range_response(path, request)


@app.get("/download/movie/{filename:path}")
async def download_movie(filename: str):
    path = MOVIES_DIR / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


# ── Music – My Music ───────────────────────────────────────────────────────
@app.get("/api/music/artists")
async def list_artists():
    return sorted(
        d.name for d in MY_MUSIC_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


@app.get("/api/music/artist/{artist}")
async def list_albums(artist: str):
    artist_path = MY_MUSIC_DIR / artist
    if not artist_path.is_dir():
        raise HTTPException(404)
    albums = []
    for item in sorted(artist_path.iterdir()):
        if item.is_dir():
            tracks = sorted(
                t.name for t in item.iterdir() if t.suffix.lower() in AUDIO_EXTS
            )
            if tracks:
                albums.append({"album": item.name, "tracks": tracks})
        elif item.suffix.lower() in AUDIO_EXTS:
            albums.append({"album": "", "tracks": [item.name]})
    return albums


def _music_path(artist: str, album: str, track: str) -> Path:
    if album:
        p = MY_MUSIC_DIR / artist / album / track
        if p.exists():
            return p
    return MY_MUSIC_DIR / artist / track


@app.get("/stream/music/{artist}/{album}/{track:path}")
async def stream_music(artist: str, album: str, track: str, request: Request):
    path = _music_path(artist, album, track)
    if not path.is_file():
        raise HTTPException(404)
    return range_response(path, request)


@app.get("/download/music/{artist}/{album}/{track:path}")
async def download_music(artist: str, album: str, track: str):
    path = _music_path(artist, album, track)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=track, media_type="application/octet-stream")


@app.get("/download/zip/music/artist/{artist}")
async def download_artist_zip(artist: str):
    artist_path = MY_MUSIC_DIR / artist
    if not artist_path.is_dir():
        raise HTTPException(404)
    files = [
        (str(f.relative_to(artist_path)), f)
        for f in sorted(artist_path.rglob("*"))
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ]
    return make_zip(files, f"{artist}.zip")


@app.get("/download/zip/music/album/{artist}/{album}")
async def download_album_zip(artist: str, album: str):
    album_path = MY_MUSIC_DIR / artist / album
    if not album_path.is_dir():
        raise HTTPException(404)
    files = [(f.name, f) for f in audio_files(album_path)]
    return make_zip(files, f"{artist} - {album}.zip")


# ── Music – Lety's Collections ─────────────────────────────────────────────
@app.get("/api/lety")
async def list_lety():
    items = []
    for entry in sorted(LETY_DIR.iterdir()):
        if entry.is_dir():
            tracks = sorted(
                str(t.relative_to(LETY_DIR))
                for t in entry.rglob("*")
                if t.is_file() and t.suffix.lower() in AUDIO_EXTS
            )
            if tracks:
                items.append({"folder": entry.name, "tracks": tracks, "path": entry.name})
        elif entry.suffix.lower() in AUDIO_EXTS:
            items.append({"folder": "", "tracks": [entry.name], "path": ""})
    return items


@app.get("/stream/lety/{rel_path:path}")
async def stream_lety(rel_path: str, request: Request):
    path = LETY_DIR / rel_path
    if not path.is_file():
        raise HTTPException(404)
    return range_response(path, request)


@app.get("/download/lety/{rel_path:path}")
async def download_lety(rel_path: str):
    path = LETY_DIR / rel_path
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/download/zip/lety/{folder}")
async def download_lety_zip(folder: str):
    folder_path = LETY_DIR / folder
    if not folder_path.is_dir():
        raise HTTPException(404)
    files = [
        (str(f.relative_to(folder_path)), f)
        for f in sorted(folder_path.rglob("*"))
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ]
    return make_zip(files, f"{folder}.zip")


# ── Audiobooks ─────────────────────────────────────────────────────────────
@app.get("/api/books/categories")
async def list_book_categories():
    return [
        {"key": k, "display": v["display"], "type": v["type"]}
        for k, v in BOOK_CATEGORIES.items()
    ]


# by_author: list authors in a category
@app.get("/api/books/{category}/authors")
async def list_authors_in_category(category: str):
    info = BOOK_CATEGORIES.get(category)
    if not info:
        raise HTTPException(404)
    if info["type"] != "by_author":
        raise HTTPException(400, "category is not by_author")
    return sorted(d.name for d in info["path"].iterdir() if d.is_dir())


# by_author: list books for an author
@app.get("/api/books/{category}/author/{author}")
async def list_books_by_author(category: str, author: str):
    info = BOOK_CATEGORIES.get(category)
    if not info:
        raise HTTPException(404)
    author_path = info["path"] / author
    if not author_path.is_dir():
        raise HTTPException(404)
    books = []
    for item in sorted(author_path.iterdir()):
        if item.is_dir():
            parts = sorted(t.name for t in item.iterdir()
                           if t.is_file() and t.suffix.lower() in AUDIO_EXTS)
            if parts:
                books.append({"title": item.name, "parts": parts})
        elif item.suffix.lower() in AUDIO_EXTS:
            books.append({"title": item.stem, "parts": [item.name]})
    return books


# by_title: list books (top-level dirs are books)
@app.get("/api/books/{category}/titles")
async def list_books_by_title(category: str):
    info = BOOK_CATEGORIES.get(category)
    if not info:
        raise HTTPException(404)
    books = []
    for item in sorted(info["path"].iterdir()):
        if item.is_dir():
            parts = sorted(t.name for t in item.iterdir()
                           if t.is_file() and t.suffix.lower() in AUDIO_EXTS)
            if parts:
                books.append({"title": item.name, "parts": parts})
        elif item.suffix.lower() in AUDIO_EXTS:
            books.append({"title": item.stem, "parts": [item.name]})
    return books


# Stream / download individual part
def _book_part_path(category: str, sub: str, title: str, part: str) -> Path:
    info = BOOK_CATEGORIES.get(category)
    if not info:
        return None
    if info["type"] == "by_author":
        return info["path"] / sub / title / part
    else:
        return info["path"] / title / part


@app.get("/stream/books/{category}/{sub}/{title}/{part:path}")
async def stream_book(category: str, sub: str, title: str, part: str, request: Request):
    path = _book_part_path(category, sub, title, part)
    if not path or not path.is_file():
        raise HTTPException(404)
    return range_response(path, request)


@app.get("/download/books/{category}/{sub}/{title}/{part:path}")
async def download_book_part(category: str, sub: str, title: str, part: str):
    path = _book_part_path(category, sub, title, part)
    if not path or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=part, media_type="application/octet-stream")


# Zip: entire book (by_author: sub=author; by_title: sub=_)
@app.get("/download/zip/books/{category}/{sub}/{title}")
async def download_book_zip(category: str, sub: str, title: str):
    info = BOOK_CATEGORIES.get(category)
    if not info:
        raise HTTPException(404)
    if info["type"] == "by_author":
        book_path = info["path"] / sub / title
    else:
        book_path = info["path"] / title
    if not book_path.is_dir():
        raise HTTPException(404)
    files = [(f.name, f) for f in audio_files(book_path)]
    return make_zip(files, f"{title}.zip")


# ── Search ────────────────────────────────────────────────────────────────
@app.get("/api/search")
async def search(q: str, category: str = "all"):
    if len(q.strip()) < 2:
        return []
    ql = q.strip().lower()
    results = []

    if category in ("movies", "all"):
        for f in sorted(MOVIES_DIR.iterdir()):
            if f.suffix.lower() in VIDEO_EXTS:
                title = clean_movie_title(f.name)
                if ql in title.lower():
                    results.append({"type": "movie", "title": title, "filename": f.name})

    if category in ("music", "all"):
        for artist_dir in sorted(MY_MUSIC_DIR.iterdir()):
            if not artist_dir.is_dir() or artist_dir.name.startswith("."):
                continue
            artist_hit = ql in artist_dir.name.lower()
            for album_dir in sorted(artist_dir.iterdir()):
                if not album_dir.is_dir():
                    continue
                if artist_hit or ql in album_dir.name.lower():
                    results.append({
                        "type": "album",
                        "artist": artist_dir.name,
                        "album": album_dir.name,
                    })

    if category in ("lety", "all"):
        for entry in sorted(LETY_DIR.iterdir()):
            if entry.is_dir() and ql in entry.name.lower():
                results.append({"type": "lety_folder", "folder": entry.name})

    if category in ("books", "all"):
        for cat_key, cat_info in BOOK_CATEGORIES.items():
            if cat_info["type"] == "by_author":
                for author_dir in sorted(cat_info["path"].iterdir()):
                    if not author_dir.is_dir():
                        continue
                    author_hit = ql in author_dir.name.lower()
                    for book_dir in sorted(author_dir.iterdir()):
                        if not book_dir.is_dir():
                            continue
                        if author_hit or ql in book_dir.name.lower():
                            results.append({
                                "type": "book",
                                "category": cat_key,
                                "cat_display": cat_info["display"],
                                "cat_type": "by_author",
                                "author": author_dir.name,
                                "title": book_dir.name,
                            })
            else:
                for book_dir in sorted(cat_info["path"].iterdir()):
                    if book_dir.is_dir() and ql in book_dir.name.lower():
                        results.append({
                            "type": "book",
                            "category": cat_key,
                            "cat_display": cat_info["display"],
                            "cat_type": "by_title",
                            "author": "_",
                            "title": book_dir.name,
                        })

    return results[:200]


# Zip: entire author (by_author only)
@app.get("/download/zip/books/{category}/author/{author}")
async def download_author_zip(category: str, author: str):
    info = BOOK_CATEGORIES.get(category)
    if not info or info["type"] != "by_author":
        raise HTTPException(404)
    author_path = info["path"] / author
    if not author_path.is_dir():
        raise HTTPException(404)
    files = [
        (str(f.relative_to(author_path)), f)
        for f in sorted(author_path.rglob("*"))
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ]
    return make_zip(files, f"{author}.zip")
