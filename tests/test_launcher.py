"""Windows launcher tests with synthetic credentials and a local fake CLI only."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
NODE = shutil.which("node")

FAKE_CLI = r"""
const fs = require('node:fs');
const readline = require('node:readline');
const args = process.argv.slice(2);
const summary = {
  args,
  utf8Text: '测试资料卡',
  fileCredentials: process.env.APP_ID === 'cli_fixture_app' &&
    process.env.APP_SECRET === 'fixture-secret=with=equals',
  foreignTokenRemoved: !process.env.USER_ACCESS_TOKEN,
  isolatedCwd: process.cwd().endsWith(require('node:path').join('.runtime', 'mcp')),
  callerEnvIgnored: !process.env.FIXTURE_DOTENV_MARKER,
  logsAreLocal: require('./utils/constants.js').ENV_PATHS.log.endsWith(
    require('node:path').join('.runtime', 'lark-logs')),
  authDataUnchanged: require('./utils/constants.js').ENV_PATHS.data === 'fixture-user-data'
};
if (process.env.FIXTURE_PROTOCOL === '1') {
  if (process.env.FIXTURE_FILE_WATCHER === '1') require('./auth/store.js');
  readline.createInterface({input: process.stdin}).on('line', line => {
    const request = JSON.parse(line);
    if (request.id !== undefined) {
      console.log(JSON.stringify({jsonrpc: '2.0', id: request.id, result: summary}));
    }
  });
} else {
  console.log(JSON.stringify(summary));
  process.exit(Number(process.env.FIXTURE_EXIT_CODE || 0));
}
"""


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL and NODE,
                     "requires Windows PowerShell and Node.js")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / ".runtime" / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="launcher-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fixture workspace"
        scripts = self.root / "scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / "start-feishu-mcp.ps1"
        shutil.copyfile(ROOT / "scripts" / self.script.name, self.script)
        shutil.copyfile(ROOT / "scripts/lark-runtime.cjs", scripts / "lark-runtime.cjs")
        self.package = self.root / "node_modules/@larksuiteoapi/lark-mcp"
        (self.package / "dist/utils").mkdir(parents=True)
        (self.package / "dist/utils/constants.js").write_text(
            "exports.ENV_PATHS = {data: 'fixture-user-data', log: 'fixture-user-log'};", encoding="utf-8")
        (self.package / "dist/auth").mkdir()
        (self.package / "dist/auth/store.js").write_text(
            "const watcher = require('node:fs').watch(__filename, () => {});\n"
            "exports.authStore = {destroy() { watcher.close(); }};\n", encoding="utf-8")
        (self.package / "dist/cli.js").write_text(FAKE_CLI, encoding="utf-8")
        (self.package / "package.json").write_text('{"version":"0.5.1"}', encoding="utf-8")
        self.other_cwd = Path(self.temp.name) / "unrelated cwd"
        self.other_cwd.mkdir()
        (self.other_cwd / ".env").write_text("FIXTURE_DOTENV_MARKER=1\n", encoding="utf-8")
        self.config = self.root / "config.conf"
        self.config.write_text(
            "# synthetic test data, never real credentials\n\n"
            "APP_ID=cli_fixture_app\nAPP_SECRET=fixture-secret=with=equals\n", encoding="utf-8")

    def run_launcher(self, *args, config=None, extra_env=None, input_text=None):
        if config is not None:
            self.config.write_text(config, encoding="utf-8")
        env = os.environ.copy()
        env.update(APP_ID="foreign-app", APP_SECRET="foreign-secret",
                   USER_ACCESS_TOKEN="foreign-user-token")
        for key in ("FIXTURE_PROTOCOL", "FIXTURE_EXIT_CODE", "FIXTURE_DOTENV_MARKER", "FIXTURE_FILE_WATCHER"):
            env.pop(key, None)
        env.update(extra_env or {})
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script), *args],
            cwd=self.other_cwd, env=env, input=input_text, capture_output=True,
            encoding="utf-8", errors="replace", timeout=20)
        for sensitive in ("fixture-secret=with=equals", "foreign-secret", "foreign-user-token"):
            self.assertNotIn(sensitive, result.stdout + result.stderr)
        return result

    def test_valid_configuration_from_unrelated_cwd_and_environment(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["utf8Text"], "测试资料卡")
        self.assertTrue(summary["fileCredentials"])
        self.assertTrue(summary["foreignTokenRemoved"])
        self.assertTrue(summary["isolatedCwd"])
        self.assertTrue(summary["callerEnvIgnored"])
        self.assertTrue(summary["logsAreLocal"])
        self.assertTrue(summary["authDataUnchanged"])
        self.assertEqual(summary["args"][0], "mcp")
        self.assertIn("--oauth", summary["args"])
        self.assertIn("user_access_token", summary["args"])
        self.assertIn("docx:document drive:drive wiki:wiki offline_access", summary["args"])
        self.assertEqual(result.stderr, "")

    def test_check_does_not_start_cli_or_create_runtime(self):
        result = self.run_launcher("-Check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OAuth and API access were not checked", result.stdout)
        self.assertFalse((self.root / ".runtime").exists())

    def test_login_uses_same_scope_and_no_credentials_in_arguments(self):
        result = self.run_launcher("-Login")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["args"][0], "login")
        self.assertNotIn("--oauth", summary["args"])
        self.assertTrue(summary["fileCredentials"])
        self.assertIn("docx:document drive:drive wiki:wiki offline_access", summary["args"])

    def test_child_exit_code_is_preserved(self):
        self.assertEqual(self.run_launcher(extra_env={"FIXTURE_EXIT_CODE": "7"}).returncode, 7)

    def test_missing_config(self):
        self.config.unlink()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 1)
        self.assertIn("config.conf is missing", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_invalid_configuration_does_not_leak_values(self):
        cases = {
            "duplicate": "APP_ID=cli_fixture_app\nAPP_ID=private-marker\nAPP_SECRET=fixture-secret=with=equals\n",
            "case_duplicate": "APP_ID=cli_fixture_app\napp_id=private-marker\nAPP_SECRET=fixture-secret=with=equals\n",
            "missing_key": "APP_ID=cli_fixture_app\n",
            "empty": "APP_ID=cli_fixture_app\nAPP_SECRET= \n",
            "placeholder": "APP_ID=cli_your_app_id\nAPP_SECRET=your_app_secret\n",
            "malformed": "private-marker\nAPP_ID=cli_fixture_app\nAPP_SECRET=fixture-secret=with=equals\n",
        }
        for name, config in cases.items():
            with self.subTest(name=name):
                result = self.run_launcher(config=config)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("private-marker", result.stderr)

    def test_quotes_comments_and_first_equals(self):
        result = self.run_launcher(config=(
            "  # comment\n\n APP_ID = 'cli_fixture_app' \n"
            ' APP_SECRET = "fixture-secret=with=equals" \n'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["fileCredentials"])

    def test_config_is_data_not_a_script(self):
        marker = self.root / "must-not-exist"
        value = f"$(New-Item -ItemType File -Path '{marker}')"
        result = self.run_launcher("-Check", config=f"APP_ID=cli_fixture_app\nAPP_SECRET={value}\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_dependency_must_exist_and_match_version(self):
        (self.package / "package.json").write_text('{"version":"9.9.9"}', encoding="utf-8")
        result = self.run_launcher("-Check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be version 0.5.1", result.stderr)
        (self.package / "dist/cli.js").unlink()
        result = self.run_launcher("-Check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Local lark-mcp is missing", result.stderr)

    def test_adapter_rejects_changed_internal_paths_without_starting_cli(self):
        (self.package / "dist/utils/constants.js").write_text("exports.ENV_PATHS = {};", encoding="utf-8")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Unable to start local lark-mcp", result.stderr)

    def test_conflicting_modes(self):
        result = self.run_launcher("-Login", "-Check")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_stdio_eof_closes_loaded_auth_watcher(self):
        request = '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        result = self.run_launcher(
            extra_env={"FIXTURE_PROTOCOL": "1", "FIXTURE_FILE_WATCHER": "1"}, input_text=request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["id"], 1)

    def test_stdio_and_exit_with_a_mock_protocol_child(self):
        request = '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        result = self.run_launcher(extra_env={"FIXTURE_PROTOCOL": "1"}, input_text=request)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        reply = json.loads(lines[0])
        self.assertEqual(reply["id"], 1)
        self.assertTrue(reply["result"]["fileCredentials"])
