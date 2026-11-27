#!/usr/bin/env python3
"""Backup archive creation, integrity validation, and retention pruning."""
from __future__ import annotations

import os
import subprocess
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional


def tar_error_message(stderr: str, returncode: int) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    useful = [line for line in lines if "Exiting with failure status" not in line]
    chosen = useful[-3:] if useful else lines[-2:]
    if chosen:
        return "；".join(chosen)
    return f"tar 退出码 {returncode}"


def backup_member_readable(backup_root: Path, relative: str) -> bool:
    path = backup_root / relative
    try:
        return path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def backup_include_list(
    backup_root: Path,
    required_members: Iterable[str],
    optional_members: Iterable[str],
) -> list[str]:
    required = list(required_members)
    missing = [
        relative for relative in required
        if not (backup_root / relative).exists()
    ]
    if missing:
        raise RuntimeError(f"备份缺少必需路径：{', '.join(missing)}")
    unreadable = [
        relative for relative in required
        if not backup_member_readable(backup_root, relative)
    ]
    if unreadable:
        raise RuntimeError(f"备份无法读取必需文件：{', '.join(unreadable)}")
    include = list(required)
    include.extend(
        relative for relative in optional_members
        if backup_member_readable(backup_root, relative)
    )
    return include


def validate_backup_archive(path: Path, required_members: Iterable[str]) -> None:
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = {member.name.rstrip("/"): member for member in archive.getmembers()}
    except (OSError, tarfile.TarError) as error:
        raise RuntimeError(f"备份归档无法读取：{error}") from error

    required = list(required_members)
    missing = [relative for relative in required if relative not in members]
    empty = [
        relative
        for relative in required
        if relative in members and members[relative].isfile() and members[relative].size == 0
    ]
    if missing or empty:
        details = []
        if missing:
            details.append(f"缺少 {', '.join(missing)}")
        if empty:
            details.append(f"空文件 {', '.join(empty)}")
        raise RuntimeError(f"备份完整性校验失败：{'; '.join(details)}")


def backup_retention_days(env: dict[str, str]) -> int:
    raw = str(env.get("BACKUP_RETENTION_DAYS", "14") or "14").strip()
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = 14
    return max(1, min(days, 3650))


def create_backup(
    *,
    backup_root: Path,
    backup_dir: Path,
    download_dir: Path,
    required_members: Iterable[str],
    optional_members: Iterable[str],
    retention_days: int,
    backup_lock: threading.Lock,
    validated_cache: dict[Path, tuple[int, int]],
    force: bool = False,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    validator: Optional[Callable[[Path], None]] = None,
) -> Optional[Path]:
    required = list(required_members)
    optional = list(optional_members)
    check_archive = validator or (lambda p: validate_backup_archive(p, required))

    with backup_lock:
        backup_dir.mkdir(parents=True, exist_ok=True)
        download_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        backup = backup_dir / f"hy2-aio-backup-{day}.tar.gz"
        if force:
            backup = backup_dir / datetime.now(timezone.utc).strftime(
                "hy2-aio-backup-%Y-%m-%d-%H%M%S-%f.tar.gz"
            )

        create = force or not backup.exists()
        if not create:
            stat = backup.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
            if validated_cache.get(backup) != fingerprint:
                try:
                    check_archive(backup)
                    validated_cache[backup] = fingerprint
                except RuntimeError:
                    backup.unlink()
                    validated_cache.pop(backup, None)
                    create = True

        if create:
            include = backup_include_list(backup_root, required, optional)
            temporary = Path(str(backup) + ".tmp")
            try:
                result = runner(
                    ["tar", "-czf", str(temporary), "-C", str(backup_root), *include],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    message = tar_error_message(result.stderr, result.returncode)
                    archive_ok = (
                        result.returncode == 1
                        and temporary.exists()
                        and temporary.stat().st_size > 0
                    )
                    if archive_ok:
                        try:
                            check_archive(temporary)
                        except RuntimeError as error:
                            raise RuntimeError(f"备份创建失败：{message}") from error
                    else:
                        raise RuntimeError(f"备份创建失败：{message}")
                if not temporary.exists() or temporary.stat().st_size == 0:
                    raise RuntimeError("备份创建失败：未生成有效归档")
                check_archive(temporary)
                os.chmod(temporary, 0o600)
                os.replace(temporary, backup)
                stat = backup.stat()
                validated_cache[backup] = (stat.st_mtime_ns, stat.st_size)
            except Exception:
                if temporary.exists():
                    temporary.unlink()
                raise

        # Never publish backups under WEB_DIR — they contain TLS keys and secrets.
        stale_web_backup = download_dir / "hy2-aio-backup-latest.tar.gz"
        if stale_web_backup.exists():
            try:
                stale_web_backup.unlink()
            except OSError:
                pass

        cutoff = time.time() - retention_days * 86400
        for path in backup_dir.glob("hy2-aio-backup-*.tar.gz"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                validated_cache.pop(path, None)
        return backup
