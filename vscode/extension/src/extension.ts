import * as child_process from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';

type AdapterConfig = {
  cliPath: string;
  workspaceRoot: string;
  dswPath: string;
  outputRoot: string;
  defaultConfiguration: string;
  projectName: string;
};

const LAST_DOSSIER_KEY = 'unitTestRunner.lastFunctionDossierMarkdown';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Unit Test Runner');
  context.subscriptions.push(output);

  context.subscriptions.push(
    vscode.commands.registerCommand('unitTestRunner.analyzeSelectedFunction', async () => {
      await analyzeSelectedFunction(context, output);
    }),
    vscode.commands.registerCommand('unitTestRunner.openLastFunctionDossier', async () => {
      await openLastFunctionDossier(context);
    }),
  );
}

export function deactivate(): void {
  // No long-lived process is kept by this thin adapter.
}

async function analyzeSelectedFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Open a C source file before running UnitTestRunner.');
  }

  const config = readConfig();
  validateConfig(config);
  const functionName = await resolveFunctionName(editor);
  const source = relativeSourcePath(editor.document.uri.fsPath, config.workspaceRoot);
  const outDir = path.join(config.outputRoot, functionName);
  const args = [
    'analyze-function',
    '--workspace',
    config.workspaceRoot,
    '--dsw',
    config.dswPath,
    '--source',
    source,
    '--function',
    functionName,
    '--configuration',
    config.defaultConfiguration,
    '--out',
    outDir,
  ];
  if (config.projectName) {
    args.push('--project', config.projectName);
  }

  output.show(true);
  output.appendLine(`> ${config.cliPath} ${args.map(quoteForLog).join(' ')}`);
  await runCli(config.cliPath, args, output);

  const markdownPath = path.join(outDir, 'reports', 'function_dossier.md');
  await context.globalState.update(LAST_DOSSIER_KEY, markdownPath);
  await openMarkdownPreview(markdownPath);
}

function readConfig(): AdapterConfig {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  const config = vscode.workspace.getConfiguration('unitTestRunner');
  return {
    cliPath: config.get<string>('cliPath', 'unit-test-runner'),
    workspaceRoot: config.get<string>('workspaceRoot', '') || workspaceFolder,
    dswPath: config.get<string>('dswPath', ''),
    outputRoot: config.get<string>('outputRoot', ''),
    defaultConfiguration: config.get<string>('defaultConfiguration', 'Win32 Debug'),
    projectName: config.get<string>('projectName', ''),
  };
}

function validateConfig(config: AdapterConfig): void {
  const missing: string[] = [];
  if (!config.workspaceRoot) {
    missing.push('unitTestRunner.workspaceRoot');
  }
  if (!config.dswPath) {
    missing.push('unitTestRunner.dswPath');
  }
  if (!config.outputRoot) {
    missing.push('unitTestRunner.outputRoot');
  }
  if (missing.length > 0) {
    throw new Error(`Missing required setting(s): ${missing.join(', ')}`);
  }
}

async function resolveFunctionName(editor: vscode.TextEditor): Promise<string> {
  const selected = editor.document.getText(editor.selection).trim();
  if (selected && /^[A-Za-z_]\w*$/.test(selected)) {
    return selected;
  }

  const line = editor.document.lineAt(editor.selection.active.line).text;
  const identifier = line.match(/[A-Za-z_]\w*/)?.[0];
  const prompt = await vscode.window.showInputBox({
    prompt: 'Function name to analyze',
    value: selected || identifier || '',
    validateInput: (value) => (/^[A-Za-z_]\w*$/.test(value) ? undefined : 'Enter a C function identifier.'),
  });
  if (!prompt) {
    throw new Error('Function analysis cancelled.');
  }
  return prompt;
}

function relativeSourcePath(sourcePath: string, workspaceRoot: string): string {
  const relative = path.relative(workspaceRoot, sourcePath);
  return relative.split(path.sep).join('/');
}

function runCli(cliPath: string, args: string[], output: vscode.OutputChannel): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = child_process.spawn(cliPath, args, { shell: false });
    child.stdout.on('data', (chunk: Buffer) => output.append(chunk.toString()));
    child.stderr.on('data', (chunk: Buffer) => output.append(chunk.toString()));
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`unit-test-runner exited with code ${code ?? 'unknown'}.`));
      }
    });
  });
}

async function openLastFunctionDossier(context: vscode.ExtensionContext): Promise<void> {
  const last = context.globalState.get<string>(LAST_DOSSIER_KEY);
  if (!last) {
    throw new Error('No previous function dossier is recorded.');
  }
  await openMarkdownPreview(last);
}

async function openMarkdownPreview(markdownPath: string): Promise<void> {
  const uri = vscode.Uri.file(markdownPath);
  await vscode.commands.executeCommand('vscode.open', uri);
  await vscode.commands.executeCommand('markdown.showPreview', uri);
}

function quoteForLog(value: string): string {
  return value.includes(' ') ? `"${value}"` : value;
}
