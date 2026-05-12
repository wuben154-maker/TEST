import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { ParameterRequest } from '@/types/analysis';
import {
  normalizeParameterRequest,
  matchesValidationRegex,
  fieldHasFormatConstraint,
  shouldHideParameterRequestNameLabel,
} from '@/lib/normalizeParameterRequest';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Lock, Send, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

const DRAFT_STORAGE_KEY = 'secmanus_hitl_form_draft';

function saveDraftToStorage(values: Record<string, string>): void {
  try {
    const nonEmpty = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v.trim() !== ''),
    );
    if (Object.keys(nonEmpty).length === 0) {
      sessionStorage.removeItem(DRAFT_STORAGE_KEY);
    } else {
      sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(nonEmpty));
    }
  } catch { /* ignore */ }
}

function readDraftFromStorage(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    return Object.fromEntries(
      Object.entries(parsed).map(([k, v]) => [k, String(v ?? '')]),
    );
  } catch {
    return {};
  }
}

function clearDraftStorage(): void {
  try { sessionStorage.removeItem(DRAFT_STORAGE_KEY); } catch { /* ignore */ }
}

interface ParameterInputProps {
  requests: ParameterRequest[];
  onSubmit: (parameters: Record<string, string>) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  /** After submission the form stays visible in read-only mode. */
  isSubmitted?: boolean;
  /** Pre-fill fields (e.g. restored submitted values after refresh). */
  initialFieldValues?: Record<string, string>;
}

