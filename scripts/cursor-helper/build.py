"""Embed the local extension and transport into the standalone use-venv command."""

import base64
import io
import json
import re
import zipfile
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def payload():
    manifest = json.loads((ROOT / "package.json").read_text())
    manifest["useVenvRevision"] = sha256(
        (ROOT / "extension.js").read_bytes()
    ).hexdigest()
    files = {
        "extension/package.json": json.dumps(manifest).encode(),
        "extension/extension.js": (ROOT / "extension.js").read_bytes(),
        "client.py": (ROOT / "client.py").read_bytes(),
        "extension.vsixmanifest": f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata><Identity Language="en-US" Id="use-venv-helper" Version="{manifest["version"]}" Publisher="ai-demo-local"/>
<DisplayName>use-venv Helper</DisplayName><Description xml:space="preserve">Local workspace automation</Description>
<Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.96.0"/></Properties></Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/>
<Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''.encode(),
        "[Content_Types].xml": b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="py" ContentType="text/plain"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>""",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


if __name__ == "__main__":
    script = ROOT.parent / "use-venv.zsh"
    source = script.read_text()
    source, count = re.subn(
        r'^HELPER_ARCHIVE_B64 = "[^"]*"$',
        'HELPER_ARCHIVE_B64 = "' + base64.b64encode(payload()).decode() + '"',
        source,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("Expected exactly one embedded helper marker")
    script.write_text(source)
