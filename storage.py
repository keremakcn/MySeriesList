"""Independent series library; episode progress is separate from catalog data."""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, date

STATUSES = ('Want to watch', 'Watching', 'On hold', 'Dropped', 'Completed')

def now():
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            version = c.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('Library requires a newer MySeriesList version.')
            if version == 1:
                backup = Path(self.path + '.before-v2.bak')
                if not backup.exists():
                    with sqlite3.connect(str(backup)) as destination:
                        c.backup(destination)
            c.executescript('''
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT NOT NULL,
                overview TEXT DEFAULT '', poster TEXT DEFAULT '', year TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Want to watch', note TEXT NOT NULL DEFAULT '',
                rating INTEGER CHECK(rating BETWEEN 1 AND 10), favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL, deleted_at TEXT);
            CREATE TABLE IF NOT EXISTS seasons (
                series_id INTEGER REFERENCES series(id), number INTEGER, name TEXT,
                loaded INTEGER DEFAULT 0, PRIMARY KEY(series_id,number));
            CREATE TABLE IF NOT EXISTS episodes (
                series_id INTEGER REFERENCES series(id), season INTEGER, number INTEGER,
                title TEXT, air_date TEXT, watched_at TEXT,
                PRIMARY KEY(series_id,season,number));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS series_active ON series(deleted_at,status);
            ''')
            columns = {r['name'] for r in c.execute('PRAGMA table_info(series)')}
            if 'metadata' not in columns:
                c.execute("ALTER TABLE series ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
            if 'progress_version' not in columns:
                c.execute('ALTER TABLE series ADD COLUMN progress_version INTEGER NOT NULL DEFAULT 0')
            c.execute('PRAGMA secure_delete=ON')
            c.execute("DELETE FROM settings WHERE key IN ('tmdb_token','tmdb_verified_hash','tmdb_verified_at')")
            c.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def query(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.connect() as c:
            c.execute(sql, args)

    def add(self, data):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('''INSERT INTO series(tmdb_id,title,overview,poster,year,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(tmdb_id) DO UPDATE SET deleted_at=NULL''',
                (data['id'], data.get('name') or 'Untitled series', data.get('overview') or '',
                 data.get('poster_path') or '', (data.get('first_air_date') or '')[:4], now()))
            sid = c.execute('SELECT id FROM series WHERE tmdb_id=?', (data['id'],)).fetchone()[0]
            self._catalog(c, sid, data)
            return sid

    def _catalog(self, c, sid, data):
        metadata = {key: data.get(key) for key in (
            'genres', 'number_of_episodes', 'number_of_seasons', 'status', 'vote_average',
            'created_by', 'networks', 'credits', 'credits_complete', 'last_air_date', 'tagline')}
        c.execute('UPDATE series SET title=?,overview=?,poster=?,year=?,metadata=? WHERE id=?',
                  (data.get('name') or 'Untitled series', data.get('overview') or '',
                   data.get('poster_path') or '', (data.get('first_air_date') or '')[:4], json.dumps(metadata), sid))
        for season in data.get('seasons', []):
            c.execute('''INSERT INTO seasons(series_id,number,name) VALUES(?,?,?)
                ON CONFLICT(series_id,number) DO UPDATE SET name=excluded.name''',
                (sid, season['season_number'], season.get('name') or 'Season'))

    def refresh(self, sid, data):
        with self.connect() as c:
            self._catalog(c, sid, data)

    def save_season(self, sid, number, data):
        with self.connect() as c:
            self._save_season(c, sid, number, data)

    def _save_season(self, c, sid, number, data):
        for ep in data.get('episodes', []):
            c.execute('''INSERT INTO episodes(series_id,season,number,title,air_date)
                VALUES(?,?,?,?,?) ON CONFLICT(series_id,season,number) DO UPDATE SET
                title=excluded.title,air_date=excluded.air_date''',
                (sid, number, ep['episode_number'], ep.get('name') or 'Episode', ep.get('air_date')))
        c.execute('UPDATE seasons SET loaded=1 WHERE series_id=? AND number=?', (sid, number))

    def save_journal(self, sid, status, rating, note, favorite, expected_version, catalog=None, seasons=None):
        """Completion and journal edits commit together, only after all remote reads succeed."""
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            item = c.execute('SELECT * FROM series WHERE id=? AND deleted_at IS NULL', (sid,)).fetchone()
            if not item or item['progress_version'] != expected_version:
                raise ValueError('Progress changed in another window. Reload before saving; your changes have not been applied.')
            if catalog is not None:
                self._catalog(c, sid, catalog)
                for number, data in seasons.items():
                    self._save_season(c, sid, number, data)
                c.execute('''UPDATE episodes SET watched_at=? WHERE series_id=? AND watched_at IS NULL
                    AND air_date IS NOT NULL AND air_date<=?''', (now(), sid, date.today().isoformat()))
            c.execute('''UPDATE series SET status=?,rating=?,note=?,favorite=?,
                progress_version=progress_version+1 WHERE id=?''', (status, rating, note, favorite, sid))

    def progress(self, sid, season, episode, watched):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            ep = c.execute('SELECT * FROM episodes WHERE series_id=? AND season=? AND number=?',
                           (sid, season, episode)).fetchone()
            if not ep:
                raise ValueError('Load this season first.')
            if watched and (not ep['air_date'] or ep['air_date'] > date.today().isoformat()):
                raise ValueError('This episode has no confirmed past or current air date.')
            self._progress(c, sid, season, episode, watched, ep)

    def _progress(self, c, sid, season, episode, watched, ep):
        if bool(ep['watched_at']) != watched:
            c.execute('UPDATE episodes SET watched_at=? WHERE series_id=? AND season=? AND number=?',
                      (now() if watched else None, sid, season, episode))
            c.execute('UPDATE series SET progress_version=progress_version+1 WHERE id=?', (sid,))
            if watched:
                c.execute("UPDATE series SET status='Watching' WHERE id=? AND status='Want to watch'", (sid,))
            else:
                c.execute("UPDATE series SET status='Watching' WHERE id=? AND status='Completed'", (sid,))

    def mark_next(self, sid, expected_version):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            item = c.execute('SELECT progress_version FROM series WHERE id=? AND deleted_at IS NULL', (sid,)).fetchone()
            if not item or item['progress_version'] != expected_version:
                return None
            ep = c.execute('''SELECT * FROM episodes WHERE series_id=? AND season>0
                AND watched_at IS NULL AND air_date IS NOT NULL AND air_date<=?
                ORDER BY season,number LIMIT 1''', (sid, date.today().isoformat())).fetchone()
            if ep:
                self._progress(c, sid, ep['season'], ep['number'], True, ep)
                return dict(ep)
            return None
