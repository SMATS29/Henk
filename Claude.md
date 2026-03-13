# Henk v0.5 — Bouwinstructie voor Claude Code

## Context

v0.4 (“Henk Schakelt”) is gebouwd en werkend. Henk heeft CLI chat, tools, security, staged memory, vector search, en model-switching met vijf providers en drie rollen (FAST/DEFAULT/HEAVY).

Dit is v0.5: **“Henk Leert”**. Het doel is dat Henk complexe taken kan uitvoeren via stapsgewijze skill-documenten, met een Requirements Object dat gesprek en werk verbindt, en een simpele heartbeat voor tijdgetriggerde meldingen.

Lees `CLAUDE.md` en `docs/henk-design-v14.docx` (hoofdstuk 5: Tools & Skills, hoofdstuk 12: Interactie) voor het volledige ontwerp.

## Wat v0.5 WEL doet

- Skill Runner: laadt Markdown skill-documenten en voert ze stap voor stap uit
- Skill-selectie via samenvattingen en een LLM-call
- Stap-tracking: houdt bij welke stap actief is, welke afgerond
- Voortgangsrapportage na elke stap
- Foutafhandeling per stap
- Requirements Object als state-machine: draft → confirmed → executing → evaluated
- Requirements worden verfijnd via gesprek voordat uitvoering start
- Simpele heartbeat: timer tijdens `henk chat` sessie voor geplande meldingen
- Skill-samenvattingen verbeterbaar via de memory review cyclus

## Wat v0.5 NIET doet

- Geen sub-skill aanroepen (een stap die een andere skill start)
- Geen Dual-Thread model (gesprek en werk lopen synchroon, niet parallel)
- Geen daemon — heartbeat werkt alleen tijdens actieve `henk chat` sessie
- Geen Tauri desktop app

## Nieuwe bestanden

```
henk/
├── henk/
│   ├── skills/                     # Skill subsysteem
│   │   ├── __init__.py
│   │   ├── runner.py               # SkillRunner: stapsgewijze uitvoering
│   │   ├── selector.py             # SkillSelector: kiest juiste skill via LLM
│   │   ├── parser.py               # SkillParser: parsed Markdown skill-documenten
│   │   └── models.py               # Dataclasses: Skill, SkillStep, SkillRun
│   ├── requirements.py             # Requirements Object state-machine
│   ├── heartbeat.py                # Simpele timer voor geplande meldingen
├── skills/                         # Voorbeeld skill-documenten (in repo)
│   └── voorbeelden/
│       └── schrijf-samenvatting.md # Voorbeeld skill
├── tests/
│   ├── test_skill_runner.py
│   ├── test_skill_selector.py
│   ├── test_skill_parser.py
│   ├── test_requirements.py
│   └── test_heartbeat.py
```

## Gewijzigde bestanden

```
henk/
├── henk/
│   ├── cli.py                      # Skill-integratie in chat, heartbeat starten
│   ├── brain.py                    # Skill-selectie en stap-uitvoering via LLM
│   ├── gateway.py                  # Skill-events loggen, Requirements Object beheren
│   ├── react_loop.py               # Integratie met Skill Runner
│   └── config.py                   # Skill en heartbeat configuratie
├── henk.yaml.default               # Skill en heartbeat settings
├── pyproject.toml                  # Versie update
```

## Skills op schijf

Skills zijn Markdown-documenten die de gebruiker schrijft en in `~/henk/skills/` plaatst. Henk schrijft nooit zelf skills — hij kan wel via de memory review cyclus voorstellen doen om samenvattingen te verbeteren.

```
~/henk/skills/
├── schrijf-blogpost.md
├── code-review.md
├── vergelijk-opties.md
└── ...
```

### Skill-formaat

Een skill is een Markdown-bestand met een vaste structuur:

