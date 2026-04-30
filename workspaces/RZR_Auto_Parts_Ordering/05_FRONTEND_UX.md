# 05 — Frontend & User Experience

## Design Philosophy

The UI must be **built for mechanics** — people with greasy hands, often on a laptop in a shop. That means:
- Large touch targets, high contrast
- Minimal clicks to accomplish tasks
- No unnecessary complexity
- Works on any laptop with a browser (no app install)

---

## Application Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️  DOME Fleet Mechanic AI                    [Mike T.] [⚡]  │
├───────────┬─────────────────────────────────────────────────────┤
│           │                                                      │
│  VEHICLE  │              MAIN CONTENT AREA                       │
│  SELECTOR │                                                      │
│           │  ┌─────────────────────┬───────────────────────┐    │
│  [RZR-01] │  │                     │                       │    │
│  [RZR-02] │  │    CHAT PANEL       │    PARTS PANEL        │    │
│  [RZR-03] │  │                     │                       │    │
│  [RZR-04] │  │  AI conversation    │  Editable parts list  │    │
│  [RZR-05] │  │  with streaming     │  Add/remove/edit qty  │    │
│  [RZR-06] │  │  responses          │                       │    │
│ >[RZR-07] │  │                     │  ┌─────────────────┐  │    │
│  [RZR-08] │  │  Inline schematics  │  │ Submit Order    │  │    │
│  [GEN-01] │  │  and procedures     │  │ [Approve & Send]│  │    │
│  [RNG-01] │  │                     │  └─────────────────┘  │    │
│           │  │  ┌───────────────┐  │                       │    │
│  FILTERS  │  │  │ Type here...  │  │  ORDER HISTORY        │    │
│  ─────── │  │  └───────────────┘  │  Recent orders...     │    │
│  □ Active │  └─────────────────────┴───────────────────────┘    │
│  □ In Shop│                                                      │
│           │  ┌──────────────────────────────────────────────┐    │
│  SEARCH   │  │  SCHEMATIC VIEWER (expandable)               │    │
│  [🔍    ] │  │  Zoomable exploded diagram with hotspots     │    │
│           │  └──────────────────────────────────────────────┘    │
└───────────┴─────────────────────────────────────────────────────┘
```

---

## Key Screens

### 1. Vehicle Selector (Left Sidebar)

- List of all fleet vehicles with unit IDs
- Color-coded status badges: 🟢 Active, 🟡 In Shop, 🔴 Down
- Search/filter by model type
- Clicking a vehicle loads its profile (VIN, model, mileage, recent repairs)
- Recent repair sessions shown under each vehicle

### 2. Chat Panel (Center)

- Full-screen-height chat interface
- Streaming AI responses (WebSocket)
- Inline rendering of:
  - Formatted repair procedures (numbered steps)
  - Parts tables with part numbers
  - Schematic thumbnails (click to expand)
  - Warning/caution blocks from service manual
- Quick-action buttons: "Show schematic", "Add to parts list"
- Message history persisted per repair session

### 3. Parts Panel (Right)

- Editable table of parts:

```
┌──────────┬──────────────────────────┬─────┬─────────┬────────┐
│ Part #   │ Description              │ Qty │ Price   │ Action │
├──────────┼──────────────────────────┼─────┼─────────┼────────┤
│ 1334441  │ CV Axle Assy, Front LH   │ [1] │ $289.99 │ [✕]    │
│ 3514699  │ Wheel Bearing, Front     │ [1] │ $45.99  │ [✕]    │
│ 7042430  │ Cotter Pin Kit           │ [1] │ $4.99   │ [✕]    │
│ 5412189  │ Axle Nut, Front          │ [1] │ $8.99   │ [✕]    │
├──────────┼──────────────────────────┼─────┼─────────┼────────┤
│ [+ Add Part Manually]              │     │ $349.96 │        │
└──────────┴──────────────────────────┴─────┴─────────┴────────┘

[✓ Approve & Submit Order]    [📋 Export PDF]    [💾 Save Draft]
```

- Quantity fields are editable inline
- Parts can be removed with ✕ button
- Manual part number entry via "Add Part" row
- Real-time subtotal calculation
- Export to PDF for manual ordering (Tier 1)
- Submit button sends to Polaris portal agent (Tier 2)

### 4. Schematic Viewer (Bottom / Modal)

- Zoomable, pannable exploded diagram
- Click-to-identify parts on the diagram (if we can map hotspots)
- Side legend showing all parts in the diagram
- Click a part in the legend → adds to parts panel

### 5. Order History Dashboard

- Table of all past orders with status tracking
- Filter by vehicle, date range, status
- Click to view order details and associated repair session

---

## Technical Implementation

### Frontend Stack
```
React 18 + Vite
├── React Router (page routing)
├── Zustand (lightweight state management)
├── React Query / TanStack Query (API data fetching + caching)
├── react-markdown (render AI responses)
├── @panzoom/panzoom (schematic viewer zoom/pan)
├── Lucide React (icon library)
└── CSS Modules (styling — matches DOME dashboard pattern)
```

### Key Components
```
/frontend/src/
├── components/
│   ├── VehicleSelector/     # Left sidebar vehicle list
│   ├── ChatPanel/           # Center chat interface
│   │   ├── ChatMessage.jsx  # Individual message rendering
│   │   ├── StreamingText.jsx # Typewriter effect for AI
│   │   └── SchematicInline.jsx # Inline diagram thumbnails
│   ├── PartsPanel/          # Right sidebar parts editor
│   │   ├── PartsTable.jsx   # Editable parts list
│   │   ├── AddPartRow.jsx   # Manual part entry
│   │   └── OrderSummary.jsx # Totals and submit button
│   ├── SchematicViewer/     # Full-screen diagram viewer
│   └── OrderHistory/        # Past orders dashboard
├── hooks/
│   ├── useChat.js           # WebSocket chat hook
│   ├── useVehicle.js        # Vehicle data fetching
│   └── useParts.js          # Parts list state management
├── api/
│   └── client.js            # Axios/fetch wrapper for FastAPI
└── App.jsx
```

### API Endpoints
```
GET    /api/vehicles              # List fleet vehicles
GET    /api/vehicles/:id          # Vehicle detail (VIN, history)
POST   /api/chat                  # Send message to AI agent
WS     /api/chat/stream           # WebSocket for streaming responses
GET    /api/parts/search          # Search parts catalog
POST   /api/parts/validate        # Validate part numbers
GET    /api/schematics/:assembly  # Get schematic images
POST   /api/orders                # Submit parts order
GET    /api/orders                # List order history
GET    /api/orders/:id            # Order detail
```

---

*Continue to → [06_CLOUD_DEPLOYMENT.md](./06_CLOUD_DEPLOYMENT.md)*
