# Stars Reborn — Architecture & Design Reference

Last Updated: 2026-04-09 (revised: HTTP service model, engine as data model authority)

For the roadmap and task list, see PLAN.md.
For a history of completed work, see CHANGELOG.txt.

---

## Project Vision

Stars Reborn is a faithful open-source clone of Stars! — the classic 16-bit Windows 4X space
strategy game by Jeff Johnson and Jeff McBride (1995/1996). The four core tenets are:

1. **Open game** — freely distributable, modifiable, and playable (cross-platform, no licensing
   restrictions).
2. **Faithful reproduction** — all original mechanics must be reverse-engineered, documented, and
   implemented. A veteran Stars! player must feel immediately at home.
3. **Respectful enhancement** — a "Legacy" mode preserves original behavior exactly; optional fixes
   address known bugs and micromanagement pain points.
4. **Collaborative** — acknowledge prior clone efforts, community research, and contributors.

---

## Correct Architecture

Stars Reborn is a **client/server game**. The engine and the view are fully decoupled services
that communicate exclusively over HTTP. There is no in-process language interop between them.

```
┌─────────────────────────────────┐        HTTP        ┌──────────────────────────────┐
│         Game Client (UI)        │ ◄────────────────► │     Game Engine (Rust)       │
│                                 │                    │                              │
│  - Renders universe state       │                    │  - Universe generation       │
│  - Collects player orders       │                    │  - Turn processing           │
│  - Submits orders to engine     │                    │  - Victory detection         │
│  - Displays turn results        │                    │  - Authoritative data model  │
│  - Enforces UI-level rules      │                    │  - Validates all inputs      │
└─────────────────────────────────┘                    └──────────────────────────────┘
```

For **single-player**: the engine runs as a local process (`localhost:PORT`). A launcher
starts both the engine and client, presenting them as a single application to the user.

For **multiplayer**: the engine runs on a remote server. The client connects to that host
instead. No code changes required on either side — just a different host address.

This means a third-party client can be built by anyone. As long as it conforms to the
engine's API contracts, it will work. The engine is the gatekeeper — it rejects anything
structurally or rules-logically invalid regardless of what client sent it.

---

## Engine Responsibilities

The engine is a standalone Rust binary exposing an HTTP API. It has four core jobs:

### 1. Universe Generation
Generate the initial star map: planet placement, hab values, mineral concentrations,
homeworld setup per race, starting fleets. Seeded for reproducibility.

### 2. Turn Processing
Each year, resolve the full turn sequence (see Turn Resolution Order below) across all
player orders. Generate per-player turn files containing only what that player can see.

### 3. Victory Detection
After each turn, evaluate all victory conditions. Notify affected players.

### 4. Data Model Authority
The engine is the **single source of truth** for all game rules and data structures:
- Technology tree (all items, costs, prerequisites, miniaturization curves)
- Race trait definitions (PRT/LRT effects, advantage point costs, rule interactions)
- Ship hull definitions (slot counts, slot types, mass, cost)
- Valid component data (per-tech stats, which slots accept which components)
- Habitat ranges and formulae
- Schema versions and API compatibility information

Clients retrieve this data from the engine rather than hardcoding it. This solves version
compatibility: a client queries the engine for the data model it needs to render correctly.

---

## Engine API Design

The API has two distinct surfaces:

### Data Model API
Read-only endpoints that expose the authoritative game rules. Clients use these to:
- Build the technology browser
- Populate the ship designer with valid components for the player's tech level
- Understand what race traits are available and their effects
- Know valid ranges for race design parameters

Example endpoints:
```
GET /model/version                  → engine version + API schema version
GET /model/technologies             → full tech tree
GET /model/technologies/{id}        → single tech item
GET /model/race/traits              → PRT/LRT definitions and point costs
GET /model/ships/hulls              → all hull definitions
GET /model/schemas                  → JSON schemas for all submitted structures
```

### Game API
Stateful endpoints for game play:

```
POST /game/new                      → create game (universe params, race files)
GET  /game/{id}/turn/{player}       → retrieve current turn file for player
POST /game/{id}/orders/{player}     → submit player orders for this turn
GET  /game/{id}/status              → turn status, victory state
POST /game/{id}/generate            → trigger turn generation (host only)
```

---

## Validation Philosophy

The engine validates **all inputs** before acting on them. Clients may enforce rules
locally to give immediate feedback (e.g., grey out a ship component the player hasn't
researched), but the engine never trusts that client-side validation occurred.

Validation layers:

1. **Structural** — does the input conform to the JSON schema for this request type?
2. **Rules-logical** — is this race design legal given the PRT/LRT combination and
   advantage point totals? Is this ship design valid for the player's tech level and
   hull type? Are these orders possible given the fleet's current state?
3. **Game-state** — does the player have authority to issue these orders? Is it this
   player's turn?

This means the JSON schemas in `stars-reborn-research-and-design/schemas/` are not just
documentation — they are the contract. The engine enforces them.

---

## Data Model Overlap (Engine as Authority)

Some concepts have meaning in both the engine and the view:

