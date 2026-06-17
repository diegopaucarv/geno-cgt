export type Language = "en" | "es" | "de" | "pt";

export interface UserConfig {
  userId: string;
  language: Language;
}

export interface Translations {
  [key: string]: string | Translations;
}
