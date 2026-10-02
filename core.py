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
    authorizations = body.get('authorizations') or []
    envelope_team = body.get('team_id') or e.get('team')
    if not envelope_team and authorizations:
        envelope_team = authorizations[0].get('team_id')
    return (envelope_team == TEAM and e.get('user') == KAAN
            and not e.get('bot_id') and not e.get('subtype')
            and e.get('type') in {'message', 'app_mention'}
            and (e.get('channel') in managed or e.get('channel_type') == 'im')
            and isinstance(e.get('ts'), str) and bool(e.get('text', '').strip()))


def event_key(e):
    return e['channel'] + ':' + e['ts']


def relative_delay_seconds(text):
    match = re.search(r'\b(\d{1,3})\s*(dakika|dk|saat)\s+sonra\b', text.lower())
    if not match:
        return None
    amount = int(match.group(1))
    multiplier = 3600 if match.group(2) == 'saat' else 60
    seconds = amount * multiplier
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
