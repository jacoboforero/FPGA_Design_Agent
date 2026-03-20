class Mhd < Formula
  desc "Planning-first multi-agent hardware design CLI"
  homepage "https://github.com/jacoboforero/FPGA_Design_Agent"
  head "https://github.com/jacoboforero/FPGA_Design_Agent.git"

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
