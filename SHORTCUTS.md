# Sending photos from the iPad

Snap a photo, have it land in a node's notes. Two actions.

> The earlier version of this file described six actions and named menu items
> precisely. That was written from a generic idea of the Shortcuts app rather
> than the one on your device, and the labels did not match. This version keeps
> the Shortcut as small as possible and describes each field by **what it does**
> — so it survives Apple renaming things, and so there is very little to get
> wrong.

## Start here: the smallest thing that works

Two actions. No list, no picker, no variables.

**Action 1 — take a photo.** Search the action list for `photo`. You want the
one that opens the camera and produces an image. (`Take Photo`.)

**Action 2 — send it.** Search for `URL`. You want the one that *fetches* a URL
and can send a body — not "Open URL", which just opens Safari.
(`Get Contents of URL`.)

Configure action 2:

| field | value |
|---|---|
| URL | `https://p.tail1a906a.ts.net/api/media?domain=electrical-engineering` |
| Method | `POST` |
| Request Body | **File** |
| the file | the photo from action 1 |

That's it. Run it. A photo of anything will do.

**Naming only the domain is deliberate** — the server attaches it to whatever
that domain is working on *today*, so the Shortcut never has to know about
nodes. Swap `electrical-engineering` for whichever domain you're photographing.
The six ids are the `.toml` filenames: `chinese`, `guitar`, `drumming`,
`electrical-engineering`, `software-dev`, `filmmaking`.

If the domain is out of season it tells you so rather than failing vaguely:

```
`guitar` has nothing active today — it is low season. Name a node explicitly.
```

…in which case add `&node=hands-and-tone` to the URL.

### Two blank fields that will break it

Found by capturing the raw request during setup. Shortcuts was sending:

```
: 
{"":"it ran"}
```

A header line with **no name**, and a JSON body with an **empty key**. That bare
`: ` is invalid HTTP, so the server rejects the whole request — and iOS reports
it as the unhelpful *"The network connection was lost"*.

So in action 2: if there's a **Headers** section, make sure there is no row with
a blank name. And leave **Request Body** as *File* — you want no JSON at all
here. Neither field looks empty in the UI, and both follow you into any action
you duplicate.

## If it doesn't work

Change the URL to `https://p.tail1a906a.ts.net/api/health` and set Method to
`GET`, with no body. That should return something starting `{"ok":true`.

- **Works** → the Shortcut can reach the server; the problem is in the body or
  headers of the POST.
- **Fails** → connectivity. Check Tailscale is on, and that the PC is awake.

## Once that works: pick the node

Only worth adding after the two-action version is landing photos.

Insert between the two actions:

1. **Fetch the list** — another `Get Contents of URL`, method `GET`, no body:
   `https://p.tail1a906a.ts.net/api/active`
2. **Pull out the array** — an action that reads a value from a dictionary, key
   `active`. (`Get Dictionary Value`.)
3. **Choose** — an action that shows a list and returns the chosen item
   (`Choose from List`). If it offers a setting for which text to display, use
   `label`.
4. Then read `domain` and `node` off the chosen item, and put them in the URL.

`/api/active` exists precisely because Shortcuts has no sane way to choose from
107 nodes — it returns only the handful the board says are live today.

## Running it from inside the app

```
shortcuts://x-callback-url/run-shortcut?name=Snap&x-success=https://p.tail1a906a.ts.net/
```

`x-success` is what makes it a round trip: iOS returns you to the app when the
Shortcut finishes rather than leaving you in Shortcuts. Verified working from an
installed PWA in standalone mode.

## What the endpoint does with the image

```
POST /api/media?domain=<domain>[&node=<node>][&caption=<text>]
```

Raw body or multipart, both accepted. It downscales to 2048px on the long edge,
applies the EXIF rotation and then strips the tag — orientation matters, and the
rest of EXIF is location and device data nobody asked to keep — and re-encodes
to JPEG so an iPhone HEIC renders anywhere. A 3000×2000 photo lands at ~16 KB.

Then it appends `![caption](/media/…)` to that node's note, and returns:

```json
{"ok": true, "url": "/media/2026-07/7e908f07.jpg", "attached_to_note": true}
```

## Two things to hold in mind

**It only works while the PC is awake.** A Shortcut that fails at 11pm because
the desktop slept is worse than no Shortcut — you'll have taken the photo, lost
the moment, and not necessarily noticed. If this becomes a habit, add a
notification on the failure branch so it tells you.

**Photos are not in git.** `data/media/` is deliberately untracked — a year of
daily photos is a repo nobody wants to clone. The consequence is real: these
files have exactly one copy unless something else copies them.
