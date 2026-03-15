# Bouwinstructie: Token Tracking & Taakpaneel in Henk CLI

## Context

Dit is een uitbreiding op de bestaande Henk-architectuur (v0.1+). Alle communicatie loopt via de Gateway — dat principe blijft onveranderd. Deze instructie voegt twee visuele elementen toe aan de CLI-interface én de bijbehorende tracking-logica in de Gateway.

Lees `CLAUDE.md` en de bestaande code volledig voordat je begint. Pas niets aan buiten de scope van deze instructie.

---

## Wat er gebouwd moet worden

### 1. Gateway: Token- en tijdregistratie per run

De Gateway logt voortaan bij elke `tool.result` en `task.result` het tokengebruik en de verstreken tijd. Dit gaat in de bestaande Gateway-state, gekoppeld aan `run_id`.

**Vereisten:**

- Voeg aan de Gateway-state per `run_id` toe:
  - `started_at`: tijdstip van `task.submit` (ISO timestamp)
  - `tokens_input`: cumulatief aantal input-tokens van alle LLM-calls binnen deze run
  - `tokens_output`: cumulatief aantal output-tokens van alle LLM-calls binnen deze run
  - `task_summary`: tekstuele samenvatting van de taak (eerste 80 tekens van de gebruikersinput, of het `description`-veld uit de envelope)

- De Brain geeft na elke LLM-call het tokengebruik terug aan de Gateway via een nieuw berichttype `brain.token_usage` met:
  ```json
  {
    "run_id": "run_01J8K3...",
    "tokens_input": 412,
    "tokens_output": 138
  }
  ```

- De Gateway accumuleert dit per `run_id` in zijn state. De Brain berekent niets — alleen de Gateway telt op.

- Voeg aan de sessie-state (los van `run_id`) toe:
  - `session_tokens_input`: totaal over alle runs in deze sessie
  - `session_tokens_output`: totaal over alle runs in deze sessie

  Deze worden bijgewerkt elke keer dat een `brain.token_usage` bericht binnenkomt.

- Bij afsluiting van een run (`task.result` of `task.failed`) blijft de run zichtbaar in de state tot de sessie eindigt, zodat het taakpaneel historische runs kan tonen.

---

### 2. CLI-layout: drie zones

De CLI-weergave krijgt drie vaste zones, van boven naar beneden:

```
┌─────────────────────────────────────┐
│  CHATGESCHIEDENIS                   │  ← Scrollbaar, groeit naar beneden
│  ...                                │
│  ...                                │
├─────────────────────────────────────┤
│  TAAKPANEEL                         │  ← Vaste hoogte, max 5 regels
│  [taak 1] 0:42 | 1.240 tokens       │
│  [taak 2] 0:08 | 312 tokens         │
├─────────────────────────────────────┤
│  > invoerveld                       │  ← Altijd onderaan
├─────────────────────────────────────┤
│  Sessie: 4.821 tokens               │  ← Één vaste statusregel
└─────────────────────────────────────┘
```

Gebruik `rich` (al aanwezig in de stack) voor de layout. Gebruik `rich.layout.Layout` of een combinatie van `rich.live.Live` + `rich.panel.Panel` om de zones gescheiden te houden.

---

### 3. Taakpaneel (zone 2)

Het taakpaneel toont alle actieve én recent afgeronde taken van de huidige sessie.

**Per taak één regel:**
```
● Analyseer Q3-rapport voor Joost   0:42   1.240 tokens
✓ Zoek vluchten Amsterdam-Lissabon  1:03   3.891 tokens
```

- `●` = actief (groen), `✓` = afgerond (grijs), `✗` = mislukt (rood)
- Taaknaam: eerste 40 tekens van `task_summary`, afgekapt met `…` indien langer
- Tijd: oplopend voor actieve taken (live bijgewerkt), eindtijd voor afgeronde taken. Formaat: `m:ss`
- Tokens: som van `tokens_input + tokens_output` voor deze run

**Gedrag:**
- Paneel is zichtbaar zodra er minimaal één taak is in de sessie
- Maximum 5 regels tegelijk; oudste afgeronde taken vallen eraf als het paneel vol is
- Actieve taken staan altijd bovenaan
- Tijd wordt elke seconde live bijgewerkt via `rich.live`

**Data-ophaling:**
Het taakpaneel vraagt de data op via de Gateway — niet rechtstreeks uit de Brain of een gedeeld object. Gebruik een synchrone method-call op de Gateway (`gateway.get_task_state()`) die een lijst van run-objecten teruggeeft. Dit is een interne call binnen hetzelfde proces (v0.1 heeft geen IPC), maar de structuur moet later vervangbaar zijn door een Named Pipe-call.

---

### 4. Statusregel (zone 4)

Één vaste regel onderaan de terminal:

```
Sessie: 4.821 tokens  (2.310 in · 2.511 uit)
```

- Totaal aantal tokens van de huidige sessie (`session_tokens_input + session_tokens_output`)
- Tussen haakjes: uitsplitsing input en output
- Wordt bijgewerkt na elk `brain.token_usage` event
- Altijd zichtbaar, ook als er geen taken zijn

---

### 5. Nieuw berichttype: `brain.token_usage`

Voeg dit toe aan de envelope-definitie in `gateway.py` en aan de documentatie in `CLAUDE.md`:

```python
# Richting: Brain → Gateway
# Payload:
{
    "run_id": str,          # Gekoppeld aan actieve taak
    "tokens_input": int,    # Input-tokens van deze LLM-call
    "tokens_output": int    # Output-tokens van deze LLM-call
}
```

De Gateway valideert dit bericht op envelopeniveau (aanwezig `run_id`, positieve integers) en werkt daarna de state bij. Geen verdere logica in de Gateway — alleen accumuleren en opslaan.

---

## Wat je NIET aanpast

- De Brain-logica (ReAct-loop, tool-calling) — alleen de return-waarde na een LLM-call wordt uitgebreid met tokengebruik
- De security proxy, file_manager, code_runner
- De memory-laag
- Het berichtenprotocol voor alle bestaande berichttypen
- `henk.yaml` — geen nieuwe configuratieopties nodig voor deze feature

---

## Volgorde van implementatie

1. Voeg `brain.token_usage` toe aan de Gateway (state-schema + handler)
2. Laat de Brain dit bericht sturen na elke LLM-call (gebruik de `usage`-velden uit de Anthropic SDK response)
3. Implementeer `gateway.get_task_state()` als interne method
4. Bouw de drie CLI-zones met `rich.live`
5. Test: start een sessie, geef twee taken op, controleer of tokens en tijd correct oplopen

---

## Acceptatiecriteria

- [ ] Tokengebruik per taak is zichtbaar in het taakpaneel en klopt met wat de Anthropic API rapporteert
- [ ] Sessietotaal onderaan klopt met de som van alle runs
- [ ] Tijd loopt live op voor actieve taken
- [ ] Afgeronde taken blijven zichtbaar met eindtijd
- [ ] Bij een lege sessie (nog geen taken) is het taakpaneel niet zichtbaar; de statusregel toont `Sessie: 0 tokens`
- [ ] De Gateway is de enige bron van waarheid voor token- en tijddata — de CLI leest nergens anders