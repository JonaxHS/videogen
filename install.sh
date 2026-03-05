#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║           VideoGen — Auto Installer v1.0                   ║
# ║  github.com/JonaxHS/videogen                               ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

REPO_URL="https://github.com/JonaxHS/videogen.git"
INSTALL_DIR="/opt/videogen"
PORT_FRONTEND=5173
PORT_BACKEND=8000

header() {
  echo ""
  echo -e "${CYAN}${BOLD}╔══════════════════════════════════════╗${NC}"
  echo -e "${CYAN}${BOLD}║        🎬  VideoGen Installer        ║${NC}"
  echo -e "${CYAN}${BOLD}╚══════════════════════════════════════╝${NC}"
  echo ""
}

info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Detect OS ──────────────────────────────────────────────────
detect_os() {
  if [ -f /etc/debian_version ]; then
    OS="debian"
  elif [ -f /etc/redhat-release ]; then
    OS="redhat"
  elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
  else
    OS="unknown"
  fi
}

# ── Install Docker ──────────────────────────────────────────────
install_docker() {
  if command -v docker &>/dev/null; then
    success "Docker ya está instalado ($(docker --version | cut -d' ' -f3 | tr -d ','))"
    return
  fi

  info "Instalando Docker..."

  if [ "$OS" = "debian" ]; then
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  elif [ "$OS" = "redhat" ]; then
    yum install -y -q yum-utils
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    yum install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl start docker
    systemctl enable docker
  elif [ "$OS" = "mac" ]; then
    warn "En Mac instala Docker Desktop manualmente: https://www.docker.com/products/docker-desktop/"
    error "Por favor instala Docker Desktop y vuelve a ejecutar el instalador."
  else
    curl -fsSL https://get.docker.com | sh
  fi

  # Add current user to docker group
  if [ "$EUID" -ne 0 ]; then
    sudo usermod -aG docker "$USER" 2>/dev/null || true
  fi

  success "Docker instalado correctamente"
}

# ── Install Git ─────────────────────────────────────────────────
install_git() {
  if command -v git &>/dev/null; then
    success "Git ya está instalado"
    return
  fi
  info "Instalando Git..."
  if [ "$OS" = "debian" ]; then
    apt-get install -y -qq git
  elif [ "$OS" = "redhat" ]; then
    yum install -y -q git
  fi
  success "Git instalado"
}

# ── Clone / Update repo ─────────────────────────────────────────
setup_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repositorio existente detectado, actualizando..."
    cd "$INSTALL_DIR"
    git pull --quiet origin main
    success "Repositorio actualizado"
  else
    info "Clonando repositorio en $INSTALL_DIR..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    success "Repositorio clonado"
  fi
}

# ── Setup .env ──────────────────────────────────────────────────
setup_env() {
  cd "$INSTALL_DIR"
  if [ ! -f ".env" ]; then
    cp .env.example .env
    info "Archivo .env creado — configura tu API key desde la interfaz web"
  else
    success "Archivo .env ya existe"
  fi
}

# ── Start services ──────────────────────────────────────────────
start_services() {
  cd "$INSTALL_DIR"
  info "Construyendo y levantando contenedores (esto puede tardar unos minutos)..."
  docker compose up --build -d
  success "Servicios iniciados correctamente"
}

# ── Get server IP ───────────────────────────────────────────────
get_ip() {
  IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || \
       curl -s --max-time 5 icanhazip.com 2>/dev/null || \
       hostname -I 2>/dev/null | awk '{print $1}' || \
       echo "TU_IP")
  echo "$IP"
}

# ── Main ────────────────────────────────────────────────────────
main() {
  header

  # Root check for Linux installs
  if [[ "$OSTYPE" != "darwin"* ]] && [ "$EUID" -ne 0 ]; then
    warn "Se recomienda ejecutar como root (sudo) para instalar dependencias"
  fi

  detect_os
  info "Sistema operativo detectado: $OS"
  echo ""

  install_git
  install_docker
  setup_repo
  setup_env
  start_services

  IP=$(get_ip)

  echo ""
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  🎉  ¡VideoGen instalado con éxito!      ${NC}"
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════${NC}"
  echo ""
  echo -e "  ${BOLD}🌐 Abre el asistente de configuración:${NC}"
  echo ""
  echo -e "  ${CYAN}${BOLD}  http://$IP:$PORT_FRONTEND${NC}"
  echo ""
  echo -e "  ${YELLOW}1. Abre esa URL en tu navegador${NC}"
  echo -e "  ${YELLOW}2. Ingresa tu Pexels API key en la pantalla de setup${NC}"
  echo -e "  ${YELLOW}3. ¡Empieza a generar reels!${NC}"
  echo ""
  echo -e "  ${BOLD}Comandos útiles:${NC}"
  echo -e "  ${CYAN}cd $INSTALL_DIR && docker compose logs -f${NC}   # Ver logs"
  echo -e "  ${CYAN}cd $INSTALL_DIR && docker compose down${NC}       # Detener"
  echo -e "  ${CYAN}cd $INSTALL_DIR && docker compose up -d${NC}      # Reiniciar"
  echo ""
}

main "$@"
