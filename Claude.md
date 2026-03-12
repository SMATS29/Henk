# Henk v0.3 — Bouwinstructie voor Claude Code

## Context

v0.2 ("Henk Doet Veilig") is gebouwd en werkend. Henk heeft een CLI chat, tools (web_search, file_manager, code_runner), security proxy, bronlabeling, kill switches en ReAct-loop met Anthropic tool-use flow.

Dit is v0.3: **"Henk Onthoudt"**. Het doel is dat Henk langetermijngeheugen krijgt — informatie onthouden tussen sessies, met een veilig staging-systeem en dagelijkse review.

Lees `CLAUDE.md` en `docs/henk-design-v14.docx` (hoofdstuk 4 en 14) voor alle details over het geheugenontwerp.

## Wat v0.3 WEL doet

- Langetermijngeheugen als Markdown-bestanden
- Drie geheugenlagen: kern (core.md), actief (active/), episodisch (episodes/)
- Staged memory: Henk schrijft nooit direct naar actief geheugen, altijd via staging
- memory_write tool die naar staging schrijft
- Provenance-labels per geheugenwijziging: user-authored, agent-suggested
- Dagelijkse review via CLI: samenvatting van voorgestelde wijzigingen, goedkeuring per onderdeel
- Vector search voor memory retrieval (ChromaDB of sqlite-vec)
- core.md wordt altijd meegestuurd bij elke LLM-call
- Relevantie-scoring met verval en gebruik-boost
- Archivering van verouderde items
- Beschrijving per geheugenonderdeel voor vector-embedding

## Wat v0.3 NIET doet

- Geen LLM-gebaseerde filtering van vector search resultaten (komt later als geheugen groeit)
- Geen Tauri desktop app — daily review gaat via CLI
- Geen automatisch verwijderen — alleen archiveren op voorstel, gebruiker beslist
- Geen skill-samenvattingen verbeteren via memory review (dat is v0.5)

## Nieuwe bestanden

```
henk/
├── henk/
│   ├── memory/                     # Memory subsysteem
│   │   ├── __init__.py
│   │   ├── store.py                # MemoryStore: CRUD op geheugenbestanden
│   │   ├── staging.py              # StagingManager: staged writes + review
│   │   ├── retrieval.py            # MemoryRetrieval: vector search + core.md
│   │   ├── scoring.py              # RelevanceScorer: scoring, verval, archivering
│   │   └── models.py               # Dataclasses: MemoryItem, StagedChange, etc.
│   ├── tools/
│   │   └── memory_write.py         # memory_write tool (schrijft naar staging)
├── tests/
│   ├── test_memory_store.py
│   ├── test_staging.py
│   ├── test_retrieval.py
│   ├── test_scoring.py
│   └── test_memory_write.py
```

## Gewijzigde bestanden

```
henk/
├── henk/
│   ├── cli.py                      # Nieuw command: henk review
│   ├── brain.py                    # Memory retrieval bij elke LLM-call
│   ├── config.py                   # Memory config secties
│   ├── gateway.py                  # memory_write tool registratie
│   └── tools/__init__.py           # memory_write exporteren
├── henk.yaml.default               # Memory configuratie toevoegen
├── pyproject.toml                  # ChromaDB dependency
```

## Geheugenstructuur op schijf

De mappenstructuur bestaat al (aangemaakt door `henk init`). v0.3 vult deze met inhoud:

```
~/henk/memory/
├── core.md                         # Kerngeheugen — altijd in context
├── active/                         # Actief geheugen — per onderwerp
│   ├── project-henk.md
│   ├── voorkeur-code.md
│   └── ...
├── episodes/                       # Episodisch — sessie-samenvattingen
│   ├── 2026-03-12.md
│   └── ...
├── .staged/                        # Staging — wacht op review
│   ├── pending/                    # Voorgestelde wijzigingen
│   │   ├── change_001.json
│   │   └── change_002.json
│   └── archive/                    # Gearchiveerde items
│       └── ...
```

