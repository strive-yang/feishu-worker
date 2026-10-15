// Compatibility adapter for lark-mcp 0.5.1: local logs and stdio shutdown.
// OAuth storage and credential handling remain owned by the official server.
// This relies on an internal exported path object; keep the version pin and tests.
const path = require('node:path');

function prepareRuntime(projectRoot = path.resolve(__dirname, '..')) {
  const packageRoot = path.join(projectRoot, 'node_modules/@larksuiteoapi/lark-mcp');
  const version = require(path.join(packageRoot, 'package.json')).version;
  if (version !== '0.5.1') throw new Error('Unsupported lark-mcp version');
  const { ENV_PATHS } = require(path.join(packageRoot, 'dist/utils/constants.js'));
  if (!ENV_PATHS || typeof ENV_PATHS.data !== 'string' || typeof ENV_PATHS.log !== 'string') {
    throw new Error('Unsupported lark-mcp runtime paths');
  }
  // constants.js does not load auth or logging. Change the log path before either
  // initializes. Leave data and keytar configuration untouched to reuse OAuth.
  ENV_PATHS.log = path.join(projectRoot, '.runtime/lark-logs');
  return path.join(packageRoot, 'dist/cli.js');
}

module.exports = { prepareRuntime };

if (require.main === module) {
  try {
    const cliPath = prepareRuntime();
    const args = process.argv.slice(2);
    if (args[0] === 'mcp' && args[args.indexOf('--mode') + 1] === 'stdio') {
      process.stdin.once('end', () => {
        // The official AuthStore file watcher otherwise keeps Node alive after
        // the protocol channel closes. Close the already-loaded watcher only;
        // do not load a new store, read tokens, or force-exit in-flight requests.
        const storePath = path.join(path.dirname(cliPath), 'auth/store.js');
        require.cache[storePath]?.exports.authStore?.destroy();
      });
    }
    require(cliPath);
  } catch {
    // Never print an exception that might contain credentials or protocol data.
    console.error('Unable to start local lark-mcp. Check the pinned dependency and runtime adapter.');
    process.exitCode = 1;
  }
}
