# Remote-login host implementation and acceptance record

## Login-screen physical-display default — 25 October 2026

Installed source sample now uses **Create virtual display at login**, unchecked by
default, without extra checkbox help text. Missing positive setting migrates both
legacy `login_primary_display` choices to physical capture. The new
`create_login_virtual_display` boolean preserves later explicit opt-ins. Enrollment,
disable/re-enable and settings writes preserve that new choice; old primary CLI
commands remain inverse compatibility aliases. Saving this preference retains its
existing next-boot timing and does not interrupt a desktop stream.

Unchecked login capture selects an existing primary output read-only: GDM/Mutter,
Plasma Login Manager/KWin and SDDM/KWin adapters verify greeter session, compositor
owner, mode and one enabled exact DRM connector, with repeated ownership/target
checks. KWin queries run as the greeter using trusted kscreen-doctor JSON. No enabled
primary or unsupported compositor is an error, with no silent virtual-display
fallback. Other SDDM compositor virtual paths remain available through the checkbox.
The protected mon1 reservation stays disconnected during physical login; desktop
adoption and on-demand desktop activation remain unchanged. Physical idle cleanup
never changes/disconnects the physical output. Checked login mode keeps fixed-mode
virtual greeter activation and cleanup.

Installed `LOGIN_DISPLAY_POLICY_PROTOCOL=1` in both policy modules and fixed
`login-virtual-on/off` wrapper/entry actions gate the new checkbox. Bundle validation
rejects incomplete policy/action updates. Root service files match the staged bundle.
The reopened sample GUI verifies the new label, unchecked/enabled state and ready
policy capability; its desktop listener remains owned, healthy and idle with both
virtual connectors disconnected. Read-only desktop query selected eDP-1 at
2560×1600@165.002. This is selector evidence, not greeter streaming acceptance.

Rollback asset backup:
`/var/lib/monitorize/remote-login-deployments/9a731caece033284b53209fee2df3fa7`.
Final source bundle: `/tmp/monitorize-login-primary-default-assets-validated-20261025`.
Live GUI evidence: `/tmp/monitorize-login-display-policy-sample.log`.
Only feature services and the idle sample GUI were restarted for this deployment.
Boot ID, session3 and display-manager PID1819 remained unchanged; no logout/reboot,
kernel reload, commit or push. Actual physical greeter video/input → login → desktop
reconnect and checked headless login still need separate live acceptance. Existing
Moonlight desktop success from the preceding test does not establish those results.

## Live enrollment source update (2026-10-25)

Implemented in the isolated app and host worktrees listed below; installation and
physical-screen acceptance are pending. On a compatible already-loaded VKMS host,
Settings enables remote login immediately: pause only an owned idle Display 1,
save enrollment, reserve disconnected mon1 in the authenticated current desktop,
start the boot dependency and supervisor, and let the existing GUI participant
adopt it. Success waits for verified listener ownership, without requiring capture
frames before a client connects. No reboot, logout, GUI relaunch or display-manager
restart is part of this enrollment path. First kernel/topology installation still
requires the host's normal initialization procedure.

The host manifest, host boot module and installed app service must all advertise
`live_enrollment=1`. Old installed assets offer an update message rather than
silently using next-boot setup. Active streams and any Display 2 listener block
setup. Saved display/codec/Auto settings and pairing remain intact. The reservation
keeps the existing fixed remote-login mode; this change does not add client-requested
resolution negotiation to the greeter.

Root setup is serialized and keeps a private recovery receipt. Retry reuses its
identity and reservation, reconciles interrupted service starts, and preserves a
healthy authenticated GUI participant. Only versioned feature-owned runtime masks
with recorded prior enablement can be recovered automatically. Custom or legacy
ambiguous masks require explicit recovery. Failed recovery retains its receipt
and reports partial setup; successful rollback reports the restored enrollment.

Source pair:

