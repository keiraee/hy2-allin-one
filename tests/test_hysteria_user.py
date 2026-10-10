import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "user harness needs Linux path semantics; run via WSL")
class EnsureHysteriaUserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "var/lib/hysteria"
        self.trace = self.root / "trace.log"
        commands = self.root / "commands"
        commands.mkdir()
        for name, body in {
            "getent": (
                f'printf "getent %s\\n" "$*" >> "{self.trace.as_posix()}"\n'
                'case "$1" in\n'
                "  group) [ \"${MOCK_GROUP_EXISTS:-1}\" = \"1\" ] && exit 0 || exit 2 ;;\n"
                "  passwd)\n"
                '    if [ "${MOCK_USER_EXISTS:-0}" = "1" ]; then\n'
                '      printf "hysteria:x:999:999::%s:/usr/sbin/nologin\\n" "${MOCK_HOME}"\n'
                "      exit 0\n"
                "    fi\n"
                "    exit 2 ;;\n"
                "esac\n"
                "exit 2\n"
            ),
            "id": (
                'if [ "${MOCK_USER_EXISTS:-0}" = "1" ]; then exit 0; fi\n'
                "exit 1\n"
            ),
            "useradd": f'printf "useradd %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "usermod": f'printf "usermod %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "groupadd": f'printf "groupadd %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
            "install": f'printf "install %s\\n" "$*" >> "{self.trace.as_posix()}"\n',
        }.items():
            path = commands / name
            path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
            path.chmod(0o755)
        self.commands = commands

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, *, user_exists: bool, home: str = "") -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PATH"] = f"{self.commands}:{env['PATH']}"
        env["MOCK_USER_EXISTS"] = "1" if user_exists else "0"
        env["MOCK_GROUP_EXISTS"] = "1"
        env["MOCK_HOME"] = home
        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -Eeuo pipefail
source {shlex.quote(str(ROOT / 'lib' / 'core.sh'))}
source {shlex.quote(str(ROOT / 'lib' / 'config.sh'))}
HYSTERIA_HOME_DIR={shlex.quote(str(self.home))}
ensure_hysteria_user
""",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_creates_user_with_real_home_not_nonexistent(self):
        result = self._run(user_exists=False)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn("useradd --system --gid hysteria", trace)
        self.assertIn(f"--home-dir {self.home} --create-home", trace)
        self.assertNotIn("/nonexistent", trace)

    def test_heals_existing_user_with_broken_home(self):
        result = self._run(user_exists=True, home="/nonexistent")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertIn(f"usermod -d {self.home} hysteria", trace)
        self.assertIn(f"install -d -o hysteria -g hysteria -m 0750 {self.home}", trace)
        self.assertNotIn("useradd", trace)

    def test_creates_missing_home_directory_for_existing_user(self):
        result = self._run(user_exists=True, home=str(self.home))
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        trace = self.trace.read_text(encoding="utf-8")
        self.assertNotIn("usermod", trace)
        self.assertIn(f"install -d -o hysteria -g hysteria -m 0750 {self.home}", trace)


if __name__ == "__main__":
    unittest.main()
