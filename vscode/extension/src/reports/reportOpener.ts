import * as path from 'path';
import * as vscode from 'vscode';

export async function openMarkdown(markdownPath: string): Promise<void> {
  const uri = vscode.Uri.file(markdownPath);
  await vscode.commands.executeCommand('vscode.open', uri);
  await vscode.commands.executeCommand('markdown.showPreview', uri);
}

export async function openReport(reportPath: string): Promise<void> {
  if (path.extname(reportPath).toLowerCase() === '.md') {
    await openMarkdown(reportPath);
    return;
  }
  await openPlainFile(reportPath);
}

export async function openPlainFile(reportPath: string): Promise<void> {
  const uri = vscode.Uri.file(reportPath);
  await vscode.commands.executeCommand('vscode.open', uri);
}
