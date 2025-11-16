#!/usr/bin/env python3
"""
hyprpaper-randomizer.py

A self-contained Python wallpaper selector. Features:
- --cache : warm cache (classify images) and exit
- --back  : rewind wallpaper using history file
- --delete-cache : remove the sqlite cache and exit
- --wallpaper-dir : path to the directory containing wallpapers
- --max-depth : integer defining the maximum depth to follow when scanning
- Uses an SQLite cache to avoid repeated image header reads
- Skips any paths present in the history file
- Designed to be run from the devshell or as the installed wrapper (hyprpaper-randomizer)
"""

from pathlib import Path
import sqlite3
import hashlib
import os
import sys
import time
import random
import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from PIL import Image
except Exception:
    Image = None

# Config (can be overridden by CLI args)
WALLPAPER_DIR = Path.home() / "wallpapers"
HISTFILE = Path.home() / ".cache" / "wallpaper-history"
CACHE_DB = Path.home() / ".cache" / "wallpaper-ratio-cache.sqlite"
MAXHIST = 10
THROTTLE = Path("/tmp/wallpaper-throttle")
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def throttle():
    N = int(time.time())
    if THROTTLE.exists():
        try:
            prev = int(THROTTLE.read_text().strip() or "0")
        except Exception:
            prev = 0
        if (N - prev) < 1:
            sys.exit(0)
    THROTTLE.write_text(str(N))


def ensure_files():
    HISTFILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    HISTFILE.touch(exist_ok=True)


def open_db():
    conn = sqlite3.connect(str(CACHE_DB), timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, match INTEGER, width INTEGER, height INTEGER, path TEXT, mtime INTEGER, size INTEGER)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON cache(key)")
    return conn


def file_meta(path: Path):
    try:
        st = path.stat()
        return int(st.st_mtime), int(st.st_size)
    except Exception:
        return 0, 0


def file_key(path: Path):
    try:
        real = path.resolve()
    except Exception:
        real = path
    mtime, size = file_meta(real)
    s = f"{str(real)}|{mtime}:{size}"
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def cache_lookup(conn, path: Path):
    k = file_key(path)
    cur = conn.execute("SELECT match, width, height FROM cache WHERE key = ?", (k,))
    row = cur.fetchone()
    if row:
        return bool(row[0]), int(row[1]) if row[1] else None, int(row[2]) if row[2] else None
    return None


def cache_set(conn, path: Path, match: bool, w: int, h: int):
    k = file_key(path)
    mtime, size = file_meta(path)
    conn.execute(
        "INSERT OR REPLACE INTO cache(key, match, width, height, path, mtime, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (k, 1 if match else 0, int(w or 0), int(h or 0), str(path), mtime, size),
    )
    conn.commit()


