import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import pt from './pt.json';
import en from './en.json';
import ru from './ru.json';

i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
        resources: {
            pt: { translation: pt },
            en: { translation: en },
            ru: { translation: ru }
        },
        fallbackLng: 'pt',
        interpolation: {
            escapeValue: false
        },
        // Padrão da comunidade: retornar a chave quando não encontrada
        // permite usar defaultValue de forma confiável
        returnNull: false,
        returnEmptyString: false
    });

export default i18n;
