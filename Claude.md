# Henk CLI Polish — Bouwinstructie voor Claude Code

## Context

Henk heeft een werkende REPL met prompt_toolkit, slash-commands en autocomplete. Deze instructie voegt vier UX-verbeteringen toe die de CLI op het niveau brengen van een moderne tool.

## Vier wijzigingen

1. **Spinner/indicator** — visuele feedback tijdens denken, tool-calls en skill-stappen
1. **Markdown rendering** — Rich Markdown voor Henk’s antwoorden
1. **Multi-line input** — Shift+Enter voor nieuwe regel, Enter om te versturen
1. **Token-teller** — totaal tokengebruik per sessie, getoond na elk antwoord

## 1. Spinner/indicator

### Wat de gebruiker ziet

```
❯ Zoek het weer in Amsterdam

⠋ Henk denkt...
⠙ web_search: weer Amsterdam
⠹ Henk denkt...

Het is 14°C en bewolkt in Amsterdam.

❯ Schrijf een samenvatting van dat rapport

⠋ Stap 1/3: Bron lezen
⠙ file_manager: read rapport.md
⠹ Stap 2/3: Hoofdpunten identificeren
⠸ Stap 3/3: Samenvatting schrijven

Hier is de samenvatting...
```

### Implementatie

Gebruik Rich’s `console.status()` voor de spinner. Het probleem: de spinner moet updaten terwijl de Brain en tools werken. Dat betekent dat de spinner in de aanroepende code zit, niet in de Brain zelf.

Maak een `SpinnerContext` class die de spinner beheert:

```python
"""Visuele feedback tijdens verwerking."""

from __future__ import annotations

from contextlib import contextmanager
from rich.console import Console


class Spinner:
    """Beheert de spinner-indicator in de REPL."""

    def __init__(self, console: Console):
        self._console = console
        self._status = None

    def start(self, message: str = "Henk denkt...") -> None:
        """Start of update de spinner met een nieuw bericht."""
        if self._status is not None:
            self._status.update(message)
        else:
            self._status = self._console.status(message, spinner="dots")
            self._status.start()

    def update(self, message: str) -> None:
        """Update het spinner-bericht."""
        if self._status is not None:
            self._status.update(message)

    def stop(self) -> None:
        """Stop de spinner."""
        if self._status is not None:
            self._status.stop()
            self._status = None
```

### Spinner integreren in de flow

De spinner moet updaten op drie momenten:

- Brain start met denken → “Henk denkt…”
- Tool wordt aangeroepen → “web_search: weer Amsterdam”
- Skill-stap start → “Stap 2/5: Bronnen zoeken”

De schoonste manier: geef een callback mee aan de ReactLoop en SkillRunner die de spinner update.

**In repl.py**, rond de `gateway.process()` call:

```python
spinner = Spinner(console)

try:
    spinner.start("Henk denkt...")
    
    # Geef spinner.update als callback mee
    response = gateway.process(stripped, on_status=spinner.update)
    
    spinner.stop()
    if response:
        console.print(...)
except Exception:
    spinner.stop()
    ...
```

**In gateway.py**, propageer de callback:

```python
def process(self, user_message: str, on_status: Callable[[str], None] | None = None) -> str:
    # ... bestaande logica ...
    response = self._react_loop.run(user_message, on_status=on_status)
    return response
```

**In react_loop.py**, roep de callback aan bij tool-calls:

```python
def run(self, user_message: str, on_status: Callable[[str], None] | None = None) -> str:
    # ...
    def execute_tool(tool_name: str, params: dict) -> ToolResult:
        if on_status:
            # Toon de tool en een relevante parameter
            detail = _tool_detail(tool_name, params)
            on_status(f"{tool_name}: {detail}")
        # ... bestaande tool executie ...
        if on_status:
            on_status("Henk denkt...")
        return result

    return self._brain.run_with_tools(user_message, execute_tool)


def _tool_detail(tool_name: str, params: dict) -> str:
    """Maak een korte beschrijving van de tool-call voor de spinner."""
    if tool_name == "web_search":
        return params.get("query", "")[:50]
    if tool_name == "file_manager":
        action = params.get("action", "")
        path = params.get("path", "")
        return f"{action} {path}"[:50]
    if tool_name == "code_runner":
        return params.get("language", "code")
    if tool_name == "memory_write":
        return params.get("title", "")[:50]
    return ""
```

