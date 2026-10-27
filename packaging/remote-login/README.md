# Remote login integration status

## Current installation workflow

Native Arch/RPM/DEB packages include the remote-login service assets and private
setup helper. Install compatible `monitorize-vkms` host support separately, then
enable **Settings → Start Monitorize after login → Also start at boot**. No source
checkout or source deployment script is required for native packages. If app assets
are missing or out of sync, reinstall/upgrade the Monitorize package with the package
manager; the source installer deliberately refuses to overwrite package-owned files.

The per-user source installer (`linux/scripts/install.sh`) builds the desktop app
and streaming engine. Login-screen startup additionally needs a root-installed
service bundle. Fully stop streaming and **Quit Monitorize from the tray menu**;
closing its window can leave Sunshine and the VKMS D-Bus service running. From the
repository root, prepare a new bundle:

```sh
cd /path/to/Monitorize
python3 scripts/stage-remote-login.py
```

After a source rebuild, an enabled remote-login installation must use the same
engine as the desktop. The source installer checks the actual binary contents;
if they differ, it stages the new desktop engine and prints repair commands,
then exits with status 1 instead of claiming a complete installation. Follow
those commands and restart the services or reboot. Keep the existing enrollment
and pairing. Changing `--cuda=off` to `--cuda=on` requires this system update too.
The desktop also reports a mismatch before handing off to the stale engine.

Native packages use the same installed engine for desktop and boot hosting and
update it through the package manager. NVIDIA encoding requires a CUDA-enabled
package; a build explicitly made without CUDA cannot provide NVENC. Encoder
startup errors now identify NVIDIA failure and its source/package repair options.

The engine/assets paths default to this checkout, and a new temporary stage is
chosen automatically. The script prints absolute administrator install commands
that work from any directory. Run those commands, reopen Monitorize, and enable
the boot option in Settings. Staging success alone does not mean installation
succeeded. An installer message saying Sunshine is running means nothing has
been installed; quit the app and retry that installer command.

To update source-managed host Python support in the same bundle, add
`--vkms-source /path/to/monitorize-vkms`. The host/bootstrap and kernel module must
already be installed. This option does not rebuild or reload the kernel module.

Always prepare a **new stage after changing source code**. The source asset installer
checks its service code against the checkout and rejects stale bundles before
changing system files. The GUI also detects different compatibility checks in the
app and privileged helper and gives the appropriate source/native repair action.
Use **Refresh startup status** after repairing prerequisites. If source code itself
changed, reopen the app to load it. A system-assets/version-check repair does not
require reinstalling VKMS or rebooting just to retry setup; reboot only when setup
reports it is required to apply the saved boot configuration or a kernel update.

Both `1.0` and `1.0.0` are accepted host versions. The minimum version remains
0.3.0; boot-display, on-demand greeter and idle-display protocol v1 must each be
advertised by both the host implementation and its matching capabilities manifest.
Additional protocol keys are allowed. Version/manifest disagreement, a missing
protocol, and incomplete service assets are reported separately.

The deployment notes below include historical experiments and temporary paths;
use the workflow above for a fresh install or update.

## Native app upgrades and removal

Arch, Fedora, openSUSE Tumbleweed, Debian Trixie and both Ubuntu targets share
the app package lifecycle helper. Unused remote login passes silently. An idle
enrollment is paused, its protected display is released, and its previous running
state is restored after upgrade. Settings, startup enablement, pairing and manual
Sunshine profiles are preserved. Existing administrator masks remain in place.

An active client, pending launch or unverifiable engine state requires explicit
disconnect approval. From a local terminal, prepare the transaction, then rerun
the usual package command:

```bash
sudo /usr/bin/python3 -I /usr/libexec/monitorize/remote-login/package-guard.py --prepare upgrade --allow-disconnect
```

Use `--prepare remove --allow-disconnect` for removal. Removal stops the managed
services, releases their reservation and disables remote-login startup; pairing
and other saved settings remain. Preparing removal takes effect immediately,
even if the subsequent package transaction is cancelled.

