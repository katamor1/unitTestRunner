import {
  TestInputChangeDraft,
  TestInputFormItem,
  TestInputFormModel,
  TestInputFormSummary,
} from './contracts';

export interface TestInputItemDraft {
  readonly itemId: string;
  readonly baselineFingerprint: string;
  readonly baselineValues: Readonly<Record<string, string>>;
  readonly baselineConfirmed: boolean;
  readonly values: Readonly<Record<string, string>>;
  readonly confirmed: boolean;
  readonly dirty: boolean;
  readonly conflict: boolean;
  readonly orphaned: boolean;
  readonly latestFingerprint?: string;
  readonly latestValues?: Readonly<Record<string, string>>;
  readonly latestConfirmed?: boolean;
}

export interface TestInputEditorDraftState {
  readonly model: TestInputFormModel;
  readonly selectedCaseId?: string;
  readonly drafts: Readonly<Record<string, TestInputItemDraft>>;
}

export function createDraftState(model: TestInputFormModel): TestInputEditorDraftState {
  const drafts: Record<string, TestInputItemDraft> = {};
  for (const item of allItems(model)) {
    drafts[item.itemId] = baselineDraft(item);
  }
  return {
    model,
    selectedCaseId: model.cases?.[0]?.caseId,
    drafts,
  };
}

export function selectCase(state: TestInputEditorDraftState, caseId: string): TestInputEditorDraftState {
  if (!state.model.cases?.some((item) => item.caseId === caseId)) {
    return state;
  }
  return { ...state, selectedCaseId: caseId };
}

export function editControl(
  state: TestInputEditorDraftState,
  itemId: string,
  control: string,
  value: string,
): TestInputEditorDraftState {
  const draft = state.drafts[itemId];
  const item = findItem(state.model, itemId);
  if (!draft || !item?.editable || !item.controls.some((candidate) => candidate.name === control)) {
    return state;
  }
  const next = {
    ...draft,
    values: { ...draft.values, [control]: value },
    confirmed: false,
  };
  return replaceDraft(state, itemId, {
    ...next,
    dirty: draftDiffersFromBaseline(next),
  });
}

export function setItemConfirmed(
  state: TestInputEditorDraftState,
  itemId: string,
  confirmed: boolean,
): TestInputEditorDraftState {
  const draft = state.drafts[itemId];
  const item = findItem(state.model, itemId);
  if (!draft || !item?.editable) {
    return state;
  }
  const next = {
    ...draft,
    confirmed,
  };
  return replaceDraft(state, itemId, {
    ...next,
    dirty: draftDiffersFromBaseline(next),
  });
}

export function discardDrafts(state: TestInputEditorDraftState): TestInputEditorDraftState {
  return createDraftState(state.model);
}

export function buildChangeDrafts(state: TestInputEditorDraftState): TestInputChangeDraft[] {
  const changes: TestInputChangeDraft[] = [];
  for (const item of allItems(state.model)) {
    const draft = state.drafts[item.itemId];
    if (!draft?.dirty || draft.conflict || draft.orphaned || !item.editable) {
      continue;
    }
    const values: Record<string, string> = {};
    for (const control of item.controls) {
      const current = draft.values[control.name] ?? '';
      const baseline = draft.baselineValues[control.name] ?? '';
      if (current !== baseline) {
        values[control.name] = current;
      }
    }
    changes.push({
      itemId: item.itemId,
      subjectFingerprint: draft.baselineFingerprint,
      values,
      confirmed: draft.confirmed,
    });
  }
  return changes;
}

export function mergeReloadedModel(
  state: TestInputEditorDraftState,
  model: TestInputFormModel,
): TestInputEditorDraftState {
  const next = createDraftState(model);
  const drafts: Record<string, TestInputItemDraft> = { ...next.drafts };
  for (const [itemId, previous] of Object.entries(state.drafts)) {
    if (!previous.dirty) {
      continue;
    }
    const latest = drafts[itemId];
    if (!latest) {
      drafts[itemId] = {
        ...previous,
        conflict: true,
        orphaned: true,
      };
      continue;
    }
    if (latest.baselineFingerprint === previous.baselineFingerprint) {
      drafts[itemId] = {
        ...previous,
        conflict: false,
        orphaned: false,
      };
      continue;
    }
    drafts[itemId] = {
      ...previous,
      conflict: true,
      orphaned: false,
      latestFingerprint: latest.baselineFingerprint,
      latestValues: latest.values,
      latestConfirmed: latest.confirmed,
    };
  }
  const selectedCaseId = model.cases?.some((item) => item.caseId === state.selectedCaseId)
    ? state.selectedCaseId
    : model.cases?.[0]?.caseId;
  return { model, drafts, selectedCaseId };
}

