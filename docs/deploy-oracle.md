# Deploy on Oracle Cloud (Always Free)

Step by step: from a new Oracle account to Sabaq running on HTTPS. After step 7, follow
`docs/runbook.md` (first deploy, backups, incidents).

What you get for free: an ARM server (Ampere A1) with up to 4 CPUs and 24 GB RAM in total,
200 GB of disk in total, and 20 GB of object storage for backups. Every image and Python
package Sabaq uses has an ARM build, so `docker compose up` works unchanged.

Free tiers change. Check Oracle's "Always Free" page before you start.

## 1. Account

1. Sign up at oracle.com/cloud/free. You need a card; Oracle places a small temporary hold.
2. **Home region**: chosen once and cannot be changed later. Free servers exist only there.
   Pick one near Egypt, for example Jeddah, Dubai, Frankfurt, Milan or Marseille.
   Health data will live in that country: ask the lawyer whether Egypt's data protection law
   (Law 151 of 2020) needs consent or a permit for it (docs/security.md).
3. **Upgrade to Pay As You Go** (Billing > Upgrade). Always Free resources stay free, but:
   - free-only accounts lose servers that stay mostly idle for 7 days (a small beta site
     will look idle), and
   - free-only accounts often get "out of capacity" when creating ARM servers.
4. Right away, add a budget alert: Billing > Budgets > Create, amount 1 USD, alert at 100%.
   You get an email if anything ever starts costing money.

## 2. Create the server

Compute > Instances > Create instance:

- **Name**: `sabaq-staging`.
- **Image**: Canonical Ubuntu 24.04 (the aarch64 one is picked automatically with the shape).
- **Shape**: Ampere > `VM.Standard.A1.Flex`, **2 OCPU, 12 GB RAM**. This leaves the other
  half of the free allowance for a production server later.
- **Networking**: create a new virtual cloud network with a public subnet; tick
  "Assign a public IPv4 address".
- **SSH keys**: upload your public key (on your laptop: `ssh-keygen -t ed25519`, then upload
  `~/.ssh/id_ed25519.pub`). Never use password login.
- **Boot volume**: 50 GB is enough.

If you see "Out of host capacity", try another availability domain or try again later.

Write down the **public IP** from the instance page.

## 3. Firewall in the Oracle console

Networking > Virtual cloud networks > your network > Security lists > Default security list.
The ingress rules must be exactly:

| Source | Protocol | Port | Why |
| --- | --- | --- | --- |
| `<your IP>/32` | TCP | 22 | SSH only from you (find your IP at ifconfig.me) |
| `0.0.0.0/0` | TCP | 80 | HTTP (Caddy redirects to HTTPS and gets the certificate) |
| `0.0.0.0/0` | TCP | 443 | HTTPS |

Delete the default rule that opens 22 to `0.0.0.0/0`. If your home IP changes, update the
22 rule here; the site keeps working.

## 4. Prepare the server

```sh
ssh ubuntu@<public IP>

# Updates (security updates then install automatically: unattended-upgrades is on by default)
sudo apt update && sudo apt full-upgrade -y

# Oracle's Ubuntu image also blocks ports inside the server. Open 80 and 443 and save.
# Do this BEFORE installing Docker, so the saved rules do not include Docker's own rules.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

sudo reboot   # if the upgrade asked for it
```

## 5. Install Docker

```sh
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
exit   # log in again so the group applies
```

Check: `docker run --rm hello-world`.

Only Caddy publishes ports (80/443). Postgres and Redis stay on Docker's internal network.

## 6. Get the code

The repository is private, so the server gets a read-only deploy key:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/sabaq_deploy -N "" -C "sabaq-staging"
cat ~/.ssh/sabaq_deploy.pub
```

On GitHub: repository > Settings > Deploy keys > Add deploy key, paste it, leave
"Allow write access" **off**. Then:

```sh
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/sabaq_deploy
  IdentitiesOnly yes