```markdown
---
name: schrijf-blogpost
summary: >
  Schrijf een blogpost over een opgegeven onderwerp. Zoekt bronnen,
  maakt een outline, schrijft een draft en levert het eindresultaat.
tags: [schrijven, content]
tools_required: [web_search, file_manager]
---

# Schrijf Blogpost

## Stap 1: Onderwerp en publiek bepalen
Bepaal het exacte onderwerp en doelpubliek. Als dit niet duidelijk is
uit de opdracht, vraag de gebruiker om verduidelijking.

**Actie:** Vat het onderwerp en publiek samen in één alinea.
**Output:** Opgeslagen als requirements.

## Stap 2: Bronnen zoeken
Zoek 3-5 relevante bronnen over het onderwerp via web_search.

**Actie:** Gebruik web_search voor elke bron.
**Output:** Lijst van bronnen met korte samenvatting per bron.

## Stap 3: Outline schrijven
Maak een outline met 4-6 secties op basis van de bronnen.

**Actie:** Schrijf de outline.
**Output:** Markdown outline opgeslagen via file_manager.

## Stap 4: Eerste draft
Schrijf de volledige blogpost op basis van de outline en bronnen.

**Actie:** Schrijf de blogpost.
**Output:** Volledige blogpost opgeslagen via file_manager.

## Stap 5: Review en oplevering
Controleer de blogpost op volledigheid en kwaliteit.
Presenteer het eindresultaat aan de gebruiker.

**Actie:** Review en lever op.
**Output:** Eindresultaat gepresenteerd.
```

Elke stap heeft:

