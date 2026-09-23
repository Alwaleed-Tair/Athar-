# أَثَر (ATHAR) — Digital Evidence Custody Platform

A prototype platform for investigators to register digital evidence,
extract EXIF metadata, and keep a cryptographically-chained,
tamper-evident audit log ("chain of custody") for every action taken on
a case or a piece of evidence.

## File tree

```
athar/
├── .env.example                  # copy to backend/.env and fill in
├── .gitignore
├── README.md
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI app, mounts frontend, startup/bootstrap
│       ├── config.py             # all env vars read here, nowhere else
│       ├── database.py           # SQLite connection + schema + bootstrap admin
│       ├── security.py           # PBKDF2 password hashing, JWT issue/verify
│       ├── deps.py               # auth + case-membership FastAPI dependencies
│       ├── audit.py              # hash-chain append + verify logic
│       ├── i18n.py               # AR/EN templates, audit messages built at read time
│       ├── analysis.py           # EXIF extraction (Pillow) + external AI call
│       └── routers/
│           ├── auth.py           # login, admin-only user creation
│           ├── cases.py          # cases, membership, audit view, verify
│           └── evidence.py       # upload (streamed+hashed), inspect, download, analyze
└── frontend/
    ├── index.html
    ├── css/
    │   └── styles.css            # design tokens, light/dark, RTL logical properties
    └── js/
        ├── api.js                # single place that attaches auth token + ?lang=
        ├── i18n.js                # all UI strings, AR + EN
        ├── state.js               # tiny in-memory store, no reloads
        ├── ui.js                  # modal helper, escaping, formatting
        ├── auth.js                # login screen
        ├── cases.js               # case list + case workspace (3 tabs)
        ├── evidence.js            # evidence table, upload, inspect modal
        ├── chain.js                # full chain-of-custody tab
        └── app.js                  # topbar, routing, full re-render on state change
```

The SQLite database (`backend/storage/athar.db`) and uploaded evidence
(`backend/storage/evidence/`) are created automatically on first run and
are **not** part of this delivery — they're listed in `.gitignore`.

## Running it

