# iPhone and iPad

iOS cannot run this backend, and a native app needs a Mac. So the phone is a
client: an installed PWA talking to this machine over Tailscale.

## Setup

**Tailscale**, on every device, same account:

```bash
sudo systemctl enable --now tailscaled   # Fedora ships it disabled
sudo tailscale up
```

On Windows, install from <https://tailscale.com/download/windows>. It runs as a
service with a tray icon, and you **sign in through the tray app, not the
command line** — a CLI sign-in there attaches the node to the wrong identity
and the machine appears under an account you did not mean.

**HTTPS** — enable HTTPS Certificates on the [DNS page](https://login.tailscale.com/admin/dns),
then:

```bash
sudo tailscale set --operator=$USER
tailscale serve --bg --https=443 http://127.0.0.1:8787
```

```powershell
# Run this one in an *elevated* prompt; there is no --operator on Windows,
# where the service already runs with the privilege the flag exists to grant.
& 'C:\Program Files\Tailscale\tailscale.exe' serve --bg --https=443 http://127.0.0.1:8787
```

Do this on each side. `serve` config is per-device, so configuring it under
Linux leaves the Windows node serving nothing.

The app stays on loopback; tailscaled terminates TLS with a Let's Encrypt cert
on the MagicDNS name. Stored by tailscaled, so it survives reboots.

**Run it as a service** — started from a shell, the server dies with the shell:

```bash
cp pgs.service.example ~/.config/systemd/user/pgs.service   # fix the paths
systemctl --user daemon-reload
systemctl --user enable --now pgs.service
sudo loginctl enable-linger $USER    # so it starts at boot without login
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows-tasks.ps1
```

That registers the same two things as Scheduled Tasks — the server at logon,
the backup daily. It is a script rather than an `.example` because a task can
compute its own paths where a systemd unit cannot. There is no equivalent of
`enable-linger`: the server task is triggered at logon, so on Windows the
machine has to be logged in, not merely on.

**Install** — open `https://p.tail1a906a.ts.net` in **Safari** (Chrome on iOS
cannot install PWAs) → Share → Add to Home Screen.

## Dual boot: two devices, two icons

Each operating system install is its own Tailscale machine with its own key and
its own MagicDNS name, because identity is per-install and nothing about a
shared disk changes that. So there are two URLs, and iOS binds a home-screen
icon to the URL it was added from. **That means two icons, and the second one
is not a mistake to be fixed.**

This was decided rather than inherited. The alternatives were worse:

- **One icon by never serving from Windows.** Free, and what the app did
  before — at the cost of the phone being unreachable for every hour spent in
  the other OS.
- **One icon by sharing a node identity between the installs.** Tailscale
  treats them as one device only until it rotates the key, and then the half
  that lost the race is signed out with no clear reason why.
- **One icon behind an always-on box.** Correct, and needs hardware that is
  not on this desk.

Two icons costs one glance to know which OS is up, and nothing else. Name them
so that glance works — the label under an iOS icon is editable when you add it,
so `Trophic` and `Trophic W` beats two identical ones.

**They cannot both be live**, which is the property that makes this safe. One
machine boots one OS, so only one server is ever up and only one icon ever
answers. The other simply fails to connect, which is a legible failure rather
than a silent write to the wrong place — and both write the same shared data
directory anyway, so even the confused case lands in one log.

## Notes

- The manifest pins `start_url` to `/`, so an icon added from any page opens
  the app root. It is the *origin* that differs between the two icons, not
  anything in the manifest — there is nothing to configure per side.
- `--host <addr>` binds directly instead, with no authentication — the
  interface is the access control. Use a tailnet address, never `0.0.0.0`.
- Status: `systemctl --user status pgs`, `journalctl --user -u pgs -f`. On the
  other side, `Get-ScheduledTaskInfo 'PGS Server'`.

## The limitation

**The PC must be awake, and booted into the side you are pointing at.** Nothing
here fixes either, and the second half is new: dual boot bought a working app
under Windows, not a phone that stops caring which OS is up. The permanent
answer to both is porting the backend to TypeScript so the PWA runs standalone
— ~1,800 lines of pure logic with tests that define it. Worth doing only if
"PC asleep" turns out to be the real friction.
