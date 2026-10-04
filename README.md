# Quartus II 9.0 SP2 in Docker

Compile legacy Altera FPGA projects on Linux with **Quartus II 9.0 SP2 Web
Edition**, running under Wine. The image includes support for **ACEX1K EP1K50
and EP1K100**, and provides the familiar `quartus_sh --flow compile` interface.

- **Container image:** [`doorsfan/quartus:9.0sp2`](https://hub.docker.com/r/doorsfan/quartus/tags)
- **Platform:** `linux/amd64`
- **Runtime:** Debian Bookworm, 32-bit Wine, and Xvfb
- **Scope:** command-line compilation and programming-file generation

Docker includes the Wine runtime, so the host does not need Quartus, Wine, or a
graphical desktop installed. The examples below use a Linux shell and Docker
Engine. Omit `sudo` if your user already has permission to run Docker.

## Quick start

Download the image and check the compiler version:

```sh
sudo docker pull doorsfan/quartus:9.0sp2
sudo docker run --rm doorsfan/quartus:9.0sp2 quartus_sh --version
```

From a directory containing your Quartus project, run:

```sh
sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:/build" \
  doorsfan/quartus:9.0sp2 \
  quartus_sh --flow compile my_project -c my_revision
```

Replace `my_project` with the project name (the `.qpf` extension is optional)
and `my_revision` with the settings filename without `.qsf`. For example,
`pentevo.qpf` with revision `top.qsf` uses `pentevo -c top`.

Reports and programming files are saved in the mounted project directory,
according to its settings. To generate an RBF as part of compilation, enable
this assignment in the project's QSF:

```tcl
set_global_assignment -name GENERATE_RBF_FILE ON
```

Other installed `quartus_*` commands, including `quartus_map`, `quartus_fit`,
`quartus_asm`, and `quartus_cpf`, can be passed to the image in the same way.

## Example: build ZX Evolution from TS-Labs

The [tslabs/zx-evo](https://github.com/tslabs/zx-evo) repository includes the
`pentevo/fpga/base/quartus_vdac2` project. This example builds that **base
configuration** for **EP1K50QC208-3**, using revision `top`.

Clone the source and run the compiler from the root of the checkout:

```sh
git clone https://github.com/tslabs/zx-evo.git
cd zx-evo

sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:/build" \
  -w /build/pentevo/fpga/base/quartus_vdac2 \
  doorsfan/quartus:9.0sp2 \
  quartus_sh --flow compile pentevo -c top
```

The project already enables RBF generation. Its output files are:

```text
pentevo/fpga/base/quartus_vdac2/top.rbf
pentevo/fpga/base/quartus_vdac2/top.sof
```

Compilation replaces the bitstreams bundled with the checkout. Mount the
**entire `zx-evo` directory**, because the project references source files in
sibling directories.

Use **`-c top`**. Quartus 9.0's flow script otherwise defaults to a revision
named after the project, creating `pentevo.qsf` and failing with:

```text
Error: Top-level design entity "pentevo" is undefined
```

The example was validated with upstream commit
[`9ce7544a0167924912dd60eba41b64e0bee9122b`](https://github.com/tslabs/zx-evo/commit/9ce7544a0167924912dd60eba41b64e0bee9122b).
To reproduce the same source version, check out that commit before compiling:

```sh
git checkout 9ce7544a0167924912dd60eba41b64e0bee9122b
```

### What the Docker options mean

| Option | Purpose |
| --- | --- |
| `--rm` | Removes the container after the compiler exits. Files in the mounted project remain. |
| `--user "$(id -u):$(id -g)"` | Uses your Linux user and group IDs so generated files belong to you with standard Docker Engine UID mapping. |
| `-v "$PWD:/build"` | Makes the current host directory available at `/build`, with read/write access. |
| `-w /build/pentevo/fpga/base/quartus_vdac2` | Sets the compiler's working directory inside the container. |

`$PWD` is the shell's current directory. The shell evaluates `id -u` and
`id -g` before invoking `sudo`. Rootless Docker and custom user namespace
mapping can require different ownership settings.

## Build the image yourself

Clone this repository:

```sh
git clone https://github.com/d00rsfan/quartus9-docker.git
cd quartus9-docker
```

Place your Windows Quartus II 9.0 SP2 Web Edition installer,
**`90sp2_quartus_free.exe`**, beside the Dockerfile. The installer is not included
in this source repository or downloaded by the build. The extractor accepts
only the installer with this SHA-256 checksum:

```text
aba011bbe101a4f555b222d02fca99a99104610ea35cf7e0102c3fac27230298
```

Check the file and build:

```sh
sha256sum 90sp2_quartus_free.exe
sudo docker build --platform linux/amd64 -t quartus:9.0sp2 .
sudo docker run --rm quartus:9.0sp2 quartus_sh --version
```

Use `quartus:9.0sp2` instead of `doorsfan/quartus:9.0sp2` in the examples to run
your local build.

The Dockerfile works with both the legacy builder and BuildKit. It downloads
the Debian base image and packages, extracts the supplied installer, and runs
full test compiles for **EP1K50QC208-3** and **EP1K100QC208-3**. Both must produce
a nonempty `.sof` for the image build to succeed.

Allow space for the roughly 1.4 GB installer, 3 GB extracted installation, Wine,
and Docker's intermediate layers and cache. The final image contains the
extracted installation; the installer remains in the build cache's extraction
stage.

## EP1K100 / 100K ACEX1K projects

The same image builds either density. Select your exact part in the project's
QSF, for example:

```tcl
set_global_assignment -name FAMILY ACEX1K
set_global_assignment -name DEVICE EP1K100QC208-3
```

Use pin assignments and constraints for your own board and package. The ZX
Evolution example above targets EP1K50; changing its device alone does not port
the design to another board.

## Validation

The image was built and tested on 2026-10-04:

| Design | Target | Result |
| --- | --- | --- |
| Included counter test | EP1K50QC208-3 | Full compile and `.sof` generation passed |
| Included counter test | EP1K100QC208-3 | Full compile and `.sof` generation passed |
| TS-Labs ZX Evolution base, `quartus_vdac2`, revision `top` | EP1K50QC208-3 | Full compile passed; `.sof` and `.rbf` generated |

The ZX Evolution build reported **0 errors and 180 warnings**, with **2,161 /
2,880 logic elements (75%)** used. Its flow report states that timing
requirements were met. Hardware behavior has not been tested.

The design warnings include a missing `none.mif` initialization file, for which
Quartus used zero-filled memory, alongside the inferred palette RAM. Review
the project's reports when evaluating the generated bitstream.

Run the launcher tests without Docker or a working Wine installation:

```sh
python3 -m unittest discover -s tests -v
```

These tests cover argument handling, the working directory, exit status,
temporary-prefix cleanup, and command validation. The FPGA compile tests in
the Dockerfile separately exercise Quartus under Wine. The counter design has
no board pin assignments and is intended only as a compiler test.

## How it works

[`scripts/extract-quartus.py`](scripts/extract-quartus.py) extracts the pinned
installer without running the InstallShield GUI. It verifies file sizes and
embedded MD5 checksums and preserves the vendor license files. Cabinet layout
and compression were checked against [Unshield](https://github.com/twogood/unshield).
Python 3.11 or newer is required for extraction; Docker installs it in the
extraction stage.

[`scripts/run-quartus.sh`](scripts/run-quartus.sh) creates a private temporary
Wine prefix for each invocation, enables Windows XP compatibility, and runs
the requested compiler under Xvfb. The installation appears at
`C:/altera/90sp2`; `/build` is also accessible as `Z:/build`. Quartus's exit code
is returned to Docker, and the Wine prefix is removed when the command ends.

### Optional: run with host Wine

Docker is the validated runtime. A convenience launcher is also included for
host Wine, but that execution mode has not been validated:

```sh
python3 scripts/extract-quartus.py 90sp2_quartus_free.exe .local/altera/90sp2
./quartus-local quartus_sh --version
```

The destination must be empty before extraction. The host needs `wine`,
`wineboot`, `wineserver`, `xvfb-run`, and `xauth`, with support for 32-bit Windows
applications. The local launcher defaults to a `win64` prefix for WoW64 Wine;
older Wine installations may need `WINEARCH=win32 ./quartus-local ...`.

## Troubleshooting

- **`Top-level design entity "pentevo" is undefined`:** pass `-c top` for the
  ZX Evolution example so Quartus loads `top.qsf`.
- **Source files are missing:** mount the common parent of the project and its
  source folders, and set `-w` to the directory containing the project. Use
  relative source paths or Wine paths such as `Z:/build/...`.
- **`X connection to :99 broken` after Quartus finishes:** this is an Xvfb
  shutdown diagnostic from Wine processes still connected to the display.
  Check the compiler's result, exit status, and generated files.
- **`wine: created the configuration directory ...`:** expected on each run,
  because the launcher creates a fresh temporary Wine prefix.
- **Wine diagnostics:** add `-e WINEDEBUG=+seh,+loaddll` before the image name,
  or set that environment variable when using `quartus-local`.

USB-Blaster/JTAG access and interactive GUI use are outside the tested scope.

## Third-party software

Quartus is proprietary Altera software and remains subject to its original
license terms. Those terms are preserved in `/opt/altera/90sp2/licenses` inside
the image and `.local/altera/90sp2/licenses` after local extraction. The GitHub
repository contains the Dockerfile, scripts, and tests; the installer and
extracted Quartus files are excluded.

The ZX Evolution project belongs to its upstream authors and is linked as a
usage example. It is not included in this repository. This project is not
affiliated with or endorsed by Altera or TS-Labs.