- Een titel (## Stap N: …)
- Instructietekst (wat Henk moet doen)
- Een **Actie:** regel (de concrete handeling)
- Een **Output:** regel (wat het resultaat is)

## Datamodellen (skills/models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    """Status van een skill-stap."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillStep:
    """Een enkele stap in een skill."""
    number: int                         # Stapnummer (1-indexed)
    title: str                          # Staptitel
    instruction: str                    # Volledige instructietekst
    action: str                         # De concrete actie
    expected_output: str                # Wat het resultaat moet zijn
    status: StepStatus = StepStatus.PENDING
    result: str | None = None           # Resultaat na uitvoering
    error: str | None = None            # Foutmelding bij failure


@dataclass
class Skill:
    """Een geparsed skill-document."""
    name: str                           # Skill naam uit frontmatter
    summary: str                        # Samenvatting voor selectie
    tags: list[str]                     # Tags voor filtering
    tools_required: list[str]           # Benodigde tools
    steps: list[SkillStep]             # Alle stappen
    source_path: str                    # Pad naar het Markdown-bestand


@dataclass
class SkillRun:
    """Een actieve skill-uitvoering."""
    skill: Skill
    current_step: int = 0               # Index van actieve stap (0-indexed)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.skill.steps)

    @property
    def active_step(self) -> SkillStep | None:
        if self.current_step < len(self.skill.steps):
            return self.skill.steps[self.current_step]
        return None

    def advance(self) -> SkillStep | None:
        """Ga naar de volgende stap. Return de nieuwe actieve stap of None als klaar."""
        self.current_step += 1
        return self.active_step
```

## SkillParser (skills/parser.py)

Parsed een Markdown skill-document naar een `Skill` object.

```python
class SkillParser:
    """Parsed Markdown skill-documenten."""

    def parse(self, file_path: Path) -> Skill:
        """Laad en parse een skill-bestand.

        Verwacht:
        - YAML frontmatter met name, summary, tags, tools_required
        - Stappen als ## Stap N: Titel
        - Per stap: instructietekst, **Actie:** regel, **Output:** regel
        """
```

Gebruik `python-frontmatter` (al een dependency) voor het parsen van frontmatter. De stappen worden geparsed via regex op `## Stap \d+:` headers.

Wees robuust: als een stap geen **Actie:** of **Output:** regel heeft, gebruik dan de hele instructietekst als actie en laat output leeg.

## SkillSelector (skills/selector.py)

Selecteert de juiste skill voor een taak via een LLM-call.

```python
class SkillSelector:
    """Selecteert de juiste skill via samenvattingen."""

    def __init__(self, skills_dir: Path, router: ModelRouter):
        self._skills_dir = skills_dir
        self._router = router
        self._parser = SkillParser()

    def select(self, user_request: str) -> Skill | None:
        """Selecteer de juiste skill voor een verzoek.

        1. Laad alle skills en hun samenvattingen
        2. Stuur samenvattingen + het verzoek naar een FAST model
        3. Model kiest de beste match of zegt 'geen skill nodig'
        4. Return de gekozen Skill of None
        """
        skills = self._load_all_skills()
        if not skills:
            return None

        summaries = "\n".join(
            f"- {s.name}: {s.summary}" for s in skills
        )

        provider = self._router.get_provider(ModelRole.FAST)
        response = provider.chat(
            messages=[{
                "role": "user",
                "content": f"Verzoek: {user_request}\n\nBeschikbare skills:\n{summaries}\n\n"
                           f"Welke skill past het best? Antwoord met alleen de skill-naam, "
                           f"of 'geen' als geen skill past."
            }],
            system="Je bent een skill-selector. Kies de best passende skill of zeg 'geen'.",
        )

        chosen_name = response.text.strip().lower()
        for skill in skills:
            if skill.name.lower() == chosen_name:
                return skill
        return None

    def _load_all_skills(self) -> list[Skill]:
        """Laad alle .md bestanden uit de skills directory."""
        skills = []
        if not self._skills_dir.exists():
            return skills
        for path in self._skills_dir.glob("*.md"):
            try:
                skills.append(self._parser.parse(path))
            except Exception:
                continue  # Skip ongeldige skills
        return skills
```

## SkillRunner (skills/runner.py)

Voert een skill stap voor stap uit.

```python
class SkillRunner:
    """Voert skills stapsgewijs uit."""

    def __init__(self, brain, gateway, react_loop):
        self._brain = brain
        self._gateway = gateway
        self._react_loop = react_loop

    def run(self, skill: Skill, requirements: 'Requirements') -> str:
        """Voer een complete skill uit.

        Voor elke stap:
        1. Laad alleen de actieve stap in context (niet de hele skill)
        2. Stuur de stap-instructie + requirements naar de Brain
        3. Brain voert uit (mogelijk met tool-calls via ReactLoop)
        4. Registreer resultaat
        5. Rapporteer voortgang
        6. Ga naar volgende stap

        Returns: eindresultaat als tekst
        """
        skill_run = SkillRun(skill=skill, started_at=datetime.now())
        results = []

        while skill_run.active_step is not None:
            step = skill_run.active_step
            step.status = StepStatus.ACTIVE

            # Log voortgang
            self._gateway.log_skill_event("step.started", skill.name, step.number, step.title)

            try:
                # Bouw de prompt voor deze stap
                step_prompt = self._build_step_prompt(step, requirements, results)

                # Voer de stap uit via de ReAct-loop (zodat tools beschikbaar zijn)
                result = self._react_loop.run(step_prompt)

                step.status = StepStatus.COMPLETED
                step.result = result
                results.append(f"Stap {step.number} ({step.title}): {result}")

                self._gateway.log_skill_event("step.completed", skill.name, step.number, step.title)

            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                self._gateway.log_skill_event("step.failed", skill.name, step.number, str(e))

                # Rapporteer fout aan gebruiker en stop
                return f"Stap {step.number} ({step.title}) is mislukt: {e}\n\nEerdere resultaten:\n" + "\n".join(results)

            skill_run.advance()

        skill_run.completed_at = datetime.now()
        return results[-1] if results else "Skill afgerond zonder resultaat."

    def _build_step_prompt(self, step: SkillStep, requirements: 'Requirements', previous_results: list[str]) -> str:
        """Bouw de prompt voor één stap.

        Bevat:
        - De stap-instructie
        - De eisen uit het Requirements Object
        - Samenvattingen van eerdere stappen (niet de volledige output)
        """
        parts = [
            f"## Actieve stap: {step.title}",
            f"\n{step.instruction}",
            f"\n**Actie:** {step.action}",
            f"**Verwachte output:** {step.expected_output}",
        ]

        if requirements.specifications:
            parts.append(f"\n## Eisen\n{requirements.specifications}")

        if previous_results:
            parts.append("\n## Eerdere stappen")
            for r in previous_results[-3:]:  # Alleen laatste 3 voor context-beperking
                parts.append(f"- {r[:200]}")

        return "\n".join(parts)
```

## Requirements Object (requirements.py)

De state-machine die gesprek en werk verbindt.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RequirementsStatus(str, Enum):
    """Status van het Requirements Object."""
    DRAFT = "draft"                 # Eisen worden bepaald via gesprek
    CONFIRMED = "confirmed"         # Gebruiker heeft eisen bevestigd
    EXECUTING = "executing"         # Skill Runner is bezig
    EVALUATED = "evaluated"         # Klaar — resultaat beschikbaar of open eisen


@dataclass
class Requirements:
    """Het Requirements Object: verbindt gesprek en werk."""

    task_description: str               # Wat de gebruiker wil
    specifications: str = ""            # Verzamelde eisen (Markdown)
    status: RequirementsStatus = RequirementsStatus.DRAFT
    skill_name: str | None = None       # Gekoppelde skill (als gevonden)
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None           # Eindresultaat

    def add_specification(self, spec: str) -> None:
        """Voeg een eis toe of update bestaande eisen."""
        if self.status not in (RequirementsStatus.DRAFT, RequirementsStatus.CONFIRMED):
            return  # Geen eisen wijzigen tijdens uitvoering
        self.specifications += f"\n- {spec}" if self.specifications else f"- {spec}"

    def confirm(self) -> None:
        """Bevestig de eisen — klaar voor uitvoering."""
        self.status = RequirementsStatus.CONFIRMED
        self.confirmed_at = datetime.now()

    def start_execution(self) -> None:
        """Markeer als in uitvoering."""
        self.status = RequirementsStatus.EXECUTING

    def complete(self, result: str) -> None:
        """Markeer als afgerond met resultaat."""
        self.status = RequirementsStatus.EVALUATED
        self.completed_at = datetime.now()
        self.result = result

    def fail(self, reason: str) -> None:
        """Markeer als mislukt."""
        self.status = RequirementsStatus.EVALUATED
        self.completed_at = datetime.now()
        self.result = f"Mislukt: {reason}"
```

### Hoe de Requirements flow werkt

1. **Gebruiker zegt iets dat een taak impliceert** — bijv. “Schrijf een blogpost over AI security”
1. **Brain detecteert dat dit een taak is** — maakt Requirements Object aan (status: DRAFT)
1. **Brain kiest een skill** (als beschikbaar) via SkillSelector
1. **Brain stelt verduidelijkingsvragen** — “Technisch of algemeen publiek?” “Hoeveel woorden?”
1. **Gebruiker antwoordt** — Brain voegt specificaties toe aan Requirements
1. **Brain vraagt bevestiging** — “Ik ga een blogpost schrijven over AI security, ~1000 woorden, technisch publiek. Akkoord?”
1. **Gebruiker bevestigt** — Requirements status → CONFIRMED
1. **Skill Runner start** — status → EXECUTING, voert stappen uit
1. **Skill Runner klaar** — status → EVALUATED, resultaat wordt gepresenteerd

De Brain beslist wanneer er genoeg informatie is om te bevestigen. Als er geen skill beschikbaar is, voert de Brain de taak uit via de reguliere ReAct-loop zonder Skill Runner.

## Brain wijzigingen (brain.py)

### Taakdetectie en requirements-flow

De Brain moet onderscheid maken tussen:

- **Gesprek** — gewoon chatten, geen taak
- **Taak** — iets dat uitvoering vereist

Voeg een methode toe die dit classificeert:

```python
def classify_input(self, user_message: str) -> str:
    """Classificeer input als 'gesprek' of 'taak'.

    Gebruikt het FAST model voor snelle classificatie.
    """
    provider = self._router.get_provider(ModelRole.FAST)
    response = provider.chat(
        messages=[{
            "role": "user",
            "content": f"Is dit een verzoek om iets te doen (taak) of gewoon een gespreksbericht?\n\n"
                       f"\"{user_message}\"\n\nAntwoord met alleen 'taak' of 'gesprek'."
        }],
        system="Classificeer berichten. Antwoord alleen met 'taak' of 'gesprek'.",
    )
    return "taak" if "taak" in response.text.strip().lower() else "gesprek"
```

### Skill-integratie

```python
class Brain:
    def __init__(self, config, router, memory_retrieval=None, skill_selector=None):
        # ... bestaande init ...
        self._skill_selector = skill_selector
        self._active_requirements: Requirements | None = None
```

## Heartbeat (heartbeat.py)

Simpele timer die tijdens een `henk chat` sessie draait.

```python
import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduledReminder:
    """Een geplande herinnering."""
    id: str
    message: str
    trigger_at: datetime
    triggered: bool = False


class Heartbeat:
    """Simpele timer voor geplande meldingen.

    Draait alleen tijdens een actieve henk chat sessie.
    Controleert elke 30 seconden of er herinneringen moeten worden getriggerd.
    """

    def __init__(self, interval_seconds: int = 30):
        self._interval = interval_seconds
        self._reminders: list[ScheduledReminder] = []
        self._timer: threading.Timer | None = None
        self._running = False
        self._callback = None  # Wordt gezet door cli.py

    def start(self, callback) -> None:
        """Start de heartbeat. Callback wordt aangeroepen met een reminder message."""
        self._callback = callback
        self._running = True
        self._tick()

    def stop(self) -> None:
        """Stop de heartbeat."""
        self._running = False
        if self._timer:
            self._timer.cancel()

    def add_reminder(self, reminder: ScheduledReminder) -> None:
        """Plan een herinnering."""
        self._reminders.append(reminder)

    def _tick(self) -> None:
        """Check of er herinneringen moeten worden getriggerd."""
        if not self._running:
            return

        now = datetime.now()
        for reminder in self._reminders:
            if not reminder.triggered and reminder.trigger_at <= now:
                reminder.triggered = True
                if self._callback:
                    self._callback(reminder.message)

        # Verwijder getriggerde herinneringen
        self._reminders = [r for r in self._reminders if not r.triggered]

        # Plan volgende tick
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True  # Stop als hoofdthread stopt
        self._timer.start()

    @property
    def pending_count(self) -> int:
        return len([r for r in self._reminders if not r.triggered])
```

### Herinnering-tool

Voeg een `reminder` tool toe zodat Henk zelf herinneringen kan plannen:

```python
class ReminderTool(BaseTool):
    """Plan een herinnering voor later in de sessie."""

    name = "reminder"
    description = "Plan een herinnering. Werkt alleen tijdens de huidige chat-sessie."
    permissions = ["write"]
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "De herinnering"},
            "minutes": {"type": "integer", "description": "Over hoeveel minuten"},
        },
        "required": ["message", "minutes"],
    }

    def __init__(self, heartbeat: Heartbeat):
        self._heartbeat = heartbeat

    def execute(self, **kwargs) -> ToolResult:
        from datetime import timedelta
        reminder = ScheduledReminder(
            id=uuid.uuid4().hex[:8],
            message=kwargs["message"],
            trigger_at=datetime.now() + timedelta(minutes=kwargs["minutes"]),
        )
        self._heartbeat.add_reminder(reminder)
        tagged = tag_output(self.name, f"Herinnering gepland over {kwargs['minutes']} minuten.", external=False)
        return ToolResult(success=True, data=tagged, source_tag="[TOOL:reminder]")
