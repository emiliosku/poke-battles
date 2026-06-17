#!/usr/bin/env bash
# OCI ARM free-tier install script for poke-battles.
# Run as a non-root user with sudo.
#
# What it does:
#   1. Installs uv, podman (or docker if available), nginx, postgres
#   2. Clones the repo and installs Python deps
#   3. Sets up systemd services for: postgres, showdown, api
#   4. Configures nginx as a reverse proxy with TLS (optional)
#
# Usage:
#   curl -fsSL https://your.host/install.sh | bash
#   # or
#   ./deploy/oci/install.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/your-user/poke-battles.git}"
APP_DIR="${APP_DIR:-/opt/poke-battles}"
DATA_DIR="${DATA_DIR:-/var/lib/poke-battles}"
APP_USER="${APP_USER:-poke}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-80}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "Re-run as root (use sudo)" >&2
        exit 1
    fi
}

install_packages() {
    log "Installing system packages"
    if command -v dnf >/dev/null 2>&1; then
        dnf -y install python3.12 python3.12-pip git nginx postgresql-server postgresql-contrib
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get -y install python3.12 python3.12-venv git nginx postgresql
    else
        log "No supported package manager found"
        exit 1
    fi
}

install_uv() {
    log "Installing uv"
    if ! command -v uv >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
}

create_user() {
    if ! id "$APP_USER" >/dev/null 2>&1; then
        log "Creating app user: $APP_USER"
        useradd --system --home-dir "$DATA_DIR" --shell /bin/bash "$APP_USER"
    fi
    mkdir -p "$DATA_DIR" "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$DATA_DIR" "$APP_DIR"
}

clone_repo() {
    if [[ ! -d "$APP_DIR/.git" ]]; then
        log "Cloning repo"
        sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
    else
        log "Repo already cloned; pulling latest"
        sudo -u "$APP_USER" -H bash -c "cd $APP_DIR && git pull --ff-only"
    fi
}

install_python_deps() {
    log "Installing Python deps"
    sudo -u "$APP_USER" -H bash -c "cd $APP_DIR && uv sync --frozen"
}

setup_showdown() {
    log "Cloning Pokémon Showdown"
    if [[ ! -d "$APP_DIR/packages/engine/server/node_modules" ]]; then
        sudo -u "$APP_USER" -H bash -c "cd $APP_DIR/packages/engine && uv run python -c 'from pokeengine.runner import ensure_showdown; ensure_showdown()'"
    fi
}

write_systemd_unit() {
    local name="$1"
    local exec="$2"
    cat > "/etc/systemd/system/${name}.service" <<EOF
[Unit]
Description=poke-battles ${name}
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=UV_PATH=${APP_DIR}/.venv/bin
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn pokeapi.main:app --host 127.0.0.1 --port ${API_PORT}
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
}

write_nginx_config() {
    cat > /etc/nginx/conf.d/poke-battles.conf <<EOF
server {
    listen ${WEB_PORT} default_server;
    server_name _;

    client_max_body_size 4M;

    location /api/ {
        proxy_pass http://127.0.0.1:${API_PORT}/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:${API_PORT}/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }

    location /health {
        proxy_pass http://127.0.0.1:${API_PORT}/health;
    }

    location / {
        root ${APP_DIR}/web/dist;
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
    rm -f /etc/nginx/sites-enabled/default
}

main() {
    require_root
    install_packages
    install_uv
    create_user
    clone_repo
    install_python_deps
    setup_showdown

    log "Writing systemd unit"
    cat > /etc/systemd/system/poke-battles-api.service <<EOF
[Unit]
Description=poke-battles API
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn pokeapi.main:app --host 127.0.0.1 --port ${API_PORT} --workers 2
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

    log "Writing nginx config"
    write_nginx_config

    log "Enabling + starting services"
    systemctl daemon-reload
    systemctl enable --now poke-battles-api
    systemctl reload nginx || systemctl restart nginx

    log "Done. API on http://127.0.0.1:${API_PORT}, web on :${WEB_PORT}"
    log "Next:  sudo -u ${APP_USER} bash -c 'cd ${APP_DIR} && uv run pokecli health'"
}

main "$@"
