#!/usr/bin/env python3
"""用真 mihomo / sing-box 内核双向验证国内直连与海外代理分流。

用法（可只传 mihomo、只传 sing-box，或两者同跑）：
    python tools/verify-domestic-routing.py --mihomo ./mihomo --config sub.yaml
    python tools/verify-domestic-routing.py --singbox ./sing-box --singbox-config sub.json
    python tools/verify-domestic-routing.py --mihomo ./mihomo --config sub.yaml \\
        --singbox ./sing-box --singbox-config sub.json

验收矩阵：
  1. CRITICAL_DOMESTIC_DOMAINS → 两端必须命中 DIRECT / direct
  2. CRITICAL_OVERSEAS_DOMAINS → 两端必须命中 PROXY / proxy（防止国内 CDN IP 抢跑直连）
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from test_domestic_coverage import (  # noqa: E402
    CRITICAL_DOMESTIC_DOMAINS,
    CRITICAL_OVERSEAS_DOMAINS,
)


def _probe_domains(proxy_port: int, domains: list[str]) -> None:
    proxy = f"http://127.0.0.1:{proxy_port}"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )
    for domain in domains:
        try:
            opener.open(f"https://{domain}/", timeout=5).read(1)
        except Exception:
            pass  # 连通性不重要，只看内核日志里的命中路由


def verify_mihomo(bin_path: str, config_path: str, port: int, api_port: int) -> int:
    import yaml

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["mixed-port"] = port
    cfg["external-controller"] = f"127.0.0.1:{api_port}"
    cfg["tun"] = {"enable": False}

    workdir = tempfile.mkdtemp(prefix="mihomo-verify-")
    cfg_path = os.path.join(workdir, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    log_path = os.path.join(workdir, "mihomo.log")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [bin_path, "-d", workdir, "-f", cfg_path],
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            time.sleep(1)
            with open(log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "Mixed(http+socks) proxy listening" in text:
                ready = True
                break
            if "fatal" in text.lower():
                print("mihomo 启动失败:\n" + text[-2000:])
                return 1
        if not ready:
            print("mihomo 120 秒未就绪")
            return 1

        time.sleep(15)
        all_domains = list(CRITICAL_DOMESTIC_DOMAINS) + list(CRITICAL_OVERSEAS_DOMAINS)
        _probe_domains(port, all_domains)
        time.sleep(3)

        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()

        hits = {}
        for m in re.finditer(r"--> ([\w.\-]+):\d+ match ([^ ]+) using (\S+)", log):
            hits.setdefault(m.group(1), (m.group(2), m.group(3)))

        return _report("mihomo", hits, direct_token="DIRECT", proxy_token="PROXY")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()


def verify_singbox(bin_path: str, config_path: str, port: int) -> int:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["log"] = {"level": "debug"}
    cfg["inbounds"] = [
        {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": port}
    ]
    workdir = tempfile.mkdtemp(prefix="singbox-verify-")
    cfg_path = os.path.join(workdir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    check = subprocess.run(
        [bin_path, "check", "-c", cfg_path], capture_output=True, text=True, check=False
    )
    if check.returncode != 0:
        print("sing-box check 失败:\n" + check.stderr[-2000:])
        return 1

    log_path = os.path.join(workdir, "singbox.log")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [bin_path, "run", "-D", workdir, "-c", cfg_path],
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 90
        ready = False
        while time.time() < deadline:
            time.sleep(1)
            with open(log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "sing-box started" in text:
                ready = True
                break
            if "FATAL" in text:
                print("sing-box 启动失败:\n" + text[-2000:])
                return 1
        if not ready:
            print("sing-box 90 秒未就绪")
            return 1

        time.sleep(10)
        all_domains = list(CRITICAL_DOMESTIC_DOMAINS) + list(CRITICAL_OVERSEAS_DOMAINS)
        _probe_domains(port, all_domains)
        time.sleep(3)

        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()

        # 匹配类似: outbound/direct[direct]: outbound connection to www.baidu.com:443
        # 或 outbound/hysteria2[🇯🇵 HY2-alice]: outbound connection to www.youtube.com:443
        hits = {}
        for m in re.finditer(
            r"outbound/([^\[]+)\[([^\]]+)\]:.*?(?:connection to|packet connection to)\s+([\w.\-]+):\d+",
            log,
        ):
            otype, otag, dom = m.group(1), m.group(2), m.group(3)
            hits.setdefault(dom, (otype, otag))

        return _report("sing-box", hits, direct_token="direct", proxy_token="proxy")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()


def _report(engine: str, hits: dict, *, direct_token: str, proxy_token: str) -> int:
    failed = 0
    print("=" * 72)
    print(f"[{engine}] 国内直连验证 — {len(CRITICAL_DOMESTIC_DOMAINS)} 个")
    print("=" * 72)
    for domain in CRITICAL_DOMESTIC_DOMAINS:
        h = hits.get(domain)
        if h is None:
            print(f"  FAIL {domain:<34} 未产生请求")
            failed += 1
            continue
        rule, out = h
        if direct_token.lower() in out.lower() or direct_token.lower() in rule.lower():
            print(f"  OK   {domain:<34} {rule:<20} {out}")
        else:
            print(f"  FAIL {domain:<34} {rule:<20} {out}  <- 应直连却走代理")
            failed += 1

    print("=" * 72)
    print(f"[{engine}] 海外代理验证 — {len(CRITICAL_OVERSEAS_DOMAINS)} 个")
    print("=" * 72)
    for domain in CRITICAL_OVERSEAS_DOMAINS:
        h = hits.get(domain)
        if h is None:
            print(f"  FAIL {domain:<34} 未产生请求")
            failed += 1
            continue
        rule, out = h
        is_direct = direct_token.lower() in out.lower() or direct_token.lower() == rule.lower()
        if not is_direct:
            print(f"  OK   {domain:<34} {rule:<20} {out}")
        else:
            print(f"  FAIL {domain:<34} {rule:<20} {out}  <- 海外域名被判直连")
            failed += 1

    print()
    print(f"[{engine}] 失败项：{failed}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo", default="")
    ap.add_argument("--config", default="")
    ap.add_argument("--singbox", default="")
    ap.add_argument("--singbox-config", default="")
    ap.add_argument("--port", type=int, default=7899)
    ap.add_argument("--api-port", type=int, default=9099)
    args = ap.parse_args()

    if not args.mihomo and not args.singbox:
        ap.error("至少需要指定 --mihomo 或 --singbox 之一")

    rc = 0
    if args.mihomo:
        if not args.config:
            ap.error("指定 --mihomo 时必须同时提供 --config")
        rc |= verify_mihomo(args.mihomo, args.config, args.port, args.api_port)
    if args.singbox:
        if not args.singbox_config:
            ap.error("指定 --singbox 时必须同时提供 --singbox-config")
        rc |= verify_singbox(args.singbox, args.singbox_config, args.port + 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