```

## CLI wijzigingen (cli.py)

### Skill-integratie in chat-loop

De chat-loop moet nu onderscheid maken tussen gesprek en taken:

```python
# In de chat while-loop:
while True:
    user_input = console.input("[bold]Henk > [/bold]")
    # ... bestaande exit/empty checks ...

    # Classificeer input
    input_type = brain.classify_input(user_input)

    if input_type == "taak" and not brain._active_requirements:
        # Nieuwe taak — maak Requirements Object aan
        requirements = Requirements(task_description=user_input)

        # Probeer een skill te selecteren
        skill = skill_selector.select(user_input) if skill_selector else None
        if skill:
            requirements.skill_name = skill.name
            console.print(f"[dim]Skill gevonden: {skill.name}[/dim]")

        brain._active_requirements = requirements

        # Laat Brain de eisen verfijnen
        response = brain.refine_requirements(user_input, requirements)
        # Brain kan vragen stellen of direct bevestigen

    elif brain._active_requirements and brain._active_requirements.status == RequirementsStatus.DRAFT:
        # Lopende requirements-verfijning
        response = brain.refine_requirements(user_input, brain._active_requirements)

    elif brain._active_requirements and brain._active_requirements.status == RequirementsStatus.CONFIRMED:
        # Eisen bevestigd — start uitvoering
        requirements = brain._active_requirements
        requirements.start_execution()

        if requirements.skill_name:
            skill = skill_selector.select(requirements.task_description)
            result = skill_runner.run(skill, requirements)
        else:
            result = react_loop.run(requirements.task_description + "\n\nEisen:\n" + requirements.specifications)

        requirements.complete(result)
        brain._active_requirements = None
        response = result

    else:
        # Gewoon gesprek
        response = gateway.process(user_input)
