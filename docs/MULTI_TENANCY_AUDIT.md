# Rapport d'audit multi-tenant — EMEFA

> **Objet :** certifier que deux entreprises hébergées sur la même instance EMEFA
> ne peuvent en aucun cas voir, modifier, supprimer, rechercher, exporter ou
> référencer les données l'une de l'autre.
>
> **Portée :** schéma complet (31 tables, migration 20), couche de persistance,
> chemin de requête HTTP, système de fichiers.
>
> **Date :** juillet 2026 · **Schéma :** version 20 · **Tests :** 296 au vert.

---

## 1. Verdict

| Question | Réponse |
| --- | --- |
| Toutes les données métier sont-elles cloisonnées par entreprise ? | **Oui** |
| Le cloisonnement dépend-il de la vigilance du développeur ? | **Non** — il est appliqué par le magasin de données, pas par l'auteur de la requête |
| `KNOWN_UNSCOPED_TABLES` est-elle vide ? | **Oui**, et un test échoue si on y ajoute quoi que ce soit |
| Les autorisations sont-elles vérifiées côté serveur ? | **Oui**, sur les 114 routes, par défaut |
| Une régression multi-tenant fait-elle échouer la CI ? | **Oui** — tâche CI dédiée |

**Réserve honnête :** cet audit certifie l'isolation *applicative* telle qu'elle est
testée aujourd'hui. Il ne couvre pas encore le chiffrement au repos de la base
entière, la sauvegarde/restauration, ni les connecteurs OAuth qui n'existent pas
encore. Voir §7.

---

## 2. Le mécanisme, pas la discipline

L'exigence était explicite :

> « Je ne veux plus dépendre du développeur pour penser à ajouter un filtre tenant.
> L'architecture doit rendre impossible, ou extrêmement difficile, l'écriture d'une
> requête non cloisonnée. »

Quatre barrières indépendantes répondent à cela.

### 2.1 `ScopedStore` — le filtre appartient au magasin

Chaque dépôt hérite de `ScopedStore` (`domain/scope.py`). Aucune de ses méthodes
n'accepte de requête sans portée : le prédicat est composé par le magasin et
placé **en tête** de la clause `WHERE`, avant tout critère fourni par l'appelant.

```python
def fetch_all(self, columns, table, where="", parameters=(), tail="", ownership=None):
    #  -> SELECT ... WHERE tenant_id = ? [AND user_id = ?] AND <where> <tail>
```

Il n'existe pas de signature permettant d'écrire une lecture non cloisonnée.
`insert()` estampille `tenant_id`, `user_id`, `created_by_user_id` et
`updated_by_user_id` ; `update_scoped()` et `delete_scoped()` portent la même
contrainte, si bien qu'une écriture visant la ligne d'une autre entreprise
retourne « introuvable » au lieu de s'appliquer.

### 2.2 `Workspace` — la portée vient de l'appareil authentifié

`api/workspace.py` construit la portée à partir du propriétaire de l'appareil
authentifié, **jamais** du corps de la requête, d'un paramètre d'URL ou d'un
en-tête. Il n'y a rien à falsifier.

```
Cookie/Bearer → device → users.tenant_id → Scope → Workspace → dépôts liés
```

> **Régression historique, désormais verrouillée.** Les dépôts ont été cloisonnés
> *avant* le chemin de requête : tous les tests unitaires passaient alors que
> l'API servait encore l'instance construite au démarrage, et Jean voyait les
> clients d'Amina. Un système à moitié isolé est pire qu'un système non isolé,
> parce qu'il *ressemble* à un système corrigé.
> `test_the_api_serves_each_owner_only_their_own_data` existe pour cela.

### 2.3 Liaison cryptographique des identifiants

Les jetons des comptes connectés sont chiffrés en AES-256-GCM avec
`tenant|user|provider` en données associées (AEAD). Une ligne déplacée d'une
entreprise à l'autre — par une restauration, une erreur SQL ou une manipulation —
**ne se déchiffre pas**. L'isolation ne repose donc pas uniquement sur une clause
`WHERE`. Voir `docs/adr/ADR-003-connected-account-credentials.md`.

### 2.4 Contraintes d'unicité incluant le tenant

Cloisonner les lectures ne dit rien des contraintes. Une clé `UNIQUE` qui omet
`tenant_id` reste une ressource partagée. Deux défauts réels ont été trouvés par
les tests Alpha/Beta et corrigés en migration 20 (§5.2).

