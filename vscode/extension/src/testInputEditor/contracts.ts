export type TestInputControlKind = 'c_expression' | 'multiline' | 'enum';

export interface TestInputSuggestion {
  value: string;
  label: string;
  source: string;
  confidence: string;
}

export interface TestInputFormControl {
  name: string;
  controlKind: TestInputControlKind;
  requiredForConfirmation: boolean;
  value: string | null;
  suggestions: readonly TestInputSuggestion[];
  enumValues: readonly string[];
}

export interface TestInputWarning {
  code: string;
  severity: string;
  message: string;
}

export interface TestInputFormItem {
  itemId: string;
  subjectFingerprint: string;
  kind: string;
  label: string;
  confirmed: boolean;
  blocking: boolean;
  editable: boolean;
  controls: readonly TestInputFormControl[];
  warnings: readonly TestInputWarning[];
}

export interface TestInputFormCase {
  caseId: string;
  location: 'test_cases' | 'additional_case_candidates';
  promotionEligible: boolean;
  items: readonly TestInputFormItem[];
}

export interface TestInputFormSummary {
  attentionCount: number;
  unresolvedCount: number;
  unconfirmedCount: number;
  executionBlockingCount: number;
  warningCount: number;
}

export interface TestInputFormModel {
  schemaVersion: '1.0';
  revision: number;
  specSha256: string;
  functionName: string;
  summary: TestInputFormSummary;
  cases?: readonly TestInputFormCase[];
}

export interface TestInputChangeDraft {
  itemId: string;
  subjectFingerprint: string;
  values: Readonly<Record<string, string>>;
  confirmed: boolean;
}

export interface TestInputApplyResult {
  revision: number;
  specSha256: string;
  updatedItemCount: number;
  confirmedItemCount: number;
  promotedCaseIds: readonly string[];
  demotedCaseIds: readonly string[];
  summary: TestInputFormSummary;
  viewsWritten: boolean;
  warnings: readonly TestInputWarning[];
}

export type TestInputEditorMessage =
  | { type: 'selectCase'; caseId: string }
  | { type: 'editControl'; itemId: string; control: string; value: string }
  | { type: 'setConfirmed'; itemId: string; confirmed: boolean }
  | { type: 'save' }
  | { type: 'discard' }
  | { type: 'reload' }
  | { type: 'openCanonical' }
  | { type: 'resolveConflict'; itemId: string; choice: 'latest' | 'draft' };

const SHA256 = /^[0-9a-f]{64}$/;
const ITEM_ID = /^item-[0-9a-f]{64}$/;
const CONTROL_KINDS = new Set<TestInputControlKind>(['c_expression', 'multiline', 'enum']);
const CASE_LOCATIONS = new Set(['test_cases', 'additional_case_candidates']);
const MAX_MESSAGE_VALUE_LENGTH = 16_384;

export function parseTestInputFormEnvelope(value: unknown): TestInputFormModel {
  return parseFormDetails(parseSuccessfulDetails(value, 'get-test-input-form'));
}

export function parseTestInputApplyEnvelope(value: unknown): TestInputApplyResult {
  const details = parseSuccessfulDetails(value, 'apply-test-input-form');
  exactKeys(details, [
    'revision', 'spec_sha256', 'updated_item_count', 'confirmed_item_count',
    'promoted_case_ids', 'demoted_case_ids', 'summary', 'views_written', 'warnings',
  ], 'apply details');
  return {
    revision: positiveInteger(details.revision, 'apply details.revision'),
    specSha256: sha256(details.spec_sha256, 'apply details.spec_sha256'),
    updatedItemCount: nonnegativeInteger(details.updated_item_count, 'apply details.updated_item_count'),
    confirmedItemCount: nonnegativeInteger(details.confirmed_item_count, 'apply details.confirmed_item_count'),
    promotedCaseIds: stringArray(details.promoted_case_ids, 'apply details.promoted_case_ids'),
    demotedCaseIds: stringArray(details.demoted_case_ids, 'apply details.demoted_case_ids'),
    summary: parseSummary(details.summary),
    viewsWritten: booleanValue(details.views_written, 'apply details.views_written'),
    warnings: warningArray(details.warnings, 'apply details.warnings'),
  };
}

export function parseTestInputCliError(value: unknown): { code: string; message: string } | undefined {
  if (!isRecord(value) || value.artifact_kind !== 'cli_result' || value.schema_version !== '1.0.0') {
    return undefined;
  }
  const data = recordValue(value.data, 'CLI data');
  const errors = data.errors;
  if (!Array.isArray(errors) || errors.length === 0 || !isRecord(errors[0])) {
    return undefined;
  }
  const code = errors[0].code;
  const message = errors[0].message;
  return typeof code === 'string' && typeof message === 'string' ? { code, message } : undefined;
}

