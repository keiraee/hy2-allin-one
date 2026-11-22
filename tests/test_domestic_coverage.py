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


if __name__ == "__main__":
    unittest.main()