```

Dit is een vereenvoudigde flow. De Brain’s `refine_requirements()` methode handelt het gesprek af: stelt vragen, voegt specificaties toe, en detecteert wanneer de gebruiker bevestigt (bijv. “ja”, “akkoord”, “ga maar”, “doe maar”).

### Heartbeat integratie

```python
# Bij het starten van henk chat:
heartbeat = Heartbeat(interval_seconds=30)

def on_reminder(message: str):
    console.print(f"\n[yellow]⏰ Herinnering: {message}[/yellow]\n[bold]Henk > [/bold]", end="")

heartbeat.start(on_reminder)

# Bij het afsluiten:
heartbeat.stop()
```

### Herinnering-tool toevoegen

```python
from henk.heartbeat import Heartbeat, ReminderTool

tools["reminder"] = ReminderTool(heartbeat=heartbeat)
```

## Gateway wijzigingen (gateway.py)

### Skill-events loggen

```python
def log_skill_event(self, event_type: str, skill_name: str, step_number: int, detail: str = "") -> None:
    """Log een skill-gerelateerd event."""
    self._transcript.log_event({
        "type": f"skill.{event_type}",
        "session_id": self._transcript.session_id,
        "skill": skill_name,
        "step": step_number,
        "detail": detail,
    })
```

## Config wijzigingen

### henk.yaml.default

Voeg toe:

```yaml
skills:
  dir: ~/henk/skills
  enabled: true