| Concept | Engine role | Client role |
|---------|------------|-------------|
| Technology tree | Defines stats, costs, prereqs, miniaturization | Renders tech browser; filters available components |
| Race traits (PRT/LRT) | Enforces rule effects each turn | Renders race designer; shows trait descriptions |
| Ship components | Defines what is valid per hull slot | Renders ship designer; enforces tech-level gating |
| Claim Adjuster (CA) | Applies terraforming-as-growth rule | May show CA-specific UI hints |
| Hab ranges | Calculates planet value | Renders hab sliders and planet value preview |

In all cases: **the engine's definition wins**. If the client and engine disagree about
whether something is valid, the engine rejects it. Clients should retrieve data model
information from the engine's `/model/` endpoints rather than maintaining independent
copies of rules.

---

## Client Architecture

The client is a pure HTTP consumer. It:

- Authenticates with the engine (JWT or session token)
- Polls or receives push notifications for turn readiness
- Retrieves its turn file (`GET /game/{id}/turn/{player}`)
- Renders the universe from that data — it knows nothing about other players' internal state
- Collects player orders through the UI
- Submits orders (`POST /game/{id}/orders/{player}`)
- Retrieves data model endpoints as needed for UI construction

The client does **not**:
- Implement game logic (movement calculations, combat simulation, research accumulation)
- Maintain authoritative copies of the tech tree or rule definitions
- Trust its own validation as sufficient — it always lets the engine make the final call

The reference client is Python/PySide6 (see `stars-reborn-ui`), but any HTTP-capable
implementation is a valid client.

---

## Packaging

The user-facing product must feel like a single application, not two services to manually
start. The packaging approach:

**Single-player packaging:**
- A thin launcher executable starts the engine process (`localhost:PORT`) and then opens
  the client, passing the engine address
- On exit, the launcher shuts down the local engine process
- The launcher is what becomes the `.exe` (Windows, via NSIS or Inno Setup) or `AppImage`
  (Linux)

**Contents of the distribution:**
```
stars-reborn/
├── launcher          ← thin binary: starts engine + client, manages lifecycle
├── engine            ← game engine binary
└── client/           ← client application files (Python + PySide6, or web assets)
```

**Multiplayer:**
- No launcher needed on the client side — client connects directly to remote engine host
- Server operators run the engine binary standalone

---

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Game engine | **Rust** | Performance for large maps and parallel turn processing; safe concurrency via rayon; ships as a standalone binary |
| Engine HTTP layer | **Rust** (axum or actix-web) | Native to the engine binary; no separate process needed |
| Reference client | **Python 3 / PySide6** | Cross-platform Qt6; QPainter space map; Win95 aesthetic |
| Client↔Engine | **HTTP + JSON** | Language-agnostic; enables third-party clients; same interface local or remote |
| Validation | **JSON Schema** | Schemas in `stars-reborn-research-and-design/schemas/`; enforced by engine |
| Game data | **JSON + gzip** | Tech tree, race definitions, turn files |
| Save files | **JSON (gzip)** | Engine-side persistence; `.sr` extension |
| Tests | **pytest** (client) + **cargo test** (engine) | Headless Python tests; Rust unit + integration tests |
| Packaging | **Rust launcher** + PyInstaller/appimage-builder | Single executable ships engine + client together |

### Why not PyO3 / in-process interop?

An earlier iteration embedded the engine as a Python extension module via PyO3. This was
the wrong direction: it tightly couples the client language to the engine, prevents
third-party clients, and makes multiplayer (remote engine) a special case requiring
different code paths. The HTTP service model eliminates all of these problems.

---

## Turn Resolution Order

The canonical Stars! turn resolution sequence (from community research):

1. Wormhole jiggles
2. Random events (comet strikes, etc.)
3. Packets/salvage move and decay
4. Fleets move (waypoints), lay mines, run devices
5. Mine fields sweep (mine-laying complete)
6. Bombing
7. Population growth
8. Factories/mines built
9. Minerals mined
10. Resources generated; production queues run
11. Research applied
12. Battle at contested locations
13. Fleets merge/split (player orders)
14. Messages generated

---

## Racial Trait System

**Primary Racial Traits (PRT)** — mutually exclusive, define the race's fundamental strategy:
JOAT, HE, SS, WM, CA, IS, SD, PP, IT, AR

**Lesser Racial Traits (LRT)** — mix-and-match modifiers, each costing or earning advantage
points:
IFE, TT, ARM, ISB, GR, UR, NAS, OBRM, CE, NRSE, OTES, MILS, LSP, BET, RS, MA, BBA, SF, PA

---

## Repository Layout

```
stars/
├── stars-reborn/                   ← integration root (build + tests; see PLAN.md M6)
├── stars-reborn_game-engine/       ← Rust engine: HTTP server, turn processing, data model
├── stars-reborn-ui/                ← Reference client: Python/PySide6 + assets
├── stars-reborn-research-and-design/  ← Docs, schemas, research, reverse-engineering
└── reference/                      ← Original game artifacts, diagrams, static data files
```