- App: `/home/vinnavan/.codex/worktrees/live-remote-login/Monitorize-testing`.
- Host: `/home/vinnavan/user/MegaProjects/.monitorize-live-enrollment-vkms`.
- Validated staged bundle: `/tmp/monitorize-live-remote-login-assets-final-20261025`.

Deployment is a separate administrator operation. Package-owned files require a
native package upgrade; the source installer refuses to overwrite them. Source-
managed files use the reviewed asset transaction and its printed rollback command.
Disable enrollment and release its reservation before replacing enrolled assets.
Keep pairing data. Do not run old experiment/identity restoration commands from
historical sections below against a newly paired shared identity.

### Source verification for this update

- Host full suite: 260 pass.
- App remote-login suite with the companion host fixture configured: 222 pass.
- App full suite: 878 tests, 7 failures and 3 errors. The same failures/errors
  reproduce on the original checkout (which also has one stale timeout assertion
  corrected in this worktree). No new full-suite failure remains. Logs and the
  original baseline comparison are in the execution ledger directory.
- Final bundle validates under `python3 -I`; 62 staged Python files parse.
- Isolated `systemd-analyze verify` passes using temporary dependencies.
- Native file staging, new module/action and additive manifest are checked;
  native binary/package builds and installation were not run.

### Live acceptance record

Record installed app/host versions, kernel, compositor/display-manager versions,
GPU, physical/headless mode and journal evidence for each run. Nothing in this
source update has been installed or exercised against a live desktop.

| Scenario | Passing criterion | Current result |
| --- | --- | --- |
| Plasma with physical screen, idle enable | Same GUI and session; listener owned and reachable; no active VD or restart | Pending live run |
| Moonlight connect, disconnect, reconnect | Exact reserved output activates; video/input work; idle timeout disconnects it; same paired PC reconnects | Pending live run |
| Logout → greeter → login → reconnect | Existing reconnect handoff works, greeter stays on demand | Pending live run |
| Disable → enable again, owned fallback masks | No restart; exact ownership recovered; administrator masks preserved | Fixture checks pass; live pending |
| Stop/Quit during setup; authorization failure | No unintended listener resurrection; accurate saved/partial status; safe retry | Fixture checks pass; live pending |
| Deliberate later reboot | Fresh boot reservation/listener uses persisted enrollment | Existing boot regression suite passes; live pending |
| GDM and SDDM, physical screen then headless | Repeat the entire cycle separately for each manager | Pending separate runs |

Mark PASS only with observed behavior and evidence. FAIL means an observed
criterion failed. BLOCKED means missing compatible assets, greeter, or required
hardware. INCONCLUSIVE means incomplete or ambiguous evidence. Fixture success
alone does not establish compositor, GPU or headless stability.

Date: 2026-10-23. Code implemented and reviewed; live installation/boot acceptance pending.

## Installation update (2026-10-23)

The user authorized deployment. Installed Monitorize 0.33.4-1 through pacman because
the existing app assets belong to the native monitorize package. A local rollback
package of the prior 0.33.3-1 installation was prepared first. Updated the separately
source-managed VKMS userspace to 0.3.0 with the validated bundle and the tested
`--host-only` installer mode. The running kernel module was not rebuilt or unloaded.

Installed static readiness reports `ready`, all protocol constants are 1, helper
copies match, Sunshine has cap_sys_admin/cap_sys_nice, package integrity reports
496 files with none missing, doctor passes and systemd unit verification succeeds.
The host helper is active. The installed app was reopened and its ordinary idle
listener resumed. Remote login units remain disabled; enrollment and live boot/
headless acceptance have not been performed.

The host transaction backup is
`/var/lib/monitorize/remote-login-deployments/db00959aa9f90d4aff10e20ecbf81929`.
Exact rollback instructions and package hashes are saved in
`/home/vinnavan/.worktrees/remote-login-artifacts/installation-receipt.json`.
The latest focused app suite has 168 passing tests, including mixed native-app /
source-managed host installation without overwriting package-owned files.

