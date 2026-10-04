"""Spike: a 'no leading $' pattern that Ollama converts AND that allows multi-line text. Throwaway."""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import post  # noqa: E402

CANDIDATES = ["^([^$](.|\\n)*)?$", "^([^$]|\\n)?(.|\\n)*$", "^(|[^$][^\\u0000]*)$", "^([^$][^$]*|[^$].*)?$"]
for pat in CANDIDATES:
    ok_ml = re.fullmatch(pat.replace("\\u0000", "\\x00"), "# Title\nbody") is not None
    rejects = re.fullmatch(pat.replace("\\u0000", "\\x00"), "$secret:X") is None
    schema = {"type": "object", "required": ["v"], "properties": {"v": {"type": "string", "pattern": pat}}}
    since = subprocess.run(["date", "+%H:%M:%S"], capture_output=True, text=True).stdout.strip()
    r = post("/api/chat", {"model": "qwen3:4b", "stream": False, "think": False, "format": schema,
                           "options": {"num_gpu": 99, "num_predict": 200},
                           "messages": [{"role": "user", "content": 'Set v to "$secret:X"'}]})
    warn = subprocess.run(["journalctl", "-u", "ollama", "--since", since, "--no-pager"],
                          capture_output=True, text=True).stdout
    converted = "conversion was incomplete" not in warn
    print(f"{pat:<28} validator: multiline={ok_ml} rejects$={rejects} | ollama converted={converted} "
          f"output={r['message']['content'][:60]!r}")
