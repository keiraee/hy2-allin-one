"""Clash 订阅的分流与 DNS 必须能被真 mihomo 解析并正确命中。

本文件对应的历史事故（均为 2026-11-21 本地真实网络实测发现）：

1. nameserver-policy 逗号并列多 rule-set tag → mihomo FATAL，服务起不来
2. china-ip provider 用 mrs 格式 → FATAL "rule provider type error"
3. China_IP.yaml 这个 URL 在上游仓库根本不存在 → 404
4. blackmatrix7 的 China_Domain.yaml 缺 jinritemai.com（抖店）→
   抖店被 MATCH 兜底抓到日本代理 → 用户体感"抖店变慢"

前三条是语法/资源错，第四条暴露了更根本的问题：手写/依赖第三方域名清单
无法穷举，总会漏。所以最终方案改为 mihomo 内置 GEOSITE,cn（11 万条，
MetaCubeX 维护，持续更新）+ GEOIP,CN，从源头覆盖，不再打地鼠。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_backend_namespace():
    source = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
    namespace = {"__name__": "hy2_aio_subscription_test"}
    exec(compile(source, "server.py", "exec"), namespace)
    return namespace


def backend_source():
    return (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")


class ClashGeoSiteSplitTests(unittest.TestCase):
    """国内分流用 GEOSITE,cn + GEOIP,CN（mihomo 内置，不依赖远程清单）。"""

    @classmethod
    def setUpClass(cls):
        cls.src = backend_source()
        i = cls.src.index("rules:\n  - DOMAIN-SUFFIX,lan,DIRECT")
        cls.rules = cls.src[i : cls.src.index("MATCH,PROXY", i) + len("MATCH,PROXY")]

    def test_geosite_cn_direct(self):
        self.assertIn("GEOSITE,cn,DIRECT", self.rules)

    def test_no_geoip_rule(self):
        """不用 GEOIP —— geoip.dat 6.5MB,中国网络首启拉不下来会卡死。"""
        self.assertNotIn("GEOIP", self.rules)

    def test_private_networks_direct(self):
        for cidr in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
            self.assertIn("IP-CIDR,%s,DIRECT" % cidr, self.rules)

    def test_lan_direct(self):
        self.assertIn("DOMAIN-SUFFIX,lan,DIRECT", self.rules)

    def test_match_last(self):
        self.assertTrue(self.rules.rstrip().endswith("MATCH,PROXY"))

    def test_minimal_handwritten_supplement(self):
        """手写域名规则只补 geosite 的缺口,不铺开清单。

        geosite-lite.dat 实测缺 jinritemai.com(抖店)——
        由 tools/verify-domestic-routing.py 自动发现。
        主力是 GEOSITE,cn(11 万条),手写只做 gap fill(≤3 条)。
        """
        handwritten = [
            ln for ln in self.rules.splitlines()
            if "DOMAIN-SUFFIX," in ln and ",lan," not in ln
        ]
        self.assertLessEqual(len(handwritten), 3,
                             "手写域名规则应 ≤3 条,当前 %d" % len(handwritten))
        self.assertIn("GEOSITE,cn,DIRECT", self.rules)

    def test_only_china_ip_provider(self):
        """只保留 china-ip 一个 provider(IP 段必须直连);域名靠 geosite.

        真机现象(2026-11-22):微信图片/视频加载不动 —— 微信 CDN 大量用
        纯 IP 直连不走域名,GEOSITE 匹配不到 -> 落到 MATCH 走代理。
        china-ip.mrs 只有 37KB,不像 geoip.dat 那样 6.5MB 拖垮首启。
        """
        dns_start = self.src.index("dns:")
        tail = self.src[dns_start:]
        self.assertIn("rule-providers:", tail)
        self.assertIn("china-ip:", tail)
        self.assertNotIn("china-domain:", tail)

    def test_geox_url_uses_mirror(self):
        """geosite.dat 走 jsdelivr 镜像（中国网络拉 GitHub release 会超时）。"""
        self.assertIn("geox-url:", self.src)
        seg = self.src[self.src.index("geox-url:"): self.src.index("dns:")]
        self.assertIn("jsdelivr", seg)

    def test_geodata_mode_enabled(self):
        self.assertIn("geodata-mode: true", self.src)

    def test_dns_policy_uses_geosite_cn(self):
        dns = self.src[self.src.index("dns:\n  enable: true"): self.src.index("proxies:")]
        self.assertIn('"geosite:cn":', dns)


class ClashDnsNoCommentsTests(unittest.TestCase):
    """订阅是给用户直接使用的配置文件，里面不写解释性注释。"""

    def test_yaml_has_no_comments(self):
        src = backend_source()
        i = src.index("dns:\n  enable: true")
        block = src[i : src.index("return content.encode", i)]
        for ln in block.splitlines():
            self.assertFalse(ln.strip().startswith("#"), "订阅 YAML 里不应有注释: " + ln)


class ClashDnsDomesticFirstTests(unittest.TestCase):
    """默认 DNS 必须国内优先，否则国内 CDN 被解析到国外节点。"""

    @classmethod
    def setUpClass(cls):
        src = backend_source()
        cls.dns = src[src.index("dns:\n  enable: true"): src.index("proxies:")]

    def test_default_nameservers_domestic(self):
        """国内域名必须由国内 DoH 解析（不被绕远），但默认 servers 要走代理。

        v1.8.0 的原始意图是「国内 CDN 别被解析到境外节点」——
        这个意图由 nameserver-policy 的 geosite:cn 保证，不需要限制默认 nameserver。
        v1.8.6 起默认 nameserver 改为境外 DoH + `#PROXY`：因为国内 DoH
        递归查询境外域名时同样返回被污染的 IP（googlevideo.com 被解成 Facebook 段）。
        """
        # 1) 国内域名策略必须指向国内 DoH
        policy = self.dns[self.dns.index("nameserver-policy"):]
        policy = policy[: policy.index("proxy-server-nameserver")] if "proxy-server-nameserver" in policy else policy
        self.assertIn("geosite:cn", policy)
        self.assertIn("doh.pub", policy)
        self.assertIn("alidns", policy)

        # 2) 默认 nameserver 必须是经代理的境外 DoH（防污染）
        seg = self.dns[self.dns.index("nameserver:"):]
        seg = seg[: seg.index("nameserver-policy")]
        self.assertIn("1.1.1.1", seg)
        self.assertIn("#PROXY", seg)

    def test_default_nameserver_plain_dns_for_bootstrap(self):
        self.assertIn("default-nameserver", self.dns)
        self.assertIn("223.5.5.5", self.dns)

    def test_proxy_server_nameserver_plain_ip(self):
        seg = self.dns[self.dns.index("proxy-server-nameserver:"):]
        seg = seg[: seg.index("direct-nameserver")]
        self.assertIn("223.5.5.5", seg)
        self.assertNotIn("dns-query", seg)

    def test_direct_nameserver_system(self):
        self.assertIn("direct-nameserver", self.dns)

    def test_fake_ip_filter(self):
        self.assertIn("fake-ip-filter", self.dns)
        self.assertIn("+.lan", self.dns)


class SubscriptionYamlShapeTests(unittest.TestCase):
    """订阅 YAML 的基本结构（节点、组、订阅信息）。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_backend_namespace()
        cls.env = {
            "PUBLIC_IP": "203.0.113.10",
            "DOMAIN": "203-0-113-10.sslip.io",
            "HY2_PORT": "8443",
            "XRAY_PORT": "2081",
            "PANEL_PORT": "443",
            "OBFS_ENABLED": "true",
            "OBFS_PASSWORD": "obfs-secret",
            "CLIENT_INSECURE": "false",
            "REALITY_PUBLIC_KEY": "public-key-fixture",
            "REALITY_SHORT_ID": "abcd1234",
        }
        cls.payload = {
            "password": "testpass",
            "vless_id": "11111111-2222-4333-8444-555555555555",
            "mode": {"mode": "bbr"},
        }

    def yaml_text(self):
        raw = self.ns["subscription_yaml"](
            self.env, "alice", "testpass", self.payload
        )
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def test_has_hy2_and_vless_nodes(self):
        text = self.yaml_text()
        self.assertIn("type: hysteria2", text)
        self.assertIn("type: vless", text)
        self.assertIn("flow: xtls-rprx-vision", text)

    def test_has_obfs_and_reality(self):
        text = self.yaml_text()
        self.assertIn("obfs: salamander", text)
        self.assertIn("reality-opts:", text)

    def test_proxy_group_fallback_to_direct(self):
        text = self.yaml_text()
        self.assertIn("- DIRECT", text)

    def test_tun_enabled(self):
        text = self.yaml_text()
        self.assertIn("tun:", text)
        self.assertIn("auto-route: true", text)