The implementation-time snapshot below records earlier evidence; this installation
update supersedes its statements that deployment was pending.

## Source pair

- Host: `/home/vinnavan/.worktrees/remote-login-host`, branch `codex/remote-login-host-support`, host version 0.3.0.
- App: `/home/vinnavan/.worktrees/remote-login-app`, branch `codex/remote-login-host-support`, based on app commit `e317755`.
- The original host checkout's GNOME fix was preserved and committed in the host feature branch.
- The original checkouts and running service installation were not replaced.

## Implemented behavior

Protected mon1 ownership, fixed 1920x1080@60 disconnected boot reservation, verified
greeter activation, adoption before desktop-engine startup, desktop activation,
20-second app idle policy with host quiescence proof, disconnected return to greeter,
and authenticated release/recovery. mon2 stays available to ordinary creation.
GNOME activation selects the exact owned output even when another virtual output
offers the same mode. No host operation treats sysfs connected status as proof of
exact active mode or encoded-frame readiness.

All three required protocol values are 1. App readiness checks trusted installed
metadata, matching helper copies, module constants and engine support. Source
staging/deployment includes host VERSION and capabilities metadata. Native app
dependencies require optional monitorize-vkms >=0.3.0; packages own distinct files.
Source install/explicit rollback refuses native package-owned files; explicit
rollback also requires disabled enrollment and a released protected display.

## Verification performed

| Check | Result |
| --- | --- |
| Host full unittest suite | 212 tests, pass |
| App focused `test_remote_login*.py` suite | 167 tests, pass |
| App greeter adapter/context suites | 9 tests, pass |
| App GDM integration suite | 13 tests, pass |
| Cross-repository actual app callback → host activation/idle | Pass against the host feature worktree |
| Existing app VKMS/package-asset tests | 3 + 3 tests, pass |
| Arch host package | Built with makepkg; contents inspected with pacman/bsdtar |
| DKMS source content from the staged package | Compiles against 7.2.11-arch1-1 headers; no module installed/loaded |
| Reviewed source deployment bundle | `validate_bundle` passes; staged readiness returns `ready` with owner UID adjusted for user-owned staging |
| Full app suite, isolated configuration | 757 tests: 2 failures, 3 errors, 1 skipped |
| Original app baseline, isolated configuration | 746 tests: identical 2 failures, 3 errors, 1 skipped |
| DEB/RPM builds and package installation | Not run: matching build environments/toolchains unavailable |
| Native app binary rebuild/install | Not performed; existing package staging/metadata tested |
| Physical-screen and headless boot cycles | Not performed |

Full suites used separate temporary `XDG_CONFIG_HOME` directories so host log files
could not affect health tests. The worktree Sunshine submodule was initialized
from the local original checkout before the final full run.

The five original baseline failures are:

- `test_flatpak_patch_sequence.FlatpakPatchSequenceTests.test_manifest_patch_sequence_applies_to_pinned_source`: patch hunks fail against the pinned Sunshine source.
- `test_installer.SunshineOnlyPackagingTest.test_add_display_uses_the_same_two_card_limit_in_vkms_mode`: test expects `sessionBusy`, QML uses `applyingConfiguration`.
- `test_settings.SettingsTest.test_backend_card_round_trip_preserves_independent_listener_selection`: fixture lacks `applyingConfiguration`.
- `test_settings.SettingsTest.test_backend_saves_each_sunshine_instance_independently`: same fixture issue.
- `test_settings.SettingsTest.test_sunshine_choice_snapshot_writes_one_patch_and_skips_repeat`: same fixture issue.

These were reproduced in the original checkout and left outside this feature's
scope. A separate host-log-dependent Sunshine-health failure reproduced in both
checkouts without isolated configuration and disappears with isolation.

## Review findings resolved

- Greeter idle used to probe the identity lock again while the host held it.
  Initial EngineGate idle authentication remains; callbacks now revalidate sender
  and session while the host independently holds the identity lock and checks
  cgroups. A test executes the actual daemon closure through this transaction.
