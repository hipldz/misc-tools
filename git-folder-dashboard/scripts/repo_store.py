from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4


class RepoStore:
    def __init__(self):
        self._repos: Dict[str, dict] = {}
        self._paths: Dict[str, Path] = {}

    def clear(self):
        self._repos.clear()
        self._paths.clear()

    def add(self, path: Path) -> str:
        repo_id = uuid4().hex
        self._paths[repo_id] = path
        return repo_id

    def update(self, repo_id: str, repo: dict):
        self._repos[repo_id] = repo

    def get_path(self, repo_id: str) -> Optional[Path]:
        return self._paths.get(repo_id)

    def all(self) -> List[dict]:
        return list(self._repos.values())