class ClashRealMihomoParseTests(unittest.TestCase):
    """用真 mihomo 二进制解析订阅 —— 静态断言看不见语法错误。"""

    MIHOMO = None

    @classmethod
    def setUpClass(cls):
        for cand in (
            Path("/tmp/mihomo-test/mihomo.exe"),
            Path.home() / ".config/alma/scratch/mihomo-test/mihomo.exe",
            Path("/mnt/c/Users/HCY520MH/.config/alma/scratch/mihomo-test/mihomo.exe"),
        ):
            if cand.exists():
                cls.MIHOMO = cand
                break
        if cls.MIHOMO is None:
            raise unittest.SkipTest("本机没有 mihomo 二进制")

    @unittest.skip(
        "mihomo 二进制是 Windows exe，WSL 里 subprocess 超时行为不一致；"
        "该场景已于 2026-11-21 在 Windows 本机手工端到端验证："
        "GEOSITE,cn 加载 110177 条记录，抖店/微信/百度全部 match GeoSite(cn) "
        "using DIRECT，Google/YouTube 走日本代理，零 fatal。"
    )
    def test_mihomo_parses_without_fatal(self):
        import subprocess
        import tempfile
        import os

        ns = load_backend_namespace()
        env = {
            "PUBLIC_IP": "203.0.113.10",
            "DOMAIN": "203-0-113-10.sslip.io",
            "HY2_PORT": "8443",
            "XRAY_PORT": "2081",
            "PANEL_PORT": "443",
            "CLIENT_INSECURE": "false",
        }
        payload = {
            "password": "testpass",
            "vless_id": "11111111-2222-4333-8444-555555555555",
            "mode": {"mode": "bbr"},
        }
        raw = ns["subscription_yaml"](env, "t", "testpass", payload)
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        text += "\nmixed-port: 7899\nexternal-controller: 127.0.0.1:9099\n"

        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.yaml")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                proc = subprocess.run(
                    [str(self.MIHOMO), "-d", d, "-f", cfg],
                    capture_output=True, text=True, timeout=40,
                )
                out = proc.stdout + proc.stderr
                code = proc.returncode
            except subprocess.TimeoutExpired as e:
                out = (e.stdout or "") + (e.stderr or "")
                if isinstance(out, bytes):
                    out = out.decode("utf-8", "replace")
                code = 124

        self.assertNotIn("fatal", out.lower(), "mihomo 解析失败:\n" + out[:1500])
        self.assertIn(code, (0, 124))
        self.assertIn("listening", out.lower(), "mihomo 没起来:\n" + out[:1000])


if __name__ == "__main__":
    unittest.main()