def get_image_dimensions(path: Path):
    if Image is not None:
        try:
            with Image.open(path) as im:
                return im.width, im.height
        except Exception:
            pass

    try:
        out = subprocess.check_output(
            ["identify", "-ping", "-format", "%w %h", str(path)],
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        parts = out.decode("utf-8", "ignore").strip().split()
        if len(parts) == 2:
            w, h = int(parts[0]), int(parts[1])
            return w, h
    except Exception:
        pass

    return None


def is_acceptable_image(w, h):
    if not w or not h:
        return False
    return int(w) > int(h)


def load_history():
    if not HISTFILE.exists():
        return []
    return [line.rstrip("\n") for line in HISTFILE.read_text().splitlines() if line.strip()]


def write_history(lines):
    HISTFILE.write_text("\n".join(lines) + ("\n" if lines else ""))


def back_action():
    history = load_history()
    if len(history) < 2:
        print("No previous wallpaper in history.")
        subprocess.run(["notify-send", "Wallpaper", "No previous wallpaper in history."])
        sys.exit(1)
    prev = history[-2]
    newhist = history[:-1]
    write_history(newhist)
    subprocess.run(["hyprctl", "hyprpaper", "reload", f",contain:{prev}"])
    print("Loaded previous wallpaper:", prev)
    sys.exit(0)


def iter_images(maxdepth=2, followlinks=True):
    base = WALLPAPER_DIR
    if not base.exists():
        return
    base = base.resolve()

    # os.walk has a followlinks parameter; set it to True to traverse symlinked dirs.
    for root, dirs, files in os.walk(base, followlinks=followlinks):
        # When following symlinks, root.resolve() may point outside of base and
        # .relative_to(base) would raise. Compute relative path without resolving,
        # and fall back to treating external targets as "max depth" so we don't
        # recurse further from them.
        try:
            rel = Path(root).relative_to(base)
            depth = len(rel.parts) if rel.parts != ("",) else 0
        except Exception:
            # root is not a subpath of base (happens when following symlinked dirs).
            # Treat as deepest level to avoid descending further into subdirs.
            depth = maxdepth

        if depth >= maxdepth:
            dirs[:] = []

        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in EXTS:
                yield p


def populate_cache(skip_history=True, maxdepth=2):
    history_set = set(load_history()) if skip_history else set()
    conn = open_db()
    files = [p for p in iter_images(maxdepth=maxdepth) if str(p) not in history_set]
    total = len(files)
    added = 0
    existing = 0
    matched = 0
    nonmatched = 0

    # Process files serially to avoid using threads that might share the SQLite connection.
    for p in files:
        # If already cached, skip expensive work and count as existing.
        if cache_lookup(conn, p) is not None:
            existing += 1
            continue

        dims = get_image_dimensions(p)
        if not dims:
            # couldn't read image dims; record as non-match (0,0 stored)
            try:
                cache_set(conn, p, False, 0, 0)
            except Exception:
                pass
            added += 1
            nonmatched += 1
            continue

        w, h = dims
        m = is_acceptable_image(w, h)
        try:
            cache_set(conn, p, m, w, h)
        except Exception:
            pass
        added += 1
        if m:
            matched += 1
        else:
            nonmatched += 1

    conn.close()
    print("Cache population complete:")
    print("  scanned:", total)
    print("  existing:", existing)
    print("  added:", added)
    print("  matched:", matched)
    print("  nonmatch:", nonmatched)


def choose_random_wallpaper(maxdepth=2):
    conn = open_db()
    history_set = set(load_history())
    candidates = []
    for p in iter_images(maxdepth=maxdepth):
        sp = str(p)
        if sp in history_set:
            continue
        c = cache_lookup(conn, p)
        if c is not None:
            match, w, h = c
            if match:
                candidates.append(p)
    if candidates:
        conn.close()
        return random.choice(candidates)

    all_candidates = [p for p in iter_images(maxdepth=maxdepth) if str(p) not in history_set]
    if not all_candidates:
        conn.close()
        return None

    random.shuffle(all_candidates)
    for p in all_candidates:
        c = cache_lookup(conn, p)
        if c is not None:
            match, w, h = c
            if match:
                conn.close()
                return p
            else:
                continue
        dims = get_image_dimensions(p)
        if not dims:
            try:
                cache_set(conn, p, False, 0, 0)
            except Exception:
                pass
            continue
        w, h = dims
        if is_acceptable_image(w, h):
            try:
                cache_set(conn, p, True, w, h)
            except Exception:
                pass
            conn.close()
            return p
        else:
            try:
                cache_set(conn, p, False, w, h)
            except Exception:
                pass
    conn.close()
    return random.choice(all_candidates) if all_candidates else None


def apply_wallpaper(p: Path):
    subprocess.run(["hyprctl", "hyprpaper", "reload", f",contain:{str(p)}"])


def append_history_and_trim(path: Path):
    history = load_history()
    history.append(str(path))
    history = history[-MAXHIST:]
    write_history(history)


def parse_args():
    parser = argparse.ArgumentParser(description="hyprpaper-randomizer")
    parser.add_argument("--back", action="store_true", help="rewind wallpaper using history file")
    parser.add_argument("--cache", action="store_true", help="warm cache (classify images) and exit")
    parser.add_argument("--delete-cache", action="store_true", help="remove the cache and exit")
    parser.add_argument("--wallpaper-dir", type=str, help="path to the directory containing wallpapers")
    parser.add_argument("--max-depth", type=int, default=2, help="maximum depth to follow when scanning directories (default: 2)")
    return parser.parse_args()


def main():
    throttle()
    ensure_files()

    args = parse_args()

    # Override wallpaper directory if requested
    if args.wallpaper_dir:
        try:
            p = Path(args.wallpaper_dir).expanduser()
            # Don't require existence here; iter_images will skip if not present.
            globals()["WALLPAPER_DIR"] = p
        except Exception:
            print("Invalid wallpaper directory:", args.wallpaper_dir)
            sys.exit(2)

    # If requested, delete the sqlite cache and exit
    if args.delete_cache:
        try:
            if CACHE_DB.exists():
                CACHE_DB.unlink()
                print("Deleted cache:", CACHE_DB)
                subprocess.run(["notify-send", "Wallpaper", "Cache deleted"])
            else:
                print("Cache not found:", CACHE_DB)
                subprocess.run(["notify-send", "Wallpaper", "Cache not found"])
        except Exception as e:
            print("Failed to delete cache:", e)
            sys.exit(1)
        return

    if args.back:
        back_action()

    if args.cache:
        populate_cache(skip_history=True, maxdepth=args.max_depth)
        return

    choice = choose_random_wallpaper(maxdepth=args.max_depth)
    if choice is None:
        print(f"No wallpaper found in {WALLPAPER_DIR} (or all candidates are in history).")
        subprocess.run(["notify-send", "Wallpaper", f"No wallpaper found in {WALLPAPER_DIR}"])
        sys.exit(1)

    apply_wallpaper(choice)
    append_history_and_trim(choice)
    print("Loaded wallpaper:", choice)


if __name__ == "__main__":
    main()