Preparation uses the setup lock, a private root recovery receipt and temporary
systemd masks. Runners refuse new launches during maintenance and acknowledge
their idle state before automatic stopping; cgroup/identity and connector checks
must pass before release. Cleanup failures block replacement with the concrete
cause. Retry after fixing it, or recover an interrupted upgrade with:

```bash
sudo /usr/bin/python3 -I /usr/libexec/monitorize/remote-login/package-guard.py --resume
```

Post-upgrade recovery failures retain the receipt and report this same command;
package files may already have been installed. After a reboot, `--resume` only
clears expired maintenance and does not replay old masks or service state.

Packages already installed with the old blocking guard may still require remote
login disabled once to install this change: pre-upgrade scripts/hooks can execute
the old installed helper. This change does not replace the separate VKMS host
package's upgrade policy. Native binary/live desktop acceptance is still pending.

### Recovery from an incompatible-host setup deadlock

Disabling an existing enrollment is independent of host compatibility for new
enrollment. The checked boot option remains switchable even when host readiness
fails or normal login startup is unchecked; the root disable action still
authenticates the enrolled account. If an older installed GUI blocks disablement,
stop the stream and use its installed administrator helper from a local terminal:

```bash
pkexec /usr/libexec/monitorize/monitorize-system-setup --remote-login disable
```

Pairing is retained. A partial result means boot startup was disabled but protected
display cleanup still needs attention; keep that result rather than deleting
ownership state. Release versions use `MAJOR.MINOR[.PATCH]`: `1.0` is valid, and
`0.3` has the same compatibility floor as `0.3.0`. Protocol and matching-helper
checks still apply. The companion source installer/host package upgrades now use
their upgrade gate; removal, unsupported versions and actual downgrades retain
their ownership guard.

## Login-screen display policy

The default captures the greeter's existing primary display. **Create virtual
display at login** is an unchecked opt-in for virtual/headless login. Legacy
preferences migrate to the new physical default; explicit new choices persist.
GDM/Mutter and Plasma Login Manager/SDDM with KWin have read-only existing-output
adapters. Other greeters need the explicit virtual path until an adapter exists.
No available display produces an error rather than silently enabling a virtual one.
Desktop virtual-display behavior is unchanged. The protected reserved slot may
exist disconnected; physical login never activates it.

Both installed policy modules require `LOGIN_DISPLAY_POLICY_PROTOCOL=1`, with the
matching fixed helper actions. The source bundle validator checks these together.
The preference retains next-boot application; saving it does not restart streams.
The current Fedora sample is installed; its checkbox/default and desktop listener
are verified. Physical-login and headless greeter acceptance remain pending.

## Live enrollment (installed sample; desktop acceptance passed)

Settings now uses the fixed `enable-live` helper action when matching installed
app and host assets advertise `live_enrollment=1`. On an already initialized host,
it reserves disconnected mon1 in the current authenticated desktop, starts the
supervisor and adopts it with the existing GUI participant. Setup succeeds only
when that participant owns a verified listener. Enrollment does not require reboot,
logout, GUI relaunch or a display-manager restart. First kernel/topology installation
is separate. The fixed greeter display mode remains unchanged.

Stop active streams and Display 2 before setup. Only an owned idle Display 1 may be
paused. Root setup uses a private journal, exact reservation generation and setup
lock. Retry preserves identity; healthy retry preserves the current D-Bus owner.
Only masks recorded by a versioned fallback grant, including prior enablement,
are automatically removed before unit enablement. Custom/ambiguous masks are refused.

Native package-owned files need native upgrades; source asset deployment refuses to
replace them. Source tests pass for the new path; real desktop validation is pending.

The remaining dated sections are historical deployment records. Their next-boot-
only enrollment instructions describe the legacy `enable` action, retained for
compatibility, rather than the Settings live-enrollment workflow.

## Compatible host implementation (2026-10-23)

