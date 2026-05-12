import { describe, expect, it } from 'vitest';
import {
  normalizeParameterRequest,
  matchesValidationRegex,
  fieldHasFormatConstraint,
  shouldHideParameterRequestNameLabel,
} from './normalizeParameterRequest';
import type { ParameterRequest } from '@/types/analysis';

describe('normalizeParameterRequest', () => {
  it('maps snake_case keys from backend understanding payloads', () => {
    const raw = {
      id: 'x',
      name: 'reply',
      description: 'd',
      param_type: 'text',
      required: true,
      validation_regex: '^[a-z]+$',
      encrypted: false,
    } as unknown as ParameterRequest;
    const n = normalizeParameterRequest(raw);
    expect(n.paramType).toBe('text');
    expect(n.validationRegex).toBe('^[a-z]+$');
  });

  it('prefers camelCase when both are present', () => {
    const raw = {
      id: 'x',
      name: 'n',
      description: '',
      paramType: 'url',
      param_type: 'text',
      required: true,
      encrypted: false,
    } as unknown as ParameterRequest;
    expect(normalizeParameterRequest(raw).paramType).toBe('url');
  });

  it('falls back to text for unknown param types', () => {
    const raw = {
      id: 'x',
      name: 'n',
      description: '',
      paramType: 'email',
      required: false,
      encrypted: false,
    } as unknown as ParameterRequest;
    expect(normalizeParameterRequest(raw).paramType).toBe('text');
  });
});

describe('matchesValidationRegex', () => {
  it('matches unicode text for dot-all pattern', () => {
    expect(matchesValidationRegex('.*', '中文 ok')).toBe(true);
  });

  it('strips global flag to avoid lastIndex flakiness on repeated test', () => {
    const pattern = '^a$';
    const re = new RegExp(pattern, 'g');
    expect(re.test('a')).toBe(true);
    expect(re.test('a')).toBe(false);
    expect(matchesValidationRegex('/^a$/g', 'a')).toBe(true);
    expect(matchesValidationRegex('/^a$/g', 'a')).toBe(true);
  });
});

describe('shouldHideParameterRequestNameLabel', () => {
  it('hides label for canonical HITL reply id/name (case-insensitive)', () => {
    expect(
      shouldHideParameterRequestNameLabel({
        id: 'reply',
        name: 'Reply',
        description: '',
        paramType: 'text',
        required: true,
        encrypted: false,
      }),
    ).toBe(true);
  });

  it('shows label when name is human-facing', () => {
    expect(
      shouldHideParameterRequestNameLabel({
        id: 'reply',
        name: 'Your answer',
        description: '',
        paramType: 'text',
        required: true,
        encrypted: false,
      }),
    ).toBe(false);
  });

  it('shows label when id is not reply', () => {
    expect(
      shouldHideParameterRequestNameLabel({
        id: 'notes',
        name: 'reply',
        description: '',
        paramType: 'text',
        required: true,
        encrypted: false,
      }),
    ).toBe(false);
  });
});

describe('fieldHasFormatConstraint', () => {
  it('is false for plain text without regex', () => {
    const req: ParameterRequest = {
      id: '1',
      name: 'r',
      description: '',
      paramType: 'text',
      required: true,
      encrypted: false,
    };
    expect(fieldHasFormatConstraint(req)).toBe(false);
  });

  it('is true when validationRegex set', () => {
    const req: ParameterRequest = {
      id: '1',
      name: 'r',
      description: '',
      paramType: 'text',
      required: true,
      validationRegex: '\\d+',
      encrypted: false,
    };
    expect(fieldHasFormatConstraint(req)).toBe(true);
  });
});
