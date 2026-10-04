#!/usr/bin/env python3
"""Extract the supplied 9.0 SP2 installer without executing InstallShield.

This deliberately supports only the SHA-256-pinned installer below. Cabinet
layout and compression were checked against the MIT-licensed Unshield project:
https://github.com/twogood/unshield/tree/main/lib
Destination paths come from this installer's own file-group records.
"""

import argparse
import hashlib
import mmap
from pathlib import Path, PureWindowsPath
import struct
import zlib

INSTALLER_SHA256 = "aba011bbe101a4f555b222d02fca99a99104610ea35cf7e0102c3fac27230298"


def unpack(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError(f"Destination must be empty: {destination}")
    with source.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != INSTALLER_SHA256:
            raise ValueError(f"Unexpected installer SHA-256: {digest}")
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            extract(data, destination.resolve())


def extract(data, destination):
    # The PE overlay contains name, Disk1 path, version, decimal size (all
    # NUL-terminated), followed by that file's bytes. No temporary CAB copies.
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    offset = 0
    for index in range(sections):
        size, start = struct.unpack_from("<II", data, pe + 24 + optional_size + index * 40 + 16)
        offset = max(offset, start + size)
    members = {}
    while offset < len(data):
        fields = []
        for _ in range(4):
            end = data.find(b"\0", offset, offset + 1024)
            if end < 0:
                raise ValueError("Unterminated installer field")
            fields.append(data[offset:end].decode("ascii"))
            offset = end + 1
        name, path, _, size = fields
        size = int(size)
        if path != "Disk1\\" + name or offset + size > len(data) or name in members:
            raise ValueError(f"Invalid installer member: {name}")
        members[name] = (offset, size)
        offset += size

    start, size = members["data1.hdr"]
    header = data[start:start + size]

    def u32(pos):
        return struct.unpack_from("<I", header, pos)[0]

    def string(pos):
        return header[pos:header.index(b"\0", pos)].decode("cp1252")

    if header[:8] != b"ISc(\0\x95\0\x01":
        raise ValueError("Unexpected cabinet version")
    descriptor = u32(12)
    table = descriptor + u32(descriptor + 12)
    count = u32(descriptor + 40)
    records = table + u32(descriptor + 44)
    directories = [string(table + u32(table + i * 4)) for i in range(u32(descriptor + 28))]

    def record(index):
        if not 0 <= index < count:
            raise ValueError("Invalid file index")
        return records + index * 87

    def contents(index):
        seen = set()
        pos = record(index)
        # Linked descriptors share payloads, including across file groups.
        while header[pos + 84] & 1:
            if index in seen:
                raise ValueError("Cyclic cabinet file link")
            seen.add(index)
            index = u32(pos + 76)
            pos = record(index)
        flags, expanded, compressed, relative = struct.unpack_from("<HQQQ", header, pos)
        if flags not in (0, 4):
            raise ValueError(f"Unsupported file flags: {flags}")
        volume = struct.unpack_from("<H", header, pos + 85)[0]
        cab_start, cab_size = members[f"data{volume}.cab"]
        length = compressed if flags & 4 else expanded
        if relative + length > cab_size:
            raise ValueError("Cabinet payload out of bounds")
        payload = data[cab_start + relative:cab_start + relative + length]
        if flags & 4:
            result = bytearray()
            cursor = 0
            while cursor < len(payload):
                chunk_size = struct.unpack_from("<H", payload, cursor)[0]
                cursor += 2
                if not chunk_size or cursor + chunk_size > len(payload):
                    raise ValueError("Invalid compressed chunk")
                result.extend(zlib.decompress(payload[cursor:cursor + chunk_size] + b"\0", -15))
                cursor += chunk_size
            payload = result
        if len(payload) != expanded or hashlib.md5(payload).digest() != header[pos + 26:pos + 42]:
            raise ValueError(f"Size/checksum mismatch for file {index}")
        return payload

    roots = {"<TARGETDIR>": "quartus", "<IP_DIR>": "ip",
             "<QDESIGNS_DIR>": "qdesigns", "<FLEXLM_DIR>": "quartus/bin"}
    written = {}
    total = 0

    def write(index, prefix):
        nonlocal total
        pos = record(index)
        flags = struct.unpack_from("<H", header, pos)[0]
        if flags & 8 or not u32(pos + 58):
            return
        name = string(table + u32(pos + 58))
        directory = directories[struct.unpack_from("<H", header, pos + 62)[0]]
        relative = PureWindowsPath(directory) / name
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError(f"Unsafe archive path: {relative}")
        target = destination / prefix / Path(*relative.parts)
        payload = contents(index)
        # Verify the target descriptor as well as the resolved linked payload.
        checksum = hashlib.md5(payload).digest()
        if checksum != header[pos + 26:pos + 42]:
            raise ValueError(f"Linked file checksum mismatch: {target}")
        if target in written:
            if written[target] != checksum:
                raise ValueError(f"Conflicting archive destinations: {target}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written[target] = checksum
        total += len(payload)

    groups = []
    for bucket in range(71):
        node = u32(descriptor + 0x3E + bucket * 4)
        while node:
            name_offset, group_offset, node = struct.unpack_from("<III", header, descriptor + node)
            group = descriptor + group_offset
            first, last = struct.unpack_from("<ii", header, group + 22)
            target = string(descriptor + u32(group + 58))
            groups.append((first, last, string(descriptor + name_offset), target))
    for first, last, name, target in sorted(groups):
        if first < 0:
            continue
        root, _, suffix = target.partition("\\")
        if root not in roots:
            continue
        prefix = Path(roots[root], *PureWindowsPath(suffix).parts)
        print(f"Extracting {name} -> {prefix}", flush=True)
        for index in range(first, last + 1):
            write(index, prefix)
    # Preserve the vendor agreements shipped with the installation wizard.
    for index in range(count):
        pos = record(index)
        if u32(pos + 58) and string(table + u32(pos + 58)) in ("license.txt", "integrated_license.txt"):
            if struct.unpack_from("<H", header, pos + 62)[0] == 0:
                write(index, Path("licenses"))
    if not (destination / "quartus/bin/quartus_sh.exe").is_file():
        raise ValueError("Compiler missing after extraction")
    print(f"Verified and extracted {len(written)} files ({total:,} bytes).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    unpack(args.installer, args.destination)
