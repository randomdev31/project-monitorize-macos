# Remote-login experiment: first prove boot VKMS output

This is stage 1 of `docs/superpowers/plans/2026-10-19-remote-login.md`.
It is an experimental probe, not the finished remote-login feature. It does not
start Sunshine before login, change pairing, set up handoff or enable headless
support in Settings. No probe is installed automatically.

## What is implemented

Read-only collector (no root required):

```sh
cd /home/vinnavan/user/MegaProjects/Monitorize-testing
PYTHONDONTWRITEBYTECODE=1 python scripts/check-remote-login-readiness.py --sunshine "$PWD/external/sunshine/build/sunshine"
```

`--json` emits structured evidence. Exit 2 means live validation is still
required. PASS refers to a named static prerequisite, never the whole feature.
Encoder/framebuffer and greeter input remain UNKNOWN until actually tested.

The optional boot probe connects dynamic `mon1` with a generated 1920x1080@60 EDID
after the installed VKMS bootstrap, before the display manager. It requires the
root-installed `monitorize_vkms.edid` module, refuses any existing session/lease
or connected mon1, and leaves physical outputs and mon2 unchanged. It takes the
existing lifecycle lock. It deliberately has no shutdown/disconnect action.

## Scope of the first live test

First keep physical screens available as a recovery path. Exit Monitorize and
stop its sessions before the test; avoid launching it during inspection because
this temporary connected output has no normal per-user lease. Record the
existing autostart setting and temporarily turn off automatic listening for the
probe boot, then restore that setting after rollback.

The probe changes one VKMS connector at the next boot. Do not start it manually
in the current desktop. Install it only when ready to reboot and with local/TTY
access available. The service does not edit display-manager settings and may
therefore expose the next real blocker: the greeter might ignore VKMS.

Before installation, ensure these paths are not files/services you already own
for another purpose; do not overwrite an existing experiment installation:

```sh
test ! -e /usr/local/libexec/monitorize-remote-login-probe
test ! -e /etc/systemd/system/monitorize-remote-login-probe.service
```

Both tests must succeed. Then install the reviewed experiment:

```sh
cd /home/vinnavan/user/MegaProjects/Monitorize-testing
sudo install -d -m 0755 /usr/local/libexec
sudo install -o root -g root -m 0755 scripts/remote-login-probe/enable-boot-output.py /usr/local/libexec/monitorize-remote-login-probe
sudo install -o root -g root -m 0644 scripts/remote-login-probe/monitorize-remote-login-probe.service /etc/systemd/system/monitorize-remote-login-probe.service
sudo systemctl daemon-reload
sudo systemctl enable monitorize-remote-login-probe.service
```

Do **not** use `enable --now` or restart the display manager. Save work, then
reboot when ready. Login normally for evidence collection; the experiment alone
does not yet provide remote login. After login:

```sh
systemctl status monitorize-remote-login-probe.service --no-pager
journalctl -b -u monitorize-remote-login-probe.service -u plasmalogin.service --no-pager > /tmp/monitorize-boot-greeter.log
cd /home/vinnavan/user/MegaProjects/Monitorize-testing
PYTHONDONTWRITEBYTECODE=1 python scripts/check-remote-login-readiness.py --sunshine "$PWD/external/sunshine/build/sunshine" --json > /tmp/monitorize-boot-readiness.json
```

The probe PASS is only: unit succeeded, connected mon1 with valid fixed EDID.
If DRM reports enabled plus modes it suggests compositor adoption, but it is
not video/input proof, especially after login. Capture test comes next only
after checking this evidence and any greeter-specific errors.

A laptop's internal eDP screen remains a physical output even with external
monitors unplugged. That is not a genuinely headless proof. Do not add display
forcing/physical disabling to this experiment; the manager adapter must be
reviewed first if VKMS is ignored.

## Rollback

If the login screen is unusable, use local TTY or already configured SSH. The
probe does not alter keyboard/TTY or SSH configuration. Remove only these two
experiment-owned files; do not remove the monitorize-vkms package:

```sh
sudo systemctl disable monitorize-remote-login-probe.service
sudo rm -- /etc/systemd/system/monitorize-remote-login-probe.service
sudo rm -- /usr/local/libexec/monitorize-remote-login-probe
sudo systemctl daemon-reload
```

Save work and reboot. Disabling/removing the unit does not disconnect the
currently used output. Normal bootstrap restores disconnected connectors after
reboot. Restore the previous automatic-listening preference afterward.

## Remaining stage-1 proof

- Root-owned, restricted Sunshine boot capture profile and input access, after
  the greeter/VKMS behavior is known. No desktop home/profile assumption.
