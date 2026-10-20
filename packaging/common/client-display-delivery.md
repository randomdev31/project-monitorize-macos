# Client display protocol delivery

The Python app and bundled Sunshine must be delivered together. The native source
installer, Arch package preparation, RPM preparation (Fedora and Tumbleweed), and
DEB build run `check-client-display-protocol.py` before compiling Sunshine. It
rejects old or incomplete source trees missing protocol v1 and its session hooks.
The installed app also checks the binary capability marker before starting a
client-controlled listener. These checks do not replace capture or live-client QA.

Before publishing this feature:

1. Commit and publish the paired `external/sunshine` changes.
2. Update the parent repository's Sunshine gitlink and all active native pins:
   `packaging/arch/sources.conf`, both RPM specs, and each
   `packaging/deb/*/sunshine.mk`.
3. Run the existing clean-submodule, pin equality, and package preflight checks.
   Native builders archive committed `HEAD`; they cannot deliver uncommitted
   development files.
4. Build and test the app and host together. Keep manual streaming as well as
   client-requested display launch in the package smoke tests.

Do not substitute the old pinned commit or invent a future commit hash. Until
the paired changes are committed and published, native release builds are
intentionally blocked. Flatpak support for this workflow remains deferred.

The new Python runtime module is included by the existing setuptools
`monitorize*` package discovery; it needs no separate installed helper entrypoint.

Guarded KDE layouts also require the binary marker `MONITORIZE_LAYOUT_RECOVERY=1`
and first-frame `stream_ready` hook. The installed Python packages include
`platform/session_layout.py` and `streaming/recovery_guardian.py` through existing
package discovery. The guardian runs as the desktop user and uses existing
`kscreen-doctor`; it requires no new root entrypoint. Its session journal and lock
must not be removed while recovery owns a live output. Full host rebuild and live
layout/capture/input/recovery QA are required; source/unit proof is insufficient.
