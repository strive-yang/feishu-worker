"""Bounded regression and loopback-only compatibility tests for the FTP fix."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE and (ROOT / "node_modules/get-uri").is_dir(), "run npm ci first")
class DependencySecurityTests(unittest.TestCase):
    def run_scenario(self, scenario, timeout=20):
        env = os.environ.copy()
        # The fixture chooses explicit loopback endpoints and does not need any
        # user credentials, tracing, or proxy settings inherited from the host.
        for name in list(env):
            if name.upper() in {"APP_ID", "APP_SECRET", "USER_ACCESS_TOKEN", "DEBUG", "NODE_OPTIONS"} or \
                    name.upper().endswith("_PROXY"):
                env.pop(name, None)
        result = subprocess.run([NODE, str(ROOT / "tests/proxy_compat.cjs"), scenario],
                                cwd=ROOT, env=env, capture_output=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"PASS: {scenario}", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_override_resolves_through_actual_mcp_dependency_chain(self):
        self.run_scenario("version")

    def test_directory_parser_does_not_stall_on_advisory_input(self):
        self.run_scenario("parser", timeout=5)

    def test_get_uri_ftp_download_listing_cache_and_not_found(self):
        self.run_scenario("ftp")

    def test_get_uri_uses_machine_listing_when_mdtm_is_unavailable(self):
        self.run_scenario("listing")

    def test_pasv_retains_control_host_by_default(self):
        self.run_scenario("pasv")

    def test_direct_http_proxy_and_data_and_ftp_pac(self):
        self.run_scenario("proxy")