**In skills/runner.py**, update spinner bij elke stap:

```python
def run(self, skill: Skill, requirements: Requirements, on_status: Callable | None = None) -> str:
    # ...
    while skill_run.active_step is not None:
        step = skill_run.active_step
        total = len(skill.steps)
        if on_status:
            on_status(f"Stap {step.number}/{total}: {step.title}")
        # ... bestaande stap-uitvoering ...
```

## 2. Markdown rendering

### Wat de gebruiker ziet

In plaats van platte tekst:

```
Hier zijn drie opties:

1. **Optie A** — snel maar duur
2. **Optie B** — langzaam maar goedkoop
3. **Optie C** — balans

```python
print("hello world")
`` `
```

Ziet de gebruiker: vetgedrukte tekst daadwerkelijk vet, genummerde lijsten netjes geïndenteerd, en code blocks met syntax highlighting en een achtergrondkleur.

### Implementatie

Rich heeft ingebouwde Markdown rendering via `Markdown`:

```python
from rich.markdown import Markdown

# In plaats van:
console.print(f"[cyan]{response}[/cyan]\n")

# Gebruik:
console.print(Markdown(response))
console.print()  # Lege regel na antwoord
```

Dat is alles. Rich doet de rest: kopjes krijgen kleur, code blocks krijgen syntax highlighting via Pygments, lijsten worden netjes gerenderd.

### Pas op: niet alles is Markdown

Foutmeldingen, spinner-tekst en slash-command output zijn geen Markdown. Gebruik `Markdown()` alleen voor Henk’s antwoorden — de output van `gateway.process()` en `react_loop.run()`.

Maak een helper:

```python
def print_henk(console: Console, text: str) -> None:
    """Print Henk's antwoord met Markdown rendering."""
    try:
        console.print(Markdown(text))
    except Exception:
        # Fallback naar platte tekst als Markdown parsing faalt
        console.print(f"[cyan]{text}[/cyan]")
    console.print()  # Lege regel
```

Gebruik `print_henk()` overal waar Henk’s antwoorden worden getoond.

## 3. Multi-line input

### Wat de gebruiker ziet

```
❯ Dit is een korte vraag[Enter]

Henk antwoordt...

❯ Dit is een langere tekst[Shift+Enter]
  die over meerdere regels gaat[Shift+Enter]
  en pas verstuurd wordt als ik Enter druk[Enter]

Henk antwoordt...
```

### Implementatie

prompt_toolkit ondersteunt multi-line input via key bindings. Shift+Enter voegt een nieuwe regel toe, Enter verstuurt.

```python
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

def _build_key_bindings() -> KeyBindings:
    """Key bindings: Enter = versturen, Shift+Enter = nieuwe regel."""
    bindings = KeyBindings()

    @bindings.add(Keys.Enter)
    def handle_enter(event):
        """Enter = verstuur het bericht."""
        event.current_buffer.validate_and_handle()

    @bindings.add(Keys.ShiftEnter)
    def handle_shift_enter(event):
        """Shift+Enter = nieuwe regel."""
        event.current_buffer.insert_text("\n")

    return bindings
```

Geef de bindings mee aan de PromptSession:

```python
session = PromptSession(
    completer=_build_completer(),
    style=PROMPT_STYLE,
    key_bindings=_build_key_bindings(),
    multiline=True,
)
```

### Prompt voor vervolg-regels

Bij multi-line input wil je een visuele indicatie dat je op een vervolg-regel zit:

```python
from prompt_toolkit.formatted_text import HTML

def _get_prompt(line_number: int, wrap_count: int) -> str:
    """Prompt voor eerste en vervolg-regels."""
    if line_number == 0:
        return HTML("<prompt>❯ </prompt>")
    return HTML("<prompt>  </prompt>")  # Ingesprongen vervolg-regel


session = PromptSession(
    # ...
    prompt_continuation="  ",  # Inspringen voor vervolg-regels
)
```

Eigenlijk is `prompt_continuation` de simpelste aanpak. Dat toont `  ` (twee spaties) voor elke vervolg-regel.

## 4. Token-teller

### Wat de gebruiker ziet

Na elk antwoord, subtiel in dim:

```
❯ Leg uit hoe TCP werkt

TCP is een verbindingsgeoriënteerd protocol...
[uitleg]

                                          sessie: 1.2k tokens

❯ En UDP?

UDP is het tegenovergestelde...

                                          sessie: 2.8k tokens
```

De teller is rechts uitgelijnd, dim, en toont het cumulatieve tokengebruik van de hele sessie.

### Implementatie

De Anthropic API retourneert token-informatie in de response:

```python
response = client.messages.create(...)
input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens
```

Maak een `TokenTracker` class:

```python
"""Token-tracking per sessie."""

from __future__ import annotations


class TokenTracker:
    """Houdt tokengebruik bij per sessie."""

    def __init__(self):
        self._total_input: int = 0
        self._total_output: int = 0
        self._call_count: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Registreer tokens van een API call."""
        self._total_input += input_tokens
        self._total_output += output_tokens
        self._call_count += 1

    @property
    def total(self) -> int:
        """Totaal tokens (input + output)."""
        return self._total_input + self._total_output

    @property
    def total_input(self) -> int:
        return self._total_input

    @property
    def total_output(self) -> int:
        return self._total_output

    @property
    def call_count(self) -> int:
        return self._call_count

    def format(self) -> str:
        """Formatteer voor weergave."""
        total = self.total
        if total < 1000:
            return f"{total} tokens"
        return f"{total / 1000:.1f}k tokens"
```

### Token-informatie ophalen uit providers

Het probleem: de `ProviderResponse` bevat nu geen token-informatie. Voeg dit toe:

```python
# In router/providers/base.py
@dataclass
class ProviderResponse:
    text: str | None
    tool_calls: list[ToolCall] | None
    raw: Any = None
    input_tokens: int = 0       # Nieuw
    output_tokens: int = 0      # Nieuw
```

**In anthropic.py:**

```python
return ProviderResponse(
    text=...,
    tool_calls=...,
    raw=response,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
)
```

**In openai_provider.py (en OpenAI-compatible providers):**

```python
return ProviderResponse(
    text=...,
    tool_calls=...,
    raw=response,
    input_tokens=getattr(response.usage, "prompt_tokens", 0),
    output_tokens=getattr(response.usage, "completion_tokens", 0),
)
```

### Token-tracking in de Brain

De Brain registreert tokens na elke API call:

```python
class Brain:
    def __init__(self, ...):
        # ...
        self.token_tracker = TokenTracker()

    def _track_response(self, response: ProviderResponse) -> None:
        """Registreer tokengebruik."""
        self.token_tracker.add(response.input_tokens, response.output_tokens)
```

Roep `_track_response()` aan na elke `provider.chat()` call in `think()`, `run_with_tools()`, `greet()`, `classify_input()`, `refine_requirements()`, `summarize_session()`.

### Weergave in de REPL

Na elk antwoord, toon de sessie-teller rechts uitgelijnd:

```python
def print_henk(console: Console, text: str, token_tracker: TokenTracker) -> None:
    """Print Henk's antwoord met Markdown en token-indicatie."""
    try:
        console.print(Markdown(text))
    except Exception:
        console.print(f"[cyan]{text}[/cyan]")

    # Token-teller rechts uitgelijnd
    token_text = f"sessie: {token_tracker.format()}"
    width = console.width
    console.print(f"[dim]{token_text:>{width}}[/dim]")
    console.print()  # Lege regel
```

## Nieuwe bestanden

