# JQM - Job Queue Manager

## Vue d'ensemble

JQM est un système de gestion de file d'attente pour l'exécution séquentielle de commandes. Il se compose de trois processus indépendants communiquant via TCP, offrant des interfaces CLI et HTTP pour la gestion et le monitoring.

## Architecture

### Composants

```
┌──────────────┐
│   Engine     │  ← Cœur de l'application (port 5051)
│  (process 1) │     Gestion file + exécution jobs
└──────┬───────┘
       │ TCP localhost
   ────┴────────────
   │               │
┌──▼────────┐  ┌──▼────────┐
│  HTTP     │  │    CLI    │
│ Server    │  │  Server   │
│ (port     │  │ (port     │
│  9200)    │  │  9201)    │
└───────────┘  └───────────┘
Process 2      Process 3
```

### Prérequis
- Python 3.9.13
- Aucun package tiers
- Réseau local (communication inter-processus)

---

## États et cycle de vie

### États des jobs

Un job peut avoir les états suivants :

- **`pending`** : En attente d'exécution
- **`running`** : En cours d'exécution
- **`completed`** : Terminé avec succès (exit_code == 0)
- **`failed`** : Terminé en erreur (exit_code != 0)
- **`skip`** : Marqué pour être ignoré lors de l'exécution

**Flag spécial** :
- Un job a un flag `to_skip` (booléen) qui est **persistant** (exportable)
- Ce flag détermine si le job doit être sauté lors de l'exécution
- Les états `pending`, `running`, `completed`, `failed` sont **volatiles** (non exportés)

### États de la file (queue)

- **`stopped`** : Aucune exécution en cours
  - Toute la file est éditable (ajouter, supprimer, réordonner, modifier)
  - Aucun job ne démarre automatiquement

- **`started`** : Exécution automatique
  - Les jobs s'exécutent séquentiellement
  - Seuls les jobs **après** le job `running` sont éditables
  - Le job `running` et l'historique (`completed`, `failed`) ne sont pas modifiables

- **`paused`** : Pause après le job courant
  - Le job `running` continue jusqu'à sa fin
  - Attend une commande `PLAY` avant d'exécuter le suivant
  - Permet de réorganiser la file pendant l'attente

### Transitions d'états de la file

```
stopped → started : Démarre l'exécution
started → paused  : Demande de pause (effective après fin du job courant)
paused → started  : Reprend l'exécution (PLAY)
started → stopped : Arrête après le job courant
paused → stopped  : Annule la pause et arrête
```

---

## Engine (Process 1)

### Rôle

Cœur de l'application, responsable de :
- Gestion de la file de jobs
- Exécution séquentielle (1 job à la fois)
- Gestion des logs
- Communication avec les serveurs HTTP/CLI

### Port

- **5051** (interne, localhost uniquement)

### Démarrage

```bash
jqm-server engine [--port 5051] [--log-dir ./jqm_logs]
```

**Options** :
- `--port` : Port d'écoute (défaut: 5051)
- `--log-dir` : Répertoire des logs (défaut: `./jqm_logs` dans le répertoire courant)

### Gestion des jobs

#### ID des jobs
- Auto-incrémenté (séquence simple: 1, 2, 3...)
- Repart de 0 au redémarrage de l'engine
- Pas de réutilisation des IDs supprimés

#### Structure d'un job

```python
{
    "id": 1,
    "command": "powershell.exe",
    "args": ["./script.ps1", "-Param", "value"],
    "cwd": "C:\\Projects\\MyApp",
    "state": "pending",  # pending|running|completed|failed|skip
    "to_skip": False,    # Flag persistant
    "exit_code": None,   # Rempli à la fin
    "log_file": "job_001.log",
    "started_at": None,  # ISO datetime
    "ended_at": None     # ISO datetime
}
```

#### Exécution

- **1 seul job à la fois**
- Ordre : FIFO (premier arrivé, premier exécuté)
- Jobs avec `to_skip=True` sont ignorés
- Redirection stdout/stderr vers fichier de log

#### Logs

**Emplacement** :
- Répertoire configurable (défaut: `./jqm_logs`)
- Un fichier par job : `job_001.log`, `job_002.log`, etc.

**Format** :
```
=== Job #1 started at 2025-12-22 16:18:10 ===
[stdout/stderr mélangés, comme dans la console]
ligne de sortie 1
ligne de sortie 2
erreur quelconque
...
=== Job #1 ended at 2025-12-22 16:23:45 (exit code: 0) ===
```

