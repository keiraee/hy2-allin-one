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

    def test_clash_uses_geoip_rule(self):
        """GEOIP,CN 是第二道保险:域名没覆盖时按 IP 判断。"""
        self.assertIn("GEOIP,CN,DIRECT", self.src)

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
