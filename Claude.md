# Henk v0.4 — Bouwinstructie voor Claude Code

## Context

v0.3 (“Henk Onthoudt”) is gebouwd en werkend. Henk heeft CLI chat, tools, security, staged memory met dagelijkse review, vector search en sessie-samenvattingen.

Dit is v0.4: **“Henk Schakelt”**. Het doel is dat Henk flexibel kan wisselen tussen AI-providers en modellen, met een abstractielaag die de rest van het systeem ontziet.

Lees `CLAUDE.md` en `docs/henk-design-v14.docx` (hoofdstuk 15: Model Router) voor het volledige ontwerp.

## Wat v0.4 WEL doet

- Model Router: abstractielaag tussen Brain en providers
- Vijf providers: Anthropic, OpenAI, Ollama, LM Studio, DeepSeek
- Drie rollen: FAST, DEFAULT, HEAVY — elk gekoppeld aan een provider/model
- Automatisch fallback bij provider-falen
- Provider-switching via henk.yaml (geen code-aanpassing nodig)
- Tool-calling abstractie: vertaalt Henk’s tools naar het formaat van elke provider
- Configureerbare limieten via CLI (henk config)

## Wat v0.4 NIET doet

- Geen Tauri desktop app
- Geen limieten aanpassen via UI (dat was v0.4 in het originele ontwerp, maar er is geen app)
- Geen LiteLLM — we bouwen een eigen lichte abstractielaag die precies past bij Henk’s architectuur

## Nieuwe bestanden

```
henk/
├── henk/
│   ├── router/                     # Model Router subsysteem
│   │   ├── __init__.py
│   │   ├── router.py               # ModelRouter: rolbepaling + provider-selectie
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # BaseProvider interface
│   │   │   ├── anthropic.py        # Anthropic provider
│   │   │   ├── openai_provider.py  # OpenAI provider (niet openai.py — conflicteert met package)
│   │   │   ├── ollama.py           # Ollama provider
│   │   │   ├── lmstudio.py         # LM Studio provider
│   │   │   └── deepseek.py         # DeepSeek provider
│   │   └── tool_adapter.py         # Vertaalt tool-definities per provider
├── tests/
│   ├── test_router.py
│   ├── test_providers.py
│   └── test_tool_adapter.py
```

## Gewijzigde bestanden

```
henk/
├── henk/
│   ├── brain.py                    # Gebruikt ModelRouter i.p.v. directe API calls
│   ├── config.py                   # Rolconfiguratie, provider settings
│   └── cli.py                      # henk config command
├── henk.yaml.default               # Rollen en providers configuratie
├── pyproject.toml                  # Nieuwe dependencies
```

## Kernidee: Brain vraagt een rol, Router geeft een model

Het designdocument zegt het helder:

> Brain: “Ik heb een model nodig voor: code” → Router: kijkt in config → geeft “claude-sonnet-4-6” terug → Brain: maakt de call. Morgen wil je Opus voor code? Eén regel in henk.yaml.

De Brain weet niet welk model of welke provider hij gebruikt. Hij vraagt de Router om een bepaalde rol (FAST, DEFAULT, HEAVY), en de Router geeft een provider-instantie terug die een uniform interface heeft.

## BaseProvider interface (router/providers/base.py)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderResponse:
    """Uniform antwoord van elke provider."""
    text: str | None                    # Tekstantwoord (None als tool_use)
    tool_calls: list[ToolCall] | None   # Tool-aanroepen (None als tekst)
    raw: Any = None                     # Originele response voor debugging


@dataclass
class ToolCall:
    """Een tool-aanroep van het model."""
    id: str                             # Uniek ID voor tool_result terugkoppeling
    name: str                           # Tool naam
    parameters: dict[str, Any]          # Tool parameters


class BaseProvider(ABC):
    """Interface voor alle model providers."""

    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        """Stuur een chat-verzoek naar het model.

        Args:
            messages: Conversatiegeschiedenis in Henk's interne formaat
            system: System prompt
            tools: Tool-definities in Henk's interne formaat (None = geen tools)
            max_tokens: Maximum tokens in antwoord

        Returns:
            ProviderResponse met tekst of tool-calls
        """

    @abstractmethod
    def supports_tools(self) -> bool:
        """Geeft aan of deze provider tool-calling ondersteunt."""

    def format_tool_result(self, tool_call_id: str, result: str) -> dict[str, Any]:
        """Formatteer een tool-resultaat voor terugkoppeling naar het model.

        Default implementatie — providers kunnen dit overriden.
        """
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}]
        }