```bash
cd backend
pip install -r requirements.txt
# optional but recommended: copy ../.env.example to .env and fill it in
cp ../.env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000** — the same port serves both the API
(under `/api/...`) and the frontend.

### First account

On first run (empty database), an ADMIN account is created automatically:

- **Username:** `admin`
- **Password:** `ChangeMe123!`

Override these before first run via `ATHAR_ADMIN_USERNAME` /
`ATHAR_ADMIN_PASSWORD` in your `.env`, or just log in and create other
accounts, then stop using this one. There is no self-registration screen
by design — only an ADMIN can create new users (`POST /api/users`), and
that endpoint sets the role explicitly; no public/unauthenticated
endpoint accepts a `role` field.

### Enabling AI analysis (optional)

Set `ATHAR_AI_KEY` in `.env` to enable the "Run AI analysis" button on
the evidence inspect screen (cross-evidence correlation: same device,
same hash, time proximity, conflicting timestamps). Without a key, the
button still works but clearly reports that analysis is disabled — it
never fabricates a result. `ATHAR_AI_URL` and the model id inside
`analysis.py` (`AI_MODEL`) are both easy to change if your key is for a
different provider or a newer model than the default.

## Design notes / how the spec's requirements are implemented

- **Chain of custody**: every sensitive action (login, login failure,
  case created/opened, member added, evidence uploaded/opened/
  downloaded/analyzed, chain verified) appends one row to `audit_log`.
  Each row's `event_hash` is `SHA256(canonical_json({previous_hash, seq,
  actor_id, action, case_id, evidence_id, ts, params}))`, computed
  **before** the row is inserted, inside a `threading.Lock` that
  re-reads the true last row from the database at lock-acquisition time
  — so two concurrent requests can never hash off the same stale
  "previous" row.
- **Verification** (`GET /api/cases/{id}/verify`) recomputes every row's
  hash from its stored fields and returns `intact`, `records_checked`,
  and `first_broken_seq`. Directly editing a row in the `.db` file (as
  in test scenario "d" below) is detected and the first broken record
  number is correctly reported.
- **i18n**: `audit_log` never stores a rendered sentence — only an
  action code (e.g. `EVIDENCE_UPLOADED`) and a small JSON of parameters.
  `i18n.py` builds the sentence at read time from the `lang` query
  parameter, so the same row renders correctly in either language and
  the `event_hash` is identical regardless of which language it's later
  read in. `api.js` is the single place on the frontend that appends
  `?lang=` to every request, and `i18n.js` is the single dictionary of
  UI strings; switching language calls `State.set({})` to trigger a
  full in-memory re-render — never `location.reload()`.
- **Access control**: `case_members` gates every case-scoped read/write.
  A case that doesn't exist and a case the user isn't a member of both
  return an identical `404` (not `403`), so membership itself is never
  leaked. This applies to ADMIN too — an admin who isn't a member of a
  case gets 404 just like anyone else; only user creation and
  case-membership grants are admin-only actions.
- **Security**: passwords are `PBKDF2-HMAC-SHA256` with a random
  16-byte salt per user (260,000 iterations); the JWT secret is read
  from `ATHAR_JWT_SECRET` only (a random in-memory fallback is used —
  with a clear startup warning — so the app doesn't crash if it's
  unset, but sessions won't survive a restart in that case); uploads
  with `.exe .dll .bat .ps1 .sh .js .jar` extensions are rejected, a max
  size is enforced while streaming, and the SHA-256 hash is computed
  chunk-by-chunk as the file is written to disk (not after the fact).

## Testing actually performed before delivery

All five required scenarios were run end-to-end against a live server
(fresh database each time) as part of building this:

- **(a)** Logged in as the bootstrap admin, created a case, opened it,
  uploaded a JPEG with real EXIF (`Make`/`Model` tags — extraction
  returned `SUCCESS` with those fields) and a `.txt` file (returned
  `NOT_APPLICABLE`, as expected for a non-image). Also confirmed a
  blocked extension (`.exe`) is rejected with `400`.
- **(b)** Requested the case's audit log with `?lang=en` then
  `?lang=ar` — same row count, same `event_hash` per row, different
  (correctly localized) `message` text in each language.
- **(c)** Ran `/verify` on the untampered chain — returned
  `intact: true`.
- **(d)** Edited a row's `action` column directly in the SQLite file
  with a separate `sqlite3` connection (bypassing the API entirely),
  then re-ran `/verify` — it correctly returned `intact: false` and
  identified the exact `seq` of the tampered row as `first_broken_seq`.
- **(e)** Created a second (`INVESTIGATOR`) user, logged in as them, and
  confirmed `GET /api/cases/{id}` for a case they were never added to
  returns `404`, and their case list is empty. After the admin
  explicitly granted them membership, the same case then returned
  `200`.

Additionally verified: downloaded evidence's SHA-256 matches the
recorded hash; the AI-analysis endpoint correctly reports `DISABLED`
(with no fabricated content) when no `ATHAR_AI_KEY` is set; membership
grants work; the frontend's `index.html`/`css`/`js` are served from the
same port as the API; weak passwords (<8 chars) are rejected on user
creation.

## What was **not** actually tested

Be aware of the following before you treat this as production-ready:

- **The frontend UI itself was not exercised in a real browser** — only
  its JS files were syntax-checked (`node --check`) and every backend
  endpoint they call was tested directly via HTTP. Click-through
  behavior (drag-and-drop upload, modal open/close, tab switching, the
  language/theme toggles' visual RTL layout, mobile responsiveness) has
  not been visually verified. I'd recommend a manual pass in an actual
  browser, especially for the Arabic/RTL layout.
- **The AI-analysis integration was not tested against a live AI API**
  — no `ATHAR_AI_KEY` was available in this environment, so only the
  "disabled" code path was exercised. The request-building and
  response-parsing code for the enabled path (`analysis.py:
  analyze_evidence`) has not been run against a real API response, and
  the default `AI_MODEL` value should be double-checked against
  whatever provider/model your key is actually for.
- **Concurrency under real load** (many simultaneous uploads/logins)
  was not load-tested; the `threading.Lock` around the audit chain and
  the single shared SQLite connection should be safe for a prototype's
  traffic but haven't been stress-tested.
- **JWT secret persistence**: if you never set `ATHAR_JWT_SECRET`, every
  server restart invalidates all existing sessions (a random secret is
  regenerated each boot). This is flagged loudly in the startup logs
  but is worth knowing before you rely on long-lived sessions.
- No automated test suite (pytest, etc.) was written — the scenario
  tests above were ad hoc scripts run once against the live server, not
  checked-in, repeatable tests.