- Verify KMS-only startup with no portal, actual encoding GPU and correct seat.
- Moonlight greeter video, keyboard/mouse, actual login, then a headless cold boot.
- Only after those gates pass: permanent boot ownership, one shared identity,
  supervisor handoff, setup UI and native packaging.

## Next experiment: Moonlight capture at the login screen

The private prepared bundle is `/tmp/monitorize-login-capture-stage-1000` on the
current development host. Preparation copies your existing instance-1 UUID,
certificate/key and paired-client state without changing the original profile.
Keep this directory private (0700); it contains credentials. It may disappear
on reboot, so install it before reboot. To recreate a missing bundle, run
`scripts/prepare-login-capture-probe.py --sunshine external/sunshine/build/sunshine --assets external/sunshine/build/assets` without sudo from the repository.
Preparation refuses an existing destination; use a new `--output` directory
rather than overwriting an earlier snapshot.

Prerequisites: first boot-output probe remains enabled; keep Monitorize closed
and automatic listening off. No Sunshine host should be running. The capture
installer refuses existing probe files and only enables next-boot startup.

```sh
sudo sh /tmp/monitorize-login-capture-stage-1000/install.sh
```

Save work, then reboot manually. **Remain at the Linux login screen**. On an
already paired Moonlight client, refresh/select the existing `Monitor 1` PC entry
and launch **Login screen**. Do not add another host or pair again for this test.

Test sequentially:

1. Login screen is visible, with no portal approval prompt. A blank/black image
   is a failed capture test, not proof that another monitor should be selected.
2. Mouse pointer moves and the username/password field responds to typing.
3. Enter your Linux credentials through Moonlight. The boot stream should close
   when logind reports a user session.

This experiment stops there: desktop autostart/handoff and logout rearming are
not installed yet. Do not expect desktop reconnect to work until normal
Monitorize is started later after appropriate boot-output rollback. The snapshot
preserves initial pairing for this test only; do not change pairings/revoke
clients or edit the boot web UI. Permanent single-identity ownership is later
work. Boot capture has audio/controllers/UPnP disabled and no application commands.
Web administration is local-only. The runner runs as your user, not root, and
requires the root-installed engine's file capability; it selects only the actual
enabled Monitorize mon1 connector by EDID, and stops when the greeter disappears
or any seat0 user session starts.

If Moonlight fails, log in locally. After either outcome collect:

```sh
journalctl -b -u monitorize-login-capture.service --no-pager > /tmp/monitorize-login-capture-journal.log
sudo cat /var/lib/monitorize-login-capture/1000/logs/sunshine.log > /tmp/monitorize-login-capture-engine.log
```

A missing engine log means the runner may have stopped before launching
Sunshine; the journal explains that stage. Record visible video, pointer/typing
and disconnect outcomes separately. Never send identity/certificate/private-key
files in chat.

Disable capture before returning to ordinary Monitorize usage:

```sh
sudo systemctl disable --now monitorize-login-capture.service
```

That stops streaming only; it does not unplug VKMS. To return fully to the
pre-experiment topology, also disable the boot-output probe and reboot, then
restore your original listening setting. Removing `/etc/monitorize-login-capture.json`,
`/etc/systemd/system/monitorize-login-capture.service`,
`/usr/local/libexec/monitorize-login-capture`,
`/usr/local/share/monitorize-login-capture` and
`/var/lib/monitorize-login-capture/1000` is optional after disabling. Delete only
experiment-owned paths; the last directory contains the private identity snapshot.

### Application-list correction after the USB test

The first capture bundle omitted Sunshine's mandatory `env` node, leaving the
app list unloaded (`No such node (env)`). Moonlight's cached Desktop app request
then failed with ID 881448767. USB networking and software KMS encoder probes
succeeded; actual streaming/input were not established.

The source template `capture-apps.json` now supplies an empty environment and
command-free Desktop/Login screen entries. Desktop retains the original name
and desktop.png image, preserving the cached app ID with the tested assets.
Apply only this file to an already installed, stopped experiment:

```sh
sudo install -o root -g root -m 0644 /home/vinnavan/user/MegaProjects/Monitorize-testing/scripts/remote-login-probe/capture-apps.json /var/lib/monitorize-login-capture/1000/apps.json
```

No rebuild is required. Keep the software encoder for this diagnostic test,
reboot when ready with USB tethering enabled, stay at the login screen and
select Desktop in the existing Moonlight host. Login screen is also available
after an app-list refresh. Leave Monitorize closed. Collect the same logs after
success/failure and record video, typing and login-disconnect separately.
