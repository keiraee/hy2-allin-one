import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_xray_rebuild_source():
    shell_source = (ROOT / "lib" / "config.sh").read_text(encoding="utf-8")
    start_marker = '  cat > "$XRAY_REBUILD_FILE" <<\'PY\'\n'
    end_marker = "\nPY\n  chmod 0755 \"$XRAY_REBUILD_FILE\""
    start = shell_source.index(start_marker) + len(start_marker)
    end = shell_source.index(end_marker, start)
    return shell_source[start:end]


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
                    "REALITY_DEST=www.cloudflare.com:443",
                    "REALITY_SERVER_NAMES=www.cloudflare.com",
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
            "www.cloudflare.com:443",
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


if __name__ == "__main__":
    unittest.main()
