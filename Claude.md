# Henk v0.2 — Fixes

Los deze vijf problemen op in de aangegeven volgorde. Test na elke stap dat bestaande tests nog slagen.

## 1. OpenAI verwijderen uit Brain (brain.py + pyproject.toml)

Model-switching is gepland voor v0.4. In v0.2 ondersteunt Henk alleen Anthropic.

### brain.py
- Verwijder `import openai`
- Verwijder in `__init__` de OpenAI client initialisatie en de provider-check. Initialiseer alleen `self._anthropic = anthropic.Anthropic(api_key=config.api_key)`
- Verwijder `_call_openai()`, `_format_openai_input()`, `_extract_openai_output_text()`
- `think()` roept direct `_call_anthropic()` aan, geen if/else op provider
- `next_step()` verwijder de `if self._provider != "anthropic"` guard — het is altijd Anthropic

### pyproject.toml
Verwijder `"openai>=1.0.0"` uit dependencies.

### Tests
Verwijder of pas OpenAI-gerelateerde tests aan in test_brain.py.

## 2. Chat-loop via Gateway laten lopen (cli.py + gateway.py)

Het probleem: cli.py roept `react_loop.run()` direct aan en schrijft zelf transcripts. De Gateway wordt omzeild. De correcte flow is: cli → gateway → react_loop → brain/tools → terug.

### gateway.py
Pas `process()` aan zodat het de ReactLoop gebruikt. De Gateway moet de ReactLoop als parameter ontvangen (of in de constructor):

```python
class Gateway:
    def __init__(self, config: Config, brain: Brain, transcript: TranscriptWriter):
        # ... bestaande init ...
        self._react_loop = None  # Wordt gezet na constructie

    def set_react_loop(self, react_loop) -> None:
        """Koppel de ReAct-loop aan de Gateway."""
        self._react_loop = react_loop

    def process(self, user_message: str) -> str:
        """Verwerk een gebruikersbericht via de ReAct-loop."""
        active_switch = self.check_kill_switches()
        if active_switch:
            raise KillSwitchActive(active_switch)

        if not user_message or not user_message.strip():
            return ""

        self.reset_counters()
        self._transcript.write("user", user_message)
        response = self._react_loop.run(user_message)
        self._transcript.write("assistant", response)
        return response
```

### cli.py
Vereenvoudig de chat-loop. Alle transcript-schrijfwerk en kill switch checks gaan via `gateway.process()`:

```python
# Na het aanmaken van react_loop:
gateway.set_react_loop(react_loop)

# In de while-loop:
try:
    response = gateway.process(user_input)
    if response:
        console.print(f"[henk]{response}[/henk]\n")
except KillSwitchActive as error:
    console.print(f"[red]Henk is gestopt ({error.switch_type}).[/red]")
    break
```

Verwijder de handmatige `transcript.write()` calls uit cli.py — dat doet de Gateway nu.

## 3. Security proxy: gebruik requests library (security/proxy.py)

proxy.py gebruikt `urllib.request` maar `requests` staat al als dependency in pyproject.toml. Herschrijf proxy.py zodat het `requests` gebruikt. Dan kan de custom `SimpleResponse` wrapper weg.

```python
"""Security proxy voor uitgaand HTTP-verkeer."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import requests as http_requests


class SecurityProxy:
    """Filtert alle uitgaande netwerkverzoeken."""

    def __init__(self, allowed_domains: list[str], allowed_methods: list[str]):
        self.allowed_domains = {d.lower() for d in allowed_domains}
        self.allowed_methods = {m.upper() for m in allowed_methods}

    def _validate_query(self, url: str) -> None:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        suspicious = ["api_key", "token", "secret", "password"]
        for key in query:
            if any(marker in key.lower() for marker in suspicious):
                raise PermissionError("Verdachte querystring geblokkeerd.")

    def request(self, method: str, url: str, **kwargs) -> http_requests.Response:
        """Voer een HTTP request uit na validatie."""
        normalized_method = method.upper()
        if normalized_method not in self.allowed_methods:
            raise PermissionError(f"HTTP methode niet toegestaan: {normalized_method}")

        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if domain not in self.allowed_domains:
            raise PermissionError(f"Domein niet toegestaan: {domain}")

        self._validate_query(url)

        timeout = kwargs.get("timeout", 10)
        return http_requests.request(normalized_method, url, timeout=timeout)
```

Verwijder de `SimpleResponse` class volledig. WebSearchTool hoeft niet aangepast te worden — `requests.Response` heeft dezelfde `.text` en `.raise_for_status()` interface.