heartbeat:
  enabled: true
  interval_seconds: 30
```

### config.py

```python
@property
def skills_dir(self) -> Path:
    return Path(self._data.get("skills", {}).get("dir", "~/henk/skills")).expanduser()

@property
def skills_enabled(self) -> bool:
    return bool(self._data.get("skills", {}).get("enabled", True))

@property
def heartbeat_enabled(self) -> bool:
    return bool(self._data.get("heartbeat", {}).get("enabled", True))

@property
def heartbeat_interval(self) -> int:
    return int(self._data.get("heartbeat", {}).get("interval_seconds", 30))
```

### pyproject.toml + **init**.py

```toml
version = "0.5.0"
```

```python
__version__ = "0.5.0"
```

## henk init aanpassen

Voeg toe:

- Maak `~/henk/skills/` aan als die niet bestaat

## Voorbeeld skill: schrijf-samenvatting.md

Plaats in de repo als `skills/voorbeelden/schrijf-samenvatting.md`. De gebruiker kopieert skills naar `~/henk/skills/`.

```markdown
---
name: schrijf-samenvatting
summary: >
  Maak een beknopte samenvatting van een document of tekst.
  Leest het bronbestand, identificeert de hoofdpunten en
  schrijft een samenvatting van de gevraagde lengte.
tags: [schrijven, samenvatting]
tools_required: [file_manager]
---

# Schrijf Samenvatting

## Stap 1: Bron lezen
Lees het bronbestand dat de gebruiker wil laten samenvatten.

**Actie:** Gebruik file_manager om het bestand te lezen.
**Output:** Inhoud van het bronbestand.

## Stap 2: Hoofdpunten identificeren
Analyseer de tekst en identificeer de 3-5 belangrijkste punten.

**Actie:** Maak een lijst van hoofdpunten.
**Output:** Genummerde lijst van hoofdpunten.

## Stap 3: Samenvatting schrijven
Schrijf een samenvatting op basis van de hoofdpunten.
Respecteer de gewenste lengte uit de eisen.