export function parseTestInputEditorMessage(value: unknown): TestInputEditorMessage {
  const record = recordValue(value, 'Webview message');
  const type = stringValue(record.type, 'Webview message.type');
  if (type === 'save' || type === 'discard' || type === 'reload' || type === 'openCanonical') {
    exactKeys(record, ['type'], `Webview ${type} message`);
    return { type };
  }
  if (type === 'selectCase') {
    exactKeys(record, ['type', 'caseId'], 'Webview selectCase message');
    return { type, caseId: boundedString(record.caseId, 'caseId', 512) };
  }
  if (type === 'editControl') {
    exactKeys(record, ['type', 'itemId', 'control', 'value'], 'Webview editControl message');
    return {
      type,
      itemId: itemId(record.itemId, 'itemId'),
      control: boundedString(record.control, 'control', 128),
      value: boundedString(record.value, 'value', MAX_MESSAGE_VALUE_LENGTH, true),
    };
  }
  if (type === 'setConfirmed') {
    exactKeys(record, ['type', 'itemId', 'confirmed'], 'Webview setConfirmed message');
    return { type, itemId: itemId(record.itemId, 'itemId'), confirmed: booleanValue(record.confirmed, 'confirmed') };
  }
  if (type === 'resolveConflict') {
    exactKeys(record, ['type', 'itemId', 'choice'], 'Webview resolveConflict message');
    const choice = stringValue(record.choice, 'choice');
    if (choice !== 'latest' && choice !== 'draft') {
      throw new Error('choice must be latest or draft.');
    }
    return { type, itemId: itemId(record.itemId, 'itemId'), choice };
  }
  throw new Error(`Unknown Webview message type: ${type}`);
}

function parseSuccessfulDetails(value: unknown, command: string): Record<string, unknown> {
  const root = recordValue(value, 'CLI envelope');
  if (root.artifact_kind !== 'cli_result' || root.schema_version !== '1.0.0') {
    throw new Error('Unsupported CLI envelope.');
  }
  const data = recordValue(root.data, 'CLI data');
  if (data.command !== command || data.outcome !== 'passed' || data.exit_code !== 0) {
    throw new Error(`CLI command ${command} did not return a successful result.`);
  }
  return recordValue(data.details, 'CLI details');
}

function parseFormDetails(details: Record<string, unknown>): TestInputFormModel {
  const allowed = ['schema_version', 'revision', 'spec_sha256', 'function', 'summary'];
  if (Object.prototype.hasOwnProperty.call(details, 'cases')) {
    allowed.push('cases');
  }
  exactKeys(details, allowed, 'form details');
  if (details.schema_version !== '1.0') {
    throw new Error('Unsupported test input form schema version.');
  }
  const fn = recordValue(details.function, 'form details.function');
  exactKeys(fn, ['name'], 'form details.function');
  return {
    schemaVersion: '1.0',
    revision: positiveInteger(details.revision, 'form details.revision'),
    specSha256: sha256(details.spec_sha256, 'form details.spec_sha256'),
    functionName: nonEmptyString(fn.name, 'form details.function.name'),
    summary: parseSummary(details.summary),
    cases: Object.prototype.hasOwnProperty.call(details, 'cases')
      ? caseArray(details.cases, 'form details.cases')
      : undefined,
  };
}

function parseSummary(value: unknown): TestInputFormSummary {
  const summary = recordValue(value, 'summary');
  exactKeys(summary, ['attention_count', 'unresolved_count', 'unconfirmed_count', 'execution_blocking_count', 'warning_count'], 'summary');
  return {
    attentionCount: nonnegativeInteger(summary.attention_count, 'summary.attention_count'),
    unresolvedCount: nonnegativeInteger(summary.unresolved_count, 'summary.unresolved_count'),
    unconfirmedCount: nonnegativeInteger(summary.unconfirmed_count, 'summary.unconfirmed_count'),
    executionBlockingCount: nonnegativeInteger(summary.execution_blocking_count, 'summary.execution_blocking_count'),
    warningCount: nonnegativeInteger(summary.warning_count, 'summary.warning_count'),
  };
}

function caseArray(value: unknown, path: string): TestInputFormCase[] {
  if (!Array.isArray(value)) {
    throw new Error(`${path} must be an array.`);
  }
  return value.map((entry, index) => {
    const item = recordValue(entry, `${path}[${index}]`);
    exactKeys(item, ['case_id', 'location', 'promotion_eligible', 'items'], `${path}[${index}]`);
    const location = stringValue(item.location, `${path}[${index}].location`);
    if (!CASE_LOCATIONS.has(location)) {
      throw new Error(`${path}[${index}].location is invalid.`);
    }
    return {
      caseId: nonEmptyString(item.case_id, `${path}[${index}].case_id`),
      location: location as TestInputFormCase['location'],
      promotionEligible: booleanValue(item.promotion_eligible, `${path}[${index}].promotion_eligible`),
      items: formItemArray(item.items, `${path}[${index}].items`),
    };
  });
}

