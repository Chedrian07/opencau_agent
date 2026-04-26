from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
import uuid


@dataclass(frozen=True)
class ScreenshotMetadata:
    shot_id: str
    session_id: str
    path: Path
    sha256: str
    ts: float

    @property
    def url(self) -> str:
        return f"/api/sessions/{self.session_id}/screenshots/{self.shot_id}.png"

    @property
    def thumb_url(self) -> str:
        return self.url


class ScreenshotStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def save_png(self, session_id: str, image: bytes) -> ScreenshotMetadata:
        shot_id = uuid.uuid4().hex
        session_dir = self._root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{shot_id}.png"
        path.write_bytes(image)
        return ScreenshotMetadata(
            shot_id=shot_id,
            session_id=session_id,
            path=path,
            sha256=hashlib.sha256(image).hexdigest(),
            ts=time.time(),
        )

    def path_for(self, session_id: str, shot_id: str) -> Path:
        return self._root / session_id / f"{shot_id}.png"