Un test parcourt désormais le schéma et échoue sur toute table portant
`tenant_id` dont la clé primaire ou un index unique serait partagé.

---

## 3. Inventaire des tables

Légende — **Propriétaire :** `ENTREPRISE` = partagé par tous les collaborateurs ·
`PERSONNEL` = propre à l'utilisateur · `IDENTITÉ` = définit la hiérarchie ·
`SYSTÈME` = interne. **Niveau :** ★★★ critique · ★★ sensible · ★ interne.

### 3.1 Données d'entreprise — `Ownership.TENANT`

Lues par `tenant_id`. Tous les collaborateurs partagent le même carnet d'affaires ;
c'est voulu, une entreprise n'a pas un CRM par employé.

| Table | Cloisonnée | Propriétaire | Mode d'accès | Niveau | Tests |
| --- | --- | --- | --- | --- | --- |
| `contacts` | ✅ | ENTREPRISE | `CrmRepository` | ★★★ | lecture, modif., suppr., recherche, référence |
| `projects` | ✅ | ENTREPRISE | `CrmRepository` | ★★★ | lecture, modif., suppr., référence |
| `deals` | ✅ | ENTREPRISE | `CrmRepository` | ★★★ | lecture, modif., suppr., référence |
| `contracts` | ✅ | ENTREPRISE | `CrmRepository` | ★★★ | lecture, modif., suppr. |
| `interactions` | ✅ | ENTREPRISE | `CrmRepository` | ★★ | lecture |
| `tasks` | ✅ | ENTREPRISE (+ `assigned_to_user_id`) | `TaskRepository` | ★★ | lecture, complétion croisée |
| `meetings` | ✅ | ENTREPRISE | `MeetingRepository` | ★★★ | lecture, suppr., rattachement projet |
| `meeting_decisions` | ✅ | ENTREPRISE | via `MeetingRepository` | ★★ | conformité schéma |
| `meeting_actions` | ✅ | ENTREPRISE | via `MeetingRepository` | ★★ | conformité schéma |
| `prospects` | ✅ | ENTREPRISE | `ProspectRepository` | ★★ | lecture |
| `initiatives` | ✅ | ENTREPRISE | `InitiativeRepository` | ★★ | lecture (snapshot) |
| `routines` | ✅ | ENTREPRISE | `RoutineRepository` | ★★★ | lecture, permission `MANAGE_ROUTINES` |
| `routine_runs` | ✅ | ENTREPRISE | `RoutineRepository` | ★★ | conformité schéma |
| `artifacts` | ✅ | ENTREPRISE | `DocumentStore` | ★★★ | export, téléchargement croisé |
| `assistants` | ✅ | ENTREPRISE | `ProfileRepository` | ★★ | assistant distinct par entreprise |
| `business_profiles` | ✅ | ENTREPRISE | `ProfileRepository` | ★★★ | profil distinct par entreprise |

> `meeting_decisions` et `meeting_actions` n'avaient **aucun** `tenant_id` : elles
> n'étaient atteignables que par leur réunion parente, ce qui n'est pas une
> frontière de sécurité. Corrigé en migration 18.

### 3.2 Données personnelles — `Ownership.USER`

Lues par `tenant_id` **et** `user_id`. Un collaborateur ne voit pas la boîte de
réception, les souvenirs ni l'agenda d'un autre.

| Table | Cloisonnée | Propriétaire | Mode d'accès | Niveau | Tests |
| --- | --- | --- | --- | --- | --- |
| `memories` | ✅ | PERSONNEL | `MemoryRepository` | ★★★ | lecture, export |
| `events` | ✅ | PERSONNEL | `AgendaRepository` | ★★ | lecture, conflits, unicité externe |
| `connected_accounts` | ✅ | PERSONNEL | `CredentialVault` | ★★★ | chiffrement lié au tenant (AEAD) |
| `conversation_turns` | ✅ | PERSONNEL | `ConversationStore` | ★★★ | conformité schéma |
| `pending_actions` | ✅ | PERSONNEL | `ApprovalRepository` | ★★★ | permission `APPROVE_ACTIONS` |
| `briefings` | ✅ | PERSONNEL | `BriefingRepository` | ★★ | même jour, deux entreprises |
| `evening_reports` | ✅ | PERSONNEL | `BriefingRepository` | ★★ | même jour, deux entreprises |
| `report_preferences` | ✅ | PERSONNEL | `ReportPreferencesRepository` | ★ | conformité schéma |
| `onboarding_state` | ✅ | PERSONNEL | `OnboardingRepository` | ★★ | conformité schéma |

