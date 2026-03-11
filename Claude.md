# Henk — Project Context voor Claude Code

## Wat is Henk?

Henk is een persoonlijke AI-orchestrator — geen chatbot, maar een collega. Een CLI-first systeem dat taken uitvoert, tools aanroept en kennis opbouwt. Het volledige architectuurdocument staat in `docs/henk-design-v14.docx`. Lees dat document voor alle details.

## Huidige fase: v0.1 — "Henk Praat"

CLI chat met Henk's persoonlijkheid, Gateway embedded in CLI-proces, JSONL logging. Geen tools, geen app, geen daemon. Zie `docs/henk-v01-instructie.md` voor de bouwopdracht.

## Fasering

- **v0.1** — CLI chat, embedded Gateway, ReAct-structuur zonder tools
- **v0.2** — Tools, security proxy, Gateway als daemon met Named Pipes, Tauri desktop app, kill switches, gedeeld gesprek
- **v0.3** — Langetermijngeheugen, staged memory, dagelijkse review
- **v0.4** — Model-switching, Ollama/LM Studio, configureerbare limieten via UI
- **v0.5** — Skill Runner, Requirements Object, heartbeat scheduler
- **v1.0** — Sub-agents, voice pipeline, webversie voor remote access

## Architectuurprincipes — ALTIJD respecteren

### Security-first
- API keys staan in `.env`, worden geladen via python-dotenv, en komen NOOIT in een LLM prompt
- Alle toekomstige tool-output wordt getagd met zijn bron (`[TOOL:naam]`) — bouw hier alvast structuur voor
- Kill switch bestanden (`~/henk/control/graceful_stop`, `hard_stop`) worden gecheckt bij elk bericht
- De Gateway bewaakt limieten, niet de Brain. Het model kan zijn eigen limieten niet overschrijven

### Scheiding van verantwoordelijkheden
- **CLI** (`cli.py`) — gebruikersinterface, REPL loop
- **Gateway** (`gateway.py`) — validatie, limieten, logging, security. Wordt later daemon
- **Brain** (`brain.py`) — persoonlijkheid, reasoning, API calls. Wordt later ReAct-loop met tools
- **Config** (`config.py`) — laden van henk.yaml en .env
- **Transcript** (`transcript.py`) — JSONL logging

### Gateway is het zenuwstelsel
- Alle communicatie loopt via de Gateway, zonder uitzondering
- De Gateway is in v0.1 een class die embedded draait; in v0.2 wordt het een daemon met Named Pipe server
- Loop-teller en limieten zitten in Gateway-state, niet in de Brain
- Bouw de Gateway zo dat hij later als los proces kan draaien zonder de interne logica te veranderen

### Brain is Henk's karakter
- System prompt is hardcoded als constante — niet uit een bestand, niet configureerbaar door het systeem
- Conversatiegeschiedenis is in-memory per sessie
- De Brain beslist WAT hij doet; de Gateway beslist OF hij het MAG

### Henk's persoonlijkheid
- Nederlands, direct, eerlijk, kort
- Geen "Natuurlijk!", "Zeker!", "Super!", "Goed idee!"
- Eén vraag tegelijk, nooit drie
- Als iets een slecht idee is: zeg het één keer, kort, met reden. Doe dan wat gevraagd is

## Mappenstructuur

```
~/henk/                         # Henk's data (aangemaakt door henk init)
├── memory/                     # Geheugen (v0.3+)
│   ├── core.md
│   ├── active/
│   ├── episodes/
│   └── .staged/
├── workspace/                  # Werkbestanden per run (v0.2+)
├── skills/                     # Skill-documenten (v0.5+)
├── control/
│   ├── graceful_stop
│   └── hard_stop
├── tools/                      # Tool-plugins (v0.2+)
│   ├── user/
│   ├── generated/
│   └── external/
├── logs/                       # JSONL transcripts
└── henk.yaml                   # Configuratie
```

## Wat NIET bouwen tenzij expliciet gevraagd

- Tool-calling of tool-definities (v0.2)
- Named Pipes of daemon-modus (v0.2)
- Tauri app of UI (v0.2)
- Envelope-protocol of message types (v0.2)
- Langetermijngeheugen, vector search, staged memory (v0.3)
- Model-switching of LiteLLM (v0.4)
- Skill Runner of skills (v0.5)
- Multi-agent (v1.0)

## Codestijl

- Python 3.11+
- Type hints overal
- Docstrings in het Nederlands
- Foutmeldingen naar de gebruiker in het Nederlands
- Code comments in het Engels (conventie)
- pytest voor tests
- Geen onnodige abstracties — YAGNI. Bouw wat nu nodig is, structureer het zo dat het later uitbreidbaar is