```
henk/
├── henk/
│   ├── spinner.py              # Spinner class
│   ├── token_tracker.py        # TokenTracker class
│   ├── output.py               # print_henk() helper met Markdown rendering
```

## Gewijzigde bestanden

```
henk/
├── henk/
│   ├── repl.py                 # Multi-line input, spinner integratie, token weergave
│   ├── react_loop.py           # on_status callback voor spinner
│   ├── gateway.py              # on_status propagatie
│   ├── brain.py                # Token tracking na elke API call
│   ├── skills/runner.py        # on_status callback voor skill-stappen
│   ├── router/providers/base.py    # input_tokens/output_tokens in ProviderResponse
│   ├── router/providers/anthropic.py  # Token-info uit response
│   ├── router/providers/openai_provider.py  # Token-info uit response
```

## Samenvatting van wijzigingen aan repl.py

De REPL wordt als volgt aangepast:

```python
from henk.spinner import Spinner
from henk.token_tracker import TokenTracker
from henk.output import print_henk

def start_repl(config, console):
    # ... bestaande init ...

    spinner = Spinner(console)
    # Token tracker zit in brain.token_tracker

    session = PromptSession(
        completer=_build_completer(),
        style=PROMPT_STYLE,
        key_bindings=_build_key_bindings(),
        multiline=True,
        prompt_continuation="  ",
    )

    while True:
        user_input = session.prompt(HTML("<prompt>❯ </prompt>"))
        stripped = user_input.strip()
        if not stripped:
            continue

        if stripped.startswith("/"):
            result = dispatch_command(stripped, config, console, **command_context)
            if result == "exit":
                break
            continue

        try:
            spinner.start("Henk denkt...")
            response = gateway.process(stripped, on_status=spinner.update)
            spinner.stop()

            if response:
                print_henk(console, response, brain.token_tracker)
        except KillSwitchActive as e:
            spinner.stop()
            console.print(f"[red]Henk is gestopt ({e.switch_type}). Typ /resume.[/red]")
        except Exception:
            spinner.stop()
            console.print("[red]Ik kan even niet bij mijn brein.[/red]\n")
```

## Tests

### test_spinner.py

- start() toont spinner
- update() verandert het bericht
- stop() stopt de spinner
- Dubbel stop() crasht niet

### test_token_tracker.py

- add() telt tokens op
- total geeft input + output
- format() geeft “1.2k tokens” voor > 1000
- format() geeft “847 tokens” voor < 1000
- Begint op 0

### test_output.py

- print_henk() rendert Markdown
- print_henk() valt terug naar platte tekst bij parse-fout
- Token-teller is rechts uitgelijnd

## Volgorde van bouwen

1. **spinner.py** — Spinner class
1. **token_tracker.py** — TokenTracker class
1. **output.py** — print_henk() helper
1. **router/providers/base.py** — voeg input_tokens/output_tokens toe aan ProviderResponse
1. **router/providers/anthropic.py + openai_provider.py** — token-info uit response
1. **brain.py** — token tracking na elke API call
1. **react_loop.py** — on_status callback
1. **gateway.py** — on_status propagatie
1. **skills/runner.py** — on_status bij skill-stappen
1. **repl.py** — alles integreren: spinner, markdown, multi-line, token-teller
1. **Tests**

## Samenvatting

Vier UX-verbeteringen:

1. **Spinner** — “Henk denkt…”, “web_search: weer Amsterdam”, “Stap 2/5: Bronnen zoeken”
1. **Markdown** — code highlighting, lijsten, kopjes in Henk’s antwoorden
1. **Multi-line** — Shift+Enter = nieuwe regel, Enter = versturen
1. **Token-teller** — “sessie: 2.8k tokens” rechts uitgelijnd na elk antwoord

**Referenties:**

- Rich Markdown: https://rich.readthedocs.io/en/latest/markdown.html
- Rich Status/Spinner: https://rich.readthedocs.io/en/latest/status.html
- prompt_toolkit key bindings: https://python-prompt-toolkit.readthedocs.io/en/latest/pages/advanced_topics/key_bindings.html