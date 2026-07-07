# Plan de Implementación + Prompt para Antigravity (Claude Opus 4.6 Thinking)
**Basado en:** `implementation_plan.md` (versión auditada, jul. 2026)
**Objetivo de este documento:** convertir el plan de arquitectura/investigación en (1) un plan de ejecución por fases con entregables concretos, y (2) un prompt único, autocontenido, listo para pegar en Antigravity para que el agente construya el repositorio completo.

---

## Parte 1 — Plan de Implementación

### Fase 0 — Andamiaje del repositorio
**Entregable:** estructura de carpetas + entorno reproducible, sin lógica de negocio todavía.

```
ecosistema-multiagente/
├── .env.example
├── requirements.txt
├── README.md
├── config/
│   └── model_router.yaml
├── core/
│   ├── clients.py          # inicialización Groq/OpenRouter/Cohere
│   ├── quotas.py           # guardianes de cuota persistentes (no solo en memoria)
│   └── router.py           # call_agent() con fallback
├── schemas/
│   ├── vibe_coding.py       # TechnicalSpec, CodeArtifact, DebugReport
│   └── deep_research.py     # SafetyClassification, CondensedTrends, GroundedReport
├── agents/
│   ├── vibe_coding/
│   │   ├── architect.py
│   │   ├── coder.py
│   │   └── debugger.py
│   └── deep_research/
│       ├── safety_filter.py
│       ├── context_compressor.py
│       ├── web_search.py
│       ├── grounding.py
│       └── synthesizer.py
├── graphs/
│   ├── vibe_coding_graph.py     # LangGraph + rollback Git
│   └── deep_research_graph.py   # LangGraph + checkpoints
├── cli.py
└── tests/
    ├── test_router_fallback.py
    ├── test_schemas.py
    └── test_graphs_mocked.py
```

**Dependencias base:** `pydantic-ai`, `langgraph`, `langgraph-checkpoint-sqlite`, `cohere`, `openai`, `python-dotenv`, `gitpython`, `pytest`, `respx` (mocking HTTP para tests sin gastar cuota real).

---

### Fase 1 — Capa de clientes y cuotas (`core/`)
- `clients.py`: los tres clientes tal como en el script auditado (Groq y OpenRouter vía SDK de OpenAI con `base_url` propio; Cohere vía `cohere.ClientV2`).
- `quotas.py`: **mejora sobre el script original** — los contadores de uso deben persistir en disco (SQLite o JSON con fecha), no solo en un diccionario en memoria, porque el proceso puede reiniciarse varias veces al día. Reinicio automático a medianoche.
  - `COHERE_DAILY_LIMIT = 25–30`
  - `GROQ_DAILY_LIMIT_PER_MODEL = 800` (por modelo, no compartido)
  - `OPENROUTER_DAILY_LIMIT = 45` (o 900 si hay top-up de $10 acreditado)
- `router.py`: `call_agent(provider, model, messages, reasoning_effort=None)` con la cascada de fallback exacta del plan auditado (Cohere→Hy3, OpenRouter→Groq gpt-oss-120b, Groq→OpenRouter), reintentos con backoff exponencial, y logging explícito de cada conmutación.

**Criterio de aceptación:** simular agotamiento de cuota de cada proveedor con un test y verificar que el fallback correcto se dispara sin llamadas reales a la API.

---

### Fase 2 — Esquemas Pydantic (`schemas/`)
Definir tipado estricto para cada frontera entre agentes, evitando que un agente reciba una salida mal formada del anterior:
- `TechnicalSpec(architecture: str, test_cases: list[str], files_to_create: list[str])`
- `CodeArtifact(files: dict[str, str], summary: str)`
- `DebugReport(passed: bool, issues: list[str], suggested_fix: str | None)`
- `SafetyClassification(is_safe: bool, reasons: list[str])`
- `CondensedTrends(technologies: list[str], rationale: str)`
- `GroundedReport(content: str, sources: list[str])`

**Criterio de aceptación:** cada esquema tiene al menos un test de validación positiva y uno de rechazo (dato malformado).

---

