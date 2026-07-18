import json
import os
import fcntl
from pathlib import Path

class State:
    def __init__(self, state_file_path):
        self.filepath = Path(state_file_path)
        self.data = {
            "processed_videos": {},
            "saved_skills": {}
        }
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        self.data = json.load(f)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                print(f"Error loading state file: {e}. Starting fresh.")
                self.data = {
                    "processed_videos": {},
                    "saved_skills": {}
                }
        else:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self._save_locked()

    def save(self):
        self._save_locked()
        
    def _save_locked(self):
        # We need to make sure the file exists before locking, or lock on 'a+'
        if not self.filepath.exists():
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
                
        with open(self.filepath, "r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.truncate()
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def is_video_processed(self, video_id):
        self.load()
        return video_id in self.data.get("processed_videos", {})

    def mark_video_processed(self, video_id, metadata):
        self._update_locked(self._mark_processed_callback, video_id, metadata)

    def _mark_processed_callback(self, data, video_id, metadata):
        if "processed_videos" not in data:
            data["processed_videos"] = {}
        data["processed_videos"][video_id] = metadata

    def get_video_metadata(self, video_id):
        self.load()
        return self.data.get("processed_videos", {}).get(video_id)

    def record_synthesized_skill(self, skill_name, video_ids, metadata=None):
        self._update_locked(self._record_synthesized_callback, skill_name, video_ids, metadata)

    def _record_synthesized_callback(self, data, skill_name, video_ids, metadata):
        if "saved_skills" not in data:
            data["saved_skills"] = {}
        data["saved_skills"][skill_name] = {
            "video_ids": video_ids,
            "metadata": metadata or {}
        }
        # Update each video's status to synthesized
        for vid in video_ids:
            if vid in data.get("processed_videos", {}):
                data["processed_videos"][vid]["status"] = "synthesized"
                data["processed_videos"][vid]["synthesized_skill_name"] = skill_name

    def _update_locked(self, callback, *args):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        # Touch file if not exists
        if not self.filepath.exists():
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"processed_videos": {}, "saved_skills": {}}, f, indent=2)
                
        with open(self.filepath, "r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                content = f.read()
                data = json.loads(content) if content else {"processed_videos": {}, "saved_skills": {}}
                
                callback(data, *args)
                
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2, ensure_ascii=False)
                self.data = data # update in-memory as well
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
