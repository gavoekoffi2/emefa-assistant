import json
from pathlib import Path

import pytest

from emefa.infrastructure.email import EmailProviderError, HimalayaEmailProvider


def make_fake(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "calls.jsonl"
    binary = tmp_path / "himalaya"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\n"
        "with open(os.environ['CALL_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "a=sys.argv\n"
        "if 'envelope' in a: print(json.dumps([{'id':'7','from':{'addr':'a@example.com'},'subject':'Sujet','date':'2026-07-20','flags':[]}]))\n"
        "elif 'read' in a: print(json.dumps('Contenu du message'))\n"
        "else: print(json.dumps({'ok':True}))\n"
    )
    binary.chmod(0o755)
    return binary, log


def test_himalaya_adapter_uses_bounded_argument_commands(tmp_path, monkeypatch):
    binary, log = make_fake(tmp_path)
    monkeypatch.setenv("CALL_LOG", str(log))
    provider = HimalayaEmailProvider("graphistegpt", str(binary), tmp_path / "config.toml")

    assert provider.search("devis; touch /tmp/pwn", 100)[0]["from"] == "a@example.com"
    assert provider.read("7")["content"] == "Contenu du message"
    provider.create_draft("client@example.com", "Sujet", "Bonjour")

    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0][calls[0].index("--page-size") + 1] == "20"
    assert "devis; touch /tmp/pwn" in calls[0]
    assert calls[1][-1] == "--preview"
    assert "[Gmail]/Drafts" in calls[2]
    assert not Path("/tmp/pwn").exists()


def test_himalaya_adapter_rejects_header_injection(tmp_path, monkeypatch):
    binary, log = make_fake(tmp_path)
    monkeypatch.setenv("CALL_LOG", str(log))
    provider = HimalayaEmailProvider("graphistegpt", str(binary))
    with pytest.raises(ValueError, match="invalid_subject"):
        provider.send("client@example.com", "Sujet\nBcc: pirate@example.com", "Bonjour")
    assert not log.exists()


def test_himalaya_adapter_normalizes_failures(tmp_path):
    provider = HimalayaEmailProvider("graphistegpt", str(tmp_path / "missing"))
    with pytest.raises(EmailProviderError, match="email_provider_unavailable"):
        provider.search("", 5)