- Explicit rollback could delete a formerly source-installed helper after native
  packages adopted it. Rollback now checks package ownership before changing any
  destination. Internal restoration after a failed current installation remains
  available. Tests cover package takeover, enabled enrollment, protected leases,
  and ordinary failed-install restoration.

## Reviewable artifacts

- Source bundle: `/home/vinnavan/.worktrees/remote-login-artifacts/reviewed-source-assets`.
- Host package: `/home/vinnavan/.worktrees/remote-login-host/packaging/arch/monitorize-vkms-0.3.0-1-x86_64.pkg.tar.zst`.
- Artifact hashes, git revisions and logs: `/home/vinnavan/.worktrees/remote-login-artifacts`.

The source bundle contains the currently built compatible Sunshine binary and
assets from the original app checkout, plus the reviewed app/host Python. It does
not contain a new kernel module, pairing secrets or enrollment state.

## Source installation test procedure (not executed)

Use this route only for the current source-managed host. For native package-owned
files, upgrade the native packages instead. Choose one route; do not overwrite
package-owned files with a source bundle.

1. Quit Monitorize from the tray, disconnect clients and stop Sunshine. If already
   enrolled, disable remote login and release its reservation first. Preserve pairing.
2. Stop `monitorize-vkms.service` and any running remote-login coordinator/experimental
   capture service. Confirm no Sunshine processes remain. This is a deliberate
   service change and has not been performed by the implementation work.
3. From the app feature worktree, install:

   ```sh
   sudo /usr/bin/python3 -I scripts/install-remote-login-assets.py \
     --stage /home/vinnavan/.worktrees/remote-login-artifacts/reviewed-source-assets
   ```

4. Save the exact rollback command/backup path printed by the installer. It replaces
   userspace and engine assets transactionally and does not enroll/start remote login.
5. Start the host D-Bus service. Launch the app from the feature worktree:

   ```sh
   MONITORIZE_SUNSHINE_BIN=/usr/libexec/monitorize/sunshine \
     PYTHONPATH=linux python3 -m monitorize
   ```

6. Confirm Settings readiness identifies all host protocols. Enable Remote login
   at boot with administrator authorization and confirm both system enrollment
   and the per-user controller report success. Do not infer live support from this.
7. Reboot deliberately with the local display available and perform the cycle below.

## Required live cycle

Record kernel, GNOME/GDM, app, host and Sunshine versions. Verify:

- Boot with no client: mon1 is reserved but disconnected; GDM remains running.
- Connect the existing paired Moonlight PC: exact mon1 activates at 1920x1080@60;
  actual encoded frames and input work.
- Sign in: expect disconnect, then reconnect to the same PC for the desktop.
- Disconnect for more than 20 seconds: the reserved VD disappears; reconnect restores
  the same reservation. Reconnect before expiry cancels removal.
- Lock/unlock does not trigger a greeter handoff. Logout returns to a disconnected
  greeter reservation, ready for an authenticated reconnect.
- Physical display layout is preserved; ordinary mon2 create/remove remains isolated.
- Coordinator/engine crashes, engine restart during idle, and stale session/token
  requests retain recoverable ownership and do not unplug another owner's output.
- Settings disable releases the reservation without deleting pairing. Desktop
  fallback and explicit asset rollback work after services/capture stop.

Only after that passes, repeat with no physical screen. If GDM cannot survive
zero outputs, mark headless mode unsupported and retain local recovery; do not
silently connect an always-on VD. Each other display manager needs its own cycle.

Do not collect key/certificate files or copy pairing identity into test reports.
Use system/user service journals for diagnostics. DEB/RPM and native app release
acceptance remain separate work on matching build/install environments.


## 25 October 2026 — installed Fedora Plasma sample acceptance