export function resolveConflict(
  state: TestInputEditorDraftState,
  itemId: string,
  choice: 'latest' | 'draft',
): TestInputEditorDraftState {
  const draft = state.drafts[itemId];
  if (!draft?.conflict) {
    return state;
  }
  const latestItem = findItem(state.model, itemId);
  if (choice === 'latest') {
    if (!latestItem) {
      const drafts = { ...state.drafts };
      delete drafts[itemId];
      return { ...state, drafts };
    }
    return replaceDraft(state, itemId, baselineDraft(latestItem));
  }
  if (!latestItem || draft.orphaned) {
    return state;
  }
  return replaceDraft(state, itemId, {
    ...draft,
    baselineFingerprint: latestItem.subjectFingerprint,
    baselineValues: controlValues(latestItem),
    baselineConfirmed: latestItem.confirmed,
    conflict: false,
    orphaned: false,
    latestFingerprint: undefined,
    latestValues: undefined,
    latestConfirmed: undefined,
    dirty: true,
  });
}

export function draftSummary(state: TestInputEditorDraftState): TestInputFormSummary {
  const unresolved = new Set<string>();
  const unconfirmed = new Set<string>();
  const blocking = new Set<string>();
  const warnings = new Set<string>();
  for (const item of allItems(state.model)) {
    const draft = state.drafts[item.itemId];
    if (!draft) {
      continue;
    }
    const itemUnresolved = item.controls.some(
      (control) => control.requiredForConfirmation
        && isUnresolvedDraftValue(draft.values[control.name]),
    );
    if (itemUnresolved) {
      unresolved.add(item.itemId);
    }
    if (!draft.confirmed) {
      unconfirmed.add(item.itemId);
    }
    if (item.blocking && itemUnresolved) {
      blocking.add(item.itemId);
    }
    if (item.warnings.length > 0) {
      warnings.add(item.itemId);
    }
  }
  return {
    attentionCount: new Set([
      ...unresolved,
      ...unconfirmed,
      ...blocking,
      ...warnings,
    ]).size,
    unresolvedCount: unresolved.size,
    unconfirmedCount: unconfirmed.size,
    executionBlockingCount: blocking.size,
    warningCount: warnings.size,
  };
}

export function isUnresolvedDraftValue(value: string | undefined): boolean {
  const text = (value ?? '').trim().toUpperCase();
  return !text || ['TBD', 'TODO', 'UNKNOWN', 'UNRESOLVED'].some((prefix) => text.startsWith(prefix));
}

export function dirtyCount(state: TestInputEditorDraftState): number {
  return Object.values(state.drafts).filter((draft) => draft.dirty).length;
}

export function conflictCount(state: TestInputEditorDraftState): number {
  return Object.values(state.drafts).filter((draft) => draft.conflict).length;
}

function draftDiffersFromBaseline(draft: Omit<TestInputItemDraft, 'dirty'> | TestInputItemDraft): boolean {
  if (draft.confirmed !== draft.baselineConfirmed) {
    return true;
  }
  const names = new Set([
    ...Object.keys(draft.baselineValues),
    ...Object.keys(draft.values),
  ]);
  for (const name of names) {
    if ((draft.values[name] ?? '') !== (draft.baselineValues[name] ?? '')) {
      return true;
    }
  }
  return false;
}

function baselineDraft(item: TestInputFormItem): TestInputItemDraft {
  const values = controlValues(item);
  return {
    itemId: item.itemId,
    baselineFingerprint: item.subjectFingerprint,
    baselineValues: values,
    baselineConfirmed: item.confirmed,
    values,
    confirmed: item.confirmed,
    dirty: false,
    conflict: false,
    orphaned: false,
  };
}

function controlValues(item: TestInputFormItem): Readonly<Record<string, string>> {
  return Object.fromEntries(item.controls.map((control) => [control.name, control.value ?? '']));
}

function allItems(model: TestInputFormModel): TestInputFormItem[] {
  return (model.cases ?? []).flatMap((entry) => entry.items);
}

function findItem(model: TestInputFormModel, itemId: string): TestInputFormItem | undefined {
  return allItems(model).find((item) => item.itemId === itemId);
}

function replaceDraft(
  state: TestInputEditorDraftState,
  itemId: string,
  draft: TestInputItemDraft,
): TestInputEditorDraftState {
  return { ...state, drafts: { ...state.drafts, [itemId]: draft } };
}
