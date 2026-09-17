import itertools
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
_RUN_SEQ = itertools.count()


def posix_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if len(text) >= 2 and text[1] == ":":
        return f"/mnt/{text[0].lower()}{text[2:]}"
    return text


def log_messages(stdout: str) -> list[str]:
    lines = []
    for raw in stdout.strip().splitlines():
        line = ANSI.sub("", raw)
        if "] " in line:
            line = line.split("] ", 1)[1]
        lines.append(line)
    return lines


def run_bash(script: str, *, env=None, cwd=ROOT) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    path = ROOT / "tests" / f".tmp_run_{os.getpid()}_{next(_RUN_SEQ)}.sh"
    path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
    try:
        return subprocess.run(
            ["bash", path.relative_to(ROOT).as_posix()],
            cwd=cwd,
            env=merged,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)


def persist_env_script() -> str:
    text = (ROOT / "lib" / "backup.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    marker = "import os\nimport re\nimport sys\nfrom pathlib import Path"
    start = text.index(marker)
    end = text.index("os.replace(temporary, path)\nPY", start)
    return text[start : end] + "os.replace(temporary, path)\n"


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
                newline="\n",
            )
            curl.chmod(0o755)
            trace = Path(tmp) / "trace.log"
            result = run_bash(
                f"""
set -Eeuo pipefail
export PATH={shlex.quote(posix_path(commands))}:"$PATH"
export MOCK_TRACE={shlex.quote(posix_path(trace))}
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
printf '%s\\n' "$*" >> {shlex.quote(posix_path(trace))}
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
  > {shlex.quote(posix_path(seen))}
EOS
  exit 0
fi
exit 1
""",
                encoding="utf-8",
                newline="\n",
            )
            curl.chmod(0o755)
            ident = commands / "id"
            ident.write_text("#!/bin/sh\nprintf '0\\n'\n", encoding="utf-8", newline="\n")
            ident.chmod(0o755)
            result = run_bash(
                f"""
set -Eeuo pipefail
export PATH={shlex.quote(posix_path(commands))}:"$PATH"
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
            self.assertIn("升级 未知 → v9.9.9", result.stdout)

    def test_cli_upgrade_skips_when_installed_version_matches_latest(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
hy2_testdir="$(mktemp -d)"
trap 'rm -rf "$hy2_testdir"' EXIT
mkdir -p "$hy2_testdir/commands"
printf '%s\n' 'AIO_VERSION=v9.9.9' \
  'HY2_MODULES_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  'HY2_REPO_SHA=0123456789abcdef0123456789abcdef01234567' > "$hy2_testdir/config.env"
cat > "$hy2_testdir/commands/curl" <<'EOS'
#!/bin/sh
printf '%s\n' '{"tag_name":"v9.9.9"}'
echo "$*" >> "$HY2_TESTDIR/trace.log"
exit 0
EOS
chmod +x "$hy2_testdir/commands/curl"
cat > "$hy2_testdir/commands/id" <<'EOS'
#!/bin/sh
printf '0\n'
EOS
chmod +x "$hy2_testdir/commands/id"
export PATH="$hy2_testdir/commands:$PATH"
export HY2_TESTDIR="$hy2_testdir"
export HY2_REPO=alice/hy2-fork
export HY2_ENV_FILE="$hy2_testdir/config.env"
unset HY2_REPO_REF
unset HY2_REPO_URL
env PATH="$hy2_testdir/commands:/usr/bin:/bin" /bin/bash "$PWD/bin/hy2.sh" upgrade
test ! -f "$hy2_testdir/seen.env"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("已是 v9.9.9，无需升级", result.stdout)
        self.assertIn("上次哈希：aaaaaaaaaaaa（提交 0123456789ab）", result.stdout)
        self.assertIn("本次哈希：未下载", result.stdout)

    def test_upgrade_already_current_compares_normalized_versions(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
printf '%s\n' 'AIO_VERSION=1.3.24' > "$root/same.env"
printf '%s\n' 'AIO_VERSION=v1.3.23' > "$root/other.env"
source ./hy2.sh
upgrade_already_current "$root/same.env" v1.3.24 && echo same-yes || echo same-no
upgrade_already_current "$root/other.env" v1.3.24 && echo other-yes || echo other-no
upgrade_already_current "$root/same.env" main && echo main-yes || echo main-no
upgrade_already_current "$root/same.env" abcdef0 && echo sha-yes || echo sha-no
upgrade_already_current "$root/same.env" 0568973f657caf864f4a8bdf88d36ddb9581af58 && echo digitsha-yes || echo digitsha-no
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            ["same-yes", "other-no", "main-no", "sha-no", "digitsha-no"],
            result.stdout.strip().splitlines(),
        )

    def test_upgrade_banner_uses_installed_version_to_target(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            env_file = Path(tmp) / "config.env"
            env_file.write_text("AIO_VERSION=1.3.21\n", encoding="utf-8")
            result = run_bash(
                f"""
set -Eeuo pipefail
source ./hy2.sh
REPO_REF=v1.3.22
printf '%s\\n' "$(normalize_aio_version 1.3.21)"
printf '%s\\n' "$(normalize_aio_version v1.3.22)"
printf '%s\\n' "$(normalize_aio_version main)"
printf '%s\\n' "$(normalize_aio_version '')"
printf '%s\\n' "$(read_installed_aio_version {shlex.quote(posix_path(env_file))})"
log_upgrade_plan {shlex.quote(posix_path(env_file))}
HY2_UPGRADE_BANNER=1
log_upgrade_plan {shlex.quote(posix_path(env_file))}
"""
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertEqual(
                ["v1.3.21", "v1.3.22", "main", "未知", "v1.3.21", "升级 v1.3.21 → v1.3.22"],
                log_messages(result.stdout),
            )

    def test_pinned_upgrade_source_logs_version_then_module_origin(self):
        result = run_bash(
            """
set -Eeuo pipefail
source ./hy2.sh
HY2_REPO=alice/hy2-fork
HY2_REPO_REF=v9.9.9
unset HY2_REPO_URL
unset HY2_UPGRADE_BANNER
resolve_upgrade_source
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        messages = log_messages(result.stdout)
        self.assertEqual("升级 未知 → v9.9.9", messages[0])
        self.assertEqual("模块来源：alice/hy2-fork @ v9.9.9", messages[1])
        self.assertTrue(messages[2].startswith("模块地址："))

    def test_saved_main_track_is_used_when_repo_ref_is_unset(self):
        script = r"""
set -Eeuo pipefail
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
printf '%s\n' 'AIO_VERSION=1.3.28' 'HY2_TRACK_REF=main' > "$root/config.env"
source ./hy2.sh
HY2_ENV_FILE="$root/config.env"
unset HY2_REPO_REF
unset HY2_REPO_URL
unset HY2_UPGRADE_BANNER
HY2_REPO=keiraee/hy2-allin-one
_bootstrap_curl() {
  if printf '%s' "${1-}" | grep -q 'commits'; then
    printf '%s\n' '{"sha":"0123456789abcdef0123456789abcdef01234567"}'
    return 0
  fi
  printf '%s\n' "unexpected curl: ${1-}" >&2
  return 1
}
resolve_upgrade_source
printf 'REF=%s\n' "$REPO_REF"
printf 'TRACK=%s\n' "$HY2_PERSIST_TRACK"
printf 'URL=%s\n' "$REPO_URL"
"""
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "run.sh"
            path.write_bytes(script.lstrip().encode("utf-8"))
            rel = path.relative_to(ROOT).as_posix()
            result = subprocess.run(
                ["bash", rel],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("keiraee/hy2-allin-one @ main", result.stdout)
        self.assertIn(
            "https://raw.githubusercontent.com/keiraee/hy2-allin-one/0123456789abcdef0123456789abcdef01234567",
            result.stdout,
        )
        self.assertIn("REF=0123456789abcdef0123456789abcdef01234567", result.stdout)
        self.assertIn("TRACK=main", result.stdout)
        self.assertIn("钉住提交：main → 0123456789ab", result.stdout)

    def test_cli_upgrade_follows_saved_main_track_instead_of_latest(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
hy2_testdir="$(mktemp -d)"
trap 'rm -rf "$hy2_testdir"' EXIT
mkdir -p "$hy2_testdir/commands"
printf '%s\n' 'AIO_VERSION=1.3.28' 'HY2_TRACK_REF=main' > "$hy2_testdir/config.env"
cat > "$hy2_testdir/commands/curl" <<'EOS'
#!/bin/sh
printf '%s\n' "$*" >> "$HY2_TESTDIR/trace.log"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then
    out="$arg"
  fi
  prev="$arg"
done
if printf '%s' "$*" | grep -q '/commits/main'; then
  printf '%s\n' '{"sha":"0123456789abcdef0123456789abcdef01234567"}'
  [ -z "$out" ] && exit 0
fi
if printf '%s' "$*" | grep -q '/releases/latest'; then
  printf '%s\n' '{"tag_name":"v1.3.28"}'
  [ -z "$out" ] && exit 0
fi
if [ -n "$out" ]; then
  {
    echo '#!/bin/sh'
    echo 'echo "HY2_REPO=${HY2_REPO-}" > "$HY2_TESTDIR/seen.env"'
    echo 'echo "HY2_REPO_REF=${HY2_REPO_REF-}" >> "$HY2_TESTDIR/seen.env"'
    echo 'echo "HY2_REPO_URL=${HY2_REPO_URL-}" >> "$HY2_TESTDIR/seen.env"'
    echo 'echo "HY2_PERSIST_TRACK=${HY2_PERSIST_TRACK-}" >> "$HY2_TESTDIR/seen.env"'
  } > "$out"
  exit 0
fi
exit 1
EOS
chmod +x "$hy2_testdir/commands/curl"
cat > "$hy2_testdir/commands/id" <<'EOS'
#!/bin/sh
printf '0\n'
EOS
chmod +x "$hy2_testdir/commands/id"
export PATH="$hy2_testdir/commands:$PATH"
export HY2_TESTDIR="$hy2_testdir"
export HY2_REPO=alice/hy2-fork
export HY2_ENV_FILE="$hy2_testdir/config.env"
unset HY2_REPO_REF
unset HY2_REPO_URL
env PATH="$hy2_testdir/commands:/usr/bin:/bin" HY2_TESTDIR="$hy2_testdir" /bin/bash "$PWD/bin/hy2.sh" upgrade
test -f "$hy2_testdir/seen.env"
grep -q 'HY2_REPO_REF=main' "$hy2_testdir/seen.env"
grep -q 'HY2_PERSIST_TRACK=main' "$hy2_testdir/seen.env"
grep -q '0123456789abcdef0123456789abcdef01234567' "$hy2_testdir/seen.env"
grep -q '/commits/main' "$hy2_testdir/trace.log"
grep -q '0123456789abcdef0123456789abcdef01234567/hy2.sh' "$hy2_testdir/trace.log"
! grep -q 'releases/latest' "$hy2_testdir/trace.log"
! grep -q 'alice/hy2-fork/main/hy2.sh' "$hy2_testdir/trace.log"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertNotIn("无需升级", result.stdout)

    def test_cli_upgrade_latest_overrides_saved_main_track(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
hy2_testdir="$(mktemp -d)"
trap 'rm -rf "$hy2_testdir"' EXIT
mkdir -p "$hy2_testdir/commands"
printf '%s\n' 'AIO_VERSION=1.3.28' 'HY2_TRACK_REF=main' > "$hy2_testdir/config.env"
cat > "$hy2_testdir/commands/curl" <<'EOS'
#!/bin/sh
printf '%s\n' "$*" >> "$HY2_TESTDIR/trace.log"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then
    out="$arg"
  fi
  prev="$arg"
done
if printf '%s' "$*" | grep -q '/releases/latest'; then
  printf '%s\n' '{"tag_name":"v9.9.9"}'
  [ -z "$out" ] && exit 0
fi
if [ -n "$out" ]; then
  {
    echo '#!/bin/sh'
    echo 'echo "HY2_REPO=${HY2_REPO-}" > "$HY2_TESTDIR/seen.env"'
    echo 'echo "HY2_REPO_REF=${HY2_REPO_REF-}" >> "$HY2_TESTDIR/seen.env"'
    echo 'echo "HY2_PERSIST_TRACK=${HY2_PERSIST_TRACK-}" >> "$HY2_TESTDIR/seen.env"'
  } > "$out"
  exit 0
fi
exit 1
EOS
chmod +x "$hy2_testdir/commands/curl"
cat > "$hy2_testdir/commands/id" <<'EOS'
#!/bin/sh
printf '0\n'
EOS
chmod +x "$hy2_testdir/commands/id"
export PATH="$hy2_testdir/commands:$PATH"
export HY2_TESTDIR="$hy2_testdir"
export HY2_REPO=alice/hy2-fork
export HY2_ENV_FILE="$hy2_testdir/config.env"
export HY2_REPO_REF=latest
unset HY2_REPO_URL
env PATH="$hy2_testdir/commands:/usr/bin:/bin" HY2_TESTDIR="$hy2_testdir" HY2_REPO_REF=latest /bin/bash "$PWD/bin/hy2.sh" upgrade
test -f "$hy2_testdir/seen.env"
grep -q 'HY2_REPO_REF=v9.9.9' "$hy2_testdir/seen.env"
grep -q 'HY2_PERSIST_TRACK=latest' "$hy2_testdir/seen.env"
grep -q 'releases/latest' "$hy2_testdir/trace.log"
grep -q 'v9.9.9/hy2.sh' "$hy2_testdir/trace.log"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_hash_label_and_fetched_modules_log(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
source ./hy2.sh
test "$(hash_label)" = "无"
test "$(hash_label "")" = "无"
test "$(hash_label abcdef0123456789)" = "abcdef012345"
test "$(hash_label abcdef0123456789 0123456789abcdef0123456789abcdef01234567)" = "abcdef012345（提交 0123456789ab）"
envf="$(mktemp)"
printf '%s\n' 'HY2_MODULES_SHA=oldhasholdhasholdhasholdhasholdhasholdhasholdhasholdhasholdha' \
  'HY2_REPO_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' > "$envf"
export HY2_ENV_FILE="$envf"
export HY2_FETCH_COMMIT=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
log_fetched_modules_hash newhashnewhashnewhashnewhashnewhashnewhashnewhashnewhashnewhas
test "$HY2_FETCH_MODULES_SHA" = "newhashnewhashnewhashnewhashnewhashnewhashnewhashnewhashnewhas"
rm -f "$envf"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        messages = log_messages(result.stdout)
        self.assertIn("上次哈希：oldhasholdha（提交 aaaaaaaaaaaa）", messages)
        self.assertIn("本次哈希：newhashnewha（提交 bbbbbbbbbbbb）", messages)
        self.assertIn("哈希已变化", messages)

    def test_fetched_modules_hash_unchanged(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
source ./hy2.sh
envf="$(mktemp)"
printf '%s\n' 'HY2_MODULES_SHA=samehashsamehashsamehashsamehashsamehashsamehashsamehashsameha' > "$envf"
export HY2_ENV_FILE="$envf"
unset HY2_FETCH_COMMIT || true
log_fetched_modules_hash samehashsamehashsamehashsamehashsamehashsamehashsamehashsameha
rm -f "$envf"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        messages = log_messages(result.stdout)
        self.assertIn("上次哈希：samehashsame", messages)
        self.assertIn("本次哈希：samehashsame", messages)
        self.assertIn("哈希未变化（模块文件与上次相同）", messages)

    def test_file_sha256_ignores_crlf(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
source ./hy2.sh
lf="$(mktemp)"
crlf="$(mktemp)"
printf 'abc\n' > "$lf"
printf 'abc\r\n' > "$crlf"
a="$(file_sha256 "$lf")"
b="$(file_sha256 "$crlf")"
rm -f "$lf" "$crlf"
test "$a" = "$b"
printf '%s\n' "$a"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb",
            result.stdout.strip().splitlines()[-1],
        )

    def test_remember_fetch_commit_from_raw_url(self):
        result = run_bash(
            r"""
set -Eeuo pipefail
source ./hy2.sh
HY2_FETCH_COMMIT=
HY2_REPO_URL=https://raw.githubusercontent.com/alice/hy2-fork/0123456789abcdef0123456789abcdef01234567
remember_fetch_commit main
printf '%s\n' "$HY2_FETCH_COMMIT"
"""
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertEqual(
            "0123456789abcdef0123456789abcdef01234567",
            result.stdout.strip().splitlines()[-1],
        )

    def test_repair_persist_updates_module_hashes(self):
        persist_py = persist_env_script()
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "config.env"
            env_file.write_text(
                "AIO_VERSION=1.3.28\nHY2_TRACK_REF=main\nHY2_MODULES_SHA=old\nHY2_REPO_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
                encoding="utf-8",
            )
            script = Path(tmp) / "persist.py"
            script.write_text(persist_py, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(env_file),
                    "1.4.0",
                    "main",
                    "newmodulesha",
                    "0123456789abcdef0123456789abcdef01234567",
                ],
                cwd=tmp,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            text = env_file.read_text(encoding="utf-8")
            self.assertIn("AIO_VERSION=1.4.0", text)
            self.assertIn("HY2_MODULES_SHA=newmodulesha", text)
            self.assertIn("HY2_REPO_SHA=0123456789abcdef0123456789abcdef01234567", text)

            completed = subprocess.run(
                [sys.executable, str(script), str(env_file), "1.4.0", "main", "", ""],
                cwd=tmp,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            kept = env_file.read_text(encoding="utf-8")
            self.assertIn("HY2_MODULES_SHA=newmodulesha", kept)
            self.assertIn("HY2_REPO_SHA=0123456789abcdef0123456789abcdef01234567", kept)

            completed = subprocess.run(
                [sys.executable, str(script), str(env_file), "1.4.0", "latest", "releasehash", "v1.4.0"],
                cwd=tmp,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            released = env_file.read_text(encoding="utf-8")
            self.assertIn("HY2_MODULES_SHA=releasehash", released)
            self.assertNotIn("HY2_REPO_SHA=", released)
            self.assertNotIn("HY2_TRACK_REF=", released)


if __name__ == "__main__":
    unittest.main()