**Caractéristiques** :
- Pas de limite de taille
- Pas de rotation automatique
- Stdout et stderr mélangés (ordre d'apparition)
- Timestamps uniquement en header/footer

---

## API Interne Engine

L'Engine expose une API TCP/JSON sur le port 5051 pour communication avec les serveurs HTTP/CLI.

### Format des messages

Identique à RCL : préfixe de longueur (8 octets) + JSON

### Commandes Client → Engine

#### list_jobs - Lister tous les jobs

```json
{
  "cmd": "list_jobs"
}
```

**Réponse** :
```json
{
  "type": "response",
  "success": true,
  "data": {
    "jobs": [
      {
        "id": 1,
        "command": "powershell.exe",
        "args": ["./script.ps1"],
        "cwd": "C:\\Projects",
        "state": "pending",
        "to_skip": false,
        "log_file": "job_001.log",
        "started_at": null,
        "ended_at": null,
        "exit_code": null
      },
      // ...
    ]
  }
}
```

#### add_job - Ajouter un job

```json
{
  "cmd": "add_job",
  "data": {
    "command": "powershell.exe",
    "args": ["./tests.ps1", "-Config", "prod.xml"],
    "cwd": "C:\\Projects\\MyApp"
  }
}
```

**Réponse** :
```json
{
  "type": "response",
  "success": true,
  "data": {
    "job_id": 42
  }
}
```

#### delete_job - Supprimer un job

```json
{
  "cmd": "delete_job",
  "job_id": 42
}
```

**Restrictions** :
- Ne peut pas supprimer un job `running`
- Si file `started`, ne peut supprimer que les jobs après le job `running`

#### update_job - Modifier un job

```json
{
  "cmd": "update_job",
  "job_id": 42,
  "data": {
    "command": "python",
    "args": ["script.py", "--verbose"],
    "cwd": "C:\\NewPath"
  }
}
```

**Restrictions** : Mêmes que `delete_job`

#### set_job_state - Changer l'état d'un job

```json
{
  "cmd": "set_job_state",
  "job_id": 42,
  "state": "skip"
}
```

**États modifiables** :
- `pending` ↔ `skip` (bascule le flag `to_skip`)
- Impossible de modifier un job `running`

#### reorder_job - Réordonner un job

```json
{
  "cmd": "reorder_job",
  "job_id": 42,
  "action": "up"  // "top" | "bottom" | "up" | "down"
}
```

**Actions** :
- `top` : Place en première position
- `bottom` : Place en dernière position
- `up` : Monte d'une position
- `down` : Descend d'une position

**Restrictions** :
- Ne peut pas réordonner un job `running`
- Si file `started`, ne peut réordonner que les jobs après le job `running`

#### get_queue_state - État de la file

```json
{
  "cmd": "get_queue_state"
}
```

**Réponse** :
```json
{
  "type": "response",
  "success": true,
  "data": {
    "state": "started",  // "stopped" | "started" | "paused"
    "current_job": 2,
    "total_jobs": 5,
    "current_job_started_at": "2025-12-22T16:18:10"
  }
}
```

#### set_queue_state - Changer l'état de la file

```json
{
  "cmd": "set_queue_state",
  "state": "paused"  // "stopped" | "started" | "paused"
}
```

#### get_job_log - Obtenir le log d'un job

```json
{
  "cmd": "get_job_log",
  "job_id": 42
}
```

**Réponse** :
```json
{
  "type": "response",
  "success": true,
  "data": {
    "log": "=== Job #42 started at ...\n..."
  }
}
```

#### export_queue - Exporter la file

```json
{
  "cmd": "export_queue"
}
```

**Réponse** :
```json
{
  "type": "response",
  "success": true,
  "data": {
    "xml": "<queue>...</queue>"
  }
}
```

#### import_queue - Importer une file

```json
{
  "cmd": "import_queue",
  "xml": "<queue>...</queue>",
  "mode": "replace"  // "replace" | "append"
}
```

**Modes** :
- `replace` : Supprime tous les jobs existants (sauf `running`) et importe
- `append` : Ajoute les jobs importés à la fin de la file

#### subscribe - S'abonner aux événements

```json
{
  "cmd": "subscribe"
}
```

Après cette commande, le client reste connecté et reçoit les événements en temps réel.

### Événements Engine → Clients

Les clients abonnés (`subscribe`) reçoivent ces événements :

#### job_added

```json
{
  "type": "event",
  "event": "job_added",
  "data": {
    "job_id": 42,
    "command": "...",
    // ... job complet
  }
}
```

#### job_removed

```json
{
  "type": "event",
  "event": "job_removed",
  "data": {
    "job_id": 42
  }
}
```

#### job_status_changed

```json
{
  "type": "event",
  "event": "job_status_changed",
  "data": {
    "job_id": 42,
    "old_state": "pending",
    "new_state": "running",
    "started_at": "2025-12-22T16:18:10"
  }
}
```

#### job_updated

```json
{
  "type": "event",
  "event": "job_updated",
  "data": {
    "job_id": 42,
    // ... job complet avec nouvelles valeurs
  }
}
```

#### queue_state_changed

```json
{
  "type": "event",
  "event": "queue_state_changed",
  "data": {
    "state": "paused",
    "current_job": 2,
    "total_jobs": 5
  }
}
```

#### queue_progress

```json
{
  "type": "event",
  "event": "queue_progress",
  "data": {
    "current_job": 3,
    "total_jobs": 5,
    "job_id": 43,
    "command": "...",
    "started_at": "2025-12-22T16:37:23"
  }
}
```

Envoyé quand un nouveau job démarre.

---

## Serveur HTTP (Process 2)

### Rôle

Interface web pour visualisation et contrôle de la file via navigateur.

### Port

- **9200** (configurable, défaut 9200)

### Démarrage

```bash
jqm-server http [--port 9200] [--engine-host localhost] [--engine-port 5051]
```

### API REST

#### Jobs

```
GET    /api/jobs              # Liste tous les jobs
POST   /api/jobs              # Ajouter un job
GET    /api/jobs/:id          # Détail d'un job
PUT    /api/jobs/:id          # Modifier un job
DELETE /api/jobs/:id          # Supprimer un job
PUT    /api/jobs/:id/state    # Changer l'état (skip/pending)
PUT    /api/jobs/:id/order    # Réordonner
```

**Exemple PUT /api/jobs/:id/order** :
```json
{
  "action": "up"  // "top" | "bottom" | "up" | "down"
}
```

#### Queue

```
GET    /api/queue/state       # État de la file
PUT    /api/queue/state       # Changer l'état
```

**Exemple PUT /api/queue/state** :
```json
{
  "state": "paused"
}
```

#### Logs

```
GET    /api/jobs/:id/log      # Contenu du log d'un job
```

#### Export/Import

```
GET    /api/queue/export      # Télécharge queue.xml
POST   /api/queue/import      # Upload d'un fichier XML
```

**POST /api/queue/import** :
```
Content-Type: multipart/form-data
file: queue.xml
mode: replace|append
```

#### Server-Sent Events

```
GET    /api/events            # Stream SSE
```

**Événements envoyés** :
- `job_added`
- `job_removed`
- `job_status_changed`
- `job_updated`
- `queue_state_changed`
- `queue_progress`

Format SSE :
```
event: job_status_changed
data: {"job_id": 42, "old_state": "pending", "new_state": "running"}

event: queue_progress
data: {"current_job": 3, "total_jobs": 5, ...}
```

### Client HTML

Interface web simple sans framework (HTML/CSS/JS vanilla).

**Fonctionnalités** :
- Affichage liste des jobs avec état
- Ajout de job (formulaire simple : commande + arguments + cwd)
- Suppression de job
- Réordonnancement (boutons ↑ ↓ ⇈ ⇊)
- Changement d'état (skip/pending)
- Contrôle file (start/pause/play/stop)
- Affichage log avec refresh auto (SSE)
- Export/Import XML
- Suivi temps réel via SSE

**Pas de templates** dans la première version (voir section Templates).

---

## Serveur CLI (Process 3)

### Rôle

Interface en ligne de commande pour contrôler l'Engine.

### Port

- **9201** (configurable, défaut 9201)

### Démarrage

```bash
jqm-server cli [--port 9201] [--engine-host localhost] [--engine-port 5051]
```

### Fonctionnement

- Accepte des connexions TCP de clients CLI
- Relaye les commandes vers l'Engine
- Retourne les réponses aux clients
- Gère les abonnements (commande `watch`)

---

## Client CLI

### Connexion

```bash
jqm [--host localhost] [--port 9201] <commande>
```

### Commandes

#### Gestion des jobs

```bash
# Lister tous les jobs
jqm list

# Ajouter un job
jqm add <command> [args...] [--cwd <directory>]
# Exemples :
jqm add powershell ./tests.ps1 -Config prod.xml
jqm add python script.py --verbose --cwd /path/to/dir

# Supprimer un job
jqm delete <job_id>

# Voir le détail d'un job
jqm detail <job_id>
# Affiche les infos + la commande CLI pour le recréer

# Changer l'état d'un job
jqm set-state <job_id> <skip|pending>

# Modifier la commande d'un job
jqm update <job_id> <command> [args...]
```

#### Réordonnancement

```bash
jqm move <job_id> <top|bottom|up|down>

# Exemples :
jqm move 5 top      # Place le job 5 en premier
jqm move 5 up       # Monte le job 5 d'une position
```

#### Contrôle de la file

```bash
jqm queue <start|stop|pause|play|status>

# Exemples :
jqm queue start     # Démarre l'exécution
jqm queue pause     # Met en pause après le job courant
jqm queue play      # Reprend l'exécution (après pause)
jqm queue stop      # Arrête l'exécution
jqm queue status    # Affiche l'état de la file
```

#### Logs

```bash
jqm log <job_id>

# Affiche le contenu du fichier de log
```

#### Export/Import

```bash
jqm export <fichier.xml>
jqm import <fichier.xml>

# Import demande confirmation :
# "Queue is not empty. Replace or Append? [r/a]: "
```

#### Surveillance temps réel

```bash
jqm watch
```

**Comportement** :
- Se connecte au serveur CLI
- S'abonne aux événements
- Affiche l'état courant de la file en temps réel
- Reste connecté indéfiniment (Ctrl+C pour quitter)

**Affichage** :

```
╔═══════════════════════════════════════════════╗
║ Queue Status: STARTED                         ║
╠═══════════════════════════════════════════════╣
║ Current Job: [2/5] Execute Tests              ║
║ Started: 2025-12-22 16:18:10                  ║
║ Duration: 00:05:23                            ║
╚═══════════════════════════════════════════════╝
```

**Mises à jour affichées** :
- Changement de job courant
- Changement du total de jobs (ajout/suppression)
- Demande de pause :
```
[2/5] Running job B (started 2025-12-22 at 16:18:10)
==> PAUSE requested
```
- Pause effective :
```
[2/5] Running job B (started 2025-12-22 at 16:18:10)
==> PAUSE requested
==> PAUSE triggered, waiting for PLAY
```
- Reprise :
```
[2/5] Running job B (started 2025-12-22 at 16:18:10)
==> PAUSE requested
==> PAUSE triggered, waiting for PLAY
==> PLAY requested
[3/5] Running job C (started 2025-12-22 at 16:37:23)
```
- File terminée :
```
All jobs done, waiting for PLAY
```

Le watch reste connecté même quand la file est vide.

### Format de sortie

**Liste des jobs** (format tabulaire) :

```
ID  State     Command                CWD                   Started
1   pending   ./test.ps1             C:\Projects\App       -
2   running   ./build.py             C:\Projects\Build     16:18:10
3   skip      ./deploy.ps1           C:\Projects\Deploy    -
4   pending   python script.py       C:\Projects\Scripts   -
5   completed ./cleanup.ps1          C:\Projects\Temp      16:10:05
```

**Détail d'un job** :

```
Job #42
  Command: powershell.exe ./tests.ps1 -Config prod.xml -Verbose
  Working Directory: C:\Projects\MyApp
  State: completed
  Exit Code: 0
  Started: 2025-12-22 16:18:10
  Ended: 2025-12-22 16:23:45
  Log File: job_042.log

To recreate this job:
  jqm add powershell ./tests.ps1 -Config prod.xml -Verbose --cwd "C:\Projects\MyApp"
```

---

## Export/Import XML

### Format XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<queue>
  <job>
    <command>powershell.exe</command>
    <args>
      <arg>./tests.ps1</arg>
      <arg>-Config</arg>
      <arg>prod.xml</arg>
    </args>
    <cwd>C:\Projects\MyApp</cwd>
    <skip>false</skip>
  </job>
  <job>
    <command>python</command>
    <args>
      <arg>build.py</arg>
      <arg>--verbose</arg>
    </args>
    <cwd>C:\Projects\Build</cwd>
    <skip>true</skip>
  </job>
</queue>
```

**Caractéristiques** :
- Exporte TOUS les jobs (y compris `completed`, `failed`)
- N'exporte PAS les états volatiles (`pending`, `running`, `completed`, `failed`)
- Exporte UNIQUEMENT le flag `to_skip` (booléen persistant)
- Pas d'export des timestamps, exit_code, log_file (données d'exécution)

### Import

**Modes** :
- `replace` : Supprime tous les jobs existants (sauf `running`) puis importe
- `append` : Ajoute les jobs importés à la fin de la file

**Comportement** :
- Les jobs importés ont l'état `pending` (ou `skip` si `<skip>true</skip>`)
- Reçoivent de nouveaux IDs (auto-incrémentés)
- Le client CLI demande confirmation du mode si la file n'est pas vide

---

## Gestion des processus

### Fichiers PID

Les 3 processus écrivent leur PID dans des fichiers :
- `jqm_engine.pid`
- `jqm_http.pid`
- `jqm_cli.pid`

**Emplacement** : Répertoire courant au moment du lancement de `jqm-server start`

### Commandes de contrôle

```bash
# Lancer les 3 processus en background
jqm-server start [options]

# Arrêter les 3 processus proprement
jqm-server stop

# Vérifier l'état (lit les PIDs, vérifie si running)
jqm-server status

# Lancer un processus individuel (foreground)
jqm-server engine [options]
jqm-server http [options]
jqm-server cli [options]
```

### Gestion des crashs

- Si HTTP ou CLI crash → Engine continue (isolation)
- Relancer manuellement le processus crashé :
  ```bash
  jqm-server http  # Relance HTTP seul, met à jour jqm_http.pid
  ```
- `jqm-server stop` arrête tous les processus (même relancés manuellement)

### Ordre de démarrage

1. **Engine** démarre en premier
2. **HTTP** et **CLI** démarrent, tentent de se connecter à l'Engine
3. Si Engine pas encore up, HTTP/CLI reessayent automatiquement (reconnexion toutes les 3s pendant 30s max)

### Arrêt propre

1. `jqm-server stop` lit les 3 fichiers PID
2. Envoie `SIGTERM` à chaque processus
3. Supprime les fichiers PID
4. Si un processus ne répond pas en 10s, envoie `SIGKILL`

---

## Templates (Feature future)

**Statut** : Non implémenté dans la première version

### Contexte

Les templates seraient utiles principalement pour le **client HTTP**, pour faciliter la saisie de commandes complexes dans un formulaire web (pas d'autocomplétion PowerShell).

### Approche recommandée

- **Phase 1** : Lancer sans templates
- **Phase 2** : Si besoin se fait sentir, implémenter :
  - Templates spécifiques au client HTTP uniquement
  - Historique des commandes récentes
  - Bouton "Clone" pour dupliquer un job existant

### Format proposé (si implémenté)

```xml
<template>
  <label>Execute Tests</label>
  <command>powershell.exe</command>
  <arguments>
    <argument>
      <label>Script Path</label>
      <parameter>-ScriptPath</parameter>
      <type>file</type>
    </argument>
    <argument>
      <label>Output Directory</label>
      <parameter>-OutputDir</parameter>
      <type>directory</type>
    </argument>
    <argument>
      <label>Test Name</label>
      <parameter>-TestName</parameter>
      <type>text</type>
    </argument>
  </arguments>
</template>
```

**Stockage** : Répertoire `./templates/` configurable via `--template-dir`

---

## Cas d'usage typiques

### Démarrage du système

```bash
# Lancer les 3 serveurs
jqm-server start --log-dir /var/log/jqm
# Écrit jqm_engine.pid, jqm_http.pid, jqm_cli.pid
# Les processus tournent en background
```

### Ajout de jobs

```bash
# Ajouter quelques jobs
jqm add powershell ./tests.ps1 -Config prod.xml --cwd C:\Projects\App
jqm add python build.py --verbose --cwd C:\Projects\Build
jqm add powershell ./deploy.ps1 --cwd C:\Projects\Deploy

# Vérifier la liste
jqm list
```

### Démarrage de l'exécution

```bash
# Démarrer la file
jqm queue start

# Surveiller en temps réel (autre terminal)
jqm watch
```

### Mise en pause pour réorganisation

```bash
# Pendant l'exécution, demander une pause
jqm queue pause
# Le job courant se termine, puis la file attend

# Réorganiser les jobs restants
jqm move 5 top
jqm move 7 up
jqm set-state 6 skip

# Reprendre
jqm queue play
```

### Export/Import

```bash
# Exporter la configuration
jqm export my_jobs.xml

# Sur une autre machine
jqm import my_jobs.xml
# Replace or Append? [r/a]: a
```

### Monitoring web

1. Ouvrir `http://localhost:9200` dans un navigateur
2. Visualisation temps réel de la file
3. Ajout/suppression/réordonnancement via interface
4. Voir les logs avec rafraîchissement auto

### Arrêt du système

```bash
jqm-server stop
# Arrête proprement les 3 processus
```

---

## Points d'attention pour l'implémentation

### Engine

1. **Threading** pour l'exécution du job :
   - Thread principal : gère la file et les connexions TCP
   - Thread d'exécution : lance le subprocess, lit stdout/stderr, écrit dans le log
   - Communication inter-threads pour les événements

2. **Gestion des subscribers** :
   - Liste des sockets abonnés
   - Broadcast des événements à tous les abonnés
   - Nettoyer les sockets déconnectés

3. **Réordonnancement** :
   - Utiliser une liste Python pour maintenir l'ordre
   - Attention aux indices lors des suppressions/ajouts

### Serveurs HTTP/CLI

1. **Reconnexion à l'Engine** :
   - Si Engine redémarre, HTTP/CLI doivent se reconnecter
   - Retry toutes les 3s

2. **Thread SSE** (HTTP) :
   - Maintenir les connexions SSE ouvertes
   - Format : `event: nom\ndata: json\n\n`

3. **Thread Watch** (CLI) :
   - Affichage rafraîchi sur événements
   - Calcul de durée côté client (started_at fourni)

### Client CLI

1. **Parsing arguments** :
   - Commande = premier arg après la sous-commande
   - Args = tous les suivants sauf `--cwd`
   - Si `--cwd` absent, utiliser `os.getcwd()`

2. **Formatage tableau** :
   - Aligner les colonnes proprement
   - Tronquer les chemins trop longs

---

## Limitations connues

- Pas d'annulation de job en cours (complexité évitée volontairement)
- Pas de retry automatique sur échec
- Pas d'authentification
- Pas de chiffrement (réseau local uniquement)
- Pas de limite de taille pour les logs (gestion manuelle)
- IDs de jobs non persistants (repart de 0 au redémarrage)

---

## Évolutions futures possibles

- Retry automatique configurable par job
- Dépendances entre jobs (graphe d'exécution)
- Exécution parallèle (N jobs simultanés)
- Notifications (email, webhook) sur fin de job
- Interface web plus riche (framework JS)
- Authentification basique (HTTP Basic Auth)
- Persistance de l'état de la file (SQLite, JSON)
- API GraphQL en alternative à REST
- Monitoring avancé (métriques, temps d'exécution)
- Planification (cron-like)

---

## Sécurité

⚠️ **Attention** : JQM n'a AUCUNE sécurité intégrée :
- Pas d'authentification sur les API
- Pas de validation des commandes
- Exécution de commandes arbitraires
- Pas de sandboxing

**Recommandations** :
- Utiliser uniquement sur réseau de confiance
- Firewall pour limiter l'accès aux ports 9200, 9201
- Ne PAS exposer sur Internet
- Considérer un reverse proxy avec authentification (nginx + Basic Auth)

---

## Résumé des ports et paramètres

| Composant | Port | Modifiable | Interface |
|-----------|------|------------|-----------|
| Engine | 5051 | Oui | TCP interne |
| Serveur HTTP | 9200 | Oui | REST + SSE |
| Serveur CLI | 9201 | Oui | TCP |
| Client CLI | - | - | Se connecte à 9201 |

**Répertoires** :
- Logs : `./jqm_logs` (configurable)
- Templates : `./templates` (feature future)
- PIDs : Répertoire courant du `jqm-server start`

**Délais** :
- Reconnexion HTTP/CLI → Engine : 3s (30s max)
- Aucun timeout d'exécution de job