```

## Provider implementaties

### anthropic.py

```python
class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def chat(self, messages, system, tools=None, max_tokens=1024) -> ProviderResponse:
        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.messages.create(**kwargs)

        tool_calls = []
        text_parts = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, parameters=dict(block.input)))
            elif hasattr(block, "text"):
                text_parts.append(block.text)

        if tool_calls:
            return ProviderResponse(text=None, tool_calls=tool_calls, raw=response)
        return ProviderResponse(text="".join(text_parts).strip(), tool_calls=None, raw=response)

    def supports_tools(self) -> bool:
        return True

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Vertaal Henk's tool-formaat naar Anthropic formaat."""
        # Anthropic gebruikt name + description + input_schema
        # Henk's interne formaat is identiek — geen conversie nodig
        return tools

    def format_tool_result(self, tool_call_id: str, result: str) -> dict:
        """Anthropic-specifiek tool_result formaat."""
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}]
        }
```

Belangrijk: bij Anthropic moet de hele `response.content` (inclusief tool_use blocks) als assistant message worden teruggestuurd. Sla `response.content` op in `ProviderResponse.raw` zodat de Brain dit kan gebruiken.

### openai_provider.py

```python
class OpenAIProvider(BaseProvider):
    """OpenAI GPT provider."""

    name = "openai"

    def __init__(self, api_key: str, model: str):
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def chat(self, messages, system, tools=None, max_tokens=1024) -> ProviderResponse:
        openai_messages = [{"role": "system", "content": system}] + messages

        kwargs = {"model": self._model, "max_tokens": max_tokens, "messages": openai_messages}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    parameters=json.loads(tc.function.arguments),
                )
                for tc in choice.message.tool_calls
            ]
            return ProviderResponse(text=None, tool_calls=tool_calls, raw=response)

        return ProviderResponse(text=choice.message.content, tool_calls=None, raw=response)

    def supports_tools(self) -> bool:
        return True

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Vertaal Henk's tool-formaat naar OpenAI function-calling formaat."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def format_tool_result(self, tool_call_id: str, result: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result}
```

### ollama.py

Ollama is OpenAI-compatible. Gebruik dezelfde client met een aangepaste base_url:

```python
class OllamaProvider(BaseProvider):
    """Ollama lokale modellen via OpenAI-compatible API."""

    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1"):
        self._client = openai.OpenAI(api_key="ollama", base_url=base_url)
        self._model = model
        # Zelfde logica als OpenAIProvider
```

Ollama ondersteunt tool-calling voor sommige modellen (Llama 3, Qwen). `supports_tools()` kan True retourneren — als het model het niet ondersteunt faalt de call en grijpt de fallback in.

### lmstudio.py

LM Studio is ook OpenAI-compatible:

```python
class LMStudioProvider(BaseProvider):
    """LM Studio lokale modellen via OpenAI-compatible API."""

    name = "lmstudio"

    def __init__(self, model: str, base_url: str = "http://localhost:1234/v1"):
        self._client = openai.OpenAI(api_key="lmstudio", base_url=base_url)
        self._model = model
        # Zelfde logica als OpenAIProvider
```

### deepseek.py

DeepSeek gebruikt de OpenAI-compatible API met hun eigen endpoint:

```python
class DeepSeekProvider(BaseProvider):
    """DeepSeek provider via OpenAI-compatible API."""

    name = "deepseek"

    def __init__(self, api_key: str, model: str):
        self._client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self._model = model
        # Zelfde logica als OpenAIProvider
```

### Opmerking: code-deduplicatie

Ollama, LM Studio en DeepSeek zijn allemaal OpenAI-compatible. Maak een `OpenAICompatibleProvider` base class die de gemeenschappelijke logica bevat, en laat deze drie plus `OpenAIProvider` daarvan erven. Alleen de constructor verschilt (base_url, api_key handling).

## ModelRouter (router/router.py)

```python
from enum import Enum


