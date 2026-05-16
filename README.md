# voltapeak_loops

Outil graphique (Tkinter) de **traitement par lot** de fichiers de voltammétrie à vagues carrées (SWV — *Square Wave Voltammetry*), supportant **deux conventions de nommage** (itérations *loops* ou séries de *dosage*), avec correction automatique de ligne de base par l'algorithme **asPLS Whittaker**, parallélisé sur tous les cœurs CPU et **export Excel à en-tête hiérarchique**.

---

## Table des matières

1. [À quoi sert cet outil ?](#à-quoi-sert-cet-outil)
2. [Fonctionnalités](#fonctionnalités)
3. [Prérequis](#prérequis)
4. [Installation](#installation)
5. [Lancement](#lancement)
6. [Format des fichiers d'entrée](#format-des-fichiers-dentrée)
7. [Utilisation — interface graphique](#utilisation--interface-graphique)
8. [Résultats produits](#résultats-produits)
9. [Chaîne de traitement par fichier](#chaîne-de-traitement-par-fichier)
10. [Paramètres algorithmiques](#paramètres-algorithmiques)
11. [Architecture du code](#architecture-du-code)
12. [Performance et multiprocessing](#performance-et-multiprocessing)
13. [Dépannage](#dépannage)
14. [Feuille de route](#feuille-de-route)
15. [Licence et auteur](#licence-et-auteur)

---

## À quoi sert cet outil ?

La **voltammétrie à vagues carrées** (Square Wave Voltammetry, SWV) est une technique électrochimique qui mesure le courant traversant une électrode en fonction d'un potentiel imposé. Le signal obtenu présente un **pic** caractéristique de l'espèce analysée, superposé à une **ligne de base** (*baseline*) qui dérive lentement avec le potentiel.

Pour exploiter le pic, il faut :

1. **lisser** le signal pour atténuer le bruit de mesure ;
2. **estimer puis soustraire** la ligne de base ;
3. **relever** les coordonnées (tension, courant) du pic corrigé.

`voltapeak_loops` automatise ces trois étapes en s'appuyant sur :

- **Savitzky-Golay** pour le lissage (convolution polynomiale locale) ;
- **asPLS Whittaker** (*asymmetric Penalized Least Squares*, bibliothèque [`pybaselines`](https://pybaselines.readthedocs.io/)) pour l'estimation robuste de la baseline, avec une pondération réduite autour du pic afin d'éviter que la baseline ne « suive » et n'efface le pic.

> **Convention de signe.** Le pipeline est calibré pour des **SWV cathodiques** : `processData` inverse systématiquement le signe du courant avant `argmax`, donc le pic doit apparaître **en courant négatif** dans le fichier d'entrée. Un fichier où le pic est déjà en courant positif (orientation anodique) sera mal traité — il faut alors inverser la colonne en amont.

`voltapeak_loops` cible les **plans d'expérience structurés** où plusieurs scans sont accumulés selon une dimension expérimentale — itérations dans le temps (*loops*) ou paliers de concentration (*dosage*). Le format des noms de fichiers porte cette information ; l'outil détecte automatiquement la convention utilisée et produit un classeur Excel à **en-tête hiérarchique sur trois niveaux** (Canal / Variante / Mesure). Pour l'exploration interactive d'un seul fichier, utiliser [`voltapeak`](https://github.com/scadinot/voltapeak) ; pour le simple traitement par lot multi-électrodes sans dimension expérimentale supplémentaire, utiliser [`voltapeak_batch`](https://github.com/scadinot/voltapeak_batch).

---

## Fonctionnalités

- Traitement de **tous les `.txt` d'un dossier**, sélectionné via la GUI.
- **Parallélisation multi-processus** (`multiprocessing.Pool(cpu_count())`), basculable en mode séquentiel.
- **Deux formats de nommage** supportés et détectés automatiquement fichier par fichier :
  - format *loops* (`*_XX_SWV_CYY_loopZZ.txt`) — itérations sur une même condition ;
  - format *dosage* (`ZZ_<concentration>_XX_SWV_CYY.txt`) — série de concentrations.
- **Séparateur de colonnes** et **séparateur décimal** configurables dans l'interface.
- **Lissage** Savitzky-Golay (fenêtre 11, ordre 2).
- **Détection de pic robuste** : exclusion des 10 % de bords du scan et filtre de pente.
- **Estimation de ligne de base asPLS** avec zone d'exclusion ±3 % centrée sur le pic.
- **Export Excel hiérarchique** : en-tête à trois niveaux (Canal / Variante / Mesure), une ligne par itération ou par concentration.
- **Exports optionnels par fichier** : graphique PNG 300 dpi, CSV ou XLSX nettoyé.
- **Journal de traitement** et **barre de progression** en temps réel.
- Bouton **« Ouvrir le dossier de résultats »** à la fin du traitement.

---

## Prérequis

- **Python ≥ 3.10** — la syntaxe des annotations de type (`T | None`, `tuple[...]`) utilisée dans le code l'impose.
- **Systèmes supportés** : Windows, macOS, Linux.
- **Tkinter** — inclus dans la distribution standard de Python sous Windows et macOS ; sous Linux, installer au préalable le paquet système :

  ```bash
  sudo apt install python3-tk        # Debian / Ubuntu
  sudo dnf install python3-tkinter   # Fedora
  ```

---

## Installation

### 1. Créer et activer un environnement virtuel (recommandé)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

> [`requirements.txt`](requirements.txt) borne les mises à jour aux versions de patch (`~=X.Y.Z`) : un `pip install` ultérieur peut prendre un correctif plus récent, mais ne franchira jamais un changement de version mineur ou majeur susceptible de casser le code. Pour une reproductibilité stricte (mêmes versions exactes sur toutes les machines, dans le temps), figer les versions (`==X.Y.Z`) ou ajouter un lock file (`pip-tools`, `uv`). Le projet n'a pas de `pyproject.toml` : la configuration de chaque outil de lint / typecheck vit dans son fichier dédié ([`ruff.toml`](ruff.toml), [`.pylintrc`](.pylintrc), [`mypy.ini`](mypy.ini), [`pyrightconfig.json`](pyrightconfig.json)).

---

## Lancement

Depuis le **dossier parent** du dossier `voltapeak_loops/` :

```bash
python -m voltapeak_loops
```

---

## Format des fichiers d'entrée

| Caractéristique          | Valeur                                                       |
|--------------------------|--------------------------------------------------------------|
| Extension                | `.txt`                                                       |
| Encodage                 | `latin-1`                                                    |
| Nombre de colonnes       | ≥ 2 (seules les 2 premières sont lues)                       |
| Première ligne           | en-tête — **ignorée** (`skiprows=1`)                         |
| Colonne 1                | Potentiel en volts (float)                                   |
| Colonne 2                | Courant en ampères — **pic attendu en valeur négative** (convention SWV cathodique : le pipeline inverse le signe avant `argmax`) |
| Séparateur de colonnes   | configurable : tabulation / virgule / point-virgule / espace |
| Séparateur décimal       | configurable : point / virgule                               |
| Nombre minimal de lignes | 11 (fenêtre Savitzky-Golay fixe — `savgol_filter` lève une exception en dessous) |

### Conventions de nommage

L'outil reconnaît **deux formats** de noms de fichiers, détectés automatiquement fichier par fichier. Le format `loops` est testé en premier car plus restrictif ; `dosage` sert ensuite de fallback.

#### Format `loops` — itérations sur une même condition

```
<n'importe-quoi>_XX_SWV_CYY_loopZZ.txt
```

| Groupe   | Signification                                       | Exemple |
|----------|-----------------------------------------------------|---------|
| `XX`     | Variante sur 2 chiffres (souvent une fréquence Hz)  | `05`    |
| `CYY`    | Identifiant de canal (C + 2 chiffres)               | `C03`   |
| `loopZZ` | Numéro d'itération (1 chiffre ou plus)              | `loop7` |

Exemples valides : `echantillon_A_05_SWV_C00_loop1.txt`, `run2_15_SWV_C12_loop10.txt`.

#### Format `dosage` — série de concentrations

```
ZZ_<concentration>_XX_SWV_CYY.txt
```

| Groupe            | Signification                                                   | Exemple |
|-------------------|-----------------------------------------------------------------|---------|
| `ZZ`              | Préfixe numérique servant au tri (ordre expérimental)           | `10`    |
| `<concentration>` | Libellé de concentration (forme libre, ne contient pas `_`)     | `250nm` |
| `XX`              | Variante sur 2 chiffres (souvent un réplica)                    | `01`    |
| `CYY`             | Identifiant de canal (C + 2 chiffres)                           | `C05`   |

Exemples valides : `01_0nm_01_SWV_C05.txt`, `10_250nm_01_SWV_C05.txt`, `13_1000nm_02_SWV_C05.txt`.

Le tri des lignes du tableau Excel final s'effectue selon le préfixe `ZZ` (numérique), **pas** selon l'ordre alphabétique du libellé de concentration : `0nm, 0.1nm, 0.25nm, …, 1000nm` apparaissent dans l'ordre expérimental.

#### Règles d'inclusion

> ⚠️ Tout fichier ne respectant **aucun** des deux motifs est **ignoré** (une ligne `« Fichier ignoré ou invalide : <nom> »` apparaît dans le journal de traitement). Vérifier le nommage si certains fichiers n'apparaissent pas dans les résultats.

> ❌ Un dossier qui mélange les deux formats provoque l'**annulation de l'export Excel** : le journal affiche un message d'erreur explicite et aucun classeur agrégé n'est produit. Séparer les deux types de fichiers dans des dossiers distincts.

### Exemple de contenu (tabulation, point décimal)

```
Potential	Current
-0.500	-1.2e-6
-0.490	-1.1e-6
-0.480	-0.9e-6
...
```

---

## Utilisation — interface graphique

La fenêtre principale s'organise ainsi :

1. **Dossier d'entrée** — bouton **Parcourir** pour sélectionner le dossier contenant les fichiers `.txt`. Le dernier dossier ouvert est mémorisé au sein de la session.
2. **Paramètres de lecture** :
   - *Séparateur de colonnes* : `Tabulation` (défaut), `Virgule`, `Point-virgule`, `Espace` ;
   - *Séparateur décimal* : `Point` (défaut) ou `Virgule` ;
   - *Export des fichiers traités* : `Ne pas exporter` (défaut), `.CSV` ou `Excel` ;
   - *Export des graphiques* : `Ne pas exporter` (défaut) ou `.png` ;
   - *Mode de traitement* : `Activer le multi-thread (un processus par cœur)` (défaut) ou `Désactiver (traitement séquentiel)`.
3. **Progression du traitement** — barre se remplissant au fil de l'avancement.
4. **Journal de traitement** — chaque fichier traité (ou en erreur, ou ignoré faute de nommage valide) y apparaît, suivi d'un récapitulatif final (nombre de fichiers, durée totale).
5. **Actions** :
   - **Lancer l'analyse** : démarre le traitement parallèle ;
   - **Ouvrir le dossier de résultats** : s'active en fin de traitement et ouvre l'explorateur natif sur le dossier de sortie.

---

## Résultats produits

À chaque exécution, un dossier frère du dossier d'entrée est créé (ou nettoyé s'il existe déjà) :

```
<dossier_entrée>            ← vos fichiers .txt
<dossier_entrée> (results)  ← sortie générée
```

### Classeur Excel agrégé

Fichier : `<nom_du_dossier>.xlsx`. **Produit lorsque deux conditions sont réunies** :

1. au moins un fichier valide a été traité avec succès (sinon aucun classeur n'est écrit) ;
2. tous les fichiers détectés appartiennent au **même format** (loops *ou* dosage). En cas de mélange, un message d'erreur est journalisé et l'export est annulé.

Lorsque ces conditions sont remplies, la structure obtenue est hiérarchique sur trois niveaux :

| *Index*   | Canal `C00`         |                     | Canal `C01`         |                     | … |
|-----------|---------------------|---------------------|---------------------|---------------------|---|
|           | Variante `05`       |                     | Variante `05`       |                     |   |
|           | Tension (V)         | Courant (A)         | Tension (V)         | Courant (A)         |   |
| *L₁*      | *v₁*                | *c₁*                | *v₁'*               | *c₁'*               |   |
| *L₂*      | *v₂*                | *c₂*                | *v₂'*               | *c₂'*               |   |
| …         | …                   | …                   | …                   | …                   |   |

- **Chaque ligne** = une itération (loop) ou une concentration, selon le format détecté.
- **Le libellé d'index varie selon le format** :
  - format *loops* → en-tête de colonne `Itération`, valeurs `loop0, loop1, loop2, …` ;
  - format *dosage* → en-tête de colonne `Concentration`, valeurs `0nm, 0.1nm, 250nm, …` (triées dans l'ordre expérimental).
- **Chaque bloc de deux colonnes** = un couple (canal, variante), avec tension et courant du pic corrigé. Selon le format, *variante* représente une fréquence (loops) ou un réplica (dosage).
- Les colonnes sont triées naturellement par canal (`C00 → C99`), puis par variante, puis Tension avant Courant.

### Par fichier traité — optionnel

| Fichier      | Toujours produit ? | Contenu                                                                                                                         |
|--------------|:------------------:|---------------------------------------------------------------------------------------------------------------------------------|
| `<nom>.png`  | si option *.png*   | Graphique 300 dpi : signal brut, lissé, baseline asPLS, signal corrigé, marqueur de pic.                                        |
| `<nom>.csv`  | si option *.CSV*   | Colonnes `Potential`, `Current` après nettoyage (courant nul retiré, tri croissant).                                            |
| `<nom>.xlsx` | si option *Excel*  | Mêmes colonnes que le CSV.                                                                                                      |

---

## Chaîne de traitement par fichier

```
┌──────────────────────────┐
│ Fichier *.txt (entrée)   │
└────────────┬─────────────┘
             │ readFile()       séparateur & décimale configurables
             ▼
┌──────────────────────────┐
│ DataFrame brut           │
└────────────┬─────────────┘
             │ processData()    courant=0 supprimé, tri sur potentiel, -I
             ▼
┌──────────────────────────┐
│ Signal nettoyé           │
└────────────┬─────────────┘
             │ smoothSignal()   Savitzky-Golay (w=11, ordre=2)
             ▼
┌──────────────────────────┐
│ Signal lissé             │
└────────────┬─────────────┘
             │ getPeakValue()   pic dans la zone centrale, filtre de pente
             ▼
┌───────────────────────────┐
│ (x_pic, y_pic) provisoires│
└────────────┬──────────────┘
             │ calculateSignalBaseLine()  asPLS, exclusion ±3 % autour du pic
             ▼
┌──────────────────────────┐
│ Baseline estimée         │
└────────────┬─────────────┘
             │ signal_corrigé = signal_lissé - baseline
             ▼
┌──────────────────────────┐
│ Signal corrigé           │
└────────────┬─────────────┘
             │ getPeakValue()   pic final
             ▼
┌──────────────────────────┐
│ (x_pic, y_pic) corrigés  │
└────────────┬─────────────┘
             │ exports optionnels (PNG / CSV / XLSX)
             ▼
┌──────────────────────────┐
│ dict de résultat         │  → agrégé dans le classeur Excel hiérarchique
└──────────────────────────┘
```

---

## Paramètres algorithmiques

Les hyperparamètres sont actuellement **codés en dur** dans le script. Leur exposition dans l'interface graphique est prévue (voir [`ROADMAP.md`](ROADMAP.md)).

| Paramètre               | Valeur     | Rôle                                                                                         |
|-------------------------|------------|----------------------------------------------------------------------------------------------|
| `window_length`         | `11`       | Largeur de la fenêtre Savitzky-Golay (nombre impair de points).                              |
| `polyorder`             | `2`        | Ordre du polynôme ajusté localement par Savitzky-Golay.                                      |
| `marginRatio`           | `0.10`     | Fraction de points exclus aux deux bords lors de la recherche du pic.                        |
| `maxSlope`              | `500`      | Pente absolue maximale tolérée pour un candidat-pic (filtre les fronts).                     |
| `exclusionWidthRatio`   | `0.03`     | Demi-largeur (fraction de la plage de potentiel) de la zone protégée autour du pic.          |
| `lambdaFactor`          | `1e3`      | Facteur multiplicatif du paramètre de lissage Whittaker : `lam = lambdaFactor · n²`.         |
| `aspls.diff_order`      | `2`        | Ordre de différence dans l'ajustement Whittaker.                                             |
| `aspls.tol`             | `1e-2`     | Tolérance de convergence.                                                                    |
| `aspls.max_iter`        | `25`       | Nombre maximum d'itérations de réajustement des poids.                                       |

---

## Architecture du code

Le projet est un package Python minimal — deux fichiers seulement :

| Fichier                      | Rôle                                                                                                  |
|------------------------------|-------------------------------------------------------------------------------------------------------|
| [`__init__.py`](__init__.py) | Métadonnées du package (`__version__`) — marque le dossier comme package et permet `python -m voltapeak_loops`. |
| [`__main__.py`](__main__.py) | Code applicatif complet (pipeline + GUI Tkinter + entry point `main()`).                              |

Chaînage des appels :

```
main()
 └── launch_gui()                    Tkinter — construit et affiche la fenêtre
      ├── (callback Parcourir)       sélection du dossier d'entrée
      └── run_analysis()             callback du bouton Lancer l'analyse
           └── iter_results()        générateur — choisit le mode au runtime
                ├── (multi-thread)   Pool(cpu_count()).imap(processFileWrapper, …)
                └── (séquentiel)     boucle for args : processFileWrapper(args)
                     └── processSignalFile()     traitement d'un fichier
                          ├── readFile()
                          ├── processData()
                          ├── smoothSignal()
                          ├── getPeakValue()            (signal lissé)
                          ├── calculateSignalBaseLine()
                          ├── getPeakValue()            (signal corrigé)
                          └── plotSignalAnalysis()      (PNG, optionnel)

           └── agrégation pandas → MultiIndex → export .xlsx hiérarchique
```

---

## Performance et multiprocessing

- Par défaut, le script utilise `multiprocessing.Pool(processes=cpu_count())` : **tous les cœurs CPU** sont sollicités.
- `Pool.imap` (et non `Pool.map`) est volontairement choisi : les résultats sont **restitués au fil de l'eau dans l'ordre des fichiers d'entrée**, ce qui permet de rafraîchir la barre de progression et le journal pendant le traitement, sans attendre la fin du lot.
- Le backend matplotlib `'Agg'` (non-interactif) est **obligatoire** : les processus enfants du pool n'ont pas accès au thread Tk.

### Mode séquentiel (option *Désactiver*)

L'option *Mode de traitement → Désactiver (traitement séquentiel)* exécute la chaîne complète **dans le processus principal**, fichier après fichier. Utile quand :

- vous **déboguez** le pipeline : les exceptions des workers sont parfois absorbées par le pool et difficiles à tracer ;
- l'**export PNG matplotlib** se comporte mal sur votre installation (anciens drivers graphiques, conflits de backend) ;
- vous tournez sur un environnement **contraint** (machine virtuelle à 1 vCPU, sandbox CI) où le `Pool` apporte un surcoût sans gain réel.

`freeze_support()` est appelé dans `main()` pour permettre un éventuel packaging PyInstaller sous Windows.

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Certains fichiers sont ignorés (ligne `« Fichier ignoré ou invalide »` dans le journal) | Nom ne respectant aucun des deux motifs supportés | Vérifier le nommage — variante et canal **obligatoirement** sur 2 chiffres |
| L'analyse s'arrête avec « le dossier mélange plusieurs formats de fichiers » | Mix de fichiers *loops* et *dosage* dans le même dossier | Séparer les deux types dans des dossiers distincts |
| `Erreur dans le fichier … : Error tokenizing data` | Mauvais séparateur de colonnes | Choisir le bon séparateur dans la GUI |
| Toutes les valeurs sont lues comme chaînes ou zéro | Mauvais séparateur décimal | Basculer entre *Point* et *Virgule* |
| Pic « inversé » ou détecté loin du sommet visible | Fichier avec pic déjà en courant positif (orientation anodique) | Pré-inverser la colonne courant en amont — le pipeline attend une convention cathodique (cf. [Format des fichiers d'entrée](#format-des-fichiers-dentrée)) |
| Le pic détecté est sur un bord | Bruit important aux extrémités | Augmenter `marginRatio` dans le code |
| La baseline épouse le pic | `lambdaFactor` trop bas ou zone d'exclusion trop étroite | Augmenter `lambdaFactor` ou `exclusionWidthRatio` |
| Les graphiques PNG ne sont pas générés | Option *Export des graphiques* sur *Ne pas exporter* (défaut) | Basculer sur *.png* dans la GUI |
| Le bouton *Ouvrir le dossier de résultats* reste grisé | Aucun fichier valide traité | Vérifier les nommages et le contenu du dossier |
| Crash au démarrage sous Linux (`ModuleNotFoundError: _tkinter`) | Tkinter non installé | `sudo apt install python3-tk` |

---

## Feuille de route

Voir [`ROADMAP.md`](ROADMAP.md) pour l'ensemble des évolutions prévues.

---

## Licence et auteur

- **Auteur** : Stéphane Cadinot ([@scadinot](https://github.com/scadinot)).
- **Licence** : MIT — voir [`LICENSE`](LICENSE).

Pour toute question ou contribution, ouvrir une *issue* sur le dépôt GitHub.
