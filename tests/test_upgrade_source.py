import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_bash(script: str, *, env=None, cwd=ROOT) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        env=merged,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class UpgradeSourceTests(unittest.TestCase):
    def test_checkout_upgrade_fetches_remote_even_when_lib_exists(self):
        result = run_bash(
            """
set -Eeuo pipefail
source ./hy2.sh
workdir="$(mktemp -d)"
mkdir -p "$workdir/lib"
touch "$workdir/lib/core.sh"
SCRIPT_DIR="$workdir"
choose_module_source upgrade
choose_module_source repair
choose_module_source status
rm -f "$workdir/lib/core.sh"
choose_module_source repair
choose_module_source status
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            ["remote", "local", "local", "remote", "installed"],
            result.stdout.strip().splitlines(),
        )

    def test_fork_slug_builds_matching_raw_url(self):
        result = run_bash(
            """
set -Eeuo pipefail
source ./hy2.sh
REPO_SLUG=alice/hy2-fork
REPO_REF=v9.9.9
HY2_REPO_URL=
apply_repo_url
printf '%s\\n' "$REPO_URL"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            "https://raw.githubusercontent.com/alice/hy2-fork/v9.9.9",
            result.stdout.strip(),
        )

    def test_custom_repo_url_overrides_github_raw(self):
        result = run_bash(
            """
set -Eeuo pipefail
source ./hy2.sh
REPO_SLUG=alice/hy2-fork
REPO_REF=v9.9.9
HY2_REPO_URL=https://example.test/mirror/v1/
apply_repo_url
printf '%s\\n' "$REPO_URL"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual("https://example.test/mirror/v1", result.stdout.strip())

    def test_resolve_latest_uses_hy2_repo_slug(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            commands = Path(tmp) / "commands"
            commands.mkdir()
            curl = commands / "curl"
            curl.write_text(
                """#!/bin/sh
printf '%s\\n' "$*" >> "$MOCK_TRACE"
if printf '%s' "$*" | grep -q '/repos/alice/hy2-fork/releases/latest'; then
  printf '%s\\n' '{"tag_name":"v9.9.9"}'
  exit 0
fi
printf '%s\\n' 'unexpected curl' >&2
exit 1
""",
                encoding="utf-8",
            )
            curl.chmod(0o755)
            trace = Path(tmp) / "trace.log"
            result = run_bash(
                f"""
set -Eeuo pipefail
export PATH={shlex.quote(str(commands))}:"$PATH"
export MOCK_TRACE={shlex.quote(str(trace))}
export HY2_REPO=alice/hy2-fork
source ./hy2.sh
resolve_latest_repo_ref
printf '%s %s %s\\n' "$REPO_SLUG" "$REPO_REF" "$REPO_URL"
""",
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertEqual(
                "alice/hy2-fork v9.9.9 https://raw.githubusercontent.com/alice/hy2-fork/v9.9.9",
                result.stdout.strip().splitlines()[-1],
            )
            self.assertIn("alice/hy2-fork", trace.read_text(encoding="utf-8"))
            self.assertNotIn("keiraee/hy2-allin-one", trace.read_text(encoding="utf-8"))

    def test_cli_upgrade_forwards_repo_slug_and_ref_to_bootstrap(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            root = Path(tmp)
            commands = root / "commands"
            commands.mkdir()
            trace = root / "trace.log"
            seen = root / "seen.env"
            curl = commands / "curl"
            curl.write_text(
                f"""#!/bin/sh
printf '%s\\n' "$*" >> {shlex.quote(str(trace))}
out=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -fsSL|-f|-s|-S|-L) shift ;;
    *) url="$1"; shift ;;
  esac
done
if printf '%s' "$url" | grep -q '/releases/latest'; then
  printf '%s\\n' '{{"tag_name":"v9.9.9"}}'
  exit 0
fi
if [ -n "$out" ]; then
  cat > "$out" <<'EOS'
#!/usr/bin/env bash
printf 'HY2_REPO=%s\\nHY2_REPO_REF=%s\\nHY2_REPO_URL=%s\\n' \\
  "${{HY2_REPO-}}" "${{HY2_REPO_REF-}}" "${{HY2_REPO_URL-}}" \\
  > {shlex.quote(str(seen))}
EOS
  exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            curl.chmod(0o755)
            ident = commands / "id"
            ident.write_text("#!/bin/sh\nprintf '0\\n'\n", encoding="utf-8")
            ident.chmod(0o755)
            result = run_bash(
                f"""
set -Eeuo pipefail
export PATH={shlex.quote(str(commands))}:"$PATH"
export HY2_REPO=alice/hy2-fork
unset HY2_REPO_REF
unset HY2_REPO_URL
bash bin/hy2.sh upgrade
""",
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertTrue(seen.exists(), result.stderr or result.stdout)
            env_text = seen.read_text(encoding="utf-8")
            self.assertIn("HY2_REPO=alice/hy2-fork", env_text)
            self.assertIn("HY2_REPO_REF=v9.9.9", env_text)
            trace_text = trace.read_text(encoding="utf-8")
            self.assertIn("alice/hy2-fork", trace_text)
            self.assertIn("v9.9.9/hy2.sh", trace_text)
            self.assertNotIn("keiraee/hy2-allin-one", trace_text)


if __name__ == "__main__":
    unittest.main()