## Datamodellen (models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Provenance(str, Enum):
    """Herkomst van een geheugenwijziging."""
    USER_AUTHORED = "user-authored"
    AGENT_SUGGESTED = "agent-suggested"
    APPROVED_BY_USER = "approved-by-user"


class ChangeType(str, Enum):
    """Type geheugenwijziging."""
    CREATE = "create"           # Nieuw item aanmaken
    UPDATE = "update"           # Bestaand item bijwerken
    ARCHIVE = "archive"         # Item archiveren


@dataclass
class MemoryItem:
    """Een enkel geheugenonderdeel."""
    id: str                             # Unieke identifier (bijv. "active/project-henk")
    path: str                           # Relatief pad vanaf memory_dir
    title: str                          # Titel van het item
    description: str                    # Korte beschrijving (1-2 zinnen) voor vector search
    content: str                        # Volledige Markdown inhoud
    score: int = 50                     # Relevantiescore
    last_used: datetime | None = None   # Laatste keer gebruikt in LLM-context
    last_updated: datetime | None = None
    provenance: Provenance = Provenance.USER_AUTHORED
    tags: list[str] = field(default_factory=list)


@dataclass
class StagedChange:
    """Een voorgestelde geheugenwijziging in staging."""
    id: str                             # Unieke change ID
    change_type: ChangeType
    target_item_id: str | None          # ID van bestaand item (None bij create)
    proposed_content: str               # Voorgestelde inhoud
    proposed_description: str           # Voorgestelde beschrijving
    provenance: Provenance
    reason: str                         # Waarom stelt Henk dit voor
    timestamp: datetime
    suspicious: bool = False            # Automatisch gemarkeerd als verdacht
```

## MemoryStore (store.py)

Beheert het lezen en schrijven van geheugenbestanden op schijf. Elke memory-item is een Markdown-bestand met YAML frontmatter:

```markdown
---
id: active/project-henk
title: Project Henk
description: Architectuur en voortgang van het Henk AI-orchestrator project.
score: 65
last_used: 2026-03-12T14:30:00Z
last_updated: 2026-03-12T10:00:00Z
provenance: approved-by-user
tags: [project, architectuur]
---

# Project Henk

Henk is een persoonlijke AI-orchestrator...
```

Verantwoordelijkheden:
- `load_item(path) -> MemoryItem` — laad een item van schijf, parse frontmatter
- `save_item(item: MemoryItem)` — schrijf item naar schijf met frontmatter
- `list_items(layer: str) -> list[MemoryItem]` — lijst alle items in core/active/episodes
- `archive_item(item: MemoryItem)` — verplaats naar .staged/archive/
- `load_core() -> str` — laad core.md als plain text (gaat altijd mee in context)

Gebruik de `python-frontmatter` library voor het parsen van YAML frontmatter in Markdown. Voeg `python-frontmatter>=1.0.0` toe aan pyproject.toml.

## StagingManager (staging.py)

Beheert het staging-proces. Henk schrijft NOOIT direct naar actief geheugen.

```python
class StagingManager:
    """Beheert staged memory wijzigingen."""

    def __init__(self, staging_dir: Path, store: MemoryStore):
        self._staging_dir = staging_dir
        self._store = store
        self._pending_dir = staging_dir / "pending"
        self._pending_dir.mkdir(parents=True, exist_ok=True)

    def stage_change(self, change: StagedChange) -> None:
        """Schrijf een voorgestelde wijziging naar staging."""
        # Markeer als verdacht als het Henk's gedragsregels probeert te wijzigen
        if self._is_suspicious(change):
            change.suspicious = True
        # Schrijf als JSON naar pending/

    def list_pending(self) -> list[StagedChange]:
        """Lijst alle pending wijzigingen."""

    def approve(self, change_id: str) -> None:
        """Keur een wijziging goed en voer door naar actief geheugen."""
        # Laad change, voer door via store, verwijder uit pending
        # Voeg approved-by-user toe aan provenance

    def reject(self, change_id: str) -> None:
        """Keur een wijziging af en verwijder uit staging."""

    def _is_suspicious(self, change: StagedChange) -> bool:
        """Check of een wijziging verdacht is."""
        suspicious_patterns = [
            "system prompt", "persoonlijkheid", "gedragsregel",
            "geen bevestiging", "skip review", "altijd toestaan",
        ]
        content_lower = change.proposed_content.lower()
        return any(pattern in content_lower for pattern in suspicious_patterns)