## 4. Versie bijwerken naar 0.2.0

### pyproject.toml
```toml
version = "0.2.0"
```

### henk/__init__.py
```python
__version__ = "0.2.0"
```

## 5. ReAct-loop: conversatiegeschiedenis meesturen (brain.py + react_loop.py)

Het probleem: `brain.next_step()` stuurt alleen het huidige bericht en observaties mee, niet de eerdere conversatiegeschiedenis. Henk heeft bij tool-gebruik dus geen context van het gesprek.

### brain.py
Herschrijf `next_step()` zodat het de volledige `self._history` meestuurt, gevolgd door het huidige bericht. Tool-resultaten worden toegevoegd als tool_result content blocks volgens de Anthropic API spec.

De Anthropic tool-use flow werkt zo:
1. Stuur messages met tools → model antwoordt met `tool_use` block
2. Stuur het `tool_use` block terug als assistant message, gevolgd door een user message met `tool_result`
3. Model antwoordt met tekst of een nieuwe `tool_use`

Pas `next_step()` aan zodat het deze flow correct implementeert. Het moet de volledige messages-lijst bijhouden inclusief tool_use en tool_result blocks.

De eenvoudigste aanpak: laat `next_step()` niet meer bestaan als aparte methode. Maak in plaats daarvan een `run_with_tools()` methode die de hele ReAct-cyclus afhandelt:

```python
def run_with_tools(self, user_message: str, tool_executor) -> str:
    """Voer een volledige tool-use cyclus uit.

    tool_executor is een callable(tool_name, params) -> ToolResult
    die door de ReactLoop wordt meegegeven.
    """
    self._history.append({"role": "user", "content": user_message})
    messages = self._history.copy()

    while True:
        response = self._anthropic.messages.create(
            model=self._config.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=self._anthropic_tools(),
            messages=messages,
        )

        # Check of het model een tool wil gebruiken
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            # Geen tool-call, model geeft een eindantwoord
            text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
            answer = text or "Ik heb nu geen antwoord."
            self._history.append({"role": "assistant", "content": answer})
            return answer

        # Model wil een tool gebruiken — voeg de hele response toe als assistant message
        messages.append({"role": "assistant", "content": response.content})

        # Voer elke tool_use uit en stuur resultaten terug
        tool_results = []
        for block in tool_use_blocks:
            result = tool_executor(block.name, dict(block.input))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result.data) if result.data else str(result.error.message) if result.error else "Geen resultaat",
            })

        messages.append({"role": "user", "content": tool_results})
        # Loop door voor de volgende stap
```

### react_loop.py
Pas `run()` aan zodat het `brain.run_with_tools()` gebruikt en de tool-executie als callback meegeeft:

```python
def run(self, user_message: str) -> str:
    self._gateway.reset_counters()

    def execute_tool(tool_name: str, params: dict) -> ToolResult:
        # Map file_manager_read/write/list naar file_manager
        mapped_name, mapped_params = self._map_tool(tool_name, params)

        decision = self._gateway.check_tool_call(mapped_name, mapped_params)
        if decision.decision != LoopDecision.ALLOW:
            # Return een fout-ToolResult zodat de Brain weet dat het niet mag
            return ToolResult(
                success=False,
                data=None,
                source_tag="",
                error=ToolError(ErrorType.CONTENT, f"Geweigerd: {decision.reason}", retry_useful=False)
            )

        run_id = self._gateway.log_tool_call(mapped_name, mapped_params)
        tool = self._tools.get(mapped_name)
        if not tool:
            return ToolResult(success=False, data=None, source_tag="", error=ToolError(ErrorType.CONTENT, f"Onbekende tool: {mapped_name}", retry_useful=False))

        if mapped_name == "file_manager" and mapped_params.get("action") == "write":
            mapped_params["run_id"] = run_id
        if mapped_name == "code_runner":
            mapped_params["run_id"] = run_id

        result = tool.execute(**mapped_params)
        self._gateway.register_tool_result(result)
        self._gateway.log_tool_result(mapped_name, result)
        return result

    return self._brain.run_with_tools(user_message, execute_tool)
```

De `_map_tool()` helper verplaatst de bestaande file_manager mapping-logica naar een aparte methode.

Let op: de Gateway's max_tool_calls limiet wordt nog steeds afgedwongen via `check_tool_call()`. De Brain loopt door totdat het model stopt of de Gateway weigert. Het model krijgt het weigeringsbericht als tool_result terug en zal dan een eindantwoord geven.
