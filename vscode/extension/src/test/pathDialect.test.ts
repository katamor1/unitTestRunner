import * as assert from 'assert';
import * as path from 'path';
import { describe, it } from 'node:test';

import {
  isPathInside,
  pathDialect,
  resolveReportedPath,
} from '../platform/pathDialect';


describe('platform-independent path dialects', () => {
  it('selects Windows semantics for drive, UNC, and mixed Windows paths', () => {
    assert.equal(pathDialect('C:\\work\\product'), path.win32);
    assert.equal(pathDialect('C:/work/product'), path.win32);
    assert.equal(pathDialect('\\\\server\\share\\product'), path.win32);
  });

  it('selects POSIX semantics for rooted POSIX paths', () => {
    assert.equal(pathDialect('/work/product'), path.posix);
  });

  it('checks containment using the path value rather than the host OS', () => {
    assert.equal(isPathInside('C:\\work\\product\\_out', 'C:\\work\\product'), true);
    assert.equal(isPathInside('C:\\work\\other', 'C:\\work\\product'), false);
    assert.equal(isPathInside('\\\\server\\share\\src\\out', '\\\\server\\share\\src'), true);
    assert.equal(isPathInside('/work/product/out', '/work/product'), true);
    assert.equal(isPathInside('/work/other', '/work/product'), false);
    assert.equal(isPathInside('/work/product/out', 'C:\\work\\product'), false);
  });

  it('resolves relative report paths and retains absolute paths in either dialect', () => {
    assert.equal(
      resolveReportedPath('reports/function_dossier.md', 'C:\\work\\out'),
      'C:\\work\\out\\reports\\function_dossier.md',
    );
    assert.equal(
      resolveReportedPath('C:\\reports\\function_dossier.md', 'D:\\work\\out'),
      'C:\\reports\\function_dossier.md',
    );
    assert.equal(
      resolveReportedPath('/reports/function_dossier.md', 'C:\\work\\out'),
      '/reports/function_dossier.md',
    );
    assert.equal(
      resolveReportedPath('reports/function_dossier.md', '/work/out'),
      '/work/out/reports/function_dossier.md',
    );
  });
});