### 3.3 Tables d'identité — exemption documentée

Ces quatre tables **ne passent pas** par `ScopedStore`. C'est délibéré et borné.

| Table | Cloisonnée | Propriétaire | Mode d'accès | Niveau | Justification |
| --- | --- | --- | --- | --- | --- |
| `tenants` | n/a | IDENTITÉ | `AccountRepository` | ★★★ | définit la hiérarchie elle-même |
| `users` | par `tenant_id` sur toute lecture de liste | IDENTITÉ | `AccountRepository` | ★★★ | l'authentification cherche par e-mail *avant* de connaître le tenant |
| `auth_tokens` | par empreinte de jeton | IDENTITÉ | `AccountRepository` | ★★★ | un lien de réinitialisation est résolu avant toute authentification |
| `invitations` | par empreinte de jeton | IDENTITÉ | `AccountRepository` | ★★★ | l'invité n'a pas encore de compte : le jeton *est* ce qui désigne l'entreprise |

**Pourquoi c'est acceptable — l'argument complet.**

1. **Cloisonner serait circulaire.** L'authentification est l'étape qui *établit*
   le tenant. Une requête de connexion ne peut pas être filtrée par le tenant
   qu'elle est en train de découvrir.
2. **Chaque clé de recherche est soit un secret à forte entropie, soit un
   identifiant déjà prouvé.** `authenticate()` prend une adresse e-mail ;
   `_consume_token()` et `peek_invitation()` prennent l'empreinte SHA-256 d'un
   jeton de 32 octets. Il n'existe aucune méthode acceptant un nom, un préfixe ou
   un critère parcourable.
3. **Aucune donnée métier.** Ces tables ne contiennent que de l'identité.
4. **Toute ligne écrite porte son `tenant_id`**, donc tout ce qui est atteint
   *après* l'authentification est cloisonné normalement.
5. **Les opérations d'administration prennent le tenant en argument obligatoire.**
   `list_members(tenant_id)`, `revoke_invitation(tenant_id, invitation_id)` : il
   n'existe pas d'appel « lister tout le monde », et une entreprise ne peut pas
   révoquer l'invitation d'une autre en devinant un identifiant.
   Testé : `test_identity_tables_are_only_reachable_by_unguessable_keys`.

**Cette liste ne peut pas s'élargir en silence :** un test affirme que
`IDENTITY_TABLES` vaut exactement ces quatre noms. En ajouter un cinquième est
une décision de sécurité qui casse la CI tant qu'elle n'est pas assumée ici.

### 3.4 Tables système

| Table | Cloisonnée | Propriétaire | Mode d'accès | Niveau | Note |
| --- | --- | --- | --- | --- | --- |
| `devices` | via `users` | SYSTÈME | `DeviceRepository` | ★★★ | pas de `tenant_id` propre : le tenant est **dérivé** par jointure sur `users`, donc il ne peut pas diverger de celui du compte |
| `schema_migrations` | n/a | SYSTÈME | `storage` | ★ | numéro de version uniquement |

---

## 4. Isolation hors base de données

| Ressource | Mécanisme | Test |
| --- | --- | --- |
| Documents produits (Word/Excel/PowerPoint) | répertoire par tenant `documents/<tenant_id>/` + catalogue `artifacts` cloisonné | `test_documents_are_stored_in_separate_directories` |
| Fichiers téléversés | répertoire par tenant `uploads/<tenant_id>/` | reprise de l'ancien format vers le tenant par défaut |
| Étagère d'outils de l'agent | construite par `Workspace`, donc sur les dépôts de l'appelant | `test_the_assistant_answers_from_the_caller_s_company_only` |
| Secrets des comptes connectés | AES-256-GCM, AEAD `tenant|user|provider` | ADR-003 |

---

## 5. Défauts trouvés et corrigés pendant l'audit

### 5.1 Le chemin de requête servait l'instance de démarrage

Tous les tests unitaires passaient ; l'API servait encore un jeu de dépôts unique.
Corrigé par `Workspace` par portée et la dépendance `current_workspace` sur
chaque routeur. **C'est le défaut le plus grave rencontré.**

### 5.2 Contraintes d'unicité partagées entre entreprises

Trouvées par les tests Alpha/Beta, pas par relecture.

