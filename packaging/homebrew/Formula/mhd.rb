class Mhd < Formula
  desc "Planning-first multi-agent hardware design CLI"
  homepage "https://github.com/jacoboforero/FPGA_Design_Agent"
  head "https://github.com/jacoboforero/FPGA_Design_Agent.git"

  depends_on "python@3.12"
  depends_on "icarus-verilog"
  depends_on "verilator"

  def install
    python = Formula["python@3.12"].opt_bin/"python3.12"
    runtime_root = libexec/"runtime"
    system python, buildpath/"packaging/homebrew/stage_runtime.py", buildpath, runtime_root

    venv = libexec/"venv"
    system python, "-m", "venv", venv
    pip = venv/"bin/pip"
    system pip, "install", "--upgrade", "pip", "setuptools", "wheel"
    system pip, "install", "-r", buildpath/"packaging/homebrew/requirements.txt"

    (bin/"mhd").write <<~EOS
      #!/bin/bash
      export MHD_RESOURCE_ROOT="#{runtime_root}"
      export MHD_TOOL_REGISTRY_PATH="#{runtime_root/"tool_registry.yaml"}"
      export MHD_INSTALL_CONTEXT="1"
      export USE_LLM="1"
      if [[ -n "\${PYTHONPATH:-}" ]]; then
        export PYTHONPATH="#{runtime_root}:\$PYTHONPATH"
      else
        export PYTHONPATH="#{runtime_root}"
      fi
      exec "#{venv/"bin/python"}" -m apps.cli.cli "\$@"
    EOS
    chmod 0555, bin/"mhd"
  end

  test do
    ENV["OPENAI_API_KEY"] = "dummy"
    ENV["XDG_CONFIG_HOME"] = testpath/".config"
    system bin/"mhd", "--help"
    system bin/"mhd", "doctor"
    assert_predicate testpath/".config/mhd/runtime.yaml", :exist?
    assert_predicate testpath/".config/mhd/runtime.benchmark.yaml", :exist?
  end

  def caveats
    <<~EOS
      Runtime prerequisites:
        - RabbitMQ must already be installed and running.
        - mhd reads credentials from your shell environment.

      Suggested setup:
        brew install rabbitmq
        brew services start rabbitmq
        echo 'export OPENAI_API_KEY=...' >> ~/.zshrc
        echo 'export RABBITMQ_URL=amqp://guest:guest@localhost:5672/' >> ~/.zshrc
        exec zsh -l
        mhd doctor

      Config location:
        - First run seeds $XDG_CONFIG_HOME/mhd when XDG_CONFIG_HOME is set.
        - Otherwise mhd seeds ~/.config/mhd.
    EOS
  end
end
