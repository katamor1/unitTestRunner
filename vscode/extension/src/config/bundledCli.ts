import * as fs from 'fs';
import * as path from 'path';

export const DEFAULT_CLI_PATH = 'unit-test-runner';

export function bundledCliRelativePath(platform = process.platform, arch = process.arch): string | undefined {
  if (platform === 'win32' && arch === 'x64') {
    return path.join('bin', 'win32-x64', 'unit-test-runner.exe');
  }
  return undefined;
}

export function resolveCliPath(
  configuredCliPath: string,
  extensionPath: string,
  exists: (candidate: string) => boolean = fs.existsSync,
  platform = process.platform,
  arch = process.arch,
): string {
  const configured = configuredCliPath.trim();
  if (configured && configured !== DEFAULT_CLI_PATH) {
    return configuredCliPath;
  }
  const bundledRelativePath = bundledCliRelativePath(platform, arch);
  if (bundledRelativePath) {
    const bundledPath = path.join(extensionPath, bundledRelativePath);
    if (exists(bundledPath)) {
      return bundledPath;
    }
  }
  return configured || DEFAULT_CLI_PATH;
}
