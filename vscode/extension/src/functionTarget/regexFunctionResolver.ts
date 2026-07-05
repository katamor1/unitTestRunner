export interface FunctionNameResolveInput {
  selectedText: string;
  documentText: string;
  cursorOffset: number;
}

const IDENTIFIER = /^[A-Za-z_]\w*$/;

export function resolveFunctionNameFromText(input: FunctionNameResolveInput): string | undefined {
  const selected = input.selectedText.trim();
  if (IDENTIFIER.test(selected)) {
    return selected;
  }
  const prefix = input.documentText.slice(0, Math.max(0, input.cursorOffset));
  const pattern = /(?:^|\n)\s*(?:static\s+)?(?:[A-Za-z_]\w*[\s*]+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{/g;
  let match: RegExpExecArray | null;
  let found: string | undefined;
  while ((match = pattern.exec(prefix)) !== null) {
    found = match[1];
  }
  return found;
}
