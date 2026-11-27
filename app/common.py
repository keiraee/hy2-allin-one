#!/usr/bin/env python3
"""Shared pure helpers for HY2 AIO Python components (server, rebuild, access)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def truthy(value: Any, default: bool = False) -> bool:
    if value is True:
        return True
    if value is False:
        return False
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def user_is_disabled(info: Any) -> bool:
    if not isinstance(info, dict):
        return False
    value = info.get("disabled", False)
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def obfs_enabled(env: dict[str, str]) -> bool:
    return truthy(env.get("OBFS_ENABLED", "true"), default=True)


def port_hop_enabled(env: dict[str, str]) -> bool:
    return truthy(env.get("PORT_HOP_ENABLED", "false"), default=False)


def port_hop_ports(env: dict[str, str]) -> str:
    """端口跳跃范围；无效时返回空串，订阅/直链退回单端口，别把坏配置发出去。"""
    if not port_hop_enabled(env):
        return ""
    try:
        base = int(str(env.get("HY2_PORT") or "8443"))
    except ValueError:
        return ""
    raw = str(env.get("PORT_HOP_RANGE") or "").strip()
    if not raw:
        raw = f"{base}-{min(base + 1000, 65535)}"
    match = re.fullmatch(r"([0-9]{1,5})-([0-9]{1,5})", raw)
    if not match:
        return ""
    start, end = int(match.group(1)), int(match.group(2))
    if start != base or end <= start or end > 65535 or end - start > 2000:
        return ""
    return f"{start}-{end}"


def port_hop_interval(env: dict[str, str]) -> str:
    raw = str(env.get("PORT_HOP_INTERVAL") or "30").strip()
    if raw.isdigit() and 5 <= int(raw) <= 3600:
        return str(int(raw))
    return "30"


def resolve_xray_port(env: dict[str, str]) -> int:
    raw = str(env.get("XRAY_PORT") or "").strip()
    if raw:
        return int(raw)
    hy2 = str(env.get("HY2_PORT") or "8443")
    panel = str(env.get("PANEL_PORT") or "443")
    if hy2 != panel:
        return int(hy2)
    if panel != "8443":
        return 8443
    return 443


def xray_port(env: dict[str, str]) -> str:
    return str(resolve_xray_port(env))


def client_insecure(env: dict[str, str]) -> bool:
    """订阅里要不要带 insecure / skip-cert-verify。"""
    raw = str(env.get("CLIENT_INSECURE", "")).strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    domain = str(env.get("DOMAIN", "")).strip()
    public_ip = str(env.get("PUBLIC_IP", "")).strip()
    return bool(domain) and domain == public_ip


def subscription_sni(env: dict[str, str]) -> str:
    """订阅里给客户端的 SNI：有域名就用域名（证书 SAN），纯 IP 才退回自定义 SNI 或 IP。"""
    explicit = str(env.get("SNI") or "").strip()
    domain = str(env.get("DOMAIN") or "").strip()
    public_ip = str(env.get("PUBLIC_IP") or "").strip()
    if domain and domain != public_ip:
        return domain
    return explicit or public_ip


def public_base_url(env: dict[str, str]) -> str:
    """Panel/subscription base URL (always HTTPS)."""
    domain = str(env.get("DOMAIN", "") or "")
    port = str(env.get("PANEL_PORT", "443") or "443")
    if port in ("443", ""):
        return f"https://{domain}"
    return f"https://{domain}:{port}"


def country_code_to_flag(code: str) -> str:
    cc = str(code or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(127397 + ord(ch)) for ch in cc)


REALITY_DEST_DEFAULT = "www.apple.com:443"


def reality_dest(env: dict[str, str]) -> str:
    return (
        str(env.get("REALITY_DEST") or REALITY_DEST_DEFAULT).strip()
        or REALITY_DEST_DEFAULT
    )


def reality_server_name(env: dict[str, str]) -> str:
    names = str(env.get("REALITY_SERVER_NAMES") or "").strip()
    if names:
        return names.split(",")[0].strip()
    dest = reality_dest(env)
    return dest.rsplit(":", 1)[0]


def atomic_bytes(path: Path, data: bytes, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, data: Any) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_bytes(path, content)
