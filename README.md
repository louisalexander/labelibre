<div align="center">

# 🏷️ labelibre

### Set your labels free.

**Print Labelife `.aml` labels on a SUPVAN T50M Pro straight from your Mac over Bluetooth, without the vendor app, without a phone, and in batches.**

[![macOS](https://img.shields.io/badge/macOS-12%2B-000000?style=for-the-badge&logo=apple&logoColor=white)](#-install)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Bluetooth LE](https://img.shields.io/badge/Bluetooth-LE-0082FC?style=for-the-badge&logo=bluetooth&logoColor=white)](https://github.com/hbldh/bleak)
[![Printer](https://img.shields.io/badge/SUPVAN-T50M%20Pro-FF6B35?style=for-the-badge&logo=printer&logoColor=white)](#-supported-hardware)

[![bleak](https://img.shields.io/badge/bleak-%E2%89%A51.0-5A29E4?style=flat-square)](https://github.com/hbldh/bleak)
[![aiohttp](https://img.shields.io/badge/aiohttp-%E2%89%A53.9-2C5BB4?style=flat-square&logo=aiohttp&logoColor=white)](https://docs.aiohttp.org/)
[![Pillow](https://img.shields.io/badge/Pillow-%E2%89%A510-8CA1AF?style=flat-square)](https://python-pillow.org/)
[![uv](https://img.shields.io/badge/built%20with-uv-DE5FE9?style=flat-square&logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![No vendor app](https://img.shields.io/badge/vendor%20app-not%20required-success?style=flat-square)](#)
[![Last commit](https://img.shields.io/github/last-commit/louisalexander/labelibre?style=flat-square)](https://github.com/louisalexander/labelibre/commits/main)
[![Repo size](https://img.shields.io/github/repo-size/louisalexander/labelibre?style=flat-square)](https://github.com/louisalexander/labelibre)
[![Stars](https://img.shields.io/github/stars/louisalexander/labelibre?style=flat-square&logo=github)](https://github.com/louisalexander/labelibre/stargazers)

</div>

---

## ✨ Why?

You design labels in the Labelife app. Then you have to print them **one at a time, from your phone**. For a shelf, a pantry or a whole box of cables, that gets old quickly.

**labelibre** speaks the printer's Bluetooth protocol directly, so you can:

- 📂 **Drag in a whole folder of `.aml` files** and print them all at once
- 🔁 **Print N copies** of each label in a single run
- 👀 **Preview** exactly what will print, as 1-bit PNGs at 8 dots/mm
- 🖥️ Use a **native-feeling Mac app** (a local web UI) *or* a **scriptable CLI**
- 🌚 Tune **density, threshold, dithering, margins and rotation**
- 🧹 Let the app **quit itself** about 2 minutes after you close its tab

## 🚀 Install

```bash
brew install uv          # if you don't have it
git clone https://github.com/louisalexander/labelibre.git
cd labelibre
./install.sh
```

This builds:

| What | Where |
|---|---|
| 🖨️ **Label Printer.app** | `/Applications` (or `~/Applications` if `/Applications` isn't writable) |
| ⌨️ **`labelprint`** CLI | `~/.local/bin/labelprint` |

The first time you print, macOS will ask for Bluetooth permission. Allow it.

## 🖱️ Use the app

1. Open **Label Printer** from Spotlight.
2. A browser tab opens at `http://127.0.0.1:8738`.
3. Drop in `.aml` files or a folder, set the number of copies, and press **Print**.

## ⌨️ Use the CLI

```bash
# Is the printer awake? Which labels are loaded?
labelprint status

# Print every label in a folder, 2 copies each
labelprint print -n 2 ~/Downloads/labels/*.aml

# Render previews without printing
labelprint preview -o /tmp/previews *.aml
```

<details>
<summary><b>All print options</b></summary>

| Flag | Default | Description |
|---|---|---|
| `-n, --copies` | `1` | Copies of each label |
| `--density` | `8` | Darkness, `1`–`15` |
| `--margin` | `8` | Blank dots at each end of the feed |
| `--bytes-per-line` | `48` | Print head width in bytes (`40` or `48`) |
| `--threshold` | `200` | Black/white cutoff, `0`–`255` |
| `--dither` | off | Dither greys instead of thresholding |
| `--rotate180` | off | Rotate the output 180° |

</details>

## ⚠️ Gotchas

> [!IMPORTANT]
> The printer must be **on** and **not connected to your phone**. BLE allows only one connection at a time, so close the Labelife app first.

- Only **`Image`** elements in `.aml` files are rendered. That covers every current Labelife image export. Text and barcode elements are skipped, and you get a warning when that happens.
- Logs are written to `~/Library/Logs/LabelPrinter.log`.

## 🔌 Supported hardware

| Printer | BLE name | Status |
|---|---|---|
| SUPVAN T50M Pro | `T0…` | ✅ Tested |
| Other SUPVAN / Katasymbol models | varies | 🤷 Might work. PRs welcome |

## 🧠 How it works

```
 .aml (LPAPI XML) ──► aml.py ──► 1-bit bitmap @ 8 dots/mm
                                      │
                                      ▼
                    protocol.py ──► print buffers ──► LZMA ──► data frames
                                                                  │
                                                                  ▼
                                             ble.py (bleak) ──► 🖨️ T50M Pro
```

| Module | Role |
|---|---|
| `supvan/protocol.py` | Frames, print buffers, LZMA compression, data frames |
| `supvan/ble.py` | `bleak` transport and the print-job sequence |
| `supvan/aml.py` | `.aml` parser and renderer |
| `supvan/cli.py` | The `labelprint` command |
| `supvan/app.py` + `static/index.html` | Local web UI on port 8738 |
| `tools/` | BLE scanning, GATT dumps, debug prints, icon generation |

## 🙏 Standing on the shoulders of giants

The protocol knowledge comes from community reverse engineering of the Katasymbol app:

- [heeen/supvan-cups](https://github.com/heeen/supvan-cups)
- [bbass07/price-tags](https://github.com/bbass07/price-tags)
- [kcsfelty/supvan-labeler](https://github.com/kcsfelty/supvan-labeler)

## 🤝 Contributing

Got a different SUPVAN model working? Added text or barcode rendering? Open a PR.

---

<div align="center">
<sub>Not affiliated with SUPVAN, Katasymbol or Labelife. Made with 🏷️ and a little too much Bluetooth sniffing.</sub>
</div>