class ModelRole(str, Enum):
    """De drie rollen voor model-selectie."""
    FAST = "fast"           # Gesprek, routing, classificatie, kleine taken
    DEFAULT = "default"     # 80% van het werk
    HEAVY = "heavy"         # Code, complexe analyse, skill-uitvoering


class ModelRouter:
    """Selecteert de juiste provider op basis van rol en configuratie."""

    def __init__(self, config: Config):
        self._config = config
        self._providers: dict[str, BaseProvider] = {}
        self._role_mapping: dict[ModelRole, list[str]] = {}  # Rol → [provider:model, fallback, ...]
        self._initialize()

    def _initialize(self) -> None:
        """Initialiseer providers en rol-mapping uit config."""
        # Lees provider-configuratie uit henk.yaml
        # Maak provider-instanties aan
        # Koppel rollen aan providers met fallback-keten

    def get_provider(self, role: ModelRole = ModelRole.DEFAULT) -> BaseProvider:
        """Geef de provider voor een bepaalde rol.

        Probeert de primaire provider. Bij falen: probeer fallbacks in volgorde.
        """
        providers_for_role = self._role_mapping.get(role, [])
        for provider_key in providers_for_role:
            provider = self._providers.get(provider_key)
            if provider and self._is_available(provider):
                return provider
        raise RuntimeError(f"Geen beschikbare provider voor rol: {role.value}")

    def _is_available(self, provider: BaseProvider) -> bool:
        """Check of een provider bereikbaar is.

        Voor API providers: check of de API key aanwezig is.
        Voor lokale providers: check of de server draait (simpele health check).
        """

    def list_providers(self) -> dict[str, str]:
        """Lijst alle geconfigureerde providers met hun status."""
        # Voor henk status output
```

## ToolAdapter (router/tool_adapter.py)

Henk’s tools zijn gedefinieerd in een intern formaat. De ToolAdapter vertaalt deze naar het formaat dat elke provider verwacht. Dit zit in de BaseProvider’s `_convert_tools()` methode — geen apart bestand nodig.

Verwijder `tool_adapter.py` uit de structuur. De vertaling zit in elke provider.

## Fallback mechanisme

Het fallback-mechanisme werkt op twee niveaus:

### 1. Provider-niveau fallback

Als een provider faalt (API error, timeout, server niet bereikbaar), probeert de Router de volgende provider in de fallback-keten voor die rol:

```yaml
roles:
  fast:
    primary: anthropic/claude-haiku-4-5
    fallback:
      - ollama/qwen2.5:3b
  default:
    primary: anthropic/claude-sonnet-4-6
    fallback:
      - openai/gpt-4o
      - deepseek/deepseek-chat
  heavy:
    primary: anthropic/claude-opus-4-6
    fallback:
      - anthropic/claude-sonnet-4-6
```

### 2. Tool-capability fallback

Als een provider geen tool-calling ondersteunt, heeft de Brain twee opties:

- Gebruik de provider zonder tools (voor simpele gesprekken)
- Val terug naar een provider die wél tools ondersteunt (voor taken die tools nodig hebben)

De Brain bepaalt dit op basis van of de huidige stap tools nodig heeft.

## Brain wijzigingen (brain.py)

De Brain wordt drastisch vereenvoudigd. Alle provider-specifieke code verdwijnt. In plaats daarvan:

```python
class Brain:
    def __init__(self, config: Config, router: ModelRouter, memory_retrieval=None):
        self._config = config
        self._router = router
        self._memory_retrieval = memory_retrieval
        self._history: list[dict[str, Any]] = []

    def think(self, user_message: str) -> str:
        """Eenvoudige chat zonder tools — gebruikt FAST of DEFAULT rol."""
        provider = self._router.get_provider(ModelRole.DEFAULT)
        system = self._build_system_prompt(user_message)

        self._history.append({"role": "user", "content": user_message})
        response = provider.chat(messages=self._history, system=system)
        self._history.append({"role": "assistant", "content": response.text})
        return response.text

    def run_with_tools(self, user_message: str, tool_executor, tools: list[dict]) -> str:
        """ReAct-cyclus met tool-calling."""
        provider = self._router.get_provider(ModelRole.DEFAULT)

        if not provider.supports_tools():
            # Fallback: probeer een provider die tools ondersteunt
            provider = self._router.get_provider(ModelRole.HEAVY)

        system = self._build_system_prompt(user_message)
        self._history.append({"role": "user", "content": user_message})
        messages = self._history.copy()

        while True:
            response = provider.chat(messages=messages, system=system, tools=tools)

            if not response.tool_calls:
                answer = response.text or "Ik heb nu geen antwoord."
                self._history.append({"role": "assistant", "content": answer})
                return answer

            # Voeg assistant response toe (met tool_use blocks)
            # Anthropic heeft de raw content nodig, OpenAI het message object
            messages.append(self._format_assistant_tool_message(provider, response))

            # Voer tools uit en stuur resultaten terug
            for tc in response.tool_calls:
                result = tool_executor(tc.name, tc.parameters)
                result_text = str(result.data) if result.data else str(result.error.message) if result.error else "Geen resultaat"
                messages.append(provider.format_tool_result(tc.id, result_text))

    def greet(self) -> str:
        """Begroeting via FAST model."""
        provider = self._router.get_provider(ModelRole.FAST)
        response = provider.chat(
            messages=[{"role": "user", "content": GREETING_INSTRUCTION}],
            system=SYSTEM_PROMPT,
        )
        return response.text

    def summarize_session(self) -> str | None:
        """Sessie-samenvatting via FAST model."""
        if not self._history:
            return None
        provider = self._router.get_provider(ModelRole.FAST)
        # ...
