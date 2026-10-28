# Monitorize for Intel macOS

Port of [vinnavannewton/project-monitorize](https://github.com/vinnavannewton/project-monitorize)
(upstream commit `547c44cbd5982172b3c20a24a21c6a6760aad707`, version 0.34).
Original Linux sources, assets, authorship and GPL-3.0 license are retained.
See [the original README](README.linux.md) for Linux functionality.

This port adds a separate macOS frontend and native CoreGraphics backend:

- Create up to two virtual displays, with independent resolution and refresh rate.
- Select an existing display for streaming without modifying its configuration.
- Launch separate Sunshine profiles for Moonlight, with ports 47989 and 49089.
- Keep credentials, apps and settings separate from an existing Sunshine installation.
- Stop owned Sunshine processes before removing their displays. The helper also
  releases its display when the frontend's stdin pipe closes after a crash.

**Status:** implementation available; native compilation, virtual display creation,
permissions and end-to-end streaming still require verification on an Intel Mac.
Linux tests do not establish macOS compatibility. The macOS CI workflow builds the
helper and wheel and runs native enumeration tests; it has not been run from this workspace.

## Requirements

- Intel Mac (`x86_64`), macOS Monterey 12 or newer, logged-in graphical session.
- Xcode Command Line Tools (`xcode-select --install`).
- Python 3.11+ for Intel, with `venv` and `pip`.
- Sunshine for Intel macOS, optional if only using virtual displays.
- Moonlight on the client for streaming.

`CGVirtualDisplay` is a **private** macOS API. Apple can change or remove it.
This is a source-based desktop port, not a signed/notarized `.app` or App Store build.
No SIP changes, kernel extensions or root permissions are required by this implementation.

## Install and launch on an Intel Mac

From this checkout (each cloud task is already isolated; no extra worktree is needed):

```sh
python3 -m venv .venv
source .venv/bin/activate
bash macos/build-native.sh
python -m pip install .
monitorize
```

Rebuild the helper and reinstall after updating native code. To develop Python code
without reinstalling, use `python -m pip install -e .` after building the helper.
The entry point selects the macOS frontend **before** importing any Linux services.
D-Bus and PyGObject are installed only on Linux.

1. Choose a virtual display or an existing display in either slot, then **Start**.
2. For a virtual display, arrange it using macOS System Settings → Displays.
3. Optionally click **Start Sunshine**, then **Pair / Sunshine settings**.
4. Set Sunshine's web credentials on first use and enter the Moonlight pairing PIN.
5. Connect Moonlight to the Mac. For slot 2, add the host as `MAC_IP:49089`.
6. Click **Stop** before closing. Closing the window stops both owned sessions.

Sunshine must support macOS `output_name` as a **CoreGraphics display ID**, not a
list index. The integration follows LizardByte/Sunshine's macOS backend at commit
`7974a409bb82f2e52a45dad901acdd10fd1d61c1`. Older builds may interpret it differently;
verify the selected display in Sunshine's log before streaming sensitive content.
Install a compatible build separately; Sunshine is not bundled or silently installed.
If it is not on PATH or in `/Applications/Sunshine.app`, set:

```sh
export MONITORIZE_SUNSHINE='/absolute/path/to/sunshine'
monitorize
```

Grant **Screen Recording** and **Accessibility** to the Sunshine executable/app in
System Settings → Privacy & Security; restart the session after granting access.
A process starting does not prove capture works: confirm the intended display from
Moonlight. Sunshine's local HTTPS web UI uses its own self-signed certificate.
The app opens it in the browser; it does not disable TLS verification.

Monitorize profiles and logs live in
`~/Library/Application Support/Monitorize/sunshine-1` and `sunshine-2`.
Web UIs use `https://localhost:47990` and `https://localhost:49090` on the Mac.
Web administration is restricted to the local PC and UPnP is disabled. Allow only
the required Sunshine streaming ports through the macOS firewall for your LAN.
Stop conflicting Sunshine instances if ports are occupied; Monitorize never kills
unrelated processes. Sunshine UI preferences and custom apps survive restarts.

## Validation

Portable configuration tests (Linux or macOS, no Qt required):

```sh
PYTHONPATH=linux python3 -m unittest discover -s macos/tests -v
```

On Intel macOS, build/install first to exercise native enumeration and argument
validation. To also test virtual creation and owner-exit cleanup in a real desktop:

```sh
MONITORIZE_TEST_VIRTUAL=1 python -m unittest discover -s macos/tests -v
```

Before relying on this port, verify on the target Mac:

- Start two virtual displays, check resolution/arrangement, stop each independently.
- Start Sunshine for each slot; pair Moonlight and verify the correct capture target.
- Verify keyboard/mouse permissions, VideoToolbox encoding and reconnect behavior.
- Close the frontend and confirm the owned displays and Sunshine processes disappear.
- Restart and confirm credentials and per-slot settings are retained.

Linux VKMS/compositor drivers, remote login/greeter streaming, systemd startup,
Linux audio routing, touch/stylus integration and the original QML frontend are not
ported. Audio support depends on the separately installed Sunshine and its macOS
audio setup. Virtual displays do not survive quitting Monitorize or logging out.