### Fase 3 — Agentes PydanticAI
Cada archivo en `agents/` envuelve una llamada de `core/router.py` en un agente PydanticAI con `result_type` fijado al esquema correspondiente de la Fase 2. Esto reemplaza las funciones sueltas del script original por unidades validadas y testeables de forma aislada.

Puntos específicos ya corregidos en el plan auditado que deben respetarse aquí:
- El Arquitecto usa `command-a-plus-05-2026`, **no** `command-a-reasoning-08-2025` (bloqueado en producción real).
- La búsqueda web real se hace con `groq/compound-mini`, **no** con `connectors` de Cohere v1 (no existe en `ClientV2`).
- El grounding/citas usa el parámetro `documents` de Cohere v2, pasando ahí los resultados de `compound-mini`.

---

### Fase 4 — Grafo LangGraph, Sistema A (Vibe Coding)
`graphs/vibe_coding_graph.py`:
- Nodos: Arquitecto → Programador → Debugger.
- Arista condicional: si `DebugReport.passed`, hacer `git commit` (checkpoint) vía GitPython y terminar con éxito.
- Si falla: reinyectar `suggested_fix` al Programador, máximo 3 ciclos.
- Si se agotan los ciclos: `git reset --hard` al último checkpoint estable (rollback real, no solo un mensaje de log).
- Fallback de modelo: si `tencent/hy3` no responde (por rate limit o por venta el 21-jul-2026), conmutar automáticamente a `openai/gpt-oss-120b` en Groq **sin intervención manual**.

**Criterio de aceptación:** un test con Hy3 mockeado para devolver 402 (crédito agotado) debe demostrar que el grafo cambia de modelo y sigue ejecutando sin caerse.

---

### Fase 5 — Grafo LangGraph, Sistema B (Deep Research)
`graphs/deep_research_graph.py`:
- Nodos: Filtro de Seguridad → Compresión de Contexto (Hy3) → Búsqueda Web Real (compound-mini) → Grounding/Citas (Command A+) → Síntesis Final (Command R+).
- Checkpointer persistente (`SqliteSaver` de LangGraph): si la ejecución falla a mitad de camino por un 429 de Cohere, debe poder **reanudarse desde el último nodo exitoso**, sin repetir etapas ya completadas (esto es explícitamente el motivo por el que el plan auditado pide checkpoints en este sistema).

**Criterio de aceptación:** simular un fallo forzado después del tercer nodo y verificar que una segunda ejecución retoma desde ahí, no desde el principio.

---

### Fase 6 — CLI y observabilidad
- `cli.py` con dos comandos: `run vibe-coding "<idea>"` y `run deep-research "<tema>"`.
- Logging estructurado de cada llamada: proveedor, modelo, éxito/fallback, cuota restante.
- **Vigilancia de fecha dura:** el router debe leer `free_until: "2026-07-21"` de `model_router.yaml` para Hy3 y emitir una advertencia visible (no silenciosa) cuando la fecha actual esté a ≤3 días de esa fecha, recordando validar el fallback antes de que ocurra el primer 402 real.

---

### Fase 7 — Tests y CI ligera
- Todos los tests contra APIs externas deben usar mocks (`respx` para las llamadas HTTP de OpenAI-compatible, mock del cliente `cohere.ClientV2`) — **cero llamadas reales de cuota gastadas en CI**.
- Cobertura mínima: fallback de router (Fase 1), validación de esquemas (Fase 2), rollback de Git (Fase 4), reanudación de checkpoint (Fase 5).

---

### Definition of Done
- [ ] Repo completo y ejecutable con `pip install -r requirements.txt` + `.env` configurado.
- [ ] Los dos pipelines corren de punta a punta contra APIs reales al menos una vez (prueba manual con cuota real, no mock).
- [ ] Ningún código usa `connectors` de Cohere v1.
- [ ] El rollback de Git y la reanudación de checkpoint están probados con fallos forzados, no solo con el camino feliz.
- [ ] El límite del 21 de julio de 2026 para Hy3 está codificado en configuración, no hardcodeado dentro de la lógica del grafo.

---