```

### Belangrijk: provider-specifieke message-formatting

Het lastige punt is dat Anthropic en OpenAI verschillende formaten verwachten voor tool-use berichten:

**Anthropic**: assistant message bevat `response.content` (lijst van text + tool_use blocks). Tool results gaan als user message met `tool_result` content blocks.

**OpenAI**: assistant message bevat `message` object met `tool_calls`. Tool results gaan als aparte `tool` role messages.

De `format_assistant_tool_message()` methode op de Brain moet dit per provider afhandelen. De eenvoudigste aanpak: sla de ruwe provider-response op en laat de provider zelf bepalen hoe de assistant message eruitziet.

Voeg een `format_assistant_message(response: ProviderResponse) -> dict` methode toe aan BaseProvider:

```python
class BaseProvider(ABC):
    @abstractmethod
    def format_assistant_message(self, response: ProviderResponse) -> dict[str, Any]:
        """Formatteer de assistant response als message voor de conversatie-history."""
```

Anthropic retourneert `{"role": "assistant", "content": response.raw.content}`.
OpenAI retourneert `{"role": "assistant", "content": response.raw.choices[0].message}`.

## Config wijzigingen

### henk.yaml.default

Vervang de huidige `provider:` sectie met:

```yaml
providers:
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
  openai:
    api_key_env: OPENAI_API_KEY
  ollama:
    base_url: http://localhost:11434/v1
  lmstudio:
    base_url: http://localhost:1234/v1
  deepseek:
    api_key_env: DEEPSEEK_API_KEY

roles:
  fast:
    primary: anthropic/claude-haiku-4-5
    fallback:
      - ollama/qwen2.5:3b
  default:
    primary: anthropic/claude-sonnet-4-6
    fallback:
      - openai/gpt-4o
      - deepseek/deepseek-chat
  heavy:
    primary: anthropic/claude-opus-4-6
    fallback:
      - anthropic/claude-sonnet-4-6
```

Formaat: `provider/model`. De Router splitst dit op `/` om de provider-instantie en het model te bepalen.

### config.py

Voeg toe:

```python
@property
def providers_config(self) -> dict:
    return self._data.get("providers", {})

@property
def roles_config(self) -> dict:
    return self._data.get("roles", {})
