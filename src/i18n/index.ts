import { en, TranslationKeys } from "./locales/en";
import { zh } from "./locales/zh";
import { ja } from "./locales/ja";
import { ko } from "./locales/ko";

export type Language = "en" | "zh" | "ja" | "ko";

export const languages: Record<Language, { name: string; nativeName: string }> = {
  en: { name: "English", nativeName: "English" },
  zh: { name: "Chinese", nativeName: "中文" },
  ja: { name: "Japanese", nativeName: "日本語" },
  ko: { name: "Korean", nativeName: "한국어" },
};

const translations: Record<Language, TranslationKeys> = {
  en,
  zh,
  ja,
  ko,
};

export function getTranslations(lang: Language): TranslationKeys {
  return translations[lang] || translations.en;
}

export function detectBrowserLanguage(): Language {
  const browserLang = navigator.language.toLowerCase();
  
  if (browserLang.startsWith("zh")) return "zh";
  if (browserLang.startsWith("ja")) return "ja";
  if (browserLang.startsWith("ko")) return "ko";
  
  return "en";
}

export { type TranslationKeys };
