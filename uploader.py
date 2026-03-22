"""Instagram photo manager with SQLite metadata, search, and tagging."""

import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
import uvicorn

BASE_DIR = Path(os.environ.get("INSTA_PHOTOS_DIR", Path.home() / "insta-photos"))
THUMB_DIR = BASE_DIR / "thumbs"
DB_PATH = BASE_DIR / "photos.db"

BASE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Insta Photo Manager")

# ─── Database ─────────────────────────────────────────────────

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_name TEXT,
                path TEXT NOT NULL,
                size INTEGER,
                media_type TEXT DEFAULT 'image',
                width INTEGER,
                height INTEGER,
                tags TEXT DEFAULT '',
                caption TEXT DEFAULT '',
                memo TEXT DEFAULT '',
                ig_posted INTEGER DEFAULT 0,
                ig_post_url TEXT,
                ig_posted_at TEXT,
                created_at TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts USING fts5(
                tags, caption, memo, original_name,
                content='photos',
                content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS photos_ai AFTER INSERT ON photos BEGIN
                INSERT INTO photos_fts(rowid, tags, caption, memo, original_name)
                VALUES (new.rowid, new.tags, new.caption, new.memo, new.original_name);
            END;
            CREATE TRIGGER IF NOT EXISTS photos_au AFTER UPDATE ON photos BEGIN
                DELETE FROM photos_fts WHERE rowid = old.rowid;
                INSERT INTO photos_fts(rowid, tags, caption, memo, original_name)
                VALUES (new.rowid, new.tags, new.caption, new.memo, new.original_name);
            END;
            CREATE TRIGGER IF NOT EXISTS photos_ad AFTER DELETE ON photos BEGIN
                DELETE FROM photos_fts WHERE rowid = old.rowid;
            END;
        """)

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ─── Helpers ──────────────────────────────────────────────────

def make_thumbnail(src_path: Path, photo_id: str) -> Optional[Path]:
    try:
        from PIL import Image
        img = Image.open(src_path)
        img.thumbnail((400, 400))
        thumb_path = THUMB_DIR / f"{photo_id}.jpg"
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=80)
        return thumb_path
    except Exception:
        return None


def get_image_dimensions(src_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(src_path) as img:
            return img.size
    except Exception:
        return (0, 0)


def get_exif_date(src_path: Path) -> Optional[str]:
    try:
        from PIL import Image
        from PIL.ExifTags import Base as ExifBase
        with Image.open(src_path) as img:
            exif = img.getexif()
            if exif:
                date_str = exif.get(ExifBase.DateTimeOriginal) or exif.get(ExifBase.DateTime)
                if date_str:
                    return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        pass
    return None


# ─── API ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    # Migrate existing flat files
    _migrate_existing_files()


def _migrate_existing_files():
    """Migrate flat files uploaded before DB existed."""
    with get_db() as db:
        for f in BASE_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".webp", ".mp4", ".mov"}:
                existing = db.execute("SELECT id FROM photos WHERE filename = ?", (f.name,)).fetchone()
                if existing:
                    continue
                photo_id = uuid.uuid4().hex[:12]
                now = datetime.now()
                date_dir = BASE_DIR / now.strftime("%Y/%m/%d")
                date_dir.mkdir(parents=True, exist_ok=True)
                new_path = date_dir / f.name
                f.rename(new_path)
                w, h = get_image_dimensions(new_path)
                media_type = "video" if f.suffix.lower() in {".mp4", ".mov"} else "image"
                make_thumbnail(new_path, photo_id)
                db.execute(
                    "INSERT INTO photos (id, filename, original_name, path, size, media_type, width, height, created_at, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (photo_id, f.name, f.name, str(new_path.relative_to(BASE_DIR)), f.stat().st_size if new_path.exists() else 0, media_type, w, h, now.isoformat(), now.isoformat()),
                )


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    tags: str = Form(""),
    memo: str = Form(""),
):
    content = await file.read()
    photo_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix.lower() or ".jpg"
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{photo_id}{ext}"

    # Save to date-based directory
    date_dir = BASE_DIR / now.strftime("%Y/%m/%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    file_path = date_dir / filename
    file_path.write_bytes(content)

    # Image metadata
    media_type = "video" if ext in {".mp4", ".mov"} else "image"
    w, h = get_image_dimensions(file_path) if media_type == "image" else (0, 0)
    created_at = get_exif_date(file_path) or now.isoformat()

    # Thumbnail
    if media_type == "image":
        make_thumbnail(file_path, photo_id)

    # DB insert
    rel_path = str(file_path.relative_to(BASE_DIR))
    with get_db() as db:
        db.execute(
            "INSERT INTO photos (id, filename, original_name, path, size, media_type, width, height, tags, memo, created_at, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (photo_id, filename, file.filename, rel_path, len(content), media_type, w, h, tags, memo, created_at, now.isoformat()),
        )

    return {"id": photo_id, "filename": filename, "size": len(content), "path": rel_path}


@app.get("/photos")
async def list_photos(
    q: str = Query("", description="Search query (tags, caption, memo)"),
    tag: str = Query("", description="Filter by tag"),
    posted: Optional[bool] = Query(None, description="Filter by IG posted status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with get_db() as db:
        if q:
            rows = db.execute(
                "SELECT p.* FROM photos p JOIN photos_fts f ON p.rowid = f.rowid WHERE photos_fts MATCH ? ORDER BY p.created_at DESC LIMIT ? OFFSET ?",
                (q, limit, offset),
            ).fetchall()
        elif tag:
            rows = db.execute(
                "SELECT * FROM photos WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (f"%{tag}%", limit, offset),
            ).fetchall()
        elif posted is not None:
            rows = db.execute(
                "SELECT * FROM photos WHERE ig_posted = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (1 if posted else 0, limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM photos ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]

    return {"total": total, "photos": [dict(r) for r in rows]}


@app.get("/photo/{photo_id}")
async def get_photo(photo_id: str, thumb: bool = Query(False)):
    if thumb:
        thumb_path = THUMB_DIR / f"{photo_id}.jpg"
        if thumb_path.exists():
            return FileResponse(thumb_path, media_type="image/jpeg")

    with get_db() as db:
        row = db.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)

    file_path = BASE_DIR / row["path"]
    if not file_path.exists():
        return JSONResponse({"error": "file missing"}, status_code=404)
    return FileResponse(file_path)


@app.patch("/photo/{photo_id}")
async def update_photo(photo_id: str, request: Request):
    data = await request.json()
    allowed = {"tags", "caption", "memo"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return JSONResponse({"error": "no valid fields"}, status_code=400)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [photo_id]

    with get_db() as db:
        db.execute(f"UPDATE photos SET {set_clause} WHERE id = ?", values)
    return {"updated": photo_id, "fields": list(updates.keys())}


@app.post("/photo/{photo_id}/mark-posted")
async def mark_posted(photo_id: str, request: Request):
    data = await request.json()
    ig_url = data.get("ig_post_url", "")
    now = datetime.now().isoformat()
    with get_db() as db:
        db.execute(
            "UPDATE photos SET ig_posted = 1, ig_post_url = ?, ig_posted_at = ? WHERE id = ?",
            (ig_url, now, photo_id),
        )
    return {"marked": photo_id}


@app.delete("/photo/{photo_id}")
async def delete_photo(photo_id: str):
    with get_db() as db:
        row = db.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        file_path = BASE_DIR / row["path"]
        if file_path.exists():
            file_path.unlink()
        thumb_path = THUMB_DIR / f"{photo_id}.jpg"
        if thumb_path.exists():
            thumb_path.unlink()
        db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    return {"deleted": photo_id}


@app.get("/tags")
async def list_tags():
    with get_db() as db:
        rows = db.execute("SELECT tags FROM photos WHERE tags != ''").fetchall()
    tag_counts: dict[str, int] = {}
    for row in rows:
        for t in row["tags"].split(","):
            t = t.strip()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    return sorted(tag_counts.items(), key=lambda x: -x[1])


@app.get("/stats")
async def stats():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        posted = db.execute("SELECT COUNT(*) FROM photos WHERE ig_posted = 1").fetchone()[0]
        total_size = db.execute("SELECT COALESCE(SUM(size), 0) FROM photos").fetchone()[0]
    return {"total": total, "posted": posted, "not_posted": total - posted, "total_size_mb": round(total_size / 1024 / 1024, 1)}


# ─── Web UI ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>insta-photos</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, sans-serif; background: #000; color: #fff; }
  .header { padding: 16px; text-align: center; position: sticky; top: 0; background: #000; z-index: 10; }
  .header h1 { font-size: 18px; font-weight: 600; }

  .search-bar { display: flex; gap: 8px; padding: 0 16px; margin-bottom: 12px; }
  .search-bar input { flex: 1; background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
                       padding: 10px 14px; color: #fff; font-size: 14px; outline: none; }
  .search-bar input:focus { border-color: #0095f6; }
  .search-bar button { background: #0095f6; border: none; color: #fff; padding: 10px 16px;
                        border-radius: 8px; font-size: 14px; cursor: pointer; }

  .tags-bar { display: flex; gap: 6px; padding: 0 16px; margin-bottom: 12px; overflow-x: auto; flex-wrap: nowrap; }
  .tag-chip { background: #1a1a1a; border: 1px solid #333; border-radius: 16px; padding: 6px 12px;
              font-size: 12px; color: #ccc; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
  .tag-chip.active { background: #0095f6; border-color: #0095f6; color: #fff; }

  .filter-bar { display: flex; gap: 8px; padding: 0 16px; margin-bottom: 12px; }
  .filter-btn { background: none; border: 1px solid #333; border-radius: 16px; padding: 6px 12px;
                font-size: 12px; color: #888; cursor: pointer; }
  .filter-btn.active { border-color: #0095f6; color: #0095f6; }

  .upload-area { margin: 0 16px 12px; padding: 32px 20px; border: 2px dashed #333;
                 border-radius: 16px; text-align: center; cursor: pointer; }
  .upload-area:active { border-color: #0095f6; }
  .upload-area p { color: #888; font-size: 14px; margin-top: 8px; }

  .upload-meta { display: none; padding: 0 16px; margin-bottom: 8px; }
  .upload-meta input { width: 100%; background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
                        padding: 10px; color: #fff; font-size: 14px; margin-bottom: 6px; }
  .preview { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 16px; margin-bottom: 8px; justify-content: center; }
  .preview img { width: 72px; height: 72px; object-fit: cover; border-radius: 8px; }

  .btn { display: block; background: #0095f6; color: #fff; border: none; padding: 12px;
         border-radius: 8px; font-size: 16px; cursor: pointer; margin: 0 16px 16px; width: calc(100% - 32px); }
  .btn:disabled { background: #333; }

  .status { color: #0095f6; font-size: 14px; padding: 0 16px; text-align: center; margin-bottom: 8px; }
  .count { color: #888; font-size: 13px; padding: 0 16px; margin-bottom: 8px; }

  .photo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; padding: 0 2px; }
  .photo-cell { position: relative; aspect-ratio: 1; }
  .photo-cell img { width: 100%; height: 100%; object-fit: cover; }
  .photo-cell .posted-badge { position: absolute; top: 4px; right: 4px; background: #0095f6;
                               width: 8px; height: 8px; border-radius: 50%; }

  .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.95); z-index: 100;
           flex-direction: column; align-items: center; justify-content: center; }
  .modal.show { display: flex; }
  .modal img { max-width: 95%; max-height: 60vh; object-fit: contain; border-radius: 8px; }
  .modal-info { width: 90%; max-width: 400px; margin-top: 16px; }
  .modal-info input, .modal-info textarea { width: 100%; background: #1a1a1a; border: 1px solid #333;
    border-radius: 8px; padding: 10px; color: #fff; font-size: 14px; margin-bottom: 8px; resize: vertical; }
  .modal-actions { display: flex; gap: 8px; margin-top: 8px; }
  .modal-actions button { flex: 1; padding: 10px; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
  .modal-actions .save-btn { background: #0095f6; color: #fff; }
  .modal-actions .del-btn { background: #333; color: #e33; }
  .modal-actions .close-btn { background: #333; color: #fff; }
  .modal-meta { color: #888; font-size: 12px; margin-top: 8px; text-align: center; }

  input[type="file"] { display: none; }
</style>
</head>
<body>
<div class="header"><h1>insta-photos</h1></div>

<div class="search-bar">
  <input type="text" id="searchInput" placeholder="검색 (태그, 메모, 파일명...)">
  <button onclick="search()">검색</button>
</div>

<div class="tags-bar" id="tagsBar"></div>

<div class="filter-bar">
  <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">전체</button>
  <button class="filter-btn" data-filter="unposted" onclick="setFilter('unposted')">미게시</button>
  <button class="filter-btn" data-filter="posted" onclick="setFilter('posted')">게시됨</button>
</div>

<div class="upload-area" onclick="document.getElementById('fileInput').click()">
  <svg width="40" height="40" fill="none" stroke="#888" stroke-width="1.5" viewBox="0 0 24 24">
    <path d="M12 16V4m0 0L8 8m4-4l4 4M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4"/>
  </svg>
  <p>탭하여 사진 선택</p>
</div>
<input type="file" id="fileInput" multiple accept="image/*,video/*">
<div class="upload-meta" id="uploadMeta">
  <input type="text" id="uploadTags" placeholder="태그 (콤마로 구분: 작업, AI, 일상)">
  <input type="text" id="uploadMemo" placeholder="메모 (선택사항)">
</div>
<div class="preview" id="preview"></div>
<button class="btn" id="uploadBtn" disabled onclick="doUpload()">업로드</button>
<div class="status" id="status"></div>

<div class="count" id="count"></div>
<div class="photo-grid" id="grid"></div>

<!-- Detail modal -->
<div class="modal" id="modal">
  <img id="modalImg" src="">
  <div class="modal-info">
    <input type="text" id="modalTags" placeholder="태그">
    <textarea id="modalMemo" rows="2" placeholder="메모"></textarea>
  </div>
  <div class="modal-meta" id="modalMeta"></div>
  <div class="modal-actions" style="width:90%;max-width:400px;margin-top:12px;">
    <button class="save-btn" onclick="saveDetail()">저장</button>
    <button class="del-btn" onclick="deletePhoto()">삭제</button>
    <button class="close-btn" onclick="closeModal()">닫기</button>
  </div>
</div>

<script>
let files = [], currentFilter = 'all', currentQuery = '', currentPhotoId = null;

document.getElementById('fileInput').onchange = (e) => {
  files = Array.from(e.target.files);
  document.getElementById('uploadBtn').disabled = files.length === 0;
  document.getElementById('uploadMeta').style.display = files.length ? 'block' : 'none';
  const preview = document.getElementById('preview');
  preview.innerHTML = '';
  files.forEach(f => {
    if (f.type.startsWith('image/')) {
      const img = document.createElement('img');
      img.src = URL.createObjectURL(f);
      preview.appendChild(img);
    }
  });
};

async function doUpload() {
  const btn = document.getElementById('uploadBtn');
  btn.disabled = true; btn.textContent = '업로드 중...';
  const tags = document.getElementById('uploadTags').value;
  const memo = document.getElementById('uploadMemo').value;
  let ok = 0;
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    fd.append('tags', tags);
    fd.append('memo', memo);
    try { const r = await fetch('/upload', {method:'POST', body:fd}); if(r.ok) ok++; } catch(e) {}
  }
  document.getElementById('status').textContent = ok+'/'+files.length+'개 업로드 완료';
  btn.textContent = '업로드'; files = [];
  document.getElementById('fileInput').value = '';
  document.getElementById('preview').innerHTML = '';
  document.getElementById('uploadMeta').style.display = 'none';
  document.getElementById('uploadTags').value = '';
  document.getElementById('uploadMemo').value = '';
  loadPhotos(); loadTags();
}

function search() {
  currentQuery = document.getElementById('searchInput').value;
  loadPhotos();
}
document.getElementById('searchInput').onkeydown = (e) => { if(e.key==='Enter') search(); };

function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
  loadPhotos();
}

async function loadPhotos() {
  let url = '/photos?limit=99';
  if (currentQuery) url += '&q=' + encodeURIComponent(currentQuery);
  if (currentFilter === 'posted') url += '&posted=true';
  if (currentFilter === 'unposted') url += '&posted=false';
  const res = await fetch(url);
  const data = await res.json();
  document.getElementById('count').textContent = data.total + '장 (표시: ' + data.photos.length + ')';
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  data.photos.forEach(p => {
    const cell = document.createElement('div');
    cell.className = 'photo-cell';
    cell.onclick = () => openModal(p);
    const img = document.createElement('img');
    img.src = '/photo/' + p.id + '?thumb=true';
    img.loading = 'lazy';
    cell.appendChild(img);
    if (p.ig_posted) {
      const badge = document.createElement('div');
      badge.className = 'posted-badge';
      cell.appendChild(badge);
    }
    grid.appendChild(cell);
  });
}

async function loadTags() {
  const res = await fetch('/tags');
  const tags = await res.json();
  const bar = document.getElementById('tagsBar');
  bar.innerHTML = '';
  tags.slice(0, 15).forEach(([tag, count]) => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.textContent = tag + ' ' + count;
    chip.onclick = () => { document.getElementById('searchInput').value = tag; search(); };
    bar.appendChild(chip);
  });
}

function openModal(p) {
  currentPhotoId = p.id;
  document.getElementById('modalImg').src = '/photo/' + p.id;
  document.getElementById('modalTags').value = p.tags || '';
  document.getElementById('modalMemo').value = p.memo || '';
  const meta = (p.width && p.height ? p.width+'x'+p.height+' | ' : '')
    + (p.size ? Math.round(p.size/1024)+'KB | ' : '')
    + (p.created_at || '').slice(0,10)
    + (p.ig_posted ? ' | IG 게시됨' : '');
  document.getElementById('modalMeta').textContent = meta;
  document.getElementById('modal').classList.add('show');
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
  currentPhotoId = null;
}

async function saveDetail() {
  if (!currentPhotoId) return;
  await fetch('/photo/' + currentPhotoId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      tags: document.getElementById('modalTags').value,
      memo: document.getElementById('modalMemo').value,
    })
  });
  closeModal(); loadPhotos(); loadTags();
}

async function deletePhoto() {
  if (!currentPhotoId || !confirm('삭제할까요?')) return;
  await fetch('/photo/' + currentPhotoId, {method: 'DELETE'});
  closeModal(); loadPhotos(); loadTags();
}

loadPhotos(); loadTags();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8686)
