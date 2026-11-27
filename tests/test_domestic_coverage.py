"""国内分流覆盖度自动验证 —— 不靠人工发现漏规则。

背景(2026-11-21):
  抖店 fxg.jinritemai.com 不在 blackmatrix7 的 China_Domain.yaml 里,
  被 MATCH 兜底抓到日本代理 → 用户体感变慢。这是"遇见一个才知道漏一个"
  的典型。微信图片发不出去也是同类问题(sing-box 没有国内分流)。

解决思路:
  1. 不再手写/依赖第三方零散域名清单 → 改用 MetaCubeX geosite(dat/srs)
     这份数据 11 万条,持续更新,覆盖抖音/抖店/微信/小红书等。
  2. 用【真内核】验证覆盖度(本文件),关键域名必须命中国内直连。
  3. 兜底:GEOIP,CN 按 IP 判断,即使域名没在 geosite 里,解析出的
     国内 IP 也会直连 —— 双保险。

本文件的核心价值:关键域名清单成代码,新域名往这里加,而不是靠用户报障。
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 必须国内直连的关键域名(用户实际反馈过 / 高频国内服务)
CRITICAL_DOMESTIC_DOMAINS = [
    # 抖音生态(小k 报障:抖店)
    "fxg.jinritemai.com",        # 抖店商家后台
    "www.jinritemai.com",
    "buyin.jinritemai.com",
    "www.douyin.com",
    "www.iesdouyin.com",
    # 抖音搜索/封面走 CDN 域名(2026-11-23 小k 报障:搜索加载不出)
    "api.amemv.com",             # 抖音业务 API
    "aweme.snssdk.com",          # 抖音接口
    "p3.douyinpic.com",          # 抖音图片 CDN
    "v3.douyinvod.com",          # 抖音视频 CDN
    # 微信生态(小k 报障:iOS sing-box 图片发不出)
    "long.open.weixin.qq.com",
    "mp.weixin.qq.com",
    "szshort.weixin.qq.com",
    "dns.weixin.qq.com",
    # 常用国内服务
    "www.baidu.com",
    "www.taobao.com",
    "www.bilibili.com",
    "www.zhihu.com",
    "www.jd.com",
    "www.12306.cn",
    "www.qq.com",
    "mail.qq.com",
    "www.aliyun.com",
    "www.tencent.com",
    # 字节其他
    "www.toutiao.com",
    "www.ixigua.com",
    "www.feishu.cn",
    # 小红书(2026-11-23 小k 报障:评论区头像加载慢)
    "www.xiaohongshu.com",
    "sns-webpic-qc.xhscdn.com",  # 小红书图片/头像 CDN
]

# 必须走代理的海外关键域名（防止被国内 CDN IP 抢跑直连或 DNS 污染）
CRITICAL_OVERSEAS_DOMAINS = [
    "www.youtube.com",
    "rr5---sn-a5msenes.googlevideo.com",
    "www.google.com",
    "api.openai.com",
    "chatgpt.com",
    "telegram.org",
    "github.com",
]

# 必须国内直连的国内 IP（不依赖域名解析，微信/抖音 CDN 大量直接用 IP）
CRITICAL_DOMESTIC_IPS = [
    "183.61.35.28",     # 微信图片 CDN (Tencent)
    "203.205.254.36",   # 微信 mmtls 长连接
    "101.32.104.4",     # 腾讯云
    "140.205.94.189",   # 阿里
]


class DomesticCoverageSourceTests(unittest.TestCase):
    """Clash (.mrs) 与 sing-box (.srs) 必须共享同一套 MetaCubeX 二进制规则集。

    不再混用裁剪版 geosite-lite.dat 与全量 .srs，确保两端命中集合逐条一致。
    """

    @classmethod
    def setUpClass(cls):
        import json
        import sys
        import yaml

        sys.path.insert(0, str(ROOT / "app"))
        import subscription

        cls.src = (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")
        env = {
            "PUBLIC_IP": "203.0.113.10",
            "DOMAIN": "example.test",
            "HY2_PORT": "8443",
            "OBFS_ENABLED": "false",
        }
        cls.clash_text = subscription.subscription_yaml(env, "alice", "pw", {}).decode("utf-8")
        cls.clash = yaml.safe_load(cls.clash_text)
        cls.singbox = json.loads(
            subscription.subscription_singbox(env, "alice", "pw", {}).decode("utf-8")
        )

    def test_clash_and_singbox_share_identical_ruleset_tags(self):
        """Clash .mrs 与 sing-box .srs 必须 1:1 对齐 4 组同源规则集。"""
        clash_tags = list(self.clash["rule-providers"].keys())
        sb_tags = [rs["tag"] for rs in self.singbox["route"]["rule_set"]]
        expected = ["geosite-private", "geosite-cn", "geosite-geolocation-!cn", "geoip-cn"]
        self.assertEqual(expected, clash_tags)
        self.assertEqual(expected, sb_tags)
        for tag, prov in self.clash["rule-providers"].items():
            self.assertEqual("mrs", prov["format"], tag)
        for rs in self.singbox["route"]["rule_set"]:
            self.assertEqual("binary", rs["format"], rs["tag"])

    def test_has_china_ip_ruleset(self):
        """纯 IP 流量也要直连 —— 微信/抖音 CDN 大量用 IP 直连不走域名。"""
        self.assertIn("RULE-SET,geoip-cn,DIRECT", self.clash["rules"])
        self.assertEqual("ipcidr", self.clash["rule-providers"]["geoip-cn"]["behavior"])
        self.assertEqual("mrs", self.clash["rule-providers"]["geoip-cn"]["format"])

    def test_no_geoip_or_geosite_dat_download(self):
        """不使用 .dat 全量文件（避免首启下载大包及 lite 裁剪差异）。"""
        self.assertNotIn("geodata-mode:", self.clash_text)
        self.assertNotIn("geosite-lite.dat", self.clash_text)
        for rule in self.clash["rules"]:
            self.assertFalse(rule.startswith("GEOIP,"), rule)
            self.assertFalse(rule.startswith("GEOSITE,"), rule)

    def test_custom_direct_suffixes_synced_to_both_engines(self):
        """手写直连补充域名（如 jinritemai.com / lan / local）必须双端同步。"""
        sb_domain_rules = [
            r for r in self.singbox["route"]["rules"] if "domain_suffix" in r and r.get("outbound") == "direct"
        ]
        sb_suffixes = set()
        for r in sb_domain_rules:
            sb_suffixes.update(r["domain_suffix"])
        for suffix in ("lan", "local", "jinritemai.com"):
            self.assertIn(f"DOMAIN-SUFFIX,{suffix},DIRECT", self.clash["rules"])
            self.assertIn(suffix, sb_suffixes)

    def test_ruleset_urls_prefer_same_origin_vps_and_fallback_for_bare_ip(self):
        """有受信 HTTPS 域名时规则集走 VPS 同源 /rules/*；裸 IP 自签证书回退镜像。"""
        import json
        import sys
        import yaml

        sys.path.insert(0, str(ROOT / "app"))
        import subscription

        for prov in self.clash["rule-providers"].values():
            self.assertTrue(prov["url"].startswith("https://example.test/rules/"), prov["url"])
        for rs in self.singbox["route"]["rule_set"]:
            self.assertTrue(rs["url"].startswith("https://example.test/rules/"), rs["url"])

        # 自定义面板端口也应带端口
        env_port = {
            "PUBLIC_IP": "203.0.113.10",
            "DOMAIN": "example.test",
            "PANEL_PORT": "8443",
            "HY2_PORT": "8443",
            "OBFS_ENABLED": "false",
        }
        sb_port = json.loads(subscription.subscription_singbox(env_port, "alice", "pw", {}).decode("utf-8"))
        self.assertTrue(sb_port["route"]["rule_set"][0]["url"].startswith("https://example.test:8443/rules/"))

        # 裸 IP 自签证书：自动回退公共镜像，避免严格校验客户端报 x509 错误
        env_ip = {
            "PUBLIC_IP": "203.0.113.10",
            "DOMAIN": "203.0.113.10",
            "HY2_PORT": "8443",
            "OBFS_ENABLED": "false",
        }
        clash_ip = yaml.safe_load(subscription.subscription_yaml(env_ip, "alice", "pw", {}).decode("utf-8"))
        sb_ip = json.loads(subscription.subscription_singbox(env_ip, "alice", "pw", {}).decode("utf-8"))
        for prov in clash_ip["rule-providers"].values():
            self.assertIn("jsdelivr", prov["url"])
            self.assertNotIn("raw.githubusercontent.com", prov["url"])
        for rs in sb_ip["route"]["rule_set"]:
            self.assertIn("jsdelivr", rs["url"])
            self.assertNotIn("raw.githubusercontent.com", rs["url"])

    def test_caddy_and_backend_serve_rules_directory(self):
        """Caddy 暴露免鉴权 /rules/* 静态优先 + 后端按需回源，拒绝路径穿越。"""
        import io
        import tempfile

        cfg_sh = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        self.assertIn("handle /rules/*", cfg_sh)
        self.assertIn("@rules_cached file", cfg_sh)

        src = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
        ns = {"__name__": "hy2_rules_test"}
        exec(compile(src, "server.py", "exec"), ns)

        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "rules"
            rules_dir.mkdir()
            payload = b"SRS\x01" + b"\x00" * 64
            (rules_dir / "geosite-cn.srs").write_bytes(payload)
            ns["RULES_DIR"] = rules_dir

            class StubHandler:
                command = "GET"
                def __init__(self, path):
                    self.path = path
                    self.status = None
                    self.headers_out = {}
                    self.wfile = io.BytesIO()
                def send_response(self, code):
                    self.status = code
                def send_header(self, k, v):
                    self.headers_out[k] = v
                def end_headers(self):
                    pass
                def send_error(self, code):
                    self.status = code

            # 1) 命中本地缓存直接 200
            h_ok = StubHandler("/rules/geosite-cn.srs")
            ns["Handler"].send_ruleset(h_ok, "geosite-cn.srs")
            self.assertEqual(200, h_ok.status)
            self.assertEqual(payload, h_ok.wfile.getvalue())

            # 2) 非白名单/路径穿越一律 404
            h_bad = StubHandler("/rules/../config.env")
            ns["Handler"].send_ruleset(h_bad, "../config.env")
            self.assertEqual(404, h_bad.status)

            # 3) 缓存缺失且离线拉取失败时 302 回退镜像
            ns["fetch_ruleset_bytes"] = lambda _name: None
            h_miss = StubHandler("/rules/geoip-cn.mrs")
            ns["Handler"].send_ruleset(h_miss, "geoip-cn.mrs")
            self.assertEqual(302, h_miss.status)
            self.assertIn("jsdelivr", h_miss.headers_out.get("Location", ""))


class CriticalDomainListTests(unittest.TestCase):
    """关键域名清单是一份显式的验收标准(不是靠用户报障才发现)。"""

    def test_critical_list_is_nonempty(self):
        self.assertGreater(len(CRITICAL_DOMESTIC_DOMAINS), 15)

    def test_list_covers_reported_issues(self):
        """用户实际报障过的场景必须在清单里。"""
        self.assertIn("fxg.jinritemai.com", CRITICAL_DOMESTIC_DOMAINS)  # 抖店
        self.assertIn("long.open.weixin.qq.com", CRITICAL_DOMESTIC_DOMAINS)  # 微信

    def test_no_duplicates(self):
        self.assertEqual(
            len(CRITICAL_DOMESTIC_DOMAINS),
            len(set(CRITICAL_DOMESTIC_DOMAINS)),
        )
        self.assertEqual(
            len(CRITICAL_OVERSEAS_DOMAINS),
            len(set(CRITICAL_OVERSEAS_DOMAINS)),
        )

    def test_overseas_list_nonempty_and_disjoint_from_domestic(self):
        self.assertGreaterEqual(len(CRITICAL_OVERSEAS_DOMAINS), 5)
        self.assertIn("www.youtube.com", CRITICAL_OVERSEAS_DOMAINS)
        self.assertFalse(set(CRITICAL_DOMESTIC_DOMAINS) & set(CRITICAL_OVERSEAS_DOMAINS))


class DomainBeforeIpRuleOrderTests(unittest.TestCase):
    """域名规则必须挡在 IP 规则之前 —— 否则海外域名会被 IP 误判成直连。

    真机 2026-11-25（小k 的 macOS sing-box 日志）：唯一一条 ERROR 是
      ERROR ... dial tcp 118.193.240.37:443: i/o timeout
    追上去发现该 IP 是 `rr5.sn-qja5mc-5q.googlevideo.com` 的解析结果
    —— YouTube CDN 在国内的缓存节点（联通陕西）。

    根因：sing-box 规则曾经写成
      {"rule_set": ["geosite-cn", "geoip-cn"], "outbound": "direct"}
    `rule_set` 数组是 **OR** 关系：geoip-cn 命中就直接直连，
    **域名判断被完全绕过**。于是「海外域名 + 国内 CDN IP」全被判成直连，
    YouTube 视频起播就 5 秒超时。Clash 那份 `GEOSITE,cn,DIRECT` +
    `RULE-SET,china-ip,DIRECT` 是同一个坑。

    修法：拆成三条，域名优先 —— 国内域名直连 → 海外域名代理 → 纯 IP 兜底。
    这一组用例就是防止以后有人图省事把规则合并回去。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")

    def test_singbox_rules_are_not_merged(self):
        """不能合并成 ["geosite-cn", "geoip-cn"] 一条（OR 会让 IP 抢跑域名）。"""
        self.assertNotIn('"rule_set": ["geosite-cn", "geoip-cn"]', self.src)

    def test_singbox_overseas_domain_rule_before_geoip(self):
        """geolocation-!cn 必须出现在 geoip-cn 直连规则之前。"""
        i_overseas = self.src.find('"rule_set": ["geosite-geolocation-!cn"], "outbound": "proxy"')
        i_geoip = self.src.find('"rule_set": ["geoip-cn"], "outbound": "direct"')
        self.assertGreater(i_overseas, 0, "缺少海外域名 → 代理 的规则")
        self.assertGreater(i_geoip, 0, "缺少 geoip-cn 直连规则")
        self.assertLess(i_overseas, i_geoip, "海外域名规则必须排在 geoip-cn 之前")

    def test_singbox_has_overseas_ruleset(self):
        import json
        import sys
        sys.path.insert(0, str(ROOT / "app"))
        import subscription
        env = {"PUBLIC_IP": "203.0.113.10", "DOMAIN": "example.test", "HY2_PORT": "8443", "OBFS_ENABLED": "false"}
        cfg = json.loads(subscription.subscription_singbox(env, "alice", "pw", {}).decode("utf-8"))
        tags = {rs["tag"]: rs["url"] for rs in cfg["route"]["rule_set"]}
        self.assertIn("geosite-geolocation-!cn", tags)
        self.assertIn("geolocation-!cn.srs", tags["geosite-geolocation-!cn"])

    def test_clash_overseas_domain_before_china_ip(self):
        i_overseas = self.src.find("RULE-SET,geosite-geolocation-!cn,PROXY")
        i_chinaip = self.src.find("RULE-SET,geoip-cn,DIRECT")
        self.assertGreater(i_overseas, 0, "Clash 缺少 RULE-SET,geosite-geolocation-!cn,PROXY")
        self.assertLess(i_overseas, i_chinaip, "Clash 的海外域名规则必须排在 geoip-cn 之前")


class DnsPollutionGuardTests(unittest.TestCase):
    """境外域名的解析必须「走代理」，否则拿到的是污染 IP。

    真机 2026-11-25（小k 的 macOS sing-box，YouTube 完全打不开）：
      nslookup rr5---sn-a5msenes.googlevideo.com
        → 2a03:2880:f11f:83:face:b00c:0:25de   ← face:b00c 是 Facebook 标志段
        → 108.160.172.1                        ← Dropbox 段
      sing-box 日志里 googlevideo 也被解成 31.13.94.37/31.13.95.169（Facebook）、
      199.59.149.230（Twitter）、59.24.3.173 …

    这是典型的 DNS 污染：Google 的域名被解析成别人家的 IP。
    即使路由规则正确把流量交给代理，代理也是去连这些假 IP，
    拿 SNI=googlevideo.com 去连 Facebook:443 → 必然失败。

    旧配置的致命点：`dns.final = "local"` —— 所有没命中规则的域名都走系统 DNS。
    Clash 那份则是 nameserver 全用国内 DoH，查境外域名同样拿到污染结果。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "app" / "subscription.py").read_text(encoding="utf-8")

    def test_singbox_dns_final_is_not_local(self):
        """dns.final 不能是 local —— 那就是把境外域名交给被污染的系统 DNS。"""
        self.assertIn('"final": "remote"', self.src)
        self.assertNotIn('"final": "local"', self.src)

    def test_singbox_remote_dns_uses_proxy_detour(self):
        """境外 DoH 必须 detour 到 proxy，否则查询本身就被干扰。"""
        self.assertIn('"tag": "remote", "server": "1.1.1.1", "detour": "proxy"', self.src)

    def test_singbox_domestic_domains_use_local_dns(self):
        """国内域名仍用 local（快且不会被污染）。"""
        import json
        import sys
        sys.path.insert(0, str(ROOT / "app"))
        import subscription
        env = {"PUBLIC_IP": "203.0.113.10", "DOMAIN": "example.test", "HY2_PORT": "8443", "OBFS_ENABLED": "false"}
        cfg = json.loads(subscription.subscription_singbox(env, "alice", "pw", {}).decode("utf-8"))
        rules = cfg["dns"]["rules"]
        self.assertTrue(any(".cn" in r.get("domain_suffix", []) and r.get("server") == "local" for r in rules))
        self.assertTrue(any("geosite-cn" in r.get("rule_set", []) and r.get("server") == "local" for r in rules))

    def test_clash_foreign_dns_goes_through_proxy(self):
        """Clash 的境外 nameserver 必须带 #PROXY，否则国内 DoH 也拿到污染结果。"""
        self.assertIn("https://1.1.1.1/dns-query#PROXY", self.src)
        self.assertIn("https://8.8.8.8/dns-query#PROXY", self.src)

    def test_clash_domestic_policy_still_local(self):
        """国内域名策略仍指向国内 DoH。"""
        i = self.src.index("nameserver-policy:")
        seg = self.src[i:i + 400]
        self.assertIn("rule-set:geosite-cn", seg)
        self.assertIn("doh.pub", seg)


if __name__ == "__main__":
    unittest.main()
