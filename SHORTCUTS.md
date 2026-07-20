# Sending photos from the iPad

Snap a photo of the whiteboard, the fretboard, the scope trace — and have it
land in the right node's notes, over Tailscale, without leaving the app.

## What was verified first

Two things were genuinely uncertain, so they were tested before any of this got
built:

| question | answer |
|---|---|
| Does `shortcuts://` fire from an **installed PWA in standalone mode**? | **Yes.** Apple documents the scheme for browsers and says nothing about standalone; it works. |
| Can Shortcuts reach the app over Tailscale? | **Yes**, and it sends plain HTTP — no App Transport Security upgrade. |

## The endpoint

```
POST /api/media?domain=<domain>&node=<node>&caption=<text>
```

Send the image as the raw request body, or as multipart — both are accepted,
because `Get Contents of URL` assembles the request differently depending on
how the file reached it, and being tolerant is cheaper than being exact.

It returns:

```json
{"ok": true, "url": "/media/2026-07/7e908f07.jpg", "attached_to_note": true}
```

and appends `![caption](/media/...)` to that node's note. The image is
downscaled to 2048px on the long edge, rotated per EXIF and then stripped of
it, and re-encoded as JPEG so an iPhone HEIC becomes something a browser can
draw. A 3000×2000 photo lands at about 16 KB.

## Two blank fields that break it

Found by capturing the raw request. Shortcuts sent:

```
: 
{"":"it ran"}
```

A header line with **no name**, and a JSON body with an **empty key**. The bare
`: ` is invalid HTTP and uvicorn rejects the whole request — which surfaced on
the phone as the uninformative "The network connection was lost".

So, in `Get Contents of URL`: delete any blank row under **Headers**, and never
leave a **JSON** key unnamed. Neither field is obviously empty in the UI, and
both follow you into any action you duplicate.

## Building the Shortcut

**Photo → node**, in six actions:

1. `Take Photo` — or `Select Photos` if you want the camera roll
2. `Get Contents of URL` → `https://p.tail1a906a.ts.net/api/active`
3. `Get Dictionary Value` → key `active`
4. `Choose from List` — pick the node; set *Item Text* to the `label` field
5. `Get Dictionary Value` twice, for `domain` and `node`, into variables
6. `Get Contents of URL`
   - URL: `https://p.tail1a906a.ts.net/api/media?domain=[domain]&node=[node]`
   - Method: **POST**
   - Request Body: **File** → the photo from step 1

Step 2–4 are why `/api/active` exists: Shortcuts has no good way to pick from
107 nodes, so it offers only the handful the board says are live today.

Name it something short — `Snap` — because the name goes in the URL below.

## Launching it from inside the app

```
shortcuts://x-callback-url/run-shortcut?name=Snap&x-success=https://p.tail1a906a.ts.net/
```

The `x-success` parameter is what makes this a round trip rather than a one-way
jump: iOS returns you to the app when the Shortcut finishes. Without it you are
left sitting in the Shortcuts app.

## The limitation, stated plainly

**This works only while the PC is awake.** A Shortcut that fails at 11pm
because the desktop slept is worse than no Shortcut — you will have taken the
photo, lost the moment, and not necessarily noticed the failure. If you build
this into a habit, put a `Show Notification` on the failure branch so it tells
you rather than failing quietly.

## Where the photos live

`data/media/YYYY-MM/<id>.jpg`, and **not in git**. A year of daily photos is a
repository nobody wants to clone. The consequence is real and worth holding
consciously: the repo stops being a complete backup, and these files have
exactly one copy unless something else copies them.
