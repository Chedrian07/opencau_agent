from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import time
import uuid


@dataclass(frozen=True)
class ScreenshotMetadata:
    shot_id: str
    session_id: str
    path: Path
    thumb_path: Path | None
    sha256: str
    size_bytes: int
    ts: float

    @property
    def url(self) -> str:
        return f"/api/sessions/{self.session_id}/screenshots/{self.shot_id}.png"

    @property
    def thumb_url(self) -> str:
        if self.thumb_path is None:
            return self.url
        return f"/api/sessions/{self.session_id}/screenshots/{self.shot_id}.webp"


class ScreenshotStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def save_png(self, session_id: str, image: bytes) -> ScreenshotMetadata:
        shot_id = uuid.uuid4().hex
        session_dir = self._root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{shot_id}.png"
        path.write_bytes(image)
        thumb_path = self._write_thumbnail(session_dir / f"{shot_id}.webp", image)
        return ScreenshotMetadata(
            shot_id=shot_id,
            session_id=session_id,
            path=path,
            thumb_path=thumb_path,
            sha256=hashlib.sha256(image).hexdigest(),
            size_bytes=len(image),
            ts=time.time(),
        )

    def path_for(self, session_id: str, shot_id: str) -> Path:
        return self._root / session_id / f"{shot_id}.png"

    def thumb_path_for(self, session_id: str, shot_id: str) -> Path:
        return self._root / session_id / f"{shot_id}.webp"

    def remove_paths(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        children = list(self._root.iterdir()) if self._root.exists() else []
        for child in children:
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass

    def _write_thumbnail(self, path: Path, image: bytes) -> Path | None:
        try:
            from PIL import Image
        except Exception:
            return None

        try:
            with Image.open(BytesIO(image)) as source:
                source.thumbnail((480, 270))
                if source.mode not in {"RGB", "RGBA"}:
                    source = source.convert("RGB")
                source.save(path, format="WEBP", quality=72)
            return path
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return None
