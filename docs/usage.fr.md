# Guide d'utilisation — étiquettes pâtisserie

Cet outil transforme la liste de produits de votre Google Sheet en un PDF prêt à imprimer (A4, 8 étiquettes par page, avec repères de coupe). Vous modifiez la feuille, vous cliquez sur un bouton, et environ 2 minutes plus tard le PDF apparaît dans Drive.

## 1. Saisie des données

Ouvrez la feuille → onglet **`real_data`**. Une ligne par produit. Colonnes :

| Colonne | Ce qu'il faut saisir | Exemple |
|---|---|---|
| `name_fr` | Nom du produit en français. Imprimé automatiquement en **MAJUSCULES** — vous pouvez le taper en minuscules. | `cake au citron` |
| `description_pt` | Description courte en portugais. Imprimée en italique, plus petite. | `bolo de citrinos` |
| `gluten`, `milk`, `egg`, `peanut`, `soy` | Cochez si le produit contient l'allergène. La petite icône correspondante s'imprime sur l'étiquette. | ☑ ☑ ☑ ☐ ☐ |
| `price` | Nombre avec **un point** comme séparateur décimal (`4.20`, pas `4,20`). Sera imprimé comme `4,20€`. | `4.20` |
| `active` | Cochez pour inclure cette ligne dans le prochain PDF. Décochez pour conserver la ligne mais la passer. | ☑ |

Pour ajouter un nouveau produit, tapez simplement dans la ligne vide suivante — les règles de colonne s'appliquent automatiquement.

## 2. Sauts de ligne

### Saut forcé (recommandé pour les titres)

Dans n'importe quelle cellule, appuyez sur **Alt + Entrée** (sur Mac : **Option + Entrée**) pour insérer un saut de ligne.

```
GATEAU BASQUE       ← ligne 1
À LA PART           ← ligne 2 (forcée)
```

Cela fonctionne dans `name_fr` comme dans `description_pt`.

### Renvoi automatique à la ligne

Les titres trop longs passent automatiquement à la ligne. **Limitez les titres à 2 lignes maximum** — au-delà (environ 27 caractères sans saut forcé), le titre passe sur 3 lignes et chevauche la description en dessous. Si votre titre est très long, insérez vous-même un Alt+Entrée à un endroit logique.

| Longueur | Comportement |
|---|---|
| jusqu'à ~14 caractères | Une ligne |
| 15–26 caractères | Passe à 2 lignes automatiquement |
| 27+ caractères sans saut forcé | Passe à 3 lignes → chevauchement visuel (à ne pas imprimer) |

## 3. Générer le PDF

1. Dans la feuille, barre de menu → **🥖 Lully** → **Generate labels (PDF)**
2. L'onglet `release_history` reçoit une nouvelle ligne avec le statut `submitted`
3. Patientez environ 2 minutes
4. La même ligne passe à `success`, avec un lien Drive dans `pdf_drive_link`
5. Cliquez sur le lien → votre PDF est là, prêt à imprimer

La feuille conserve un historique permanent de tous les PDF que vous avez générés, avec un instantané CSV des données exactes qui ont produit chacun d'eux. Vous pouvez donc toujours réimprimer une version passée.

## 4. Impression

Ouvrez le PDF et imprimez sur du **papier A4, échelle 100 %** (pas d'« ajuster à la page », pas de marges ajoutées). Les repères aux coins de chaque étiquette servent de guides de découpe après impression.

## 5. En cas d'erreur

Si la nouvelle ligne dans `release_history` affiche le statut `failed`, regardez la colonne `notes` pour voir le message d'erreur.

| `notes` indique… | Cause probable | Solution |
|---|---|---|
| `Missing name_fr` | Une ligne active n'a pas de nom de produit | Remplissez `name_fr` ou décochez `active` pour cette ligne |
| `No active rows` | Aucune ligne n'est cochée | Cochez au moins une case `active` |
| `invalid_grant` / `Token expired` | La connexion Google a expiré | Demandez à votre contact technique de renouveler le token OAuth |
| `Tab 'real_data' is empty` | L'onglet a été vidé ou renommé | Ne renommez pas `real_data` ; gardez au moins la ligne d'en-tête |

Si vous ne reconnaissez pas l'erreur, envoyez le texte de `notes` et le `request_id` à votre contact technique.

## 6. Astuces

- **Cochez les allergènes avec soin** — ils s'impriment comme de petites icônes auxquelles les clients se fient. Une coche oubliée signifie qu'un client ne peut pas voir l'allergène en un coup d'œil.
- **Décochez `active`** pour les produits que vous ne vendez pas aujourd'hui, plutôt que de supprimer la ligne — votre catalogue complet reste prêt pour la prochaine fois.
- **Ne supprimez pas de lignes dans `release_history`** — c'est votre journal d'audit de chaque lot d'étiquettes imprimé.
- **Ne renommez pas les onglets** — `real_data`, `sample` et `release_history` sont les noms que le système cherche.
