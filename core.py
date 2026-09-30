"""Pure policy and durable queue; no network or credentials at import time."""
import json
import os
import sqlite3
from datetime import datetime
import re
from zoneinfo import ZoneInfo

KAAN = 'U0C31EU2ULV'
TEAM = 'T0C40NM35DE'
OPERATIONS = 'C0C36ANFXQS'
REPORTS = 'C0C2R2EJJ79'
APPROVALS = 'C0C36A6CHR8'
SUPPORT = 'C0C36ASERD0'
# Kaan + Ece's private working room. Individual department workers join as
# their own Slack apps when each has a separately authorized bot identity.
ACTIVE_DEPARTMENTS = 'C0C3K46MGBC'
CHANNELS = {OPERATIONS, REPORTS, APPROVALS, SUPPORT, ACTIVE_DEPARTMENTS}
DEPARTMENT_CHANNELS = {
    'C0C2R2F9LKH', 'C0C2R2GUCF9', 'C0C306K536X', 'C0C306VT3A7',
    'C0C306X2CE7', 'C0C31G6KFKP', 'C0C31G7V52R', 'C0C34EAHR8E',
    'C0C3A3CJVGU', 'C0C3A3FNY0L', 'C0C40Q16NJU',
}
ALL_CONTEXT_CHANNELS = CHANNELS | DEPARTMENT_CHANNELS
TZ = ZoneInfo('Europe/Istanbul')

def accepted(body):
    e = body.get('event', {})
    raw_channels = os.getenv('MANAGED_CHANNELS', '')
    managed = {item.strip() for item in raw_channels.split(',') if item.strip()} or CHANNELS
    return (body.get('team_id') == TEAM and e.get('user') == KAAN
            and not e.get('bot_id') and not e.get('subtype')
            and e.get('type') in {'message', 'app_mention'}
            and (e.get('channel') in managed or e.get('channel_type') == 'im')
            and isinstance(e.get('ts'), str) and bool(e.get('text', '').strip()))

def event_key(e):
    # An app_mention and message event can represent the same message.
    return e['channel'] + ':' + e['ts']

def relative_delay_seconds(text):
    """Return a short Turkish relative delay, if the sender explicitly requested one."""
    match = re.search(r'\b(\d{1,3})\s*(dakika|dk|saat)\s+sonra\b', text.lower())
    if not match:
        return None
    amount = int(match.group(1))
    multiplier = 3600 if match.group(2) == 'saat' else 60
    seconds = amount * multiplier
    # Keep ad-hoc Slack scheduling bounded; long recurring scheduling needs an explicit setup.
    return seconds if 60 <= seconds <= 8 * 3600 else None

def schedule(now):
    now = now.astimezone(TZ)
    if now.weekday() == 6:
        return None
    if (now.hour, now.minute) == (10, 0):
        return ('morning:' + now.date().isoformat(), OPERATIONS, 'morning')
    if (now.hour, now.minute) == (18, 0):
        return ('evening:' + now.date().isoformat(), REPORTS, 'evening')
    return None

class Store:
    def __init__(self, path):
        self.path = path
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT, state TEXT, output TEXT, error TEXT, created TEXT, due TEXT)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'due' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN due TEXT')

    def db(self):
        return sqlite3.connect(self.path, timeout=20)

    def enqueue(self, key, payload, due=None):
        with self.db() as db:
            return db.execute("INSERT OR IGNORE INTO jobs (id,payload,state,output,error,created,due) VALUES (?,?,'pending',NULL,NULL,?,?)", (key, json.dumps(payload, ensure_ascii=False), datetime.now(TZ).isoformat(), due)).rowcount == 1

    def next(self):
        with self.db() as db:
            row = db.execute("SELECT id,payload,output FROM jobs WHERE state='pending' AND (due IS NULL OR due<=?) ORDER BY COALESCE(due,created), created LIMIT 1", (datetime.now(TZ).isoformat(),)).fetchone()
        return (row[0], json.loads(row[1]), row[2]) if row else None

    def state(self, key, state, output=None, error=None):
        with self.db() as db:
            db.execute('UPDATE jobs SET state=?,output=COALESCE(?,output),error=? WHERE id=?', (state, output, error, key))

    def recent(self):
        with self.db() as db:
            rows = db.execute('SELECT id,payload,state,output FROM jobs ORDER BY created DESC LIMIT 30').fetchall()
        return [{'id':r[0], 'request':json.loads(r[1]), 'delivery_state':r[2], 'reply':r[3]} for r in reversed(rows)]

    def active_work(self):
        """Return the earliest real queued work item, never an invented availability state."""
        with self.db() as db:
            rows = db.execute("SELECT id,payload,due,state FROM jobs WHERE state IN ('pending','prepared','sending') ORDER BY COALESCE(due,created), created LIMIT 20").fetchall()
        for key, raw, due, state in rows:
            payload = json.loads(raw)
            if payload.get('kind') in {'delayed_reply', 'working_reply'}:
                return {'id': key, 'payload': payload, 'due': due, 'state': state}
        return None
