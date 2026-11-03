# Label Printer — SUPVAN T50M Pro over Bluetooth (macOS)

Batch-prints Labelife `.aml` label files on a SUPVAN T50M Pro (BLE name `T0…`)
without the vendor app.

## Install
    ./install.sh          # builds /Applications/Label Printer.app + ~/.local/bin/labelprint

## Use
* **App:** open *Label Printer* (Spotlight). A browser tab opens: drop `.aml` files or a
  folder, set copies, press Print. The app quits itself ~2 min after its tab is closed.
* **CLI:**
      labelprint status
      labelprint print -n 2 ~/Downloads/labels/*.aml
      labelprint preview -o /tmp/previews *.aml

Printer must be on and **not connected to a phone** (BLE allows one connection).
Logs: `~/Library/Logs/LabelPrinter.log`.

## Layout
* `supvan/protocol.py` – frames, print buffers, LZMA, data frames
* `supvan/ble.py` – bleak transport + print job sequence
* `supvan/aml.py` – `.aml` (LPAPI XML) parser/renderer, 8 dots/mm
* `supvan/app.py`, `supvan/static/index.html` – local web UI (port 8738)

Protocol from community reverse engineering of the Katasymbol app:
heeen/supvan-cups, bbass07/price-tags, kcsfelty/supvan-labeler.
Only `Image` elements in `.aml` files are rendered (all current Labelife image exports);
text/barcode elements are reported as ignored.
