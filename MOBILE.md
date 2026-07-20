# iPhone and iPad

iOS cannot run this backend, and a native app needs a Mac. So the phone is a
client: an installed PWA talking to this machine over Tailscale.

## Setup

**Tailscale**, on both devices, same account:

```bash
sudo systemctl enable --now tailscaled   # Fedora ships it disabled
sudo tailscale up
```

**HTTPS** — enable HTTPS Certificates on the [DNS page](https://login.tailscale.com/admin/dns),
then:

```bash
sudo tailscale set --operator=$USER
tailscale serve --bg --https=443 http://127.0.0.1:8787
```

The app stays on loopback; tailscaled terminates TLS with a Let's Encrypt cert
on the MagicDNS name. Stored by tailscaled, so it survives reboots.

**Run it as a service** — started from a shell, the server dies with the shell:

```bash
cp pgs.service.example ~/.config/systemd/user/pgs.service   # fix the paths
systemctl --user daemon-reload
systemctl --user enable --now pgs.service
sudo loginctl enable-linger $USER    # so it starts at boot without login
```

**Install** — open `https://p.tail1a906a.ts.net` in **Safari** (Chrome on iOS
cannot install PWAs) → Share → Add to Home Screen.

## Notes

- The manifest pins `start_url` to `/`, so an icon added from any page opens
  the app root.
- `--host <addr>` binds directly instead, with no authentication — the
  interface is the access control. Use a tailnet address, never `0.0.0.0`.
- Status: `systemctl --user status pgs`, `journalctl --user -u pgs -f`.

## The limitation

**The PC must be awake.** Nothing here fixes that. The permanent answer is
porting the backend to TypeScript so the PWA runs standalone — ~1,800 lines of
pure logic with tests that define it. Worth doing only if "PC asleep" turns out
to be the real friction.
