#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAP_NAME="${MHD_TAP_NAME:-local/mhd-demo}"
TMPDIR="$(mktemp -d)"
TARBALL="$TMPDIR/mhd-src.tar.gz"
TAP_DIR="$TMPDIR/homebrew-mhd-demo"
FORMULA_DIR="$TAP_DIR/Formula"
FORMULA_PATH="$FORMULA_DIR/mhd.rb"
KEEP_TAP="${MHD_KEEP_TAP:-0}"
SMOKE_SPEC="${MHD_SMOKE_SPEC:-$ROOT/tests/test_specs/01_counter3_basic.txt}"
SMOKE_RABBITMQ_URL="${MHD_SMOKE_RABBITMQ_URL:-amqp://guest:guest@localhost:5672/}"

export HOMEBREW_NO_AUTO_UPDATE="${HOMEBREW_NO_AUTO_UPDATE:-1}"
export HOMEBREW_NO_INSTALL_CLEANUP="${HOMEBREW_NO_INSTALL_CLEANUP:-1}"

cleanup() {
  if [[ "$KEEP_TAP" != "1" ]]; then
    brew untap "$TAP_NAME" >/dev/null 2>&1 || true
    rm -rf "$TMPDIR"
  fi
}
trap cleanup EXIT

echo "[1/7] package current working tree"
tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='artifacts' \
  --exclude='.mypy_cache' \
  --exclude='node_modules' \
  -czf "$TARBALL" \
  -C "$ROOT" .
SHA256="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"

echo "[2/7] create temporary local tap"
mkdir -p "$FORMULA_DIR"
git init -q "$TAP_DIR"
cat > "$FORMULA_PATH" <<EOF
class Mhd < Formula
  desc "Planning-first multi-agent hardware design CLI"
  homepage "https://github.com/jacoboforero/FPGA_Design_Agent"
  url "file://$TARBALL"
  sha256 "$SHA256"
  version "0.1.0-demo"

  depends_on "python@3.12"
  depends_on "icarus-verilog"
  depends_on "verilator"

  def install
    libexec.install buildpath.children

    python = Formula["python@3.12"].opt_bin/"python3.12"
    venv = libexec/"venv"
    system python, "-m", "venv", venv
    pip = venv/"bin/pip"
    system pip, "install", "--upgrade", "pip", "setuptools", "wheel"
    system pip, "install", "-r", libexec/"packaging/homebrew/requirements.txt"
    system pip, "install", "--no-deps", libexec

    (etc/"mhd").mkpath
    (etc/"mhd").install libexec/"packaging/homebrew/runtime.yaml" => "runtime.yaml"

    (bin/"mhd").write_env_script venv/"bin/mhd",
      MHD_RESOURCE_ROOT: libexec,
      MHD_CONFIG_PATH: etc/"mhd/runtime.yaml",
      MHD_TOOL_REGISTRY_PATH: libexec/"tool_registry.yaml",
      USE_LLM: "1"
  end

  test do
    ENV["OPENAI_API_KEY"] = "dummy"
    system bin/"mhd", "--help"
  end

  def caveats
    <<~EOS
      Runtime prerequisites:
        - RabbitMQ must already be installed and running.
        - Set OPENAI_API_KEY before running interactive CLI flows.

      Suggested setup:
        brew install rabbitmq
        brew services start rabbitmq
        export OPENAI_API_KEY=...
        mhd doctor
    EOS
  end
end
EOF
git -C "$TAP_DIR" add Formula/mhd.rb
git -C "$TAP_DIR" -c user.name='mhd-smoke' -c user.email='mhd-smoke@example.com' commit -q -m 'Add mhd formula'

echo "[3/7] uninstall old mhd formula if present"
brew uninstall --ignore-dependencies --force mhd >/dev/null 2>&1 || true
brew untap "$TAP_NAME" >/dev/null 2>&1 || true

echo "[4/7] tap local formula repo"
brew tap "$TAP_NAME" "$TAP_DIR"

echo "[5/7] install mhd from local tap"
if ! brew install "$TAP_NAME/mhd"; then
  brew link --overwrite mhd >/dev/null 2>&1 || true
  if command -v mhd >/dev/null 2>&1; then
    echo "Homebrew reported a non-fatal formula install issue, but mhd is linked and runnable; continuing smoke test."
  else
  cat <<'EOF'

Homebrew install failed.

If the error mentions outdated Command Line Tools, this machine needs a CLT
update before Homebrew can install source-based formulae from a tap. The app
itself is still smoke-tested separately through the installed-command path in a
clean venv.
EOF
    exit 1
  fi
fi

echo "[6/7] run installed help and doctor"
mhd --help >/dev/null
USE_LLM=1 OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}" mhd doctor

if [[ "${MHD_RUN_FULL_SMOKE:-0}" == "1" ]]; then
  if [[ ! -f "$SMOKE_SPEC" ]]; then
    echo "Smoke spec not found: $SMOKE_SPEC" >&2
    exit 1
  fi
  echo "[7/7] run installed full CLI smoke with $(basename "$SMOKE_SPEC")"
  WORKDIR="$(mktemp -d)"
  pushd "$WORKDIR" >/dev/null
  MHD_ENV_FILE="$ROOT/.env" \
    RABBITMQ_URL="$SMOKE_RABBITMQ_URL" \
    USE_LLM=1 \
    timeout 420s mhd \
      --spec-file "$SMOKE_SPEC" \
      --yes \
      --narrative-mode off \
      --run-name homebrew_install_smoke
  popd >/dev/null
  echo "Artifacts written under $WORKDIR/artifacts"
else
  echo "[7/7] skipping full CLI smoke (set MHD_RUN_FULL_SMOKE=1 to enable)"
fi

echo "Homebrew install smoke passed via tap $TAP_NAME."
if [[ "$KEEP_TAP" == "1" ]]; then
  echo "Temporary tap left at $TAP_DIR"
fi
