# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Aim is an open-source ML experiment tracker. It has two main parts:
- A **Python SDK** (`aim/sdk/`, `aim/`) used by training scripts to log runs
- A **web UI** with a FastAPI backend (`aim/web/api/`) and a React/TypeScript frontend (`aim/web/ui/src/`)

## Commands

### Running the app (development)

Backend (FastAPI via uvicorn, auto-reload):
```bash
aim up --dev --repo <path-to-aim-repo>
```

Frontend dev server (proxies API to port 43800 by default):
```bash
cd aim/web/ui && npm start
```

### Backend

```bash
# Linting (Python, single-quotes, 120 char lines)
ruff check .
ruff format .

# Tests
pytest tests/
pytest tests/api/test_runs.py  # single file
```

### Frontend

```bash
cd aim/web/ui
npm run lint        # eslint
npm run format:fix  # eslint --fix
npm test            # jest
npm run build       # production build + gzip
```

## Architecture

### Backend (FastAPI)

`aim/web/api/__init__.py` is the entry point — it creates the FastAPI app, mounts the API at `/api`, and registers all routers. To add a new API feature:
1. Create `aim/web/api/{feature}/views.py` with an `APIRouter`
2. Import and register it in `aim/web/api/__init__.py`

All routers use `from aim.web.api.utils import APIRouter` (a thin wrapper around FastAPI's router). The `object_factory` dependency provides access to the Aim repo and runs.

The SDK's `Repo` class (`aim/sdk/repo.py`) is the central data access layer. `repo.list_active_runs()` returns hashes of currently running experiments; `run.active` checks if a specific run is live.

### Frontend (React/TypeScript)

**Routing**: Routes are defined in `routes/routes.tsx` using entries from `PathEnum` (`config/enums/routesEnum.ts`). Setting `showInSidebar: true` and providing an `icon` field automatically renders the page in the left sidebar via `SideBar.tsx`.

**Adding a new page** requires touching 4 files:
1. `config/enums/routesEnum.ts` — add a `PathEnum` entry
2. `config/pageTitles/pageTitles.ts` — add a page title constant
3. `routes/routes.tsx` — add the route object (lazy-imported component)
4. Create the page component under `pages/{FeatureName}/`

**Icons**: Icons are a custom icon font. Valid icon names are the `IconName` union type in `components/kit/Icon/Icon.d.ts`. Use `<Icon name="runs" />` etc.

**State management**: Uses a lightweight custom model system. `createModel<State>(initialState)` in `services/models/model.ts` returns a model with `setState`, `getState`, and `subscribe`. Components subscribe via the `useModel(model)` hook. The Container/Presenter pattern is standard: `FooContainer.tsx` holds model subscription and passes props down to `Foo.tsx`.

**API calls**: All HTTP calls go through `services/api/api.ts` which exposes `API.get`, `API.post`, etc. Each returns `{ call, abort }`. Endpoints are grouped in `services/api/endpoints.ts`.

### Data flow for a new page with backend data
1. Backend: `aim/web/api/{feature}/views.py` → register router in `__init__.py`
2. Frontend service: `services/api/{feature}/{feature}Service.ts` using `API.get`
3. Frontend model: `services/models/{feature}/{feature}Model.ts` using `createModel`
4. Container component subscribes via `useModel`, passes data to presenter
5. Route + sidebar entry in `routes/routes.tsx` and `config/enums/routesEnum.ts`
