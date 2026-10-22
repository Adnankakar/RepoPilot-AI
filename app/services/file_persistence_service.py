"""
file_persistence_service.py

Persists RepositoryFile metadata records and RepositoryFileSkip records
for a completed discovery run.

Only metadata is stored — path, size, extension, encoding, and the
nullable fields (blob_hash, language, commit_sha) that are populated by
later pipeline stages.  No file content is written to the database.
"""

import logging
from sqlalchemy.orm import Session

from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.services.file_discovery_service import DiscoveryResult

logger = logging.getLogger(__name__)


def persist_discovered_files(
    db: Session,
    repository_id: str,
    discovery: DiscoveryResult,
) -> int:
    """
    Insert a RepositoryFile row for every file in *discovery*.

    Uses the caller's session — no commit is issued here so the caller
    can combine this write with other changes in one transaction.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    repository_id:
        Primary key of the owning Repository row.
    discovery:
        Result returned by discover_files().

    Returns
    -------
    int
        Number of rows added to the session.
    """
    for f in discovery.files:
        db.add(
            RepositoryFile(
                repository_id=repository_id,
                path=f.relative_path,
                size_bytes=f.size_bytes,
                extension=f.extension,
                encoding=f.encoding,
                # Populated by later pipeline stages; null at discovery time.
                blob_hash=None,
                language=None,
                commit_sha=None,
            )
        )

    for s in discovery.skipped:
        db.add(
            RepositoryFileSkip(
                repository_id=repository_id,
                path=s.relative_path,
                reason=s.reason,
            )
        )

    file_count = len(discovery.files)
    skip_count = len(discovery.skipped)
    logger.info(
        "Queued %d file metadata records and %d skip records for repository %s",
        file_count,
        skip_count,
        repository_id,
    )
    return file_count
