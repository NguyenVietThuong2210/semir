# prod.md — Production Operations & History

**Purpose:** Single reference for how to inspect (**investigate**) and **deploy** the Semir
Dashboard production server, plus a dated log of production incidents/changes. When the user
says *"investigate prod"* or *"deploy prod"*, follow this file.

> ⚠️ **This file is committed to git — never write secrets (passwords/keys) here.**
> Credentials live only in `prod_visual.env` (gitignored) at the repo root.

---

## 1. Server & access

| Item | Value |
|------|-------|
| Public URL | https://analytics-customer-dashboard.com |
| Server IP | `14.225.254.192` (also in `.env.prod` `ALLOWED_HOSTS`) |
| OS | Ubuntu 24.04.4 LTS |
| Spec | **2 vCPU, 1.9 GB RAM** (tight — see §5), 38 GB disk (~23 GB free) |
| Project dir | `/home/semir/semir/` |
| SSH user | `root` |
| SSH credentials | **`prod_visual.env`** (repo root, gitignored): `PROD_ID` = IP, the **2nd** `PROD_PASS` line = SSH root password. (The 1st `PROD_USER`/`PROD_PASS` pair is the *web app* admin login, not SSH.) |

### How to connect (Windows dev box → prod)
No SSH key is installed locally; login is **password-based**. Use PuTTY's `plink`
(`C:\Program Files\PuTTY\plink`, already on PATH). Read the password from `prod_visual.env` first.

```bash
# read prod_visual.env → PROD_ID + 2nd PROD_PASS, then:
plink -ssh -pw "<SSH_PASSWORD>" -batch root@14.225.254.192 "<remote command>"
# append  2>&1 | grep -v obsolete   to drop the harmless docker-compose 'version' warning
```
The host key is already trusted in `~/.ssh/known_hosts`. First-ever plink connect may need
`echo y | plink ...` once to cache the key in PuTTY's store.

---

## 2. Stack (prod = `docker-compose.yml`, no override)

4 containers, `restart: unless-stopped`:

| Container | Role |
|-----------|------|
| `semir_web` | Django + **gunicorn** — `wsgi:application --workers 3 --timeout 600` (see Dockerfile `CMD`) |
| `semir_nginx` | reverse proxy + SSL termination |
| `semir_db` | PostgreSQL 16 |
| `semir_redis` | cache / scheduler leader-lock / rate-limit budget |

**No source bind-mount on `semir_web`** (build-time `COPY` only). A code edit is live only after
rebuild+deploy — there is no autoreload in prod.

---

## 3. Investigate prod (read-only playbook)

```bash
# container health + uptime
cd /home/semir/semir && docker compose ps
# memory / swap (RAM is the usual bottleneck)
free -m ; swapon --show
# top memory processes
ps -eo rss,comm --sort=-rss | head -8
# web logs — recent
docker compose logs --tail=200 --no-color web 2>&1 | grep -iE 'error|traceback|SIGKILL|customer_tab|slow'
# gunicorn OOM signature to watch for:
#   [ERROR] Worker (pid:N) was sent SIGKILL! Perhaps out of memory?
# access-log response SIZE (bytes) is the 2nd-to-last number — a huge value = bloated fragment
```

Data-shape / counts via Django shell (read-only):
```bash
docker compose exec -T web python manage.py shell -c "<python>"
```

---

## 4. Deploy prod

Deployment is **manual, git-pull based**, via `scripts/deploy.sh` run **on the server**:

```bash
plink -ssh -pw "<pw>" -batch root@14.225.254.192 "cd /home/semir/semir && bash scripts/deploy.sh"
```
`deploy.sh` steps: `git pull origin main` → `docker compose build --no-cache web` →
`docker compose down && up -d` → `migrate` → `perm sync` → `collectstatic`.

**Pre-deploy checklist:** code merged to `main`; local "Testing for Release" green (see
`CLAUDE.md`); remember the ~1.9 GB RAM ceiling — a `--no-cache` build + running stack is tight,
watch `free -m` during build.

---

## 5. Known constraints

- **RAM is the hard limit.** At idle `semir_web` alone holds ~1.0 GB (3 gunicorn workers).
  Python does not return freed memory to the OS, so a worker that served one heavy request stays
  inflated. Available RAM is normally only ~200 MB.
- **Swap:** a **4 GB swapfile** was added 2026-09-26 (see history) with `vm.swappiness=10`. It is
  the safety net against OOM kills; it does **not** make heavy requests faster.
- Any new endpoint that renders a large unpaginated list is an OOM risk on this box — paginate/cap
  server-side.

---

## 6. History log

### 2026-09-26 — "Active Zalo Mini App" tab slow + gunicorn OOM kills
- **Symptom:** `/cnv/customer-analytics/` → *Active Zalo Mini App* tab (`ca_zalo`) loading very slowly on PROD.
- **Diagnosis (from `semir_web` logs):**
  - `GET /cnv/customer-analytics/tab/ca_zalo/` returned **~46 MB** HTML (`200 46262153`), ~25–30 s/request.
  - Repeated `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?` right after each ca_zalo hit.
  - Box: 1.9 GB RAM, **0 swap**, ~200 MB free (dropped to **25 MB** during one ca_zalo render).
- **Root cause:** `App/analytics/customer_tabs.py::_customer_ca_zalo` loads the **full** Zalo lists
  into memory (`list(...)`, no pagination) — **55,190** mini-app + **53,051** OA = **108,241 rows** —
  and `App/templates/cnv/tabs/ca_zalo.html` renders every row → ~46 MB fragment. FE lazy-load is
  **tab-level only** (`components/lazy_tabs_js.html`), no row-level paging. Workers ballooned to
  ~450 MB each and, with no swap, got OOM-killed.
- **Fix applied (Option 2 — low-impact, OS-level, no code/deploy/downtime):**
  added a **4 GB `/swapfile`** + `vm.swappiness=10`, persisted in `/etc/fstab` and
  `/etc/sysctl.d/99-swappiness.conf`. Independently verified (8/8 checks PASS): swap active,
  reboot-persistent, all 4 containers untouched (no restart), no new errors.
  Commands used:
  ```bash
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
  ```
- **Follow-up (not yet done):** Option 1 — server-side pagination/cap of the `ca_zalo` tab lists to
  cut the 46 MB fragment and the ~30 s render (swap fixes *stability*, not *speed*). Export path
  (`get_cnv_comparison_data` → `excel_export`) is separate and must keep exporting the **full** list.