| Table | Défaut | Conséquence | Correction |
| --- | --- | --- | --- |
| `briefings` | `PRIMARY KEY (brief_date)` | la première entreprise à générer un rapport un jour donné rendait ce jour indisponible à toutes les autres | clé `(tenant_id, user_id, brief_date)` |
| `evening_reports` | idem | idem | idem |
| `events` | `UNIQUE (source, external_id)` | deux entreprises synchronisant le même agenda partagé entraient en collision | `UNIQUE (tenant_id, user_id, source, external_id)` |

Le troisième n'avait pas encore de conséquence visible : il aurait cassé la
synchronisation d'agenda **au moment où le connecteur aurait été branché**.
C'est précisément la raison pour laquelle l'OAuth attend la fin de cette
certification.

### 5.3 Une seconde entreprise ne pouvait pas démarrer

La migration 2 n'amorçait que le tenant par défaut ; toute autre entreprise
échouait à sa première requête (`default business profile missing`).
`ProfileRepository` provisionne désormais assistant et profil à la demande.

### 5.4 Le CRM avait été cloisonné par utilisateur

Erreur de conception de ma part, corrigée avant livraison : chaque collaborateur
aurait eu son propre carnet de clients, ce qui contredit la demande explicite de
ne pas rattacher aux individus ce qui appartient à l'entreprise.

---

## 6. Autorisations — vérifiées côté serveur

Le front n'est jamais une barrière. `api/authorization.py` installe une
dépendance **globale** : elle s'applique à toutes les routes existantes et
futures, et **refuse par défaut** toute route non classée.

| Rôle | Lire | Écrire | Supprimer | Profil entreprise | Collaborateurs | Routines | Entreprise |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Propriétaire | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Administrateur | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Manager | ✅ | ✅ | ✅ | — | — | ✅ | — |
| Collaborateur | ✅ | ✅ | — | — | — | — | — |
| Lecture seule | ✅ | — | — | — | — | — | — |

Garanties testées :

- toute route enregistrée possède une politique — sinon la CI échoue ;
- la table ne mentionne pas de route disparue ;
- la surface non authentifiée vaut exactement 14 routes, et la modifier casse un test ;
- **échec fermé** prouvé : une route enregistrée sans politique répond `403` ;
- les rôles restreignent les **actions**, pas la **visibilité** — les cinq sièges
  lisent le même CRM d'entreprise ;
- une suspension coupe l'accès immédiatement, pas à l'expiration de session.

---

## 7. Ce qui n'est pas couvert

Énoncé franchement, pour que la décision de lancer soit prise en connaissance de cause.

| Sujet | État | Risque |
| --- | --- | --- |
| Chiffrement de la base au repos | non fait — seuls les secrets des comptes connectés sont chiffrés | accès disque = accès aux données métier |
| Sauvegarde / restauration par entreprise | non fait | une restauration globale rejouerait toutes les entreprises |
| Suppression complète d'une entreprise (RGPD) | non fait | pas de « supprimer mon compte » |
| Quotas et isolation des ressources | non fait | une entreprise peut consommer le CPU/la base des autres |
| SQLite en écriture concurrente | limite connue | à revoir avant un volume réel de tenants |
| Journal d'audit consultable par le client | événements émis, pas d'interface | traçabilité non offerte au client |
| Connecteurs OAuth (Gmail, Calendar, Microsoft) | **non commencés, volontairement** | à construire sur cette base, pas avant |

---

## 8. Conclusion

L'isolation applicative entre entreprises est **certifiée** au périmètre décrit
en §3 et §4 : quatre barrières indépendantes, zéro table métier non cloisonnée,
quatre exemptions d'identité justifiées et verrouillées par test, 296 tests dont
une tâche CI dédiée qui fait échouer toute régression.

Les trois défauts réels rencontrés ont tous été trouvés par des tests
d'isolation, aucun par relecture de code — ce qui est l'argument le plus solide
en faveur de la tâche CI dédiée.

Le développement des connecteurs OAuth peut commencer.

---

### Références

- `backend/emefa/domain/scope.py` — `Scope`, `Ownership`, `ScopedStore`
- `backend/emefa/domain/accounts.py` — comptes, jetons, invitations
- `backend/emefa/domain/roles.py` — matrice rôles/permissions
- `backend/emefa/api/authorization.py` — `ROUTE_POLICY`, dépendance globale
- `backend/tests/test_tenant_isolation.py` — conformité du schéma
- `backend/tests/test_two_companies.py` — certification Alpha/Beta
- `backend/tests/test_permissions.py` — couverture et comportement des rôles
- `backend/tests/test_accounts.py` — parcours SaaS
- `docs/adr/ADR-003-connected-account-credentials.md` — liaison cryptographique