function formItemArray(value: unknown, path: string): TestInputFormItem[] {
  if (!Array.isArray(value)) {
    throw new Error(`${path} must be an array.`);
  }
  const result = value.map((entry, index) => {
    const item = recordValue(entry, `${path}[${index}]`);
    exactKeys(item, ['item_id', 'subject_fingerprint', 'kind', 'label', 'confirmed', 'blocking', 'editable', 'controls', 'warnings'], `${path}[${index}]`);
    return {
      itemId: itemId(item.item_id, `${path}[${index}].item_id`),
      subjectFingerprint: sha256(item.subject_fingerprint, `${path}[${index}].subject_fingerprint`),
      kind: nonEmptyString(item.kind, `${path}[${index}].kind`),
      label: nonEmptyString(item.label, `${path}[${index}].label`),
      confirmed: booleanValue(item.confirmed, `${path}[${index}].confirmed`),
      blocking: booleanValue(item.blocking, `${path}[${index}].blocking`),
      editable: booleanValue(item.editable, `${path}[${index}].editable`),
      controls: controlArray(item.controls, `${path}[${index}].controls`),
      warnings: warningArray(item.warnings, `${path}[${index}].warnings`),
    };
  });
  const ids = result.map((item) => item.itemId);
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${path} contains duplicate item IDs.`);
  }
  return result;
}

function controlArray(value: unknown, path: string): TestInputFormControl[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${path} must be a non-empty array.`);
  }
  return value.map((entry, index) => {
    const item = recordValue(entry, `${path}[${index}]`);
    exactKeys(item, ['name', 'control_kind', 'required_for_confirmation', 'value', 'suggestions', 'enum_values'], `${path}[${index}]`);
    const controlKind = stringValue(item.control_kind, `${path}[${index}].control_kind`);
    if (!CONTROL_KINDS.has(controlKind as TestInputControlKind)) {
      throw new Error(`${path}[${index}].control_kind is invalid.`);
    }
    if (item.value !== null && typeof item.value !== 'string') {
      throw new Error(`${path}[${index}].value must be a string or null.`);
    }
    return {
      name: nonEmptyString(item.name, `${path}[${index}].name`),
      controlKind: controlKind as TestInputControlKind,
      requiredForConfirmation: booleanValue(item.required_for_confirmation, `${path}[${index}].required_for_confirmation`),
      value: item.value as string | null,
      suggestions: suggestionArray(item.suggestions, `${path}[${index}].suggestions`),
      enumValues: stringArray(item.enum_values, `${path}[${index}].enum_values`),
    };
  });
}

function suggestionArray(value: unknown, path: string): TestInputSuggestion[] {
  if (!Array.isArray(value)) {
    throw new Error(`${path} must be an array.`);
  }
  return value.map((entry, index) => {
    const item = recordValue(entry, `${path}[${index}]`);
    exactKeys(item, ['value', 'label', 'source', 'confidence'], `${path}[${index}]`);
    return {
      value: stringValue(item.value, `${path}[${index}].value`),
      label: stringValue(item.label, `${path}[${index}].label`),
      source: stringValue(item.source, `${path}[${index}].source`),
      confidence: stringValue(item.confidence, `${path}[${index}].confidence`),
    };
  });
}

function warningArray(value: unknown, path: string): TestInputWarning[] {
  if (!Array.isArray(value)) {
    throw new Error(`${path} must be an array.`);
  }
  return value.map((entry, index) => {
    const item = recordValue(entry, `${path}[${index}]`);
    exactKeys(item, ['code', 'severity', 'message'], `${path}[${index}]`);
    return {
      code: nonEmptyString(item.code, `${path}[${index}].code`),
      severity: nonEmptyString(item.severity, `${path}[${index}].severity`),
      message: stringValue(item.message, `${path}[${index}].message`),
    };
  });
}

function exactKeys(value: Record<string, unknown>, keys: string[], path: string): void {
  const expected = new Set(keys);
  const actual = Object.keys(value);
  if (actual.some((key) => !expected.has(key)) || keys.some((key) => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new Error(`${path} has unexpected or missing properties.`);
  }
}

function recordValue(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${path} must be an object.`);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function stringValue(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${path} must be a string.`);
  }
  return value;
}

function nonEmptyString(value: unknown, path: string): string {
  const text = stringValue(value, path);
  if (!text) {
    throw new Error(`${path} must not be empty.`);
  }
  return text;
}

function boundedString(value: unknown, path: string, max: number, allowEmpty = false): string {
  const text = stringValue(value, path);
  if ((!allowEmpty && !text) || text.length > max || text.includes('\0')) {
    throw new Error(`${path} is invalid.`);
  }
  return text;
}

function booleanValue(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') {
    throw new Error(`${path} must be a boolean.`);
  }
  return value;
}

function nonnegativeInteger(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(`${path} must be a non-negative integer.`);
  }
  return value;
}

function positiveInteger(value: unknown, path: string): number {
  const number = nonnegativeInteger(value, path);
  if (number < 1) {
    throw new Error(`${path} must be positive.`);
  }
  return number;
}

function sha256(value: unknown, path: string): string {
  const text = stringValue(value, path);
  if (!SHA256.test(text)) {
    throw new Error(`${path} must be a lowercase SHA-256.`);
  }
  return text;
}

function itemId(value: unknown, path: string): string {
  const text = stringValue(value, path);
  if (!ITEM_ID.test(text)) {
    throw new Error(`${path} is invalid.`);
  }
  return text;
}

function stringArray(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new Error(`${path} must be an array of strings.`);
  }
  return value as string[];
}
