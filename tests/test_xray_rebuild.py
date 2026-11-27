import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_xray_rebuild_source():
    return (ROOT / "app" / "rebuild_xray.py").read_text(encoding="utf-8")


class XrayRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env_file = self.root / "config.env"
        self.users_file = self.root / "users.json"
        self.out_file = self.root / "xray.json"
        self.env_file.write_text(
            "\n".join(
                [
                    "HY2_PORT=8443",
                    "PANEL_PORT=443",
                    "XRAY_PORT=8443",
                    "REALITY_DEST=www.apple.com:443",
                    "REALITY_SERVER_NAMES=www.apple.com",
                    "REALITY_PRIVATE_KEY=private-fixture",
                    "REALITY_SHORT_ID=abcd1234",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.users_file.write_text(
            json.dumps(
                {
                    "alice": {
                        "password": "x",
                        "vless_id": "11111111-2222-4333-8444-555555555555",
                        "disabled": False,
                    },
                    "bob": {
                        "password": "y",
                        "vless_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                        "disabled": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_rebuild_writes_vision_reality_inbound_for_enabled_users(self):
        source = load_xray_rebuild_source()
        keys = {
            "HY2_ENV_FILE": str(self.env_file),
            "HY2_USERS_FILE": str(self.users_file),
            "HY2_XRAY_CONFIG": str(self.out_file),
        }
        previous = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        try:
            glob = {"__name__": "hy2_aio_xray_rebuild_test"}
            exec(compile(source, "rebuild_xray.py", "exec"), glob)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        config = json.loads(self.out_file.read_text(encoding="utf-8"))
        inbound = config["inbounds"][0]
        self.assertEqual("vless", inbound["protocol"])
        self.assertEqual(8443, inbound["port"])
        self.assertEqual("reality", inbound["streamSettings"]["security"])
        self.assertEqual(
            "www.apple.com:443",
            inbound["streamSettings"]["realitySettings"]["dest"],
        )
        self.assertEqual(
            ["11111111-2222-4333-8444-555555555555"],
            [item["id"] for item in inbound["settings"]["clients"]],
        )
        self.assertEqual("xtls-rprx-vision", inbound["settings"]["clients"][0]["flow"])
        self.assertEqual("alice", inbound["settings"]["clients"][0]["email"])

    def test_unit_files_use_official_xray_binary(self):
        config = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
        install = (ROOT / "lib" / "install.sh").read_text(encoding="utf-8")
        self.assertIn("XTLS/Xray-core", install)
        self.assertIn("Xray-linux-64.zip", install)
        self.assertIn("ExecStart=/usr/local/bin/xray run -c /etc/hy2-aio/xray.json", config)
        self.assertIn("hy2-xray.service", config)
        self.assertIn("reload-xray", config)
        unit = config[config.index("Description=HY2 AIO Xray VLESS+Reality") :]
        unit = unit[: unit.index("[Install]")]
        self.assertNotIn("ReadWritePaths=/run/hy2-aio", unit)

    def test_default_reality_dest_is_apple_not_cloudflare(self):
        self.env_file.write_text(
            "\n".join(
                [
                    "HY2_PORT=8443",
                    "PANEL_PORT=443",
                    "XRAY_PORT=8443",
                    "REALITY_PRIVATE_KEY=private-fixture",
                    "REALITY_SHORT_ID=abcd1234",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        source = load_xray_rebuild_source()
        keys = {
            "HY2_ENV_FILE": str(self.env_file),
            "HY2_USERS_FILE": str(self.users_file),
            "HY2_XRAY_CONFIG": str(self.out_file),
        }
        previous = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        try:
            glob = {"__name__": "hy2_aio_xray_rebuild_default_test"}
            exec(compile(source, "rebuild_xray.py", "exec"), glob)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        config = json.loads(self.out_file.read_text(encoding="utf-8"))
        reality = config["inbounds"][0]["streamSettings"]["realitySettings"]
        self.assertEqual("www.apple.com:443", reality["dest"])
        self.assertEqual(["www.apple.com"], reality["serverNames"])

    def test_ensure_reality_env_migrates_legacy_cloudflare_dest(self):
        import shutil
        import subprocess

        if os.name == "nt" or not shutil.which("bash"):
            self.skipTest("requires POSIX bash")
        self.env_file.write_text(
            "\n".join(
                [
                    "HY2_PORT=8443",
                    "PANEL_PORT=443",
                    "XRAY_PORT=8443",
                    "REALITY_DEST=www.cloudflare.com:443",
                    "REALITY_SERVER_NAMES=www.cloudflare.com",
                    "REALITY_PRIVATE_KEY=priv-keep",
                    "REALITY_PUBLIC_KEY=pub-keep",
                    "REALITY_SHORT_ID=abcd1234",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script = f"""
set -euo pipefail
source "{ROOT / 'lib' / 'core.sh'}"
ENV_FILE="{self.env_file}"
read_env
ensure_reality_env
"""
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        updated = self.env_file.read_text(encoding="utf-8")
        self.assertIn("REALITY_DEST=www.apple.com:443", updated)
        self.assertIn("REALITY_SERVER_NAMES=www.apple.com", updated)
        self.assertNotIn("www.cloudflare.com", updated)
        self.assertIn("REALITY_PRIVATE_KEY=priv-keep", updated)


if __name__ == "__main__":
    unittest.main()
