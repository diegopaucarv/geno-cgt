import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import type { Language, UserConfig } from "./types";
import translationsData from "./translations";

const STORAGE_KEY = "gt_user_config";

function loadUserConfig(): UserConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (
        parsed &&
        typeof parsed.userId === "string" &&
        ["en", "es", "de", "pt"].includes(parsed.language)
      ) {
        return parsed as UserConfig;
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Default: detect from browser or fallback to Spanish
  const browserLang = navigator.language.slice(0, 2);
  const supportedLanguages: Language[] = ["en", "es", "de", "pt"];
  const detected = supportedLanguages.includes(browserLang as Language)
    ? (browserLang as Language)
    : "es";

  return {
    userId: "",
    language: detected,
  };
}

function saveUserConfig(config: UserConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

/**
 * Resolves a dot-separated key path like "auth.loginButton" against the
 * translations object. Returns the key itself if not found.
 */
function resolveTranslation(
  translations: Record<string, any>,
  key: string,
): string {
  const parts = key.split(".");
  let current: any = translations;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return key;
    current = current[part];
  }
  return typeof current === "string" ? current : key;
}

export interface I18nContextValue {
  /** Current language code */
  language: Language;
  /** Set the language and persist to localStorage */
  setLanguage: (lang: Language) => void;
  /** Current user ID */
  userId: string;
  /** Set the user ID and persist to localStorage */
  setUserId: (id: string) => void;
  /**
   * Get a translated string by dot-separated key.
   * Example: t("auth.loginButton") → "Sign In" (en) / "Ingresar" (es)
   */
  t: (key: string, replacements?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<UserConfig>(loadUserConfig);

  const setLanguage = useCallback((lang: Language) => {
    setConfig((prev) => {
      const next = { ...prev, language: lang };
      saveUserConfig(next);
      return next;
    });
  }, []);

  const setUserId = useCallback((id: string) => {
    setConfig((prev) => {
      const next = { ...prev, userId: id };
      saveUserConfig(next);
      return next;
    });
  }, []);

  const t = useCallback(
    (key: string, replacements?: Record<string, string | number>): string => {
      const langTranslations = translationsData[config.language];
      if (!langTranslations) return key;

      let result = resolveTranslation(langTranslations, key);

      if (replacements) {
        for (const [rk, rv] of Object.entries(replacements)) {
          result = result.replaceAll(`{${rk}}`, String(rv));
        }
      }

      return result;
    },
    [config.language],
  );

  // Sync language to <html lang> attribute for accessibility
  useEffect(() => {
    document.documentElement.lang = config.language;
  }, [config.language]);

  return (
    <I18nContext.Provider
      value={{
        language: config.language,
        setLanguage,
        userId: config.userId,
        setUserId,
        t,
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}
