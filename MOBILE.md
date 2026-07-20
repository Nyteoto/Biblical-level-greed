# Getting it on iPhone and iPad

## The constraint, first

**iOS cannot run this backend.** It is Python; iOS does not let an app spawn a
Python server, and building a native iOS app needs macOS and Xcode, which you do
not have. So the phone is a *client*, and the server runs on your PC.

That is not a workaround — the frontend is already a static site talking to a
JSON API, so a phone browser is a first-class client. It just has to be able to
reach the API.

## Step 1 — install it to the home screen (done, works now)

The app is now a PWA: its own icon, no Safari chrome, launches like an app.

1. On the PC: `pgs --host <address> --port 8787` (see step 2 for the address)
2. On the phone, open that URL in **Safari** (Chrome on iOS cannot install PWAs)
3. Share → **Add to Home Screen**

You get a real icon, a fullscreen app, and the layout already fits: no page
overflows horizontally at 390pt, and content is padded clear of the notch and
home indicator.

## Step 2 — let the phone reach the PC

There is **no authentication in this app.** Whatever can route to the address
can read your journal and rewrite your history. So the network is the access
control, and the choice of address is the entire security decision.

### Recommended — Tailscale (free, private, works anywhere)

A WireGuard mesh between your own devices. Nothing is exposed to the internet
and no traffic goes through a third party.

**Linux.** Installing the package does not start the daemon — Fedora ships the
unit disabled, so `tailscale ip` fails with *"failed to connect to local
Tailscale daemon"* until you do:

```bash
sudo systemctl enable --now tailscaled   # --now also starts it
sudo tailscale up                        # prints a URL; open it to sign in
```

**Windows.** Install from <https://tailscale.com/download/windows>. It runs as a
service with a tray icon; **sign in through the tray app, not the command line.**
The CLI exists at `C:\Program Files\Tailscale\tailscale.exe` but is not on
PATH by default — you do not need it, because:

**Then, on either OS:**

```bash
pgs --host tailscale --port 8787
```

`--host tailscale` asks Tailscale for this machine's tailnet address and binds
that specific interface. That is safer than typing an address by hand and much
safer than `0.0.0.0`: the app is reachable only by your own signed-in devices,
which is what makes running it without a login defensible at all. If the daemon
is down it tells you, rather than silently binding nothing.

Then on the phone, open the printed URL in **Safari** → Add to Home Screen.
Works from anywhere, not just your WiFi.

### Home only — LAN

`pgs --host 0.0.0.0 --port 8787`, then `http://<pc-lan-ip>:8787` on the phone.

Simple, but everyone on that WiFi can read and write your data. Fine on a
trusted home network; not fine in a café, an office, or a shared flat.

### Not recommended — a public host

Putting this on a VPS means your practice log lives on a rented computer, open
to anyone who finds the port, until authentication exists. Do not, yet.

## Dual-boot: you get two Tailscale devices

Each OS install has its own machine identity, so Linux and Windows appear as
**two separate devices with two different addresses**, even on the same
hardware. Only one is ever online, but the phone still needs to know which.

Two consequences:

1. **Two URLs, so potentially two home-screen icons.** A PWA fixes its start
   URL at install time. Turn on **MagicDNS** in the Tailscale admin console and
   you at least get stable names — `http://pekka-linux:8787` — instead of
   memorising two `100.x` addresses.
2. **Point both installs at one data folder.** Otherwise the phone writes to
   whichever OS is booted and the two copies diverge. The append-only log is
   built to survive exactly that (see `SYNC.md`), but a shared folder avoids the
   problem rather than repairing it afterwards:

```bash
pgs --data-dir /mnt/shared/pgs-data --host tailscale --port 8787
```

If you would rather not share a folder, git still reconciles it — just actually
`git pull --rebase` when you switch OS, or the divergence simply sits there
until you do.

The simplest version of all this: **pick the OS you use most and only serve
from that one.** One address, one icon, no divergence.

## The real limitation

**The PC must be awake.** You will want to tick off practice at 11pm on the
sofa or on a train, and that is exactly when a sleeping desktop fails you.

Mitigations, in order of effort: leave the PC on; wake-on-LAN; or run the server
on something always-on that you own (a Raspberry Pi with the data on it, still
over Tailscale).

The permanent fix is different, and it is a rewrite — see below.

## Where this stops being enough

Everything above makes the phone a *window onto the PC*. If the answer needs to
be "the app works on the train with the PC off", the backend has to leave the
PC entirely: port the logic from Python to TypeScript, keep the data in the
browser, and the app becomes a static site with no server at all.

That is roughly 1,800 lines of pure logic — loader, state, xp, todos, writer,
edits — none of which does I/O beyond reading and writing files. The 170 tests
define the behaviour precisely enough to port against.

It would also mean rethinking what "the files are the source of truth" means on
a device with no filesystem you can hand-edit. That is the real design question,
not the porting.

Do not start it until the mobile client above has been used for a few weeks and
the actual friction is known.
