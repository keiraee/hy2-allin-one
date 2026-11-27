"""End-to-end upgrade compatibility drill: legacy v1.8.7 layout -> refactored modular layout.

Simulates an existing production server installed with v1.8.7 (monolithic shell modules,
no app/ or web/ subdirs in modules/, legacy REALITY_DEST=www.cloudflare.com:443 in config.env)
upgrading to the refactored multi-module layout, and verifies:
1. Legacy REALITY_DEST=www.cloudflare.com:443 is automatically migrated to www.apple.com:443
   while preserving REALITY_PRIVATE_KEY / REALITY_PUBLIC_KEY / REALITY_SHORT_ID / XRAY_PORT.
2. write_rebuild_helper, write_xray_rebuild_helper, write_backend, and write_panel install
   all decoupled files (common.py, subscription.py, activity.py, backup_ops.py, server.py,
   rebuild_config.py, rebuild_xray.py, index.html) cleanly into target directories.
3. Installed rebuild_config.py and rebuild_xray.py run standalone against migrated config.env
   and produce valid Hysteria YAML + Xray Reality JSON (dest=www.apple.com:443).
4. Installed server.py imports cleanly from APP_DIR (with no repo path in sys.path) and
   generates Clash / sing-box / Base64 / direct-link subscriptions with sni=www.apple.com.
5. Installed modules/ + bin/hy2.sh load all shell modules (including lib/network.sh) cleanly.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LegacyUpgradeCompatibilityTests(unittest.TestCase):
    def test_v187_layout_upgrades_cleanly_to_modular_layout(self):
        if os.name == "nt" or not shutil.which("bash"):
            self.skipTest("requires POSIX bash")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_dir = root / "etc" / "hy2-aio"
            hy2_dir = root / "etc" / "hysteria"
            app_dir = root / "usr" / "local" / "lib" / "hy2-aio"
            mod_dir = app_dir / "modules"
            web_dir = root / "var" / "www" / "hy2-aio"
            for d in (cfg_dir, hy2_dir, app_dir, mod_dir / "lib", mod_dir / "bin", web_dir):
                d.mkdir(parents=True, exist_ok=True)

            # 1. Seed a realistic v1.8.7 installation (no app/, no web/, no lib/network.sh, legacy CF dest)
            env_file = cfg_dir / "config.env"
            env_file.write_text(
                "\n".join(
                    [
                        "DOMAIN=panel.example.com",
                        "PUBLIC_IP=203.0.113.10",
                        "PANEL_PORT=443",
                        "PANEL_PATH=secret-panel",
                        "PANEL_USER=admin",
                        "PANEL_PASS=pass1234",
                        "HY2_PORT=8443",
                        "XRAY_PORT=8443",
                        "STATS_PORT=9999",
                        "API_SECRET=secret-api-token",
                        "OBFS_ENABLED=true",
                        "OBFS_PASSWORD=obfs-secret",
                        "REALITY_DEST=www.cloudflare.com:443",
                        "REALITY_SERVER_NAMES=www.cloudflare.com",
                        "REALITY_PRIVATE_KEY=priv-legacy-keep",
                        "REALITY_PUBLIC_KEY=pub-legacy-keep",
                        "REALITY_SHORT_ID=deadbeef",
                        "CLIENT_INSECURE=false",
                        "PORT_HOP_ENABLED=false",
                        "COUNTRY_CODE=SG",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            users_file = cfg_dir / "users.json"
            users_file.write_text(
                json.dumps(
                    {
                        "user1": {
                            "password": "u1-password",
                            "vless_id": "11111111-2222-4333-8444-555555555555",
                            "token": "tok-user1",
                            "disabled": False,
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            # Legacy v1.8.7 monolithic artifacts in APP_DIR (no helper .py modules yet)
            (app_dir / "server.py").write_text("# old v1.8.7 server.py\n", encoding="utf-8")
            (app_dir / "rebuild_config.py").write_text("# old v1.8.7\n", encoding="utf-8")
            (app_dir / "rebuild_xray.py").write_text("# old v1.8.7\n", encoding="utf-8")

            # 2. Run the new version's upgrade/install functions in bash against the isolated tree
            hy2_cfg = hy2_dir / "config.yaml"
            xray_cfg = cfg_dir / "xray.json"
            script = f"""
set -euo pipefail
SCRIPT_DIR="{ROOT}"
source "${{SCRIPT_DIR}}/lib/core.sh"
source "${{SCRIPT_DIR}}/lib/config.sh"
source "${{SCRIPT_DIR}}/lib/network.sh"
source "${{SCRIPT_DIR}}/lib/backend.sh"
source "${{SCRIPT_DIR}}/lib/panel.sh"

# Sandbox shim: test hosts may not have system users hy2-aio / caddy / hysteria
chown() {{ return 0; }}
install() {{
  local args=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -o|-g) shift 2 ;;
      *) args+=("$1"); shift ;;
    esac
  done
  command install "${{args[@]}}"
}}

# Redirect system paths into temp sandbox
CONFIG_DIR="{cfg_dir}"
ENV_FILE="{env_file}"
USERS_FILE="{users_file}"
HYSTERIA_CONFIG="{hy2_cfg}"
XRAY_CONFIG="{xray_cfg}"
APP_DIR="{app_dir}"
APP_FILE="{app_dir}/server.py"
REBUILD_FILE="{app_dir}/rebuild_config.py"
XRAY_REBUILD_FILE="{app_dir}/rebuild_xray.py"
WEB_DIR="{web_dir}"
PANEL_INDEX="{web_dir}/index.html"