```

## MemoryRetrieval (retrieval.py)

Selecteert welk geheugen mee gaat in de LLM-context bij elke call.

Twee mechanismen:
1. **core.md altijd mee** — bij elke LLM-call
2. **Vector search** — query tegen beschrijvingen van alle items, boven relevantiedrempel

Bij gebruik van een item: score +10.

Gebruik ChromaDB met standaard embedding functie:

```python
import chromadb

client = chromadb.PersistentClient(path=str(memory_dir / ".vectordb"))
collection = client.get_or_create_collection(
    name="henk_memory",
    metadata={"hnsw:space": "cosine"}
)
```

Elk geheugenitem wordt geïndexeerd op zijn `description` veld. Bij toevoegen of updaten van een item wordt de vector index bijgewerkt.

Methoden:
- `get_context(query: str) -> str` — core.md + relevante items als samengestelde tekst
- `rebuild_index()` — herbouw vector index vanaf alle geheugenbestanden

## RelevanceScorer (scoring.py)

```
Beginscore:          50
Verval:              -10 per week (op basis van last_used/last_updated)
Gebruik:             +10 bij daadwerkelijk gebruik in LLM-context
Minimum:             0 (niet negatief)
Archiveerdrempel:    10 (kandidaat voor archivering)
Auto-archivering:    Score 0 + twee reviews niet behouden
```

Methoden:
- `apply_decay(items) -> list[MemoryItem]` — pas verval toe
- `get_archive_candidates(items) -> list[MemoryItem]` — items onder drempel

## memory_write tool (tools/memory_write.py)

Een tool die Henk aanroept om iets te onthouden. Schrijft ALTIJD naar staging.

Parameters: title, description, content, reason.
Provenance: altijd `agent-suggested`.
De StagingManager checkt of de wijziging verdacht is.

## Brain wijzigingen (brain.py)

### Memory context meesturen

Bij elke LLM-call haalt de Brain geheugencontext op via MemoryRetrieval en voegt dat toe aan de system prompt:

```python
def _build_system_prompt(self, user_message: str) -> str:
    memory_context = ""
    if self._memory_retrieval:
        memory_context = self._memory_retrieval.get_context(user_message)
    if memory_context:
        return f"{SYSTEM_PROMPT}\n\n## Geheugen\n{memory_context}"
    return SYSTEM_PROMPT
```

De Brain krijgt `MemoryRetrieval` als optionele parameter in de constructor. Als het None is, werkt Henk zonder geheugen (backwards compatible).

### memory_write in tool-definities

Voeg toe aan `_anthropic_tools()`.

### Sessie-samenvatting

Voeg `summarize_session()` methode toe: maakt een LLM-call die de conversatiegeschiedenis samenvat in 3-5 zinnen. Wordt aangeroepen bij het afsluiten van `henk chat` en ge-staged als episodische herinnering.

## CLI wijzigingen (cli.py)

### Nieuw command: `henk review`

Toont alle pending wijzigingen. Per wijziging:
- Toon type, herkomst, reden, inhoud (max 300 karakters)
- Verdachte wijzigingen met rode waarschuwing, default = Nee
- Normale wijzigingen, default = Ja
- Na goedkeuring/afkeuring: volgende

Na alle wijzigingen: toon archiveringskandidaten (lage score). Gebruiker beslist per item.

### Memory initialisatie in `henk chat`

Initialiseer MemoryStore, StagingManager, MemoryRetrieval na config laden. Geef retrieval mee aan Brain. Voeg memory_write toe aan tools dict.

### Sessie-samenvatting bij afsluiten

Na de chat while-loop: als er een gesprek was, roep `brain.summarize_session()` aan en stage het resultaat als episodische samenvatting.

### henk init aanpassen

Voeg toe:
- Maak `~/henk/memory/.staged/pending/` aan
- Maak `~/henk/memory/.staged/archive/` aan

## Config wijzigingen

### henk.yaml.default

Voeg toe:

```yaml
memory:
  vector: true
  relevance_threshold: 0.3
  review_schedule: daily
  store_third_party_pii: false
  scoring:
    initial_score: 50
    decay_per_week: 10
    use_boost: 10
    archive_threshold: 10
