import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from core import *

class PolicyTests(unittest.TestCase):
    def body(self):
        return {'team_id':TEAM, 'event':{'type':'message', 'user':KAAN, 'channel':OPERATIONS, 'ts':'1789929318.067389', 'text':'Önceliğimiz nedir?'}}

    def test_allowed_and_rejected_sources(self):
        b = self.body()
        self.assertTrue(accepted(b))
        for patch in [{'user':'OTHER'}, {'bot_id':'BOT'}, {'subtype':'message_changed'}, {'channel':'OTHER'}]:
            changed = self.body()
            changed['event'].update(patch)
            self.assertFalse(accepted(changed))
        b['team_id'] = 'OTHER'
        self.assertFalse(accepted(b))

    def test_timestamp_and_dedup_survive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d)/'test.db')
            e = self.body()['event']
            key = event_key(e)
            self.assertTrue(key.endswith('1789929318.067389'))
            self.assertTrue(Store(path).enqueue(key, e))
            self.assertFalse(Store(path).enqueue(key, dict(e, type='app_mention')))
            s = Store(path)
            self.assertEqual(s.next()[1]['ts'], e['ts'])
            s.state(key, 'sending', 'response')
            self.assertIsNone(Store(path).next())

    def test_istanbul_schedule_and_sunday(self):
        self.assertEqual(schedule(datetime(2026,9,21,10,0,tzinfo=TZ))[2], 'morning')
        self.assertEqual(schedule(datetime(2026,9,21,18,0,tzinfo=TZ))[2], 'evening')
        self.assertIsNone(schedule(datetime(2026,9,20,10,0,tzinfo=TZ)))
        self.assertIsNone(schedule(datetime(2026,9,21,9,0,tzinfo=TZ)))

if __name__ == '__main__':
    unittest.main()
