"""Freezes repository implementation."""
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from domain.interfaces import IFreezesRepository


class FreezesRepository(IFreezesRepository):
    """JSON-based auto-reply freezes repository."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._freezes: Dict[int, float] = {}
        self._load()
    
    def _load(self) -> None:
        """Load freezes from JSON file."""
        try:
            if not self.file_path.exists():
                return
            
            raw = self.file_path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            self._freezes.clear()
            now = time.time()
            
            for k, ts in data.items():
                try:
                    uid = int(k)
                    tsv = float(ts)
                    if tsv > now:
                        self._freezes[uid] = tsv
                except Exception:
                    continue
        except Exception:
            logging.exception("Failed to load freezes from JSON")
    
    def _save(self) -> None:
        """Save freezes to JSON file."""
        try:
            data = {str(uid): ts for uid, ts in self._freezes.items()}
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            logging.exception("Failed to save freezes to JSON")
    
    def _cleanup(self, now: Optional[float] = None) -> None:
        """Remove expired freezes."""
        if now is None:
            now = time.time()
        
        expired = [uid for uid, ts in self._freezes.items() if ts <= now]
        changed = False
        for uid in expired:
            if self._freezes.pop(uid, None) is not None:
                changed = True
        
        if changed:
            self._save()
    
    def set_freeze(self, user_id: int, hours: int) -> float:
        """Set freeze for user. Returns expiration timestamp."""
        expires_at = time.time() + hours * 3600
        self._freezes[user_id] = expires_at
        self._save()
        return expires_at
    
    def get_freeze(self, user_id: int) -> Optional[float]:
        """Get freeze expiration timestamp."""
        self._cleanup()
        expires_at = self._freezes.get(user_id)
        if expires_at is None:
            return None
        if expires_at <= time.time():
            self._freezes.pop(user_id, None)
            return None
        return expires_at
    
    def clear_freeze(self, user_id: int) -> bool:
        """Clear freeze. Returns True if freeze was removed."""
        removed = self._freezes.pop(user_id, None) is not None
        if removed:
            self._save()
        return removed
    
    def is_frozen(self, user_id: int) -> bool:
        """Check if user is frozen."""
        return self.get_freeze(user_id) is not None