**Actie:** Schrijf de samenvatting.
**Output:** Samenvatting opgeslagen via file_manager.
```

## Brain: refine_requirements methode

```python
def refine_requirements(self, user_input: str, requirements: Requirements) -> str:
    """Verfijn eisen via gesprek.

    De Brain:
    1. Analyseert de taak en wat er nog onduidelijk is
    2. Stelt maximaal één gerichte vraag (Henk stelt nooit drie vragen tegelijk)
    3. Voegt antwoorden toe aan requirements.specifications
    4. Detecteert bevestiging en zet status naar CONFIRMED

    Bevestigingspatronen: 'ja', 'akkoord', 'ga maar', 'doe maar', 'prima', 'start maar'
    """
    provider = self._router.get_provider(ModelRole.DEFAULT)
    system = self._build_system_prompt(user_input)

    # Bouw een prompt die de Brain vraagt om eisen te verfijnen
    prompt = (
        f"De gebruiker wil: {requirements.task_description}\n"
        f"Huidige eisen:\n{requirements.specifications or '(nog geen)'}\n"
        f"Laatste bericht van de gebruiker: {user_input}\n\n"
        f"Analyseer of er genoeg informatie is om te beginnen. "
        f"Als er iets onduidelijk is, stel dan één gerichte vraag. "
        f"Als alles duidelijk is, vat de eisen samen en vraag bevestiging. "
        f"Als de gebruiker bevestigt (ja/akkoord/doe maar), antwoord dan exact met: [CONFIRMED]"
    )

    response = provider.chat(
        messages=self._history + [{"role": "user", "content": prompt}],
        system=system,
    )

    answer = response.text

    if "[CONFIRMED]" in answer:
        requirements.confirm()
        answer = answer.replace("[CONFIRMED]", "").strip()
    else:
        # Voeg eventuele nieuwe specificaties toe
        requirements.add_specification(user_input)

    self._history.append({"role": "user", "content": user_input})
    self._history.append({"role": "assistant", "content": answer})
    return answer
```

## Tests

### test_skill_parser.py

- Parsed een geldige skill met frontmatter en stappen
- Stappen worden correct genummerd
- Ontbrekende Actie/Output regels worden graceful afgehandeld
- Ongeldige bestanden geven een duidelijke fout

### test_skill_selector.py

- Selecteert de juiste skill op basis van een verzoek
- Retourneert None als geen skill past
- Werkt met lege skills directory

### test_skill_runner.py

- Voert alle stappen van een skill sequentieel uit
- Stopt bij een gefaalde stap met foutmelding
- Rapporteert voortgang per stap
- Eerdere resultaten worden meegestuurd (max 3)

### test_requirements.py

- Status-flow: draft → confirmed → executing → evaluated
- Specificaties toevoegen werkt in draft en confirmed
- Specificaties toevoegen wordt genegeerd tijdens executing
- Complete en fail zetten status naar evaluated

### test_heartbeat.py

- Herinnering triggert na opgegeven tijd
- Callback wordt aangeroepen bij trigger
- Stop beëindigt de timer
- Meerdere herinneringen worden onafhankelijk getrackt

## Volgorde van bouwen

1. **skills/models.py** — dataclasses
1. **skills/parser.py** — Markdown skill-parser
1. **skills/selector.py** — skill-selectie via LLM
1. **requirements.py** — Requirements Object state-machine
1. **skills/runner.py** — stapsgewijze uitvoering
1. **heartbeat.py** — timer + ScheduledReminder + ReminderTool
1. **brain.py wijzigingen** — classify_input, refine_requirements, skill-integratie
1. **gateway.py wijzigingen** — skill-events loggen
1. **react_loop.py wijzigingen** — integratie met skill-stap uitvoering
1. **cli.py wijzigingen** — taakdetectie, requirements-flow, heartbeat
1. **config.py + henk.yaml.default** — skill en heartbeat config
1. **Voorbeeld skill** — schrijf-samenvatting.md
1. **Tests**

## Samenvatting

v0.5 voegt toe:

1. Skill Runner: stapsgewijze uitvoering van Markdown skill-documenten
1. Skill-selectie via samenvattingen en LLM-classificatie
1. Requirements Object: draft → confirmed → executing → evaluated
1. Eisen-verfijning via gesprek voordat uitvoering begint
1. Simpele heartbeat met herinneringen tijdens chat-sessie
1. Voortgangsrapportage per skill-stap
1. Voorbeeld skill meegeleverd

**Kernregel: één stap tegelijk in context. Niet de hele skill laden.**

**Referenties:**

- `CLAUDE.md` — architectuurprincipes
- `docs/henk-design-v14.docx` — hoofdstuk 5.2 (Skills), 5.3 (Skill Runner), 12.2 (Requirements Object)