/** Why the cloned voice stopped, in words the reader can act on.
 *
 * The server classifies a refusal by its real cause instead of reporting one
 * generic "rejected" code. This turns that cause into a sentence that says
 * what happened *and* what to do about it — a spent quota, an expired key and
 * a deleted voice all need different responses, and telling the user only
 * that "the new voice is unavailable" told them none of it.
 */

const REASONS: Record<string, string> = {
  speech_voice_not_found: "la voix configurée n'existe plus chez le fournisseur",
  speech_key_invalid: "la clé du fournisseur de voix est invalide ou expirée",
  speech_key_not_entitled: "cette clé n'a pas accès à cette voix",
  speech_quota_exceeded: 'le quota de synthèse vocale est épuisé',
  speech_voice_limit_reached: 'le nombre de voix du forfait est atteint',
  speech_account_blocked: 'le compte du fournisseur de voix est suspendu',
  speech_model_unavailable: "le modèle vocal demandé n'est pas disponible",
  speech_language_unsupported: 'cette voix ne prend pas en charge le français',
  speech_format_unsupported: "le format audio demandé n'est pas accepté",
  speech_rate_limited: 'trop de demandes simultanées',
  speech_not_configured: "aucune voix n'est configurée",
  speech_request_invalid: 'la demande de synthèse a été refusée',
  speech_provider_rejected_request: 'le fournisseur a refusé la demande',
  speech_provider_unavailable: 'le fournisseur de voix est injoignable',
}

/** Failures that pass on their own: the user should wait, not go and fix something. */
const TRANSIENT = new Set(['speech_rate_limited', 'speech_provider_unavailable'])

export function describeSpeechFailure(cause: unknown): string {
  const code = cause instanceof Error ? cause.message : typeof cause === 'string' ? cause : ''
  const reason = REASONS[code]
  if (!reason) {
    // An unrecognised code is still shown rather than hidden: an opaque
    // message with no code is exactly what made this hard to diagnose.
    return code
      ? `Voix clonée indisponible (${code}). La voix standard reste active.`
      : 'Voix clonée indisponible. La voix standard reste active.'
  }
  return TRANSIENT.has(code)
    ? `Voix clonée en pause : ${reason}. La voix standard prend le relais.`
    : `Voix clonée indisponible : ${reason}. La voix standard reste active — corrigez la configuration vocale pour la rétablir.`
}