The companion monitorize-vkms 0.3.0 development tree now implements boot-display,
on-demand greeter and idle-display protocol v1. Source bundles must include the
matching host Python, executable copies, VERSION and capabilities manifest. Native
host upgrades use the package manager; source installers and explicit rollback
refuse package-owned files. Native app replacements use the lifecycle above;
separate host updates and explicit source rollback still require disabled
enrollment and a released protected display. Pairing is retained.

Remote login still requires live physical-screen GNOME/GDM acceptance and a separate
headless test; installing compatible protocols is not that validation.
Native app builders include service assets and an optional monitorize-vkms >=0.3.0
dependency. Portable binaries require companion native system packages and explicit
administrator enrollment through Settings. No package install enables the feature.

The following deployment notes include historical experiments; use newly staged
bundles from the matching source pair instead of old temporary bundle paths.

Local implementation is under validation. No package/staging operation enables
remote login automatically. Current integration uses a protected fixed mon1 output,
KMS and software encoding; automatic client-mode resizing, saved layout policies
and normal instance-2 coexistence still require integration before full feature parity.
Do not treat the Settings page as proof of live support.

Native RPM/DEB/Arch builders stage the same private service bundle. Source runs
can prepare those assets without installing or starting them:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/stage-remote-login.py \
  --output /tmp/monitorize-remote-login-assets \
  --sunshine external/sunshine/build/sunshine \
  --assets external/sunshine/build/assets
```

This does not install monitorize-vkms. Enrollment requires its root-installed
`BOOT_DISPLAY_PROTOCOL = 1` helper and boot_display module. Do not just install the
new unit against an older helper. Keep the working experimental boot setup until
replacement deployment and rollback have been reviewed and tested.

Settings enrollment is explicit administrator authorization. It refuses running
Sunshine engines, migrates identity once, disables the old probe for next boot,
and enables replacement units without starting them or restarting the display
manager. The per-user controller is enabled separately by the GUI; partial setup
is reported if that fails. Reboot only after both portions succeed.

After deployment, collect:

```sh
journalctl -b -u monitorize-remote-login.service \
  -u monitorize-remote-login-boot@1000.service \
  -u monitorize-remote-login-desktop@1000.service --no-pager
journalctl --user -b -u monitorize-remote-controller.service --no-pager
```

Use the enrolled account UID in place of 1000. Do not collect identity/key files.
Test login/disconnect/same-entry reconnect and logout return with a local screen
available first. Fully headless and other display managers remain separate tests.
Disable through Settings; reboot releases the protected display. Wi-Fi and the
shared authoritative pairing identity remain intact.

## Source deployment for the fixed-display handoff test

Close Monitorize and stop streaming first. The replacement below changes installed
code and the Sunshine KMS capability; it does not restart the display manager,
rebuild/reload VKMS, enable services or disconnect the connected output.

Prepare as your normal user, choosing an output directory that does not exist:

```sh
cd /path/to/Monitorize
PYTHONDONTWRITEBYTECODE=1 python scripts/stage-remote-login.py \
  --output /tmp/monitorize-remote-login-ready \
  --sunshine external/sunshine/build/sunshine \
  --assets external/sunshine/build/assets \
  --vkms-source /path/to/monitorize-vkms
```

The optional host source supplies Python support and its executable helper copies;
it does not install/build a kernel module. Then install with administrator rights:

```sh
sudo systemctl stop monitorize-login-capture.service monitorize-vkms.service
sudo /usr/bin/python3 -I scripts/install-remote-login-assets.py \
  --stage /tmp/monitorize-remote-login-ready
```

The installer refuses running Sunshine/supervisor/host-service processes, validates
the bundle, and keeps root-protected original files/modes/engine capabilities under
`/var/lib/monitorize/remote-login-deployments/`. It prints the exact asset-rollback
command. Failed installation attempts restore replaced files; no enrollment or
network data is in this asset transaction. Stopping the old capture service is
intentional: restart it manually if installation is abandoned.

Launch the source app with the built engine:

```sh
MONITORIZE_SUNSHINE_BIN="$PWD/external/sunshine/build/sunshine" \
  PYTHONPATH=linux python -m monitorize
