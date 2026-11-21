#!/usr/bin/env python3
"""用真 mihomo 内核验证关键国内域名是否命中直连。

用法（需先有 mihomo 二进制 + 一份可用的订阅 YAML）：
    python tools/verify-domestic-routing.py --mihomo ../mihomo-test/mihomo.exe --config sub.yaml

它做的事：
  1. 起一个临时 mihomo（独立端口、tun 关闭）
  2. 逐个访问 CRITICAL_DOMESTIC_DOMAINS
  3. 读 mihomo 日志里每个域名的命中规则
  4. 命中 DIRECT（GeoSite/GeoIP/RuleSet）→ PASS
     命中 PROXY/Match → FAIL（说明该域名会被绕道国外）

这才是"不靠用户报障"的验证方式 —— 新增关键域名进 tests/test_domestic_coverage.py
的清单，跑一次就知道覆盖没覆盖。
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from test_domestic_coverage import CRITICAL_DOMESTIC_DOMAINS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int, default=7899)
    ap.add_argument("--api-port", type=int, default=9099)
    args = ap.parse_args()

    import yaml

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["mixed-port"] = args.port
    cfg["external-controller"] = "127.0.0.1:%d" % args.api_port
    cfg["tun"] = {"enable": False}

    workdir = tempfile.mkdtemp(prefix="mihomo-verify-")
    cfg_path = os.path.join(workdir, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    log_path = os.path.join(workdir, "mihomo.log")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [args.mihomo, "-d", workdir, "-f", cfg_path],
        stdout=logf, stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.time() + 40
        ready = False
        while time.time() < deadline:
            time.sleep(1)
            with open(log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "Mixed(http+socks) proxy listening" in text:
                ready = True
                break
            if "fatal" in text.lower():
                print("mihomo 启动失败:")
                print(text[-2000:])
                return 1
        if not ready:
            print("mihomo 40 秒未就绪:")
            with open(log_path, encoding="utf-8", errors="replace") as f:
                print(f.read()[-2000:])
            return 1

        # 再等规则集下载完（geosite.dat 首次下载）
        time.sleep(8)

        proxy = "http://127.0.0.1:%d" % args.port
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        for domain in CRITICAL_DOMESTIC_DOMAINS:
            try:
                opener.open("https://%s/" % domain, timeout=6).read(1)
            except Exception:
                pass  # 连通性不重要，只看命中规则

        time.sleep(3)

        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()

        hits = {}
        for m in re.finditer(r"--> ([\w.\-]+):\d+ match ([^ ]+) using (\S+)", log):
            dom, rule, out = m.group(1), m.group(2), m.group(3)
            hits.setdefault(dom, (rule, out))

        passed, failed = [], []
        for domain in CRITICAL_DOMESTIC_DOMAINS:
            h = hits.get(domain)
            if h is None:
                failed.append((domain, "未产生请求", "-"))
                continue
            rule, out = h
            (passed if "DIRECT" in out else failed).append((domain, rule, out))

        print("=" * 70)
        print("关键国内域名分流验证 — %d 个" % len(CRITICAL_DOMESTIC_DOMAINS))
        print("=" * 70)
        for d, r, o in passed:
            print("  OK   %-30s %-26s %s" % (d, r, o))
        for d, r, o in failed:
            print("  FAIL %-30s %-26s %s  <- 会被绕道代理" % (d, r, o))
        print()
        print("通过 %d / %d" % (len(passed), len(CRITICAL_DOMESTIC_DOMAINS)))
        if failed:
            print("失败 %d 个 —— 需要补规则或检查数据源" % len(failed))
            return 1
        print("全部命中国内直连")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()


if __name__ == "__main__":
    sys.exit(main())