```

### config.py

Voeg properties toe voor memory_vector_enabled, memory_relevance_threshold, memory_scoring.

### pyproject.toml

```toml
version = "0.3.0"
```

Voeg dependencies toe: `chromadb>=0.4.0`, `python-frontmatter>=1.0.0`.

### henk/__init__.py

```python
__version__ = "0.3.0"
```

## Veiligheid

### Memory payload NIET loggen

Pas `gateway.log_tool_result()` aan: als tool_name == "memory_write", log dan `"[MEMORY — niet gelogd]"` in plaats van de payload. Dit staat in het designdocument.

### Verdachte wijzigingen

StagingManager markeert wijzigingen als verdacht als ze patronen bevatten die Henk's gedragsregels proberen te wijzigen. Bij `henk review` worden verdachte wijzigingen met waarschuwing getoond.

## Tests

### test_memory_store.py
- Laden en opslaan van MemoryItem met frontmatter
- list_items geeft items uit juiste laag
- archive_item verplaatst naar archive/
- load_core geeft core.md inhoud

### test_staging.py
- stage_change schrijft JSON naar pending/
- approve verplaatst naar actief geheugen en voegt approved-by-user toe
- reject verwijdert uit pending
- Verdachte wijzigingen worden gemarkeerd
- Patronen die system prompt wijzigen zijn verdacht

### test_retrieval.py
- core.md is altijd meegenomen in context
- Vector search vindt relevante items
- Score wordt verhoogd na gebruik
- Items onder threshold worden niet meegenomen

### test_scoring.py
- Beginscore is 50
- Verval is correct per week
- Score wordt niet negatief
- Items onder archiveerdrempel worden gevonden

### test_memory_write.py
- Tool schrijft naar staging, niet naar actief geheugen
- Output is getagd met [TOOL:memory_write]
- ToolResult is correct gestructureerd

## Volgorde van bouwen

1. **models.py** — dataclasses als fundament
2. **store.py** — CRUD op geheugenbestanden met frontmatter
3. **scoring.py** — relevantie-scoring
4. **staging.py** — staging-proces met verdachte-wijziging detectie
5. **retrieval.py** — vector search + core.md, ChromaDB setup
6. **memory_write.py** — de tool
7. **brain.py wijzigingen** — memory context in system prompt, summarize_session()
8. **gateway.py wijzigingen** — memory payload niet loggen
9. **cli.py wijzigingen** — henk review, memory init, sessie-samenvatting
10. **config.py + henk.yaml.default** — memory config
11. **Tests**

## Samenvatting

v0.3 voegt toe:
1. Langetermijngeheugen als Markdown + YAML frontmatter
2. Staged memory — nooit direct schrijven, altijd via review
3. Vector search voor relevante context bij elke LLM-call
4. core.md altijd in context
5. memory_write tool voor Henk om dingen te onthouden
6. `henk review` voor dagelijkse goedkeuring
7. Sessie-samenvattingen automatisch ge-staged
8. Relevantie-scoring met verval en archivering
9. Verdachte-wijziging detectie

**Kernregel: Henk schrijft NOOIT direct naar actief geheugen. Alles gaat via staging.**

**Referenties:**
- `CLAUDE.md` — architectuurprincipes
- `docs/henk-design-v14.docx` — hoofdstuk 4 (Memory Detail), hoofdstuk 6.6 (Staged Memory), hoofdstuk 14 (Geheugen Detail)