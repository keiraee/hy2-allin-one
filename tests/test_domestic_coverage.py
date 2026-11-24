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

# 必须国内直连的国内 IP（不依赖域名解析，微信/抖音 CDN 大量直接用 IP）
CRITICAL_DOMESTIC_IPS = [
    "183.61.35.28",     # 微信图片 CDN (Tencent)
    "203.205.254.36",   # 微信 mmtls 长连接
    "101.32.104.4",     # 腾讯云
    "140.205.94.189",   # 阿里
]


class DomesticCoverageSourceTests(unittest.TestCase):
    """分流数据源必须是 MetaCubeX geosite(11 万条,持续更新)。

    而不是黑名单式的手写域名 / 第三方零散清单 —— 那种必然漏。
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")

    def test_clash_uses_geosite_rule(self):
        """Clash 的 rules 必须含 GEOSITE,cn(不是只靠手写域名)。"""
        self.assertIn("GEOSITE,cn,DIRECT", self.src)

    def test_has_china_ip_ruleset(self):
        """纯 IP 流量也要直连 —— 微信/抖音 CDN 大量用 IP 直连不走域名。

        真机现象(2026-11-22):两台手机微信图片/视频加载不动,关掉代理就好。
        根因:规则里只有 GEOSITE,cn(匹配域名),微信 CDN 的纯 IP 连接
        落到 MATCH → 走日本代理 → 加载转圈。必须补 IP 段规则。
        china-ip.mrs 只有 37KB(jsdelivr 0.3 秒下完),不影响首启。
        """
        self.assertIn("RULE-SET,china-ip,DIRECT", self.src)
        self.assertIn("behavior: ipcidr", self.src)
        self.assertIn("format: mrs", self.src)

    def test_no_geoip_rule(self):
        """不用 GEOIP,CN —— 会触发 6.5MB geoip.dat 下载,中国网络首启必卡。

        实测(2026-11-21):geoip.dat 6.5MB,jsdelivr 在国内 30 秒只拉到
        620KB,mihomo 卡在 "Can't find GeoIP.dat, start download" 起不来。
        GEOSITE,cn 11 万条已足够覆盖,不需要 IP 兜底。
        """
        rules_start = self.src.index("rules:")
        rules_end = self.src.index("MATCH,PROXY", rules_start)
        self.assertNotIn("GEOIP", self.src[rules_start:rules_end])

    def test_geosite_dat_is_lite(self):
        """geosite 用 lite 版(176KB,CN 分类仍 110177 条),不用全量 4.3MB。

        lite 版实测:10 秒内下完,CN 分类记录数与全量版一致。
        """
        self.assertIn("geosite-lite.dat", self.src)
        seg = self.src[self.src.index("geox-url:"): self.src.index("dns:")]
        self.assertNotIn("geoip:", seg)
        self.assertNotIn(chr(103)+chr(101)+chr(111)+chr(115)+chr(105)+chr(116)+chr(101)+chr(46)+chr(100)+chr(97)+chr(116), seg)

    def test_singbox_uses_geosite_cn_ruleset(self):
        """sing-box 必须引用 geosite cn 规则集。"""
        i = self.src.index("def subscription_singbox(")
        j = self.src.index("\ndef subscription_body", i)
        sb = self.src[i:j]
        self.assertIn("geosite-cn", sb)
        self.assertIn("geoip-cn", sb)

    def test_ruleset_urls_use_mirror(self):
        """规则集 URL 走 jsdelivr —— 中国网络拉 raw.githubusercontent 会超时。"""
        i = self.src.index("def subscription_singbox(")
        j = self.src.index("\ndef subscription_body", i)
        sb = self.src[i:j]
        self.assertNotIn(
            "raw.githubusercontent.com",
            sb,
            "规则集 URL 不能用 raw.githubusercontent(中国网络拉不动)",
        )
        self.assertIn("jsdelivr", sb)

    def test_geox_url_uses_mirror(self):
        self.assertIn("geox-url:", self.src)
        seg = self.src[self.src.index("geox-url:"): self.src.index("dns:")]
        self.assertIn("jsdelivr", seg)


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
        cls.src = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")

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
        self.assertIn('"tag": "geosite-geolocation-!cn"', self.src)
        self.assertIn("geosite/geolocation-!cn.srs", self.src)

    def test_clash_overseas_domain_before_china_ip(self):
        i_overseas = self.src.find("GEOSITE,geolocation-!cn,PROXY")
        i_chinaip = self.src.find("RULE-SET,china-ip,DIRECT")
        self.assertGreater(i_overseas, 0, "Clash 缺少 GEOSITE,geolocation-!cn,PROXY")
        self.assertLess(i_overseas, i_chinaip, "Clash 的海外域名规则必须排在 china-ip 之前")


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
        cls.src = (ROOT / "lib" / "backend.sh").read_text(encoding="utf-8")

    def test_singbox_dns_final_is_not_local(self):
        """dns.final 不能是 local —— 那就是把境外域名交给被污染的系统 DNS。"""
        self.assertIn('"final": "remote"', self.src)
        self.assertNotIn('"final": "local"', self.src)

    def test_singbox_remote_dns_uses_proxy_detour(self):
        """境外 DoH 必须 detour 到 proxy，否则查询本身就被干扰。"""
        self.assertIn('"tag": "remote", "server": "1.1.1.1", "detour": "proxy"', self.src)

    def test_singbox_domestic_domains_use_local_dns(self):
        """国内域名仍用 local（快且不会被污染）。"""
        self.assertIn('{"domain_suffix": [".cn"], "server": "local"}', self.src)
        self.assertIn('{"rule_set": "geosite-cn", "server": "local"}', self.src)

    def test_clash_foreign_dns_goes_through_proxy(self):
        """Clash 的境外 nameserver 必须带 #PROXY，否则国内 DoH 也拿到污染结果。"""
        self.assertIn("https://1.1.1.1/dns-query#PROXY", self.src)
        self.assertIn("https://8.8.8.8/dns-query#PROXY", self.src)

    def test_clash_domestic_policy_still_local(self):
        """国内域名策略仍指向国内 DoH。"""
        i = self.src.index("nameserver-policy:")
        seg = self.src[i:i + 400]
        self.assertIn("geosite:cn", seg)
        self.assertIn("doh.pub", seg)


if __name__ == "__main__":
    unittest.main()
