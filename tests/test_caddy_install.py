import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "shell installation harness requires Linux paths")
class CaddyInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.commands = self.root / "commands"
        self.caddy_dir = self.root / "usr/bin"
        self.local_unit = self.root / "etc/systemd/system/caddy.service"
        self.vendor_unit = self.root / "usr/lib/systemd/system/caddy.service"
        self.legacy_bin = self.root / "usr/local/bin/caddy"
        self.trace = self.root / "trace.log"
        self.commands.mkdir(parents=True)
        self.caddy_dir.mkdir(parents=True)
        self.local_unit.parent.mkdir(parents=True, exist_ok=True)

        source = (ROOT / "lib/install.sh").read_text(encoding="utf-8")
        source = source.replace(
            "/etc/systemd/system/caddy.service", self.local_unit.as_posix()
        )
        source = source.replace("/usr/local/bin/caddy", self.legacy_bin.as_posix())
        self.install_source = self.root / "install.sh"
        self.install_source.write_text(source, encoding="utf-8")

        package_command = """
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$MOCK_TRACE"
if [ "${MOCK_CREATE_PACKAGE_BINARY:-1}" = "1" ]; then
  mkdir -p "$MOCK_CADDY_DIR"
  printf '#!/bin/sh\\nprintf "v2.11.4 h1:test\\n"\\n' > "$MOCK_CADDY_DIR/caddy"
  chmod 0755 "$MOCK_CADDY_DIR/caddy"
fi
if [ "${MOCK_CREATE_VENDOR_UNIT:-0}" = "1" ]; then
  mkdir -p "$(dirname "$MOCK_VENDOR_UNIT")"
  printf '[Service]\\nExecStart=%s/caddy run --config /etc/caddy/Caddyfile\\n' \
    "$MOCK_CADDY_DIR" > "$MOCK_VENDOR_UNIT"
fi
"""
        for manager in ("dnf", "yum", "zypper"):
            self._write_command(manager, package_command)
        self._write_command(
            "systemctl",
            """
printf 'systemctl %s\\n' "$*" >> "$MOCK_TRACE"
if [ "${1:-}" = "cat" ]; then
  if [ -f "$MOCK_LOCAL_UNIT" ]; then
    cat "$MOCK_LOCAL_UNIT"
    exit 0
  fi
  if [ -f "$MOCK_VENDOR_UNIT" ]; then
    cat "$MOCK_VENDOR_UNIT"
    exit 0
  fi
  exit 1
fi
""",
        )
        self._write_command(
            "install", "printf 'install %s\\n' \"$*\" >> \"$MOCK_TRACE\""
        )
        self._write_command(
            "groupadd", "printf 'groupadd %s\\n' \"$*\" >> \"$MOCK_TRACE\""
        )
        self._write_command(
            "useradd", "printf 'useradd %s\\n' \"$*\" >> \"$MOCK_TRACE\""
        )
        self._write_command("getent", "exit 1")
        self._write_command("id", "exit 1")

    def tearDown(self):
        self.temporary.cleanup()

    def _write_command(self, name: str, body: str):
        path = self.commands / name
        path.write_text(f"#!/bin/sh\n{body.strip()}\n", encoding="utf-8")
        path.chmod(0o755)

    def _write_caddy(self):
        path = self.caddy_dir / "caddy"
        path.write_text(
            '#!/bin/sh\nprintf "v2.11.4 h1:test\\n"\n', encoding="utf-8"
        )
        path.chmod(0o755)
        return path

    def _run_install(self, *, package_unit=False, manager="dnf"):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.commands}:{self.caddy_dir}:{env['PATH']}",
                "MOCK_CADDY_DIR": str(self.caddy_dir),
                "MOCK_CREATE_VENDOR_UNIT": "1" if package_unit else "0",
                "MOCK_LOCAL_UNIT": str(self.local_unit),
                "MOCK_VENDOR_UNIT": str(self.vendor_unit),
                "MOCK_TRACE": str(self.trace),
            }
        )
        return subprocess.run(
            [
                "bash",
                "-c",
                """
set -Eeuo pipefail
source "$1"
log() { :; }
warn() { printf 'WARN: %s\\n' "$*" >&2; }
die() { printf 'ERROR: %s\\n' "$*" >&2; return 1; }
PKG_MANAGER="$2"
install_caddy_v12
""",
                "caddy-install-test",
                str(self.install_source),
                manager,
            ],
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_preserves_package_provided_systemd_unit(self):
        result = self._run_install(package_unit=True)

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertTrue(self.vendor_unit.exists())
        self.assertFalse(self.local_unit.exists())
        self.assertIn(str(self.caddy_dir / "caddy"), self.vendor_unit.read_text())
        trace = self.trace.read_text(encoding="utf-8")
        self.assertLess(
            trace.index("systemctl daemon-reload"),
            trace.index("systemctl cat caddy.service"),
        )

    def test_uses_noninteractive_zypper_syntax_and_preserves_its_unit(self):
        result = self._run_install(package_unit=True, manager="zypper")

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("zypper --non-interactive install caddy", trace)
        self.assertFalse(self.local_unit.exists())

    def test_generated_unit_uses_the_resolved_package_binary(self):
        result = self._run_install()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        unit = self.local_unit.read_text(encoding="utf-8")
        self.assertIn(f"ExecStart={self.caddy_dir}/caddy ", unit)
        self.assertIn(f"ExecReload={self.caddy_dir}/caddy ", unit)
        self.assertNotIn(str(self.legacy_bin), unit)

    def test_existing_binary_repairs_missing_runtime_scaffolding(self):
        self._write_caddy()

        result = self._run_install()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertTrue(self.local_unit.exists())
        trace = self.trace.read_text(encoding="utf-8")
        self.assertNotIn("dnf ", trace)
        self.assertIn("groupadd --system caddy", trace)
        self.assertIn("useradd --system", trace)
        self.assertIn("install -d -o caddy -g caddy", trace)
        self.assertIn("systemctl enable caddy.service", trace)

    def test_replaces_legacy_unit_that_points_to_a_missing_binary(self):
        caddy = self._write_caddy()
        self.local_unit.write_text(
            "[Service]\n"
            f"ExecStart={self.legacy_bin} run --config /etc/caddy/Caddyfile\n",
            encoding="utf-8",
        )

        result = self._run_install()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        unit = self.local_unit.read_text(encoding="utf-8")
        self.assertIn(f"ExecStart={caddy} ", unit)
        self.assertNotIn(str(self.legacy_bin), unit)


if __name__ == "__main__":
    unittest.main()
