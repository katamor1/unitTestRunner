import * as path from 'path';


const WINDOWS_DRIVE_ROOT = /^[A-Za-z]:[\\/]/;
const WINDOWS_UNC_ROOT = /^(?:\\\\|\/\/)[^\\/]+[\\/][^\\/]+/;


export function pathDialect(value: string): typeof path.win32 | typeof path.posix {
  if (WINDOWS_DRIVE_ROOT.test(value) || WINDOWS_UNC_ROOT.test(value) || value.includes('\\')) {
    return path.win32;
  }
  return path.posix;
}

export function isPathInside(candidate: string, root: string): boolean {
  const rootDialect = pathDialect(root);
  const candidateDialect = pathDialect(candidate);
  if (
    rootDialect !== candidateDialect
    && (rootDialect.isAbsolute(root) || candidateDialect.isAbsolute(candidate))
  ) {
    return false;
  }
  const resolvedRoot = rootDialect.resolve(root);
  const resolvedCandidate = rootDialect.resolve(candidate);
  const relative = rootDialect.relative(resolvedRoot, resolvedCandidate);
  return relative === ''
    || (!!relative && relative !== '..' && !relative.startsWith(`..${rootDialect.sep}`) && !rootDialect.isAbsolute(relative));
}

export function resolveReportedPath(value: string, workspace: string): string {
  const reportedDialect = pathDialect(value);
  if (reportedDialect.isAbsolute(value)) {
    return value;
  }
  const workspaceDialect = pathDialect(workspace);
  const relative = workspaceDialect === path.win32
    ? value.replace(/\//g, '\\')
    : value.replace(/\\/g, '/');
  return workspaceDialect.resolve(workspace, relative);
}
