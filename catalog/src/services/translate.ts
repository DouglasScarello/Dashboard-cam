import { invoke } from '@tauri-apps/api/core';

/**
 * LibreTranslate Service — Módulo de tradução via Backend Tauri (Proxy)
 * 
 * Usa o comando Tauri 'translate_text' para contornar problemas de CORS/CSP
 * e garantir conectividade estável com o container local.
 */

// Cache em memória: "pt→en:texto" → "translated text"
const translationCache = new Map<string, string>();

/**
 * Traduz um texto de um idioma para outro via Backend Tauri
 * 
 * @param text - Texto a traduzir
 * @param source - Código do idioma de origem (ex: 'pt')
 * @param target - Código do idioma de destino (ex: 'en')
 * @returns Texto traduzido ou texto original em caso de falha
 */
export async function translateText(
    text: string,
    source: string,
    target: string
): Promise<string> {
    // Não traduz se origem = destino
    if (source === target) return text;

    // Não traduz textos vazios ou muito curtos
    const trimmed = text?.trim();
    if (!trimmed || trimmed.length < 3) return text;

    // Verifica cache
    const cacheKey = `${source}→${target}:${trimmed}`;
    const cached = translationCache.get(cacheKey);
    if (cached) return cached;

    try {
        // Usa invoke do Tauri para passar a tradução pelo backend Rust (Proxy)
        // Isso ignora CORS e CSP do navegador
        const translated = await invoke<string>('translate_text', {
            q: trimmed,
            source,
            target
        });

        if (translated) {
            console.log(`[TRANSLATE] Sucesso: "${trimmed.substring(0, 20)}..." -> "${translated.substring(0, 20)}..."`);
            translationCache.set(cacheKey, translated);
            return translated;
        }
        return text;
    } catch (err) {
        console.error("[TRANSLATE] Erro na tradução:", err);
        return text;
    }
}

/**
 * Traduz um array de textos
 */
export async function translateArray(
    texts: string[],
    source: string,
    target: string
): Promise<string[]> {
    if (source === target || !texts || texts.length === 0) return texts;

    // Filtra textos vazios ou inválidos
    const validTexts = texts.map(t => t?.trim()).filter(t => t && t.length >= 2);
    if (validTexts.length === 0) return texts;

    // Traduz um por um (com cache)
    // Nota: O LibreTranslate não tem API nativa de batch eficiente por parágrafo,
    // mas o cache em memória cuida da performance se houver repetição.
    return Promise.all(texts.map(t => translateText(t, source, target)));
}

/**
 * Traduz um array de objetos de localização
 */
export async function translateLocations(
    locations: any[],
    source: string,
    target: string
): Promise<any[]> {
    if (source === target || !locations || locations.length === 0) return locations;

    return Promise.all(locations.map(async loc => {
        const translatedLoc = { ...loc };
        if (loc.details) {
            translatedLoc.details = await translateText(loc.details, source, target);
        }
        if (loc.city && loc.city !== 'null') {
            translatedLoc.city = await translateText(loc.city, source, target);
        }
        return translatedLoc;
    }));
}

/**
 * Traduz um bloco grande de texto (como um relatório de inteligência)
 */
export async function translateBlock(
    content: string,
    source: string,
    target: string
): Promise<string> {
    if (source === target || !content) return content;
    return await translateText(content, source, target);
}

/**
 * Limpa o cache de traduções
 */
export function clearTranslationCache(): void {
    translationCache.clear();
}
