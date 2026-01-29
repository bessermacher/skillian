# Skillian Architecture & Algorithms

This document explains how Skillian works through visualized algorithms and detailed explanations.

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Concept: Skill = Tools + Knowledge + Prompt](#core-concept)
3. [Request Flow Algorithm](#request-flow-algorithm)
4. [Agent Orchestration Loop](#agent-orchestration-loop)
5. [Tool Execution Algorithm](#tool-execution-algorithm)
6. [Skill Registry & Routing](#skill-registry--routing)
7. [LLM Provider Abstraction](#llm-provider-abstraction)
8. [Connector Pattern](#connector-pattern)
9. [Component Interactions](#component-interactions)

---

## System Overview

Skillian is an AI-powered assistant for diagnosing SAP BW data issues. The system uses a modular skill-based architecture where each domain (Financial, Sales, Inventory) has specialized tools and knowledge.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              SKILLIAN                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐   │
│  │   Client    │────▶│  FastAPI    │────▶│        Agent            │   │
│  │  (Request)  │     │  Endpoint   │     │   (Orchestration)       │   │
│  └─────────────┘     └─────────────┘     └───────────┬─────────────┘   │
│                                                       │                  │
│                            ┌──────────────────────────┴───────────┐     │
│                            │                                      │     │
│                            ▼                                      ▼     │
│                   ┌─────────────────┐                  ┌──────────────┐ │
│                   │  Skill Registry │                  │ LLM Provider │ │
│                   │  ┌───────────┐  │                  │ (Ollama/     │ │
│                   │  │ Financial │  │                  │  Claude/     │ │
│                   │  │   Skill   │  │                  │  OpenAI)     │ │
│                   │  ├───────────┤  │                  └──────────────┘ │
│                   │  │   Sales   │  │                                   │
│                   │  │   Skill   │  │                                   │
│                   │  ├───────────┤  │                                   │
│                   │  │ Inventory │  │                                   │
│                   │  │   Skill   │  │                                   │
│                   │  └───────────┘  │                                   │
│                   └────────┬────────┘                                   │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │   Connectors    │                                   │
│                   │ (Mock/HANA/RFC) │                                   │
│                   └─────────────────┘                                   │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │    SAP BW       │                                   │
│                   │    Data         │                                   │
│                   └─────────────────┘                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Concept

The fundamental building block of Skillian is the **Skill**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           SKILL                                      │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │     TOOLS       │  │    KNOWLEDGE    │  │   SYSTEM PROMPT     │  │
│  │                 │  │     (RAG)       │  │                     │  │
│  │ • get_cost_     │  │                 │  │ "You are a          │  │
│  │   center        │  │ • Markdown      │  │  financial analyst  │  │
│  │ • list_cost_    │  │   documents     │  │  expert in SAP BW   │  │
│  │   centers       │  │ • Domain        │  │  cost center        │  │
│  │ • compare_      │  │   knowledge     │  │  analysis..."       │  │
│  │   budget        │  │ • Best          │  │                     │  │
│  │                 │  │   practices     │  │                     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
│                                                                      │
│         Skill = Tools + Knowledge + System Prompt                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Tool Structure

Each tool follows a strict pattern with Pydantic validation:

```
┌─────────────────────────────────────────────────┐
│                    TOOL                          │
├─────────────────────────────────────────────────┤
│  name: "get_cost_center"                        │
│  description: "Retrieve cost center details"    │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │         INPUT SCHEMA (Pydantic)          │   │
│  │  cost_center_id: str (required)          │   │
│  │  fiscal_year: int = 2024 (optional)      │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │         FUNCTION                         │   │
│  │  async def get_cost_center(             │   │
│  │      connector, cost_center_id, ...     │   │
│  │  ) -> dict                               │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Request Flow Algorithm

When a user sends a message, it flows through the system as follows:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        REQUEST FLOW ALGORITHM                             │
└──────────────────────────────────────────────────────────────────────────┘

                    User: "What is the budget for CC-1001?"
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: API RECEIVES REQUEST                                             │
│                                                                          │
│   POST /chat                                                             │
│   Body: { "message": "What is the budget for CC-1001?" }                │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: DEPENDENCY INJECTION                                             │
│                                                                          │
│   ┌───────────────┐     ┌───────────────┐     ┌───────────────┐        │
│   │  get_settings │────▶│ get_llm_      │────▶│  get_skill_   │        │
│   │   (cached)    │     │   provider    │     │   registry    │        │
│   └───────────────┘     │   (cached)    │     │   (cached)    │        │
│                         └───────────────┘     └───────┬───────┘        │
│                                                       │                 │
│                                                       ▼                 │
│                                               ┌───────────────┐        │
│                                               │   get_agent   │        │
│                                               │ (fresh/request)│        │
│                                               └───────────────┘        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: AGENT PROCESSING (See Agent Loop below)                          │
│                                                                          │
│   agent.process("What is the budget for CC-1001?")                      │
│                                                                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: RETURN RESPONSE                                                  │
│                                                                          │
│   {                                                                      │
│     "response": "Cost center CC-1001 has a budget of $150,000...",      │
│     "tool_calls": [                                                      │
│       { "tool": "get_cost_center", "args": {...}, "result": {...} }     │
│     ],                                                                   │
│     "finished": true                                                     │
│   }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Orchestration Loop

The agent implements a **ReAct-style loop** (Reasoning + Acting):

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATION ALGORITHM                          │
└──────────────────────────────────────────────────────────────────────────┘

                          ┌───────────────────┐
                          │  User Message     │
                          │  Received         │
                          └─────────┬─────────┘
                                    │
                                    ▼
                          ┌───────────────────┐
                          │ Add to            │
                          │ Conversation      │
                          └─────────┬─────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           ▼                           │
        │                 ┌───────────────────┐                 │
        │                 │ Convert to        │                 │
        │    ITERATION    │ LangChain         │                 │
        │      LOOP       │ Messages          │                 │
        │   (max = 10)    └─────────┬─────────┘                 │
        │                           │                           │
        │                           ▼                           │
        │                 ┌───────────────────┐                 │
        │                 │ Call LLM          │                 │
        │                 │ model.ainvoke()   │                 │
        │                 └─────────┬─────────┘                 │
        │                           │                           │
        │                           ▼                           │
        │                 ┌───────────────────┐                 │
        │                 │ Has Tool Calls?   │                 │
        │                 └─────────┬─────────┘                 │
        │                           │                           │
        │              ┌────────────┴────────────┐              │
        │              │                         │              │
        │            YES                        NO              │
        │              │                         │              │
        │              ▼                         ▼              │
        │    ┌─────────────────┐      ┌─────────────────┐      │
        │    │ Execute Each    │      │ Add Final       │      │
        │    │ Tool            │      │ Response        │      │
        │    └────────┬────────┘      └────────┬────────┘      │
        │             │                        │                │
        │             ▼                        │                │
        │    ┌─────────────────┐               │                │
        │    │ Add Tool        │               │                │
        │    │ Results to      │               │                │
        │    │ Conversation    │               │                │
        │    └────────┬────────┘               │                │
        │             │                        │                │
        │             │ (loop back)            │                │
        └─────────────┘                        │
                                               ▼
                                    ┌───────────────────┐
                                    │ Return            │
                                    │ AgentResponse     │
                                    └───────────────────┘

```

### Message Flow Example

```
Iteration 1:
┌────────────────────────────────────────────────────────────────────────┐
│ MESSAGES TO LLM                                                         │
├────────────────────────────────────────────────────────────────────────┤
│ [SYSTEM] You are Skillian, an AI assistant specialized in SAP BW...    │
│ [USER] What is the budget for CC-1001?                                 │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LLM RESPONSE                                                            │
├────────────────────────────────────────────────────────────────────────┤
│ tool_calls: [                                                           │
│   { name: "get_cost_center", args: { cost_center_id: "CC-1001" } }     │
│ ]                                                                       │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          Execute get_cost_center
                                    │
                                    ▼
Iteration 2:
┌────────────────────────────────────────────────────────────────────────┐
│ MESSAGES TO LLM                                                         │
├────────────────────────────────────────────────────────────────────────┤
│ [SYSTEM] You are Skillian...                                           │
│ [USER] What is the budget for CC-1001?                                 │
│ [ASSISTANT] (tool_calls: get_cost_center)                              │
│ [TOOL] { "cost_center_id": "CC-1001", "budget": 150000, ... }          │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LLM RESPONSE                                                            │
├────────────────────────────────────────────────────────────────────────┤
│ content: "Cost center CC-1001 has a budget of $150,000 for fiscal      │
│           year 2024. Current spending is at $45,230..."                │
│ tool_calls: []  (empty - no more tools needed)                         │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                         Return Final Response
```

---

## Tool Execution Algorithm

When the LLM decides to call a tool:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      TOOL EXECUTION ALGORITHM                             │
└──────────────────────────────────────────────────────────────────────────┘

              Tool Call: { name: "get_cost_center",
                           args: { cost_center_id: "CC-1001" } }
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: REGISTRY LOOKUP                                                  │
│                                                                          │
│   registry.get_tool("get_cost_center")                                  │
│                                                                          │
│   ┌─────────────────┐                                                   │
│   │  tool_index     │                                                   │
│   │  ─────────────  │                                                   │
│   │  "get_cost_     │───▶ "financial" (skill name)                      │
│   │   center"       │                                                   │
│   └─────────────────┘                                                   │
│            │                                                             │
│            ▼                                                             │
│   ┌─────────────────┐                                                   │
│   │  skills         │                                                   │
│   │  ─────────────  │                                                   │
│   │  "financial"    │───▶ FinancialSkill instance                       │
│   └─────────────────┘                                                   │
│            │                                                             │
│            ▼                                                             │
│   skill.get_tool("get_cost_center") → Tool instance                     │
│                                                                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: INPUT VALIDATION (Pydantic)                                      │
│                                                                          │
│   ┌─────────────────────────────────────────┐                           │
│   │  GetCostCenterInput.model_validate({    │                           │
│   │    "cost_center_id": "CC-1001"          │                           │
│   │  })                                      │                           │
│   └─────────────────────────────────────────┘                           │
│                         │                                                │
│           ┌─────────────┴─────────────┐                                 │
│           │                           │                                 │
│        VALID                       INVALID                              │
│           │                           │                                 │
│           ▼                           ▼                                 │
│   Continue               Return validation error                        │
│                                                                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: FUNCTION EXECUTION                                               │
│                                                                          │
│   tool.function(cost_center_id="CC-1001", fiscal_year=2024)             │
│                        │                                                 │
│                        ▼                                                 │
│   ┌─────────────────────────────────────────┐                           │
│   │  connector.execute_query(               │                           │
│   │    query_type="cost_center",            │                           │
│   │    parameters={                         │                           │
│   │      "cost_center_id": "CC-1001",       │                           │
│   │      "fiscal_year": 2024                │                           │
│   │    }                                     │                           │
│   │  )                                       │                           │
│   └─────────────────────────────────────────┘                           │
│                        │                                                 │
│                        ▼                                                 │
│   ┌─────────────────────────────────────────┐                           │
│   │  RESULT:                                │                           │
│   │  {                                      │                           │
│   │    "cost_center_id": "CC-1001",         │                           │
│   │    "name": "Marketing",                 │                           │
│   │    "budget": 150000,                    │                           │
│   │    "actuals": 45230,                    │                           │
│   │    "variance": 104770                   │                           │
│   │  }                                      │                           │
│   └─────────────────────────────────────────┘                           │
│                                                                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: RETURN RESULT                                                    │
│                                                                          │
│   JSON string result added to conversation as ToolMessage               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Skill Registry & Routing

The registry manages all skills and provides tool routing:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SKILL REGISTRY                                     │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   _skills: dict[str, Skill]                                             │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  "financial"  →  FinancialSkill                                  │  │
│   │  "sales"      →  SalesSkill                                      │  │
│   │  "inventory"  →  InventorySkill                                  │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│   _tool_index: dict[str, str]                                           │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  "get_cost_center"     →  "financial"                            │  │
│   │  "list_cost_centers"   →  "financial"                            │  │
│   │  "compare_budget"      →  "financial"                            │  │
│   │  "get_sales_order"     →  "sales"                                │  │
│   │  "check_inventory"     →  "inventory"                            │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

REGISTRATION ALGORITHM:

    register(skill)
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Skill name      │ NO  │ Raise           │
│ already exists? │────▶│ DuplicateSkill  │
└────────┬────────┘     │ Error           │
         │ YES          └─────────────────┘
         ▼
┌─────────────────┐
│ For each tool   │
│ in skill.tools: │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Tool name       │ NO  │ Raise           │
│ already exists? │────▶│ DuplicateTool   │
└────────┬────────┘     │ Error           │
         │ YES          └─────────────────┘
         ▼
┌─────────────────┐
│ Add to _skills  │
│ Add to _tool_   │
│ index           │
└─────────────────┘


TOOL LOOKUP ALGORITHM:

    get_tool(tool_name)
         │
         ▼
┌─────────────────┐
│ skill_name =    │
│ _tool_index     │
│ [tool_name]     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ skill =         │
│ _skills         │
│ [skill_name]    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ return skill.   │
│ get_tool(       │
│   tool_name)    │
└─────────────────┘
```

---

## LLM Provider Abstraction

The factory pattern allows swapping LLM providers:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      LLM PROVIDER FACTORY                                 │
└──────────────────────────────────────────────────────────────────────────┘

                    Settings.llm_provider
                           │
                           ▼
              ┌────────────────────────┐
              │  create_llm_provider   │
              │      (factory)         │
              └───────────┬────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
       "ollama"      "anthropic"      "openai"
          │               │               │
          ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ OllamaProvider  │ │ AnthropicProv.  │ │ OpenAIProvider  │
│                 │ │                 │ │                 │
│ • ChatOllama    │ │ • ChatAnthropic │ │ • ChatOpenAI    │
│ • Local LLM     │ │ • Claude API    │ │ • GPT-4 API     │
│ • llama3.2      │ │ • claude-3-5-   │ │ • gpt-4o        │
│                 │ │   sonnet        │ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  LLMProvider        │
                  │  Protocol           │
                  │  ─────────────────  │
                  │  get_chat_model()   │
                  │  model_name         │
                  │  provider_name      │
                  └─────────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  LangChain          │
                  │  BaseChatModel      │
                  │  (with tools bound) │
                  └─────────────────────┘
```

---

## Connector Pattern

Connectors abstract SAP BW data access:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      CONNECTOR PATTERN                                    │
└──────────────────────────────────────────────────────────────────────────┘

                         Connector Protocol
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
    │ MockConnector │  │ HANAConnector │  │ RFCConnector  │
    │  (Dev/Test)   │  │  (Direct DB)  │  │ (Legacy SAP)  │
    └───────┬───────┘  └───────────────┘  └───────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────┐
    │                    MockConnector                       │
    │                                                        │
    │   Sample Data:                                         │
    │   ┌─────────────────────────────────────────────────┐ │
    │   │ COST_CENTERS = {                                │ │
    │   │   "CC-1001": {                                  │ │
    │   │     "name": "Marketing",                        │ │
    │   │     "budget": 150000,                           │ │
    │   │     "actuals": 45230,                           │ │
    │   │     ...                                         │ │
    │   │   }                                             │ │
    │   │ }                                               │ │
    │   └─────────────────────────────────────────────────┘ │
    │                                                        │
    │   execute_query(query_type, parameters)               │
    │        │                                               │
    │        ▼                                               │
    │   ┌─────────────────────────────────────┐             │
    │   │ match query_type:                   │             │
    │   │   "cost_center" → _get_cost_center  │             │
    │   │   "cost_center_list" → _list_...    │             │
    │   │   "profit_center" → _get_profit...  │             │
    │   │   "transactions" → _search_trans... │             │
    │   └─────────────────────────────────────┘             │
    │                                                        │
    └───────────────────────────────────────────────────────┘


QUERY EXECUTION FLOW:

    Tool Function
         │
         │  connector.execute_query(
         │    "cost_center",
         │    {"cost_center_id": "CC-1001"}
         │  )
         │
         ▼
    ┌─────────────────┐
    │ Query Type      │
    │ Router          │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ _get_cost_      │
    │ center()        │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Lookup in       │
    │ COST_CENTERS    │
    │ dict            │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │ Return:                         │
    │ {                               │
    │   "cost_center_id": "CC-1001",  │
    │   "name": "Marketing",          │
    │   "budget": 150000,             │
    │   ...                           │
    │ }                               │
    └─────────────────────────────────┘
```

---

## Component Interactions

Complete sequence diagram for a user query:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE INTERACTION SEQUENCE                          │
└──────────────────────────────────────────────────────────────────────────┘

   User        FastAPI       Agent      Registry    LLM       Tool     Connector
    │            │             │           │         │          │          │
    │  POST /chat│             │           │         │          │          │
    │ ──────────>│             │           │         │          │          │
    │            │             │           │         │          │          │
    │            │ process()   │           │         │          │          │
    │            │────────────>│           │         │          │          │
    │            │             │           │         │          │          │
    │            │             │ get_all_  │         │          │          │
    │            │             │ tools()   │         │          │          │
    │            │             │──────────>│         │          │          │
    │            │             │<──────────│         │          │          │
    │            │             │           │         │          │          │
    │            │             │ bind_tools│         │          │          │
    │            │             │ & invoke  │         │          │          │
    │            │             │──────────────────-->│          │          │
    │            │             │                     │          │          │
    │            │             │   tool_calls:       │          │          │
    │            │             │   get_cost_center   │          │          │
    │            │             │<────────────────────│          │          │
    │            │             │           │         │          │          │
    │            │             │ get_tool()│         │          │          │
    │            │             │──────────>│         │          │          │
    │            │             │<──────────│         │          │          │
    │            │             │           │         │          │          │
    │            │             │ execute() │         │          │          │
    │            │             │─────────────────────────────-->│          │
    │            │             │           │         │          │          │
    │            │             │           │         │          │execute_  │
    │            │             │           │         │          │query()   │
    │            │             │           │         │          │─────────>│
    │            │             │           │         │          │<─────────│
    │            │             │           │         │          │          │
    │            │             │  result   │         │          │          │
    │            │             │<───────────────────────────────│          │
    │            │             │           │         │          │          │
    │            │             │ invoke    │         │          │          │
    │            │             │ (with tool result)  │          │          │
    │            │             │──────────────────-->│          │          │
    │            │             │                     │          │          │
    │            │             │   final response    │          │          │
    │            │             │<────────────────────│          │          │
    │            │             │           │         │          │          │
    │            │ AgentResp.  │           │         │          │          │
    │            │<────────────│           │         │          │          │
    │            │             │           │         │          │          │
    │  ChatResp. │             │           │         │          │          │
    │<───────────│             │           │         │          │          │
    │            │             │           │         │          │          │
```

---

## Error Handling

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ERROR HANDLING FLOW                                │
└──────────────────────────────────────────────────────────────────────────┘

                    Tool Execution
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    Pydantic        Connector       Runtime
    Validation       Error          Error
          │              │              │
          ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                                                          │
│   All errors are caught and returned as JSON:           │
│                                                          │
│   {                                                      │
│     "error": true,                                       │
│     "message": "Validation error: cost_center_id        │
│                 is required"                             │
│   }                                                      │
│                                                          │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                                                          │
│   Error JSON added to conversation as ToolMessage       │
│   LLM sees error and can:                               │
│     • Retry with corrected parameters                   │
│     • Inform user of the issue                          │
│     • Try alternative approach                          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Adding a New Skill

Step-by-step algorithm for extending Skillian:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      ADD NEW SKILL ALGORITHM                              │
└──────────────────────────────────────────────────────────────────────────┘

STEP 1: Create Directory Structure
─────────────────────────────────────
    app/skills/{domain}/
    ├── __init__.py
    ├── skill.py          # Skill class
    ├── tools.py          # Tool functions + schemas
    └── knowledge/        # RAG documents
        └── guide.md


STEP 2: Define Tool Input Schemas
─────────────────────────────────────
    class MyToolInput(BaseModel):
        param: str = Field(description="...")
        optional: int | None = Field(default=None)


STEP 3: Implement Tool Functions
─────────────────────────────────────
    async def my_tool(
        connector: Connector,
        param: str,
        optional: int | None = None
    ) -> dict:
        result = await connector.execute_query(
            "query_type",
            {"param": param}
        )
        return result


STEP 4: Create Skill Class
─────────────────────────────────────
    class DomainSkill(BaseSkill):
        def __init__(self, connector: Connector):
            self._connector = connector
            self._tools = [
                Tool(
                    name="my_tool",
                    description="...",
                    function=partial(my_tool, connector),
                    input_schema=MyToolInput
                )
            ]

        @property
        def name(self) -> str:
            return "domain"

        @property
        def description(self) -> str:
            return "Domain-specific analysis..."

        @property
        def system_prompt(self) -> str:
            return "You are an expert in..."

        @property
        def tools(self) -> list[Tool]:
            return self._tools


STEP 5: Register in Dependencies
─────────────────────────────────────
    # app/dependencies.py

    from app.skills.domain.skill import DomainSkill

    @lru_cache
    def get_skill_registry() -> SkillRegistry:
        connector = get_connector()
        registry = SkillRegistry()
        registry.register(FinancialSkill(connector))
        registry.register(DomainSkill(connector))  # NEW
        return registry


STEP 6: Add Connector Support (if needed)
─────────────────────────────────────
    # app/connectors/mock.py

    async def execute_query(self, query_type: str, ...):
        match query_type:
            case "new_query_type":
                return self._handle_new_query(parameters)
```

---

## Summary

Skillian implements a **modular, protocol-based architecture** with these key algorithms:

| Algorithm | Purpose | Key Files |
|-----------|---------|-----------|
| **Request Flow** | Route user messages through the system | `main.py`, `api/routes.py` |
| **Agent Loop** | ReAct-style reasoning with tool execution | `core/agent.py` |
| **Tool Execution** | Validate inputs, execute, return results | `core/tool.py` |
| **Registry Routing** | Map tool names to skills efficiently | `core/registry.py` |
| **LLM Factory** | Abstract LLM provider selection | `llm/factory.py` |
| **Connector Pattern** | Abstract data access layer | `connectors/` |

The system is designed for extensibility - adding new skills, tools, LLM providers, or connectors follows well-defined patterns without modifying core logic.
