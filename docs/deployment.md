# Deploying TestHarbor on your own server

This guide sets up one TestHarbor instance for one company, served over HTTPS on its own domain,
with accounts for your testers.

```
internet ──443──► Caddy (HTTPS, Let's Encrypt) ──► frontend (Next.js) ──► backend (FastAPI) ──► PostgreSQL
```

Only Caddy is reachable from outside. The frontend, backend and database are only reachable inside
the server's Docker network.

## Requirements

- A Linux server with Docker Engine and the Compose plugin (v2.24 or newer). 2 GB of RAM is enough
  for small teams.
- A domain name, for example `testharbor.example.com`, with a DNS **A/AAAA record pointing to the
  server**.
- Ports **80 and 443** open to the internet. Caddy needs both to get and renew certificates.

## 1. Install

```sh
sudo mkdir -p /opt/testharbor && sudo chown "$USER" /opt/testharbor
git clone https://github.com/mirosgit/testharbor.git /opt/testharbor
cd /opt/testharbor
cp .env.example .env
```

Edit `.env`:

```sh
DOMAIN=testharbor.example.com
SECRET_KEY=<output of: openssl rand -hex 32>
DB_PASSWORD=<output of: openssl rand -hex 24>
SEED_DEMO=false
```

- `SECRET_KEY` signs session cookies. If it leaks, someone could forge a sign-in. If you change it,
  everyone is signed out.
- `DB_PASSWORD` is only applied when the database volume is **first created**. To change it later,
  you also have to change it inside Postgres (`ALTER USER testharbor PASSWORD '...'`).
- Keep `.env` private: `chmod 600 .env`.

## 2. Start

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production override turns on HTTPS through Caddy and secure cookies. It removes all published
ports except 80 and 443, and it refuses to start if `DOMAIN`, `SECRET_KEY` or `DB_PASSWORD` are
missing.

To save typing, use an alias:

```sh
alias th='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
```

Open `https://testharbor.example.com`. The first start can take a minute while Caddy gets the
certificate. To watch it: `th logs -f caddy`.

## 3. Create the first admin

```sh
th exec backend python -m app.manage create-admin
```

The command asks for the email, name and password (at least 10 characters). This is the **only**
way to create the first admin. There is no sign-up page, so nobody can claim the instance before
you do.

## 4. Add your testers

In TestHarbor, open **Settings › Users › Invite user**. Enter the email and role, then send the
generated link to the person over a channel you trust (Slack, email…).

- The link works **once** and expires after **72 hours**. Pending links are listed on the same page
  and can be revoked.
- **Tester:** works with cases, runs and results, and manages their own API tokens.
- **Admin:** everything a tester can do, plus managing users and deleting projects.
- **Forgotten password:** use **⋯ › Password reset link** next to the user and send them that link.
- **Someone leaves:** use **⋯ › Deactivate**. They are signed out immediately and their API tokens
  stop working. Their name stays on the results they recorded.

Each tester creates their own API token for CI under **Settings › API tokens**. A token acts as its
owner. Tokens cannot manage users or other tokens.

## 5. Backups

```sh
./deploy/backup.sh          # writes backups/testharbor-<date>.dump and keeps the newest 14
```

To run it every day, add a cron entry (`crontab -e`):

```
15 3 * * * cd /opt/testharbor && ./deploy/backup.sh >> backups/backup.log 2>&1
```

Copy `backups/` off the server as well, for example to object storage or another machine. A backup
that only exists on the same disk doesn't protect you from losing the server.

To restore, stop the app containers and load the dump:

```sh
th stop backend frontend
th exec -T db pg_restore -U testharbor -d testharbor --clean --if-exists < backups/testharbor-YYYYMMDD-HHMMSS.dump
th start backend frontend
```

## 6. Updating

```sh
cd /opt/testharbor
./deploy/backup.sh
git pull
th up -d --build
```

Database migrations run automatically when the backend starts.

## Security checklist

- [ ] `SECRET_KEY` and `DB_PASSWORD` are random, and `.env` is `chmod 600`.
- [ ] Only 22, 80 and 443 are open in the firewall. For example with ufw:
      `ufw allow OpenSSH && ufw allow 80,443/tcp && ufw allow 443/udp && ufw enable`.
- [ ] You started with `docker-compose.prod.yml`. Check with `th ps`: only `caddy` should list
      `0.0.0.0` ports.
- [ ] `SEED_DEMO=false`.
- [ ] Admin accounts use long, unique passwords. Keep the number of admins small.
- [ ] Backups run and are copied off the server. Do a test restore once.
- [ ] Update regularly (`git pull`, then `th up -d --build`).

Built-in protections:
- Passwords are hashed with argon2id.
- After 5 failed sign-ins, an account is locked for 15 minutes, on top of a per-IP rate limit.
- Sign-in errors are generic, so they don't reveal which emails exist.
- Sessions are re-checked on every request. A password change, "sign out other sessions" or
  deactivation takes effect immediately.
- Invite and reset links are one-time and expire.
- API tokens are stored only as hashes.
- Responses carry security headers: CSP, X-Frame-Options and HSTS.

## Admin recovery (on the server)

| Problem | Command |
|---|---|
| Lost the admin password | `th exec backend python -m app.manage reset-password --email you@example.com` |
| Account locked by too many attempts | `th exec backend python -m app.manage unlock --email you@example.com` |
| See all accounts | `th exec backend python -m app.manage list-users` |
| Make an existing user an admin | `th exec backend python -m app.manage create-admin --email them@example.com --update` |

## Troubleshooting

- **No certificate / `ERR_SSL_PROTOCOL_ERROR`:** check that DNS points to the server and that ports
  80 and 443 are open. Read `th logs caddy`.
- **Signed out right after signing in:** the site must be opened over `https://`, because cookies
  are `Secure` in production.
- **Sign-in says the account is locked:** wait 15 minutes, or run `manage unlock`.
- **Running behind another proxy or load balancer** (instead of Caddy on 80/443): it must overwrite
  `X-Forwarded-For` with the real client IP, and it must be the only way in.
