# Validation — Phase 1: Foundation

Phase 1 is complete and ready to merge when all criteria below pass.

---

## 1. Environment

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Must start without errors. Confirm SQLite `prices.db` is created.

---

## 2. Route Smoke Tests

Run manually with `curl` or a browser:

### Health
- `GET /health` → HTTP 200, JSON `{"status": "ok"}`

### Auth
- `GET /register` → HTTP 200, HTML form with email + password fields
- `POST /register` (valid email + password) → redirects to `/`
- `POST /register` (duplicate email) → HTTP 200, form re-renders with error message
- `GET /login` → HTTP 200, HTML form
- `POST /login` (valid credentials) → redirects to `/`, session cookie set
- `POST /login` (invalid credentials) → HTTP 200, form re-renders with error
- `POST /login` 5× with wrong password from same IP → 6th attempt returns 429 or lockout error
- `POST /logout` → redirects to `/`, session cleared

### Landing
- `GET /` (anonymous) → HTTP 200, HTML with suburb input, store checkboxes, search form
- `GET /` (authenticated) → HTTP 200, shows user name or logout link in header

### Search (skeleton — no real results yet)
- `POST /search` with `query=milk&stores=woolworths,coles` → HTTP 200, search page renders (empty results is acceptable in Phase 1)

---

## 3. Database Checks

After `POST /register` + `POST /login`:
```sql
SELECT id, email FROM users;      -- should show registered user
SELECT id, user_id FROM user_preferences;  -- may be empty at this stage
```

---

## 4. Manual Browser Checklist

- [ ] `/` loads with no console errors
- [ ] Store checkboxes are interactive (Alpine.js) — clicking Woolworths highlights it
- [ ] Search form submits and replaces the `#results` div via HTMX (even if empty results)
- [ ] Register → Login → Logout flow works end-to-end
- [ ] On Railway: `/health` returns 200 with `"status": "ok"`
- [ ] Railway PostgreSQL: confirm `DATABASE_URL` is set and tables are created (check Railway logs for `init_db()` success)

---

## 5. Security Checks

- [ ] `SESSION_SECRET_KEY` is set in Railway Variables (not the default placeholder)
- [ ] Passwords are stored as bcrypt hashes (not plaintext) — verify in DB: `SELECT password_hash FROM users`
- [ ] HTTPS-only session cookie set (visible in browser DevTools → Application → Cookies)
