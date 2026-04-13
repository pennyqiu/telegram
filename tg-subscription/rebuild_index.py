"""重建 Redis 中的播客索引（从 /audio/ 目录扫描 MP3 文件）"""
import redis, json, re
from pathlib import Path

r = redis.from_url("redis://redis:6379/0", decode_responses=True)
audio_dir = Path("/audio")
episodes = []

for mp3 in sorted(audio_dir.glob("*.mp3")):
    name = mp3.stem

    ep_match = re.search(r'ep(\d+)$', name)
    if ep_match:
        num = ep_match.group(1)
        title = f"Episode {num}"
        date = f"ep{num}"
        url = f"https://rationalreminder.ca/podcast/{num}"
    else:
        date_part = re.sub(r'^rational_reminder_', '', name).replace('_', ' ').strip()
        title = f"Rational Reminder — {date_part}"
        date = date_part
        url = "https://rationalreminder.ca/podcast"

    episodes.append({
        "id": name,
        "source": "rational_reminder",
        "source_name": "Rational Reminder",
        "title": title,
        "date": date,
        "original_url": url,
        "mp3_file": mp3.name,
        "summary_preview": "",
        "created_at": "2026-04-12",
    })

r.set("podcast_episodes_index", json.dumps(episodes, ensure_ascii=False))
print(f"rebuilt: {len(episodes)} episodes")
for e in episodes:
    print(f"  {e['mp3_file']}")