```

Open **Settings → Remote login at boot**, check consent and Enable. Both system
setup and the desktop-controller setup must report success before rebooting.
Enrollment disables the old experimental services for the next boot, preserves
source pairing as a backup and uses one shared identity. A root-only pending
receipt permits retry after interrupted first enrollment without copying stale
identity data over the retained copy. Re-run setup after an error; do not delete
identity directories. Fully quit the app before repeating the source installer.

First live test: keep the local display available. Reboot, connect to the existing
Moonlight PC/Desktop, type the Linux password, expect disconnect, then reconnect to
the same PC/Desktop. Check video/input/audio. Log out and reconnect to verify the
login screen returns. This baseline uses the single fixed virtual output on both
sides; primary-screen capture and normal client-requested desktop display policies
are not yet wired into this managed runner. Do not judge those as implemented.

Rollback after enrollment is two separate operations: disable in Settings first,
then stop feature engines and use the printed asset rollback command. Restoring
assets does not change enrollment/unit enablement or synchronize pairing back to a
stale experimental snapshot. Keep the authoritative shared identity intact; do not
restart the old experiment after new pairings without explicit identity migration.

## Updating the idle-display lifecycle on an enrolled host

Locally implemented; live reconnect/headless/logout acceptance remains required.
The reserved desktop output disconnects after the final authenticated client has
been absent for 20 seconds, including when it is the last screen. A managed
listener stays reachable; an authenticated launch reconnects/activates the same
reserved output before capture. The on-demand greeter update below changes logout to return to a disconnected reservation. Locking does
not initiate a greeter handoff. The fixed 1920×1080@60 remote-login mode is retained.

The bundle must update both Monitorize's service Python and the VKMS host Python
(idle-display protocol v1); changing only the GUI is insufficient. No kernel or
Sunshine rebuild is needed for this update when using the existing compatible
Monitorize engine. A prepared and validated bundle is available for this local
checkout at `/tmp/monitorize-remote-login-idle-ready` until temporary files are
cleared. Fully quit Monitorize, then run from the repository:

```sh
sudo systemctl stop monitorize-remote-login.service monitorize-vkms.service
sudo /usr/bin/python3 -I scripts/install-remote-login-assets.py \
  --stage /tmp/monitorize-remote-login-idle-ready
sudo systemctl start monitorize-vkms.service monitorize-remote-login.service
MONITORIZE_SUNSHINE_BIN="$PWD/external/sunshine/build/sunshine" \
  PYTHONPATH=linux python -m monitorize
```

Keep the existing enrollment and shared identity; do not delete pairing data or
repeat enrollment just to install this update. The installer prints a rollback
command. These commands stop existing streams and replace installed service code;
the agent has not run them. No reboot is needed for the desktop lifecycle test.

1. Start listening and connect through the same Moonlight PC/Desktop.
2. Disconnect, wait more than 20 seconds, and verify the virtual output disappears.
3. Reconnect to the same PC and verify its output returns with working video/input.
4. Repeat with a reconnect before 20 seconds; removal must be cancelled.
5. Run `monitorize-vkms remove`: it deliberately stops the managed session and
   removes its reserved output. Use Monitorize Start before connecting again.
6. Log out and verify the login-screen output/stream returns; enter the password,
   expect disconnect, and reconnect to the same PC for the desktop.

Do the physical-screen test before a genuinely headless test. Ordinary application
cleanup still cannot bypass the protected lease. Explicit CLI removal uses the
coordinator; an unavailable coordinator offers administrator recovery only after
engine cgroups and identity ownership have exited. A lease bound to a different
session is retained with an error rather than forcibly reassigned.

Verification: 127 focused remote-login tests, 16 host boot-display tests and 12 CLI
tests pass. The broad app run was interrupted and had failures; it is not a passing
full-suite result. No live service, display or graphics test was run for this update.


## On-demand greeter update (local source; awaiting live acceptance)

New boot setup reserves mon1 with EDID but leaves its connector disconnected.
Sunshine starts with the private lifecycle protocol and no capture output. Only an
authenticated launch connects the VD. Root verifies the exact active greeter and
fixed boot-runner PID/epoch, tries common kernel hotplug, waits for an enabled
exact DRM connector, and uses the KDE worker as greeter UID if autoactivation fails.
Actual capture readiness requires Sunshine's encoded-frame event. Other greeter
compositors can use the common path but have no validated explicit adapter yet.

Last-client disconnect removes the VD after 20 seconds, including the only screen.
Logout now returns to a disconnected reservation and listener, without recreating
an active output. Local login without Moonlight also permits the desktop listener
to start without a VD. A replacement greeter invalidates the boot ownership context.
Physical display layout is preserved. Fixed remote-login mode remains 1920×1080@60.

This update needs BOTH service Python and host Python with
`GREETER_ON_DEMAND_PROTOCOL = 1`. Use the new bundle
`/tmp/monitorize-remote-login-greeter-ready`, not the older idle-only bundle. It
includes Python/helper updates and the existing compatible Sunshine binary; no
kernel/Sunshine build is needed for this source update.

After fully quitting Monitorize, run from this repository:

```sh
sudo systemctl stop monitorize-remote-login.service monitorize-vkms.service
sudo /usr/bin/python3 -I scripts/install-remote-login-assets.py \
  --stage /tmp/monitorize-remote-login-greeter-ready
