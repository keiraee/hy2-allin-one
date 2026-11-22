#!/usr/bin/env python3
"""用真 mihomo 验证 china-ip 规则集覆盖度 —— 不靠人肉发现漏网 IP。

用法:
    python tools/verify-ip-coverage.py --mihomo <二进制> --config <订阅yaml>

它会:
  1. 起临时 mihomo(独立端口, 关 tun)
  2. 逐个访问 IP 清单里的国内 IP(清单在 tests/test_domestic_coverage.py)
  3. 读日志命中规则,必须 DIRECT
  4. 任何 IP 命中 PROXY → FAIL,并列出是哪条规则漏了

为什么需要它:
  域名清单可以穷举(有 geosite 11 万条),但 **IP 段无法凭直觉判断覆盖**。
  微信/抖音 CDN 大量用纯 IP 直连,漏一个段就绕道代理、图片转圈。
  靠用户报障才发现是打地鼠;这个工具把它变成开箱验收。
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
from test_domestic_coverage import CRITICAL_DOMESTIC_IPS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int, default=7908)
    ap.add_argument("--api-port", type=int, default=9108)
    args = ap.parse_args()

    import yaml

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["mixed-port"] = args.port
    cfg["external-controller"] = "127.0.0.1:%d" % args.api_port
    cfg["tun"] = {"enable": False}

    workdir = tempfile.mkdtemp(prefix="mihomo-ipverify-")
    cfg_path = os.path.join(workdir, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    log_path = os.path.join(workdir, "mihomo.log")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([args.mihomo, "-d", workdir, "-f", cfg_path],
                            stdout=logf, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 120
        ok = False
        while time.time() < deadline:
            time.sleep(1)
            with open(log_path, encoding="utf-8", errors="replace") as f:
                txt = f.read()
            if "Mixed(http+socks) proxy listening" in txt:
                ok = True
                break
            if "fatal" in txt.lower():
                print("mihomo 启动失败:\n" + txt[-2000:])
                return 1
        if not ok:
            print("mihomo 120 秒未就绪:\n" + open(log_path, encoding="utf-8", errors="replace").read()[-2000:])
            return 1
        time.sleep(15)  # 等规则集下载完成

        proxy = "http://127.0.0.1:%d" % args.port
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        for ip in CRITICAL_DOMESTIC_IPS:
            try:
                opener.open("http://%s/" % ip, timeout=4).read(1)
            except Exception:
                pass
        time.sleep(3)

        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()

        hits = {}
        for m in re.finditer(r"--> ([\d.]+):\d+ match ([^ ]+) using (\S+)", log):
            hits.setdefault(m.group(1), (m.group(2), m.group(3)))

        passed, failed, unknown = [], [], []
        for ip in CRITICAL_DOMESTIC_IPS:
            h = hits.get(ip)
            if h is None:
                unknown.append(ip)
                continue
            (passed if "DIRECT" in h[1] else failed).append((ip, h[0], h[1]))

        print("=" * 68)
        print("国内 IP 覆盖验证 — %d 个" % len(CRITICAL_DOMESTIC_IPS))
        print("=" * 68)
        for ip, rule, out in passed:
            print("  OK   %-16s %-24s %s" % (ip, rule, out))
        for ip, rule, out in failed:
            print("  FAIL %-16s %-24s %s  <- 绕道代理" % (ip, rule, out))
        for ip in unknown:
            print("  ?    %-16s 未产生连接(测试目标不可达,不代表未覆盖)" % ip)
        print()
        print("通过 %d / %d" % (len(passed), len(CRITICAL_DOMESTIC_IPS)))
        if failed:
            print("失败 %d 个 —— china-ip 规则集需要换更全的数据源" % len(failed))
            return 1
        print("全部命中国内直连" if not unknown else "已覆盖的 IP 全部直连")
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
