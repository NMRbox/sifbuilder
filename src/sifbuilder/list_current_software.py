#!/usr/bin/env python3
from pathlib import Path

def iter_stanzas(path: Path):
    buf = []
    for line in path.read_text().splitlines():
        if line.strip():
            buf.append(line)
        elif buf:
            yield buf; buf = []
    if buf:
        yield buf

def find_nmrbox_software(status_path=Path("/var/lib/dpkg/status")):
    for stanza in iter_stanzas(status_path):
        fields = {}
        for line in stanza:
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        if fields.get("Status") == "install ok installed" and "Nmrbox-Software" in fields:
            print(fields["Nmrbox-Software"].upper())

if __name__ == "__main__":
    find_nmrbox_software()