sudo systemctl start monitorize-vkms.service monitorize-remote-login.service
```

Keep enrollment and pairing data. The installer prints its rollback command. A
reboot is required to test the new boot reservation from a clean start; the agent
has not installed assets, restarted services, changed displays or rebooted.

Acceptance sequence (start with a physical display available):

1. Reboot without connecting Moonlight: there must be no active VD at the greeter.
2. Log in locally without Moonlight: there must be no active VD on the desktop.
3. Log out; connect Moonlight to the existing PC/Desktop. Verify greeter video/input.
4. Disconnect for >20 seconds: VD disappears; reconnect: same VD/PC works again.
5. Sign in through Moonlight; expect disconnection, then reconnect to the same PC.
6. Log out again: no active VD until the next authenticated client launch.
7. Repeat headless only after the physical-display cycle passes. Confirm the greeter
   starts and stays alive with zero outputs. A greeter that cannot do this remains
   unsupported for on-demand operation; there is no silent always-connected fallback.

If activation fails, collect the supervisor and boot-runner journals. A connector
that is connected but disabled is not reported capture-ready; failed preparation
retains cleanup responsibility. Existing limitations and pending live tests remain
explicit; one successful compositor does not establish universal support.

## Retired seamless experiment

Remote login uses the disconnect-and-reconnect workflow. The experimental
persistent engine has been removed. Existing experimental enrollments are read
as reconnect enrollments, restoring the saved encoder/adapter. Run normal
`--remote-login enable` after updating installed assets to persist the migration
and restore only the experiment-owned linger change. Keep pairing and Wi-Fi.
Stop the old coordinator and persistent engine before installing the update;
the installer removes its unit/Python modules with recoverable backups. Its old
device-group drop-in is inert without the unit. Then reboot.


User-run rollback deployment (Quit Monitorize from tray and disconnect first;
run individually and stop on any error):

```sh
cd /path/to/Monitorize
cmake --build external/sunshine/build --target sunshine -j2 > /tmp/monitorize-reconnect-build.log 2>&1
python scripts/stage-remote-login.py --output /tmp/monitorize-reconnect-restored --sunshine "$PWD/external/sunshine/build/sunshine" --assets "$PWD/external/sunshine/build/assets" --vkms-source ../monitorize-vkms
sudo systemctl stop monitorize-remote-login.service monitorize-remote-login-persistent@1000.service monitorize-vkms.service
sudo /usr/bin/python3 -I scripts/install-remote-login-assets.py --stage /tmp/monitorize-reconnect-restored
pkexec /usr/libexec/monitorize/monitorize-system-setup --remote-login enable
```

Reboot after all commands succeed. Moonlight should show the same paired PC;
connect to login, sign in, then reconnect to reach the desktop.