EOF
git clone git@github.com:moustafasayed068/sabaq.git
cd sabaq
```

## 7. Domain and `.env`

1. At your domain registrar, add an **A record**: `staging.<your domain>` (or the bare
   domain) pointing to the public IP. Wait until `ping staging.<your domain>` shows that IP.
   No domain yet? For a short test you can use `<ip-with-dashes>.sslip.io`
   (for `203.0.113.7`: `203-0-113-7.sslip.io`). Use your own domain for the beta.
2. Create `.env`:

```sh
cp .env.example .env
chmod 600 .env
# Random values (run each one, paste the output into .env):
python3 -c "import secrets; print(secrets.token_urlsafe(50))"          # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"          # POSTGRES_PASSWORD
python3 -c "import secrets; print('staff-' + secrets.token_hex(8) + '/')"  # DJANGO_ADMIN_URL
python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # FIELD_ENCRYPTION_KEYS
python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # BACKUP_ENCRYPTION_KEYS (a different one)
nano .env
```

Set these for the domain (example `staging.sabaq.run`):

```
DJANGO_ALLOWED_HOSTS=staging.sabaq.run
DJANGO_CSRF_TRUSTED_ORIGINS=https://staging.sabaq.run
SITE_ADDRESS=staging.sabaq.run
LOGIN_CODE_SENDER=outbox
SENTRY_ENVIRONMENT=staging
```

Leave the `PAYMOB_*` values empty until the keys arrive (checkout stays closed).
Save `FIELD_ENCRYPTION_KEYS` and `BACKUP_ENCRYPTION_KEYS` in your password manager **now**.

3. Start it and continue with `docs/runbook.md` > First deploy, step 2 onwards:

```sh
docker compose up -d --build     # the first build on ARM takes a few minutes
docker compose ps
curl -s https://staging.sabaq.run/healthz   # ok
```

## 8. Backups off the server

The `backup` service writes one encrypted dump a day into a Docker volume on this disk.
Copy it to Oracle Object Storage every day (20 GB free):

1. Console: Storage > Buckets > Create bucket `sabaq-backups` (Standard, private).
   Write down the **namespace** shown on the bucket page.
2. Profile (top right) > My profile > Customer secret keys > Generate. Copy the access key
   and the secret (the secret is shown once).
3. On the server:

```sh
sudo apt install -y rclone
sudo mkdir -p /root/.config/rclone
sudo tee /root/.config/rclone/rclone.conf >/dev/null <<'EOF'
[oci]
type = s3
provider = Other
access_key_id = <access key>
secret_access_key = <secret>
region = <region id, e.g. me-jeddah-1>
endpoint = https://<namespace>.compat.objectstorage.<region id>.oraclecloud.com
force_path_style = true
EOF
sudo chmod 600 /root/.config/rclone/rclone.conf

# Test once
BACKUPS=$(docker volume inspect sabaq_backups -f '{{.Mountpoint}}')
sudo rclone copy "$BACKUPS" oci:sabaq-backups && sudo rclone ls oci:sabaq-backups

# Every day at 03:30, copy any new backup files
echo "30 3 * * * root rclone copy $BACKUPS oci:sabaq-backups" | sudo tee /etc/cron.d/sabaq-backups
```

`rclone copy` never deletes from the bucket. Once a month, also download the newest backup
to a machine outside Oracle: if the Oracle account is ever lost, so is the bucket.
Files are encrypted; the key stays in your password manager.

## 9. Deploying a new version

```sh
cd ~/sabaq
git fetch --tags && git pull
docker compose up -d --build
docker compose exec web python manage.py check --deploy
```

Going back: `docs/runbook.md` > Incidents > Bad deploy.

## Checklist

- [ ] Pay As You Go on, 1 USD budget alert set
- [ ] SSH only from your IP, by key; only 80/443 open to everyone
- [ ] `check --deploy` prints no issues; `/healthz` answers `ok` over HTTPS
- [ ] Staff account with 2FA created (runbook step 4)
- [ ] Field and backup keys saved off the server
- [ ] One backup copied to the bucket; one restore test done (runbook > Restore)
