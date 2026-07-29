# Catalogue de compétences EMEFA

Chaque sous-dossier est une compétence, au format `jarvis-skills` schéma 1.0 :

```
ma-competence/
├── skill.yaml     manifeste (obligatoire)
├── PROMPT.md      prompt système (ou SYSTEM_PROMPT dans skill.py)
└── README.md      documentation (optionnel)
```

## Ce qu'une compétence peut et ne peut pas faire

Une compétence apporte **un prompt et un manifeste**. Elle n'apporte jamais de
code exécutable : `skill.py` est lu par analyse syntaxique (`ast`), jamais
importé. Voir `emefa/domain/skills/loader.py` pour le raisonnement.

Concrètement, une compétence peut expliquer à EMEFA *comment* mener une tâche
avec les outils qu'elle possède déjà. Elle ne peut pas :

- ajouter un outil ;
- accorder une permission ;
- contourner la politique de risque (appliquée dans le code, pas dans le prompt) ;
- lire un secret.

`requires_tools` déclare les outils nécessaires. Si EMEFA ne les a pas, la
compétence apparaît comme **inutilisable** et son prompt n'est jamais injecté —
plutôt que de faire croire à EMEFA qu'elle peut faire quelque chose qu'elle ne
peut pas.

`requires_env` déclare les variables d'environnement nécessaires. Même règle.

## Champs propres à EMEFA

Le standard amont ne les porte pas ; un produit hébergé en a besoin.

| Champ | Rôle |
|---|---|
| `risk` | classe d'action maximale (`observe`, `personal_read`, `local_write`, `communicate`, `destructive`). Absent ou inconnu ⇒ `personal_read`. Une classe refusée par la politique rend la compétence inutilisable. |

## Licences

`web-researcher/` provient de [jarvis-skills](https://github.com/Grominet95/jarvis-skills)
sous licence MIT — voir `NOTICE-jarvis-skills-MIT.txt`. Les autres compétences
sont originales.