```

Verwijder de oude `provider` en `model` properties. Vervang ze door de Router.

### .env.example

```
# Henk API keys — vul minimaal één provider in
ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# DEEPSEEK_API_KEY=
# Ollama en LM Studio hebben geen API key nodig
```

## CLI wijzigingen

### Nieuw command: `henk config`

Toont de huidige configuratie en laat limieten aanpassen:

```python
@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Toon huidige configuratie"),
    set_limit: str = typer.Option(None, "--set", help="Stel limiet in, bijv. 'max_tool_calls=8'"),
):
    """Bekijk of wijzig Henk's configuratie."""
    data_dir = _get_data_dir()
    cfg = load_config(data_dir)

    if set_limit:
        key, _, value = set_limit.partition("=")
        # Schrijf naar henk.yaml
        # Valideer dat de key bestaat en de value geldig is
        ...
        console.print(f"{key} ingesteld op {value}")
        return

    if show or not set_limit:
        # Toon rollen met actieve providers
        router = ModelRouter(cfg)
        console.print("[bold]Rollen:[/bold]")
        for role in ModelRole:
            try:
                provider = router.get_provider(role)
                console.print(f"  {role.value}: {provider.name}/{provider._model}")
            except RuntimeError:
                console.print(f"  {role.value}: [red]geen provider beschikbaar[/red]")

        console.print(f"\n[bold]Limieten:[/bold]")
        console.print(f"  max_tool_calls: {cfg.max_tool_calls}")
        console.print(f"  max_retries_content: {cfg.max_retries_content}")
        console.print(f"  max_retries_technical: {cfg.max_retries_technical}")
```

### henk status uitbreiden

Voeg provider-informatie toe aan `henk status`:

```
Gateway:     actief (embedded in CLI)
Kill switch: normaal
Provider:    anthropic/claude-sonnet-4-6 (DEFAULT)
Fallback:    openai/gpt-4o, deepseek/deepseek-chat
```

## Dependencies

### pyproject.toml

```toml
version = "0.4.0"

dependencies = [
    "typer>=0.9.0",
    "anthropic>=0.40.0",
    "openai>=1.0.0",        # Terug — nu voor OpenAI, Ollama, LM Studio, DeepSeek
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "rich>=13.0.0",
    "requests>=2.31.0",
    "chromadb>=0.4.0",
    "python-frontmatter>=1.0.0",
]
```

### henk/**init**.py

```python
__version__ = "0.4.0"
```

## Tests

### test_router.py

- Router selecteert juiste provider voor elke rol
- Fallback werkt als primaire provider niet beschikbaar is
- RuntimeError als geen enkele provider beschikbaar is
- Provider-status check werkt (API key aanwezig, server bereikbaar)

### test_providers.py

- Anthropic provider formatteert tool-calls correct
- OpenAI provider vertaalt tools naar function-calling formaat
- OpenAI-compatible providers (Ollama, LM Studio, DeepSeek) gebruiken juiste base_url
- ProviderResponse is uniform ongeacht de provider
- format_tool_result en format_assistant_message zijn provider-specifiek correct

### test_tool_adapter.py (verwijderd — logica zit in providers)

Voeg in plaats daarvan tests toe aan test_providers.py voor tool-conversie per provider.

## Volgorde van bouwen

1. **router/providers/base.py** — BaseProvider interface + ProviderResponse + ToolCall
1. **router/providers/anthropic.py** — Anthropic provider (verplaats bestaande logica uit brain.py)
1. **router/providers/openai_provider.py** — OpenAI provider + OpenAICompatibleProvider base
1. **router/providers/ollama.py** — erft van OpenAICompatible
1. **router/providers/lmstudio.py** — erft van OpenAICompatible
1. **router/providers/deepseek.py** — erft van OpenAICompatible
1. **router/router.py** — ModelRouter met rol-mapping en fallback
1. **brain.py herschrijven** — vervang directe API calls door Router
1. **config.py aanpassen** — nieuwe provider/rollen config
1. **cli.py aanpassen** — henk config, henk status uitbreiden
1. **henk.yaml.default** — rollen-configuratie
1. **Tests**

## Samenvatting

v0.4 voegt toe:

1. ModelRouter als abstractielaag — Brain vraagt een rol, Router geeft een provider
1. Vijf providers: Anthropic, OpenAI, Ollama, LM Studio, DeepSeek
1. Drie rollen: FAST, DEFAULT, HEAVY
1. Automatisch fallback bij provider-falen
1. `henk config` voor configuratiebeheer via CLI
1. OpenAI-compatible base class voor Ollama, LM Studio en DeepSeek
1. Uniform ProviderResponse formaat ongeacht de provider

**Kernregel: de Brain weet niet welk model hij gebruikt. Hij vraagt een rol, de Router levert.**

**Referenties:**

- `CLAUDE.md` — architectuurprincipes
- `docs/henk-design-v14.docx` — hoofdstuk 15 (Model Router)
- Let op: Ollama heeft een bekende bug met Qwen 3.5 tool-calling. vLLM of llama-server zijn alternatieven.