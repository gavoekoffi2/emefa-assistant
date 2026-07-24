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
    assert "message" in calls[2]
    assert "save" in calls[2]
    assert not Path("/tmp/pwn").exists()


def test_himalaya_adapter_sends_plain_text_as_mime_not_mml_template(tmp_path, monkeypatch):
    binary, log = make_fake(tmp_path)
    monkeypatch.setenv("CALL_LOG", str(log))
    provider = HimalayaEmailProvider(
        "graphistegpt", str(binary), sender="assistant@example.com"
    )

    result = provider.send(
        "client@example.com",
        "Compte rendu – été",
        "Bonjour,\n\nVoici [la référence] et les prochaines étapes.\nCordialement.",
    )

    assert result["status"] == "sent"
    call = json.loads(log.read_text().splitlines()[-1])
    assert "message" in call
    assert "send" in call
    assert "template" not in call
    raw_message = call[-1]
    assert "Content-Type: text/plain" in raw_message
    assert "Content-Transfer-Encoding:" in raw_message
    assert "From: assistant@example.com" in raw_message
    assert "To: client@example.com" in raw_message
    assert "Subject:" in raw_message


def test_himalaya_adapter_rejects_header_injection(tmp_path, monkeypatch):
    binary, log = make_fake(tmp_path)
    monkeypatch.setenv("CALL_LOG", str(log))
    provider = HimalayaEmailProvider("graphistegpt", str(binary))
    with pytest.raises(ValueError, match="invalid_subject"):
        provider.send("client@example.com", "Sujet\nBcc: pirate@example.com", "Bonjour")
    assert not log.exists()


def test_smtp_backend_reuses_himalaya_config_and_starttls(tmp_path, monkeypatch):
    password_command = tmp_path / "password"
    password_command.write_text("#!/bin/sh\nprintf app-password")
    password_command.chmod(0o700)
    config = tmp_path / "config.toml"
    config.write_text(
        f'''[accounts.graphistegpt]\nemail = "assistant@example.com"\n\n'''
        '''[accounts.graphistegpt.message.send.backend]\ntype = "smtp"\nhost = "smtp.example.com"\nport = 587\n\n'''
        '''[accounts.graphistegpt.message.send.backend.encryption]\ntype = "start-tls"\n\n'''
        '''[accounts.graphistegpt.message.send.backend.auth]\ntype = "password"\n'''
        f'cmd = "{password_command}"\n'
    )
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            events.append(("close",))

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self, context):
            events.append(("starttls", bool(context)))

        def login(self, sender, password):
            events.append(("login", sender, password))

        def send_message(self, message):
            events.append(("send", message["From"], message["To"], message["Subject"]))

    monkeypatch.setattr("emefa.infrastructure.email.smtplib.SMTP", FakeSMTP)
    provider = HimalayaEmailProvider("graphistegpt", config=config)

    result = provider.send("client@example.com", "Sujet", "Bonjour")

    assert result["status"] == "sent"
    assert ("connect", "smtp.example.com", 587, 30.0) in events
    assert ("starttls", True) in events
    assert ("login", "assistant@example.com", "app-password") in events
    assert ("send", "assistant@example.com", "client@example.com", "Sujet") in events


def test_himalaya_adapter_normalizes_failures(tmp_path):
    provider = HimalayaEmailProvider("graphistegpt", str(tmp_path / "missing"))
    with pytest.raises(EmailProviderError, match="email_provider_unavailable"):
        provider.search("", 5)
