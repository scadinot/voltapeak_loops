# ROADMAP — voltapeak_loops

Évolutions planifiées, regroupées en **vagues de priorité**. L'ordre des vagues est indicatif : un item peut être avancé si une demande utilisateur le rend prioritaire. Aucun item n'a de date d'engagement — le projet reste en usage interne GROUPE TRACE et avance par opportunité.

> Cette feuille de route est partagée entre les trois projets [`voltapeak`](https://github.com/scadinot/voltapeak), [`voltapeak_batch`](https://github.com/scadinot/voltapeak_batch) et [`voltapeak_loops`](https://github.com/scadinot/voltapeak_loops) : les items marqués **(commun)** s'appliquent aux trois et bénéficieront idéalement de la même implémentation (cf. Vague 6 — mutualisation du noyau scientifique).

---

## Table des matières

1. [Vague 1 — Hygiène & robustesse](#vague-1--hygiène--robustesse)
2. [Vague 2 — Configurabilité](#vague-2--configurabilité)
3. [Vague 3 — Fonctionnalités utilisateur](#vague-3--fonctionnalités-utilisateur)
4. [Vague 4 — Qualité logicielle](#vague-4--qualité-logicielle)
5. [Vague 5 — Distribution](#vague-5--distribution)
6. [Vague 6 — Extensions scientifiques](#vague-6--extensions-scientifiques)
7. [Contribuer](#contribuer)

---

## Vague 1 — Hygiène & robustesse

Items qui éliminent des pièges connus ou des limitations documentées dans le [`README`](README.md).

- **Encodage configurable** *(commun)* — l'encodage de lecture est aujourd'hui figé à `latin-1`. Exposer dans l'UI une bascule `latin-1 / utf-8 / utf-8-sig`, avec auto-détection optionnelle (`chardet`).
- **Support du pic anodique** *(commun)* — `processData` inverse systématiquement le signe du courant. Ajouter une case à cocher *« Pic en courant positif (anodique) »* qui désactive l'inversion.
- **Garde-fou explicite sur le nombre de points** *(commun)* — le lissage utilise `window_length=11` en dur ; un fichier de moins de 11 lignes fait actuellement échouer `savgol_filter` avec une exception brute. Ajouter un contrôle préalable et un message d'erreur lisible dans le journal.
- **Validation préalable du nommage** *(spécifique loops)* — avant lancement, afficher dans le journal un récapitulatif clair : nombre de fichiers détectés en format *loops*, en format *dosage*, et ignorés. Permet de repérer un mauvais nommage sans devoir attendre la fin du traitement.
- **Aperçu du format détecté avant traitement** *(spécifique loops)* — bouton « Analyser le dossier » qui parse tous les noms et affiche un résumé (formats détectés, conflits éventuels) sans lancer le pipeline scientifique.

---

## Vague 2 — Configurabilité

Exposer dans l'UI ce qui est aujourd'hui codé en dur.

- **Exposition des hyperparamètres** *(commun)* — panneau « Paramètres avancés » repliable, avec les sliders / champs numériques pour :
  - `window_length` (Savitzky-Golay)
  - `polyorder`
  - `marginRatio`
  - `maxSlope`
  - `exclusionWidthRatio`
  - `lambdaFactor`
- **Patterns de nommage personnalisables** *(spécifique loops)* — les regex `RE_LOOPS` et `RE_DOSAGE` sont aujourd'hui figées dans le code. Permettre à l'utilisateur de fournir ses propres expressions régulières (sauvegardées dans un profil).
- **Profils de paramètres** *(commun)* — sauvegarde / rechargement de jeux de paramètres nommés (JSON dans `~/.voltapeak/profiles/`), pour basculer rapidement entre différentes campagnes.

---

## Vague 3 — Fonctionnalités utilisateur

- **Bouton « Annuler »** — interrompre proprement un lot en cours (fermer le `Pool`, vider la queue de résultats, restaurer la barre de progression).
- **Statistiques par variante / itération** — sur l'Excel agrégé, ajouter une feuille secondaire avec moyenne et écart-type par canal × variante (utile pour les *loops* répétitives).
- **Visualisation rapide d'une feuille agrégée** — bouton « Aperçu » qui ouvre une figure matplotlib affichant l'évolution du pic corrigé selon l'index (itération ou concentration), sans devoir ouvrir Excel.
- **Filtre de noms à inclure / exclure** — champ texte (glob) pour ne traiter qu'un sous-ensemble du dossier.

---

## Vague 4 — Qualité logicielle

- **Tests automatisés** *(commun)* — couverture `pytest` sur les fonctions pures (`readFile`, `processData`, `smoothSignal`, `getPeakValue`, `calculateSignalBaseLine`, `parseFileName`) avec jeux de données synthétiques (gaussienne + baseline + bruit).
- **CI GitHub Actions** *(commun)* — workflow qui lance `ruff`, `mypy`, `pyright`, `pylint` et `pytest` à chaque push / PR.
- **Type-checking strict** *(commun)* — passer `mypy --strict` proprement (aujourd'hui plusieurs `# type: ignore` ou imports non typés pour `pybaselines`, `scipy`, `numpy`).
- **Tests d'intégration GUI** — `pytest-tk` ou pilotage par `pyautogui` pour vérifier que le pipeline end-to-end ne régresse pas sur un jeu de fichiers de référence (incluant les deux formats *loops* / *dosage*).

---

## Vague 5 — Distribution

- **Packaging PyInstaller** *(commun)* — exécutable autonome `voltapeak_loops.exe` pour utilisateurs non-développeurs (`freeze_support()` déjà en place).
- **Découpage en modules** *(commun)* — éclater `__main__.py` en `io.py`, `processing.py`, `plotting.py`, `naming.py`, `aggregate.py`, `gui.py`, `cli.py`. Pré-requis pour la mutualisation (Vague 6).
- **Mode CLI** *(commun)* — sous-commande `python -m voltapeak_loops --input <dir>` qui fait tourner le pipeline et produit les sorties sans GUI (utile pour scripts batch externes).

---

## Vague 6 — Extensions scientifiques

- **Mutualisation du noyau scientifique** *(commun)* — extraire `readFile`, `processData`, `smoothSignal`, `getPeakValue`, `calculateSignalBaseLine` dans un package partagé `voltapeak_core`, importé par les trois projets. Élimine la duplication actuelle et garantit que les correctifs scientifiques se propagent.
- **Détection multi-pics** *(commun)* — repérer plusieurs maxima locaux significatifs et tous les annoter, au lieu du seul maximum global.
- **Métriques de qualité du fit** *(commun)* — afficher SNR, résidus baseline, FWHM du pic, pour qualifier objectivement la détection.
- **Support d'autres techniques voltammétriques** *(commun)* — DPV (*Differential Pulse Voltammetry*), CV (*Cyclic Voltammetry*) : pipelines adaptés mais réutilisant le noyau de lissage / baseline.
- **Format de nommage générique** *(spécifique loops)* — au-delà des deux formats actuels (*loops*, *dosage*), permettre la déclaration d'un format arbitraire via une expression régulière nommée et le mapping de ses groupes vers les axes du MultiIndex (Canal / Variante / Mesure).

---

## Contribuer

- Pour proposer une évolution non listée : ouvrir une *issue* sur le dépôt avec le label `enhancement`.
- Pour signaler un bug : ouvrir une *issue* avec le label `bug` et joindre un fichier `.txt` reproductible si possible.
- Les contributions externes (pull requests) sont les bienvenues — préférer une discussion préalable en issue pour les changements architecturaux.