export function ParameterInput({ 
  requests, 
  onSubmit, 
  onCancel,
  isSubmitting = false,
  isSubmitted = false,
  initialFieldValues,
}: ParameterInputProps) {
  const { t } = useLanguage();
  const normalizedRequests = useMemo(
    () => requests.map((r) => normalizeParameterRequest(r)),
    [requests],
  );
  const title = normalizedRequests.some((r) => r.isClarification)
    ? t.parameterInput.clarificationTitle
    : t.parameterInput.title;
  const [values, setValues] = useState<Record<string, string>>(() => {
    const draft = isSubmitted ? {} : readDraftFromStorage();
    return { ...draft, ...(initialFieldValues ?? {}) };
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Ensure boolean fields always have explicit values.
    setValues((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const req of normalizedRequests) {
        if (req.paramType !== 'boolean') continue;
        if (next[req.id] !== 'true' && next[req.id] !== 'false') {
          next[req.id] = 'false';
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [normalizedRequests]);

  const initialSerialized = initialFieldValues ? JSON.stringify(initialFieldValues) : '';
  useEffect(() => {
    if (!initialSerialized) return;
    let parsed: Record<string, string>;
    try {
      parsed = JSON.parse(initialSerialized) as Record<string, string>;
    } catch {
      return;
    }
    if (Object.keys(parsed).length === 0) return;
    setValues((prev) => {
      if (isSubmitted) {
        return { ...prev, ...parsed };
      }
      const next = { ...prev };
      let changed = false;
      for (const [k, v] of Object.entries(parsed)) {
        if (next[k] === undefined || next[k] === '') {
          next[k] = v;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [initialSerialized, isSubmitted]);

  useEffect(() => {
    if (isSubmitted) clearDraftStorage();
  }, [isSubmitted]);

  useEffect(() => {
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    };
  }, []);

  const handleChange = useCallback((id: string, value: string) => {
    setValues(prev => {
      const next = { ...prev, [id]: value };
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
      draftTimerRef.current = setTimeout(() => saveDraftToStorage(next), 300);
      return next;
    });
    if (errors[id]) {
      setErrors(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  }, [errors]);

  const handleBlur = useCallback((id: string) => {
    setTouched(prev => ({ ...prev, [id]: true }));
  }, []);

  const validate = useCallback(() => {
    const newErrors: Record<string, string> = {};
    
    for (const req of normalizedRequests) {
      const value = values[req.id] || '';
      
      // Required field validation.
      if (req.required && !value.trim()) {
        newErrors[req.id] = t.parameterInput.requiredField;
        continue;
      }
      
      // Regex validation.
      if (req.validationRegex && value) {
        if (!matchesValidationRegex(req.validationRegex, value)) {
          newErrors[req.id] = t.parameterInput.invalidFormat;
        }
      }
      
      // URL validation.
      if (req.paramType === 'url' && value) {
        try {
          new URL(value);
        } catch {
          newErrors[req.id] = t.parameterInput.invalidUrl;
        }
      }
      
      // JSON validation.
      if (req.paramType === 'json' && value) {
        try {
          JSON.parse(value);
        } catch {
          newErrors[req.id] = t.parameterInput.invalidJson;
        }
      }
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [normalizedRequests, values, t.parameterInput]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    
    const allTouched: Record<string, boolean> = {};
    normalizedRequests.forEach(req => { allTouched[req.id] = true; });
    setTouched(allTouched);
    
    if (validate()) {
      const submitValues = { ...values };
      normalizedRequests.forEach((req) => {
        if (req.paramType === 'boolean' && submitValues[req.id] !== 'true') {
          submitValues[req.id] = 'false';
        }
      });
      clearDraftStorage();
      onSubmit(submitValues);
    }
  }, [validate, onSubmit, values, normalizedRequests]);

  const renderInput = (req: ParameterRequest, inputAriaLabel?: string) => {
    const value = values[req.id] || '';
    const error = touched[req.id] ? errors[req.id] : undefined;
    const isPassword = req.paramType === 'password';
    const isJson = req.paramType === 'json';
    const isPlainText = req.paramType === 'text';
    const isBoolean = req.paramType === 'boolean';
    const showValidHint =
      fieldHasFormatConstraint(req) && Boolean(value) && !error;
    
    const baseInputClass = cn(
      "transition-all duration-200",
      error && "border-destructive focus-visible:ring-destructive",
      showValidHint && "border-green-500/50"
    );
    
    const disabled = isSubmitting || isSubmitted;

    if (isBoolean) {
      const checked = value === 'true';
      return (
        <label
          htmlFor={req.id}
          className={cn(
            'flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
            error ? 'border-destructive' : 'border-border',
            disabled ? 'opacity-70' : 'cursor-pointer',
          )}
        >
          <input
            id={req.id}
            type="checkbox"
            checked={checked}
            onChange={(e) => handleChange(req.id, e.target.checked ? 'true' : 'false')}
            onBlur={() => handleBlur(req.id)}
            disabled={disabled}
            aria-label={inputAriaLabel}
          />
          <span>{req.description || req.name}</span>
        </label>
      );
    }

    if (isJson) {
      return (
        <Textarea
          id={req.id}
          value={value}
          onChange={e => handleChange(req.id, e.target.value)}
          onBlur={() => handleBlur(req.id)}
          placeholder={req.placeholder || '{"key": "value"}'}
          className={cn(baseInputClass, "font-mono text-sm min-h-[100px]")}
          disabled={disabled}
          aria-label={inputAriaLabel}
        />
      );
    }

    if (isPlainText) {
      return (
        <Textarea
          id={req.id}
          value={value}
          onChange={e => handleChange(req.id, e.target.value)}
          onBlur={() => handleBlur(req.id)}
          placeholder={req.placeholder || ''}
          className={cn(baseInputClass, "min-h-[120px] text-sm resize-y")}
          disabled={disabled}
          rows={5}
          aria-label={inputAriaLabel}
        />
      );
    }
    
    return (
      <div className="relative">
        <Input
          id={req.id}
          type={isPassword ? 'password' : 'text'}
          value={value}
          onChange={e => handleChange(req.id, e.target.value)}
          onBlur={() => handleBlur(req.id)}
          placeholder={req.placeholder || (isPassword ? '••••••••' : '')}
          className={cn(baseInputClass, isPassword && "pr-10")}
          disabled={disabled}
          aria-label={inputAriaLabel}
        />
        {isPassword && (
          <Lock className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        )}
      </div>
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 animate-fade-in">
      <div className="rounded-lg border border-primary/20 bg-gradient-to-br from-primary/5 to-transparent p-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
            <Lock className="w-4 h-4 text-primary" />
          </div>
          <span className="text-sm font-semibold text-foreground">{title}</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 font-medium ml-auto">
            {t.parameterInput.encryptedStorage}
          </span>
        </div>
        
        <div className="space-y-4">
          {normalizedRequests.map((req) => {
            const hideNameLabel = shouldHideParameterRequestNameLabel(req);
            const inputAriaLabel = hideNameLabel ? title : undefined;
            return (
            <div key={req.id} className="space-y-2">
              {!hideNameLabel && (
              <div className="flex items-center justify-between">
                <Label 
                  htmlFor={req.id} 
                  className="text-sm font-medium text-foreground"
                >
                  {req.name}
                  {req.required && <span className="text-destructive ml-1">*</span>}
                </Label>
                {req.encrypted && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Lock className="w-3 h-3" />
                    {t.parameterInput.encrypted}
                  </span>
                )}
              </div>
              )}
              {hideNameLabel && req.encrypted && (
              <div className="flex justify-end">
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Lock className="w-3 h-3" />
                  {t.parameterInput.encrypted}
                </span>
              </div>
              )}
              
              {req.description && (
                <p className="text-xs text-muted-foreground">{req.description}</p>
              )}
              
              {renderInput(req, inputAriaLabel)}
              
              {touched[req.id] && errors[req.id] && (
                <div className="flex items-center gap-1 text-xs text-destructive">
                  <AlertCircle className="w-3 h-3" />
                  {errors[req.id]}
                </div>
              )}
              
              {touched[req.id] &&
                !errors[req.id] &&
                values[req.id] &&
                fieldHasFormatConstraint(req) && (
                <div className="flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle2 className="w-3 h-3" />
                  {t.parameterInput.validFormat}
                </div>
              )}
            </div>
            );
          })}
        </div>
        
        <div className="flex items-center gap-2 mt-6">
          {onCancel && !isSubmitted && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              {t.common.cancel}
            </Button>
          )}
          <Button
            type="submit"
            size="sm"
            className="flex-1"
            disabled={isSubmitting || isSubmitted}
          >
            {isSubmitted ? (
              <>
                <CheckCircle2 className="w-4 h-4 mr-2" />
                {t.parameterInput.submitted ?? '已提交'}
              </>
            ) : isSubmitting ? (
              <>
                <span className="animate-spin mr-2">⏳</span>
                {t.parameterInput.submitting}
              </>
            ) : (
              <>
                <Send className="w-4 h-4 mr-2" />
                {t.parameterInput.submit}
              </>
            )}
          </Button>
        </div>
        
        {!isSubmitted && (
          <p className="text-xs text-muted-foreground mt-3 text-center">
            {t.parameterInput.encryptedNotice}
          </p>
        )}
      </div>
    </form>
  );
}
