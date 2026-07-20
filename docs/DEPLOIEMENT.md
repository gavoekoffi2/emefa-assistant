# Déploiement EMEFA Web

## Accès

- Application : https://emefa.76.13.129.252.sslip.io
- Santé du service : https://emefa.76.13.129.252.sslip.io/health
- Déploiement : conteneur Docker `emefa-web`, réseau Traefik `web`
- Données : volume Docker persistant `emefa_emefa_data`

## Activation privée

Le code d’activation réel est conservé uniquement dans le fichier `.env` protégé (`chmod 600`). Il ne doit pas être ajouté à Git.

Trois navigateurs au maximum peuvent être activés. La déconnexion révoque le navigateur et libère sa place.

## Activer la conversation vocale temps réel

1. Ouvrir `/root/projets/emefa/.env` sur le serveur.
2. Renseigner `EMEFA_ELEVENLABS_API_KEY` et `EMEFA_ELEVENLABS_AGENT_ID` sans guillemets.
3. La clé ne doit jamais être envoyée au navigateur : `/v1/realtime/session` génère une URL de conversation éphémère après vérification du navigateur privé.
4. La conversation utilise ElevenLabs Agents en continu : détection de parole, synthèse vocale et interruption pendant la réponse.

## Activer le moteur agent (DeepSeek ou OpenRouter)

Deux options — la clé ne doit jamais être commitée dans le dépôt ni exposée au navigateur.

**Option A — DeepSeek direct :**

1. Dans le même fichier `.env`, renseigner `EMEFA_DEEPSEEK_API_KEY` sans guillemets.
2. Conserver `EMEFA_DEEPSEEK_MODEL=deepseek-v4-flash`.

**Option B — OpenRouter (recommandé si vous avez une clé `sk-or-…`) :**

1. Dans le même fichier `.env`, renseigner `EMEFA_OPENROUTER_API_KEY` sans guillemets.
2. Optionnel : choisir le modèle avec `EMEFA_OPENROUTER_MODEL` (défaut : `deepseek/deepseek-chat`, économique et compatible avec les appels d'outils). Vérifier le nom exact sur openrouter.ai/models si le modèle par défaut renvoie une erreur.
3. Si les deux clés sont présentes, DeepSeek direct est prioritaire.

## Activer l'envoi d'e-mails (SMTP)

EMEFA peut envoyer des e-mails depuis votre adresse professionnelle. Chaque
envoi demande votre approbation explicite dans l'interface avant de partir.

1. Dans `.env`, renseigner :
   - `EMEFA_SMTP_HOST` (ex. `smtp.gmail.com`)
   - `EMEFA_SMTP_PORT` (587 par défaut)
   - `EMEFA_SMTP_USERNAME` et `EMEFA_SMTP_PASSWORD` — pour Gmail, créer un
     **mot de passe d'application** (compte Google → Sécurité → Validation en
     deux étapes → Mots de passe des applications), jamais votre mot de passe
     principal.
   - `EMEFA_SMTP_FROM` (votre adresse d'expéditeur)
2. Pour la recherche, la lecture et les brouillons (IMAP), ajouter aussi :
   - `EMEFA_IMAP_HOST` (ex. `imap.gmail.com`)
   - `EMEFA_IMAP_PORT` (993 par défaut)
   - `EMEFA_IMAP_USERNAME` / `EMEFA_IMAP_PASSWORD` (repli automatique sur les
     identifiants SMTP si absents — même compte, ex. graphistegpt).
3. Redémarrer le service. Les compétences `email_send`, `email_search`,
   `email_read` et `email_create_draft` n'apparaissent dans
   `/v1/system/status` que si la configuration correspondante est présente.
4. Test : demandez par écrit ou à la voix « Envoie un e-mail de test à … » —
   la carte d'approbation doit apparaître avant tout envoi.

## Brancher la voix sur le cerveau EMEFA (Custom LLM)

Une fois le moteur agent activé ci-dessus, la voix peut utiliser le même cerveau
et le même contexte métier que le texte :

1. Dans `.env`, définir `EMEFA_VOICE_LLM_TOKEN` avec un secret long et aléatoire
   (ex. `openssl rand -hex 32`).
2. Dans le dashboard ElevenLabs → votre agent → **LLM** : choisir **Custom LLM**,
   renseigner l'URL `https://<votre-domaine>/v1/voice-llm/chat/completions`
   et, comme clé API, la valeur exacte de `EMEFA_VOICE_LLM_TOKEN`.
3. Garder la persona ElevenLabs courte : chaque tour vocal passe désormais par
   le moteur gouverné d'EMEFA — profil, mémoire, tâches, pipeline et e-mail y
   sont accessibles à la voix. Les actions à conséquence (envoi d'e-mail,
   effacements) ne s'exécutent jamais depuis la voix seule : EMEFA annonce
   oralement qu'une approbation attend à l'écran, et reprend une fois votre
   décision prise.
4. Rollback immédiat possible : re-sélectionner le LLM ElevenLabs d'origine dans
   le dashboard, sans redéploiement.

Puis recréer seulement le service EMEFA :

```bash
cd /root/projets/emefa
docker compose -f docker-compose.prod.yml up -d --force-recreate emefa
```

5. Vérifier :

```bash
curl -fsS https://emefa.76.13.129.252.sslip.io/health
```

Sans clé, l’application reste accessible et activable, mais affiche que le moteur de langage n’est pas encore configuré.

## Coût IA

Tarifs officiels DeepSeek consultés lors du déploiement :

- `deepseek-v4-flash` : 0,14 USD par million de tokens d’entrée hors cache ;
- entrée en cache : 0,0028 USD par million de tokens ;
- sortie : 0,28 USD par million de tokens.

La facturation dépend uniquement des tokens consommés. Source : https://api-docs.deepseek.com/quick_start/pricing

## Exploitation

```bash
# État
docker compose -f docker-compose.prod.yml ps

# Journaux
docker logs --tail 100 emefa-web

# Redéploiement
docker compose -f docker-compose.prod.yml up -d --build
```

Le conteneur utilise `restart: unless-stopped` et redémarre automatiquement après un redémarrage du VPS.