read_env
ensure_reality_env
read_env

write_rebuild_helper
write_xray_rebuild_helper
write_backend
write_panel

HY2_ENV_FILE="$ENV_FILE" HY2_USERS_FILE="$USERS_FILE" HY2_HYSTERIA_CONFIG="$HYSTERIA_CONFIG" "$REBUILD_FILE"
HY2_ENV_FILE="$ENV_FILE" HY2_USERS_FILE="$USERS_FILE" HY2_XRAY_CONFIG="$XRAY_CONFIG" "$XRAY_REBUILD_FILE"

# Sync modules dir exactly as repair_cmd does
mkdir -p "{mod_dir}/lib" "{mod_dir}/bin" "{mod_dir}/web" "{mod_dir}/app"
cp -a "${{SCRIPT_DIR}}/lib/"* "{mod_dir}/lib/"
cp -a "${{SCRIPT_DIR}}/bin/"* "{mod_dir}/bin/"
cp -a "${{SCRIPT_DIR}}/web/." "{mod_dir}/web/"
cp -a "${{SCRIPT_DIR}}/app/." "{mod_dir}/app/"
"""
            proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, f"Upgrade drill failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")

            # 3. Verify legacy Cloudflare dest was migrated while keeping keys
            migrated_env = env_file.read_text(encoding="utf-8")
            self.assertIn("REALITY_DEST=www.apple.com:443", migrated_env)
            self.assertIn("REALITY_SERVER_NAMES=www.apple.com", migrated_env)
            self.assertNotIn("www.cloudflare.com", migrated_env)
            self.assertIn("REALITY_PRIVATE_KEY=priv-legacy-keep", migrated_env)
            self.assertIn("REALITY_PUBLIC_KEY=pub-legacy-keep", migrated_env)
            self.assertIn("REALITY_SHORT_ID=deadbeef", migrated_env)

            # 4. Verify all decoupled Python modules & frontend HTML were installed
            for fname in (
                "common.py",
                "subscription.py",
                "activity.py",
                "backup_ops.py",
                "server.py",
                "rebuild_config.py",
                "rebuild_xray.py",
            ):
                self.assertTrue((app_dir / fname).is_file(), f"Missing installed {fname}")
            self.assertTrue((web_dir / "index.html").is_file())
            self.assertIn("<!doctype html>", (web_dir / "index.html").read_text(encoding="utf-8").lower())

            # 5. Verify rebuilt xray.json & hysteria config.yaml
            xray = json.loads(xray_cfg.read_text(encoding="utf-8"))
            reality = xray["inbounds"][0]["streamSettings"]["realitySettings"]
            self.assertEqual("www.apple.com:443", reality["dest"])
            self.assertEqual(["www.apple.com"], reality["serverNames"])
            self.assertEqual("priv-legacy-keep", reality["privateKey"])
            self.assertIn('listen: ":8443"', hy2_cfg.read_text(encoding="utf-8"))

            # 6. Verify installed server.py imports cleanly WITHOUT repo on sys.path and renders subscriptions
            verify_py = f"""
import importlib.util, json, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("installed_server", "{app_dir / 'server.py'}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
env = mod.read_env_file(Path("{env_file}"))
info = json.loads(Path("{users_file}").read_text(encoding="utf-8"))["user1"]
links = mod.direct_links(env, "user1", info["password"], info)
assert "sni=www.apple.com" in links, links
assert "www.cloudflare.com" not in links, links
yaml_out = mod.subscription_yaml(env, "user1", info["password"], info).decode("utf-8")
assert "servername: \\"www.apple.com\\"" in yaml_out or "www.apple.com" in yaml_out
sb = json.loads(mod.subscription_singbox(env, "user1", info["password"], info).decode("utf-8"))
assert any(o.get("type") == "vless" for o in sb["outbounds"])
print("INSTALLED_SERVER_OK")
"""
            py_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            py_proc = subprocess.run(
                ["python3", "-I", "-c", verify_py],
                cwd=str(tmp),
                env=py_env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, py_proc.returncode, f"Installed server.py failed:\n{py_proc.stderr}")
            self.assertIn("INSTALLED_SERVER_OK", py_proc.stdout)

            # 7. Verify all installed shell modules (including lib/network.sh) source cleanly
            mod_verify = f"""
set -euo pipefail
for m in core.sh install.sh config.sh network.sh panel.sh user.sh cert.sh access.sh backup.sh mode.sh backend.sh cli.sh deps.sh; do
  source "{mod_dir}/lib/$m"
done
declare -F dispatch_cli_command >/dev/null
declare -F port_cmd >/dev/null
declare -F hop_cmd >/dev/null
declare -F obfs_cmd >/dev/null
echo "INSTALLED_MODULES_OK"
"""
            cli_proc = subprocess.run(
                ["bash", "-c", mod_verify],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, cli_proc.returncode, cli_proc.stderr)
            self.assertIn("INSTALLED_MODULES_OK", cli_proc.stdout)


if __name__ == "__main__":
    unittest.main()
