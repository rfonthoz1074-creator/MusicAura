"""
database.py - Módulo de persistencia local en SQLite para AuraMusic Android.
Gestiona favoritos, historial y registro de canciones descargadas o reproducidas.
"""

import sqlite3
import os
from typing import List, Dict, Optional

class MusicDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            try:
                from kivy.app import App
                app = App.get_running_app()
                base_dir = app.user_data_dir if app else "."
            except Exception:
                base_dir = "."
            self.db_path = os.path.join(base_dir, "auramusic.db")
        else:
            self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS favorites (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration INTEGER DEFAULT 0,
                thumbnail_url TEXT,
                genre TEXT DEFAULT 'Pop',
                year TEXT DEFAULT '2024',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration INTEGER DEFAULT 0,
                thumbnail_url TEXT,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.commit()

    def add_favorite(self, video_id: str, title: str, artist: str, duration: int = 0, thumbnail_url: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""INSERT OR REPLACE INTO favorites 
                (video_id, title, artist, duration, thumbnail_url) 
                VALUES (?, ?, ?, ?, ?)""",
                (video_id, title, artist, duration, thumbnail_url))
            conn.commit()

    def remove_favorite(self, video_id: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM favorites WHERE video_id = ?", (video_id,))
            conn.commit()

    def is_favorite(self, video_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM favorites WHERE video_id = ?", (video_id,))
            return c.fetchone() is not None

    def get_favorites(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT video_id, title, artist, duration, thumbnail_url FROM favorites ORDER BY added_at DESC")
            return [dict(row) for row in c.fetchall()]

    def add_history(self, video_id: str, title: str, artist: str, duration: int = 0, thumbnail_url: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""INSERT INTO history (video_id, title, artist, duration, thumbnail_url) 
                         VALUES (?, ?, ?, ?, ?)""",
                      (video_id, title, artist, duration, thumbnail_url))
            conn.commit()
