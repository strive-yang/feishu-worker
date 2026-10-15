"""Offline checks of installed tool schemas, not a live MCP tools/list call."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "node_modules/@larksuiteoapi/lark-mcp"


@unittest.skipUnless(shutil.which("node") and PACKAGE.is_dir(), "run npm ci first")
class LocalToolTests(unittest.TestCase):
    def test_whitelisted_schemas_exist_and_support_user_identity(self):
        launcher = (ROOT / "scripts/start-feishu-mcp.ps1").read_text(encoding="utf-8-sig")
        tool_section = launcher.split("$FeishuTools = @(", 1)[1].split(") -join", 1)[0]
        expected = re.findall(r'"([a-zA-Z0-9.]+)"', tool_section)
        self.assertEqual(len(expected), len(set(expected)))
        code = r"""
const base = './node_modules/@larksuiteoapi/lark-mcp/dist/mcp-tool/tools/zh/';
const tools = [
  ...require(base + 'gen-tools/zod/docx_v1.js').docxV1Tools,
  ...require(base + 'gen-tools/zod/drive_v1.js').driveV1Tools,
  ...require(base + 'gen-tools/zod/wiki_v1.js').wikiV1Tools,
  ...require(base + 'gen-tools/zod/wiki_v2.js').wikiV2Tools,
  ...require(base + 'builtin-tools/docx/builtin.js').docxBuiltinTools
];
const expected = JSON.parse(process.argv[1]);
const selected = expected.map(name => {
  const tool = tools.find(t => t.name === name);
  if (!tool || !tool.accessTokens.includes('user') || !tool.schema) {
    throw new Error('Missing user-compatible tool schema: ' + name);
  }
  require('zod').z.object(tool.schema);
  return tool.name;
});
const unexpected = Object.keys(require.cache).filter(p =>
  /lark-mcp[\\/]dist[\\/](auth[\\/]|utils[\\/]logger\.js)/.test(p));
if (unexpected.length) throw new Error('Offline check imported live auth/logging modules');
console.log(JSON.stringify(selected));
"""
        result = subprocess.run([shutil.which("node"), "-e", code, json.dumps(expected)],
                                cwd=ROOT, capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual(result.stderr, "")

    def test_import_filename_boundary_and_independent_full_title(self):
        code = r"""
const assert = require('node:assert/strict');
const {z} = require('zod');
for (const locale of ['zh', 'en']) {
  const tool = require('./node_modules/@larksuiteoapi/lark-mcp/dist/mcp-tool/tools/' +
    locale + '/builtin-tools/docx/builtin.js').larkDocxBuiltinImportTool;
  const schema = z.object(tool.schema);
  const title = 'Synthetic full title ' + 'x'.repeat(40);
  const markdown = '# ' + title + '\n\nSynthetic test content.';
  const parse = name => schema.safeParse({data: {markdown, file_name: name}, useUAT: true});
  assert.equal(parse('a'.repeat(27)).success, true);
  assert.equal(parse('a'.repeat(28)).success, false);
  assert.equal(parse('\u540d'.repeat(27)).success, true);
  assert.equal(parse('\u540d'.repeat(28)).success, false);
  assert.equal(parse('\u{1f4c4}'.repeat(27)).success, true);
  assert.equal(parse('\u{1f4c4}'.repeat(28)).success, false);
  assert.equal(parse(title).success, false);
  const accepted = parse('synthetic-card');
  assert.equal(accepted.success, true);
  assert.equal(accepted.data.data.markdown, markdown);
  assert.equal(accepted.data.useUAT, true);
}
assert.equal(Object.keys(require.cache).filter(p =>
  /lark-mcp[\\/]dist[\\/](auth[\\/]|utils[\\/]logger\.js)/.test(p)).length, 0);
console.log('PASS: short import name, full title preserved, no handler or auth invoked');
"""
        result = subprocess.run([shutil.which("node"), "-e", code], cwd=ROOT,
                                capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_runtime_adapter_changes_only_log_path_without_loading_auth(self):
        code = r"""
const path = require('node:path');
const constants = require('./node_modules/@larksuiteoapi/lark-mcp/dist/utils/constants.js');
const before = {...constants.ENV_PATHS};
const cli = require('./scripts/lark-runtime.cjs').prepareRuntime();
const assert = require('node:assert/strict');
assert.equal(cli, path.resolve('node_modules/@larksuiteoapi/lark-mcp/dist/cli.js'));
assert.equal(constants.ENV_PATHS.log, path.resolve('.runtime/lark-logs'));
for (const key of Object.keys(before).filter(k => k !== 'log')) {
  assert.equal(constants.ENV_PATHS[key], before[key]);
}
assert.equal(Object.keys(require.cache).filter(p =>
  /lark-mcp[\\/]dist[\\/](auth[\\/]|utils[\\/]logger\.js|cli\.js)/.test(p)).length, 0);
console.log('PASS: log path local, OAuth paths unchanged, no auth or logger initialized');
"""
        result = subprocess.run([shutil.which("node"), "-e", code], cwd=ROOT,
                                capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_dependency_is_pinned_and_locked(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        installed = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["dependencies"]["@larksuiteoapi/lark-mcp"], "0.5.1")
        self.assertEqual(lock["packages"]["node_modules/@larksuiteoapi/lark-mcp"]["version"], "0.5.1")
        self.assertEqual(installed["version"], "0.5.1")