User authorized sample installation and testing without commits. Installed the
validated source-managed app-service and VKMS userspace bundle through desktop
Polkit authentication. Existing source checkouts and running kernel were preserved.
Feature services were stopped for asset replacement and restored; no PC reboot,
logout, display-manager restart or kernel reload occurred. All 62 installed service
Python files match the staged bundle. Installed live readiness reports ready.

Rollback asset backup:
`/var/lib/monitorize/remote-login-deployments/5ddb4e8165b5f25bffc48ded83a91e0d`.
Use the source installer's printed rollback command only after disabling enrollment,
releasing the reservation and stopping feature engines; pairing remains authoritative.

Actual Qt backend test in the visible sample GUI:
- Disable succeeded with reboot_required=false and enabled=false.
- Live enable succeeded with activated=true, configured=true and reboot_required=false.
- Repeated enable succeeded with reused=true and the same authenticated participant.
- Session 3 and boot bec34a9f-af17-4727-b299-cba26127eb84 were unchanged.
- Root receipt reached complete; protected lease belongs to UID1000/session3/desktop.
- Idle: both VKMS connectors disconnected, physical eDP-1 remained enabled.
- User confirmed Moonlight video and keyboard/mouse work. Supervisor journal shows
  streaming at 21:08:39 IST and capture_ready=true at 21:08:40.
- Disconnect grace began 21:09:01; both virtual connectors were disconnected after
  cleanup, with desktop_listening restored at 21:09:23 and listener ports retained.
- Desktop engine PID309548 stayed unchanged through reuse/stream/idle cleanup;
  display manager PID1819 stayed unchanged throughout enrollment testing.

Evidence: `/tmp/monitorize-live-sample-test-results.jsonl` and
`/tmp/monitorize-live-sample-test.log`; supervisor journal for this boot.
Visible sample remains open/listening. The future-login user controller points to
the isolated app worktree; keep that worktree while testing this sample.
No commits/pushes. Logout/greeter/reconnect, deliberate reboot, GDM/SDDM and headless
acceptance were not performed in this run. Plasma desktop success does not establish
those results. 30 focused setup/coordinator tests also passed after installation.

Verification for the physical-login default: 293 focused remote/login/GDM/KWin/UI
tests pass. Full app: 892 tests, 7 failures/3 errors; exact corresponding failures
are reproduced in the original checkout (843 tests, 8 failures/3 errors, including
its stale host worker timeout assertion). Full suites isolated both XDG_CONFIG_HOME
and XDG_STATE_HOME; an initial config-only run exposed existing live layout-recovery
state to session fixtures, so later comparison runs used separate state directories.
No live display recovery changes were made to address test expectations. Bundle
validation, installed-source comparison (62 files), Python syntax and diff checks
pass. Existing desktop Moonlight success is from the earlier sample test; this
update's physical-greeter streaming remains untested until a deliberate logout.


## Normal checkout integration — 25 October 2026

User's terminal launch resolved to `/home/vinnavan/user/MegaProjects/Monitorize-testing`
with `PYTHONPATH=linux`, still showing the old checkbox because implementation had
only been retained in the isolated worktree. Integrated 37 differing app files and
6 companion host files into the normal app/host checkouts, without commits. Existing
Plasma source edits were retained; prior differing files and a manifest are backed
up under `/home/vinnavan/.local/state/monitorize-source-integration-20261025`.

Reopened actual `python3 -m monitorize` from the normal checkout; current process
cwd and label source verified. Future-login controller now also uses that normal
checkout. `Create virtual display at login` is unchecked by default and enabled
against the installed policy. Plasma Login Manager uses the authenticated KWin
existing-primary capture path, alongside GDM; no remaining GDM-only guard applies
to that option. Actual greeter capture/input still requires deliberate logout
acceptance; desktop listener is verified healthy in session3.

Normal-checkout verification: 293 focused app tests and all 260 host tests pass;
both diff checks pass. Original source checkouts now contain the implemented work;
earlier notes that implementation remains isolated are historical. No root assets
needed replacement in this step; they already matched the implemented policy.
