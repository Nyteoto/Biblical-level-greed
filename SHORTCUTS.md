# Photos from iOS

Two actions.

1. **Take Photo** — search the action list for `photo`; the one that opens the
   camera.
2. **Get Contents of URL** — search `URL`; the one that *fetches* (not "Open
   URL"). Set:
   - URL `https://p.tail1a906a.ts.net/api/media?domain=electrical-engineering`
   - Method `POST`
   - Request Body **File** → the photo from step 1

Naming only the domain attaches to whatever it is working on today. Domain ids
are the `.toml` filenames. Out of season, it says so and asks for `&node=<id>`.

**Two blank fields break it.** A Headers row with no name sends `: `, which is
invalid HTTP and surfaces on iOS as "The network connection was lost". And
leave Request Body as *File* — no JSON.

**If it fails:** change the URL to `/api/health`, method `GET`, no body. Returns
`{"ok":true` → connection is fine, the POST body is wrong. Nothing → Tailscale
is off or the PC is asleep.

## Launching from the app

```
shortcuts://x-callback-url/run-shortcut?name=Snap&x-success=https://p.tail1a906a.ts.net/
```

`x-success` returns you to the app afterwards. Works from an installed PWA.

## Picking a node

Only worth adding once photos are landing. Between the two actions: GET
`/api/active`, take the `active` key, `Choose from List` (display `label`), then
put the chosen `domain` and `node` in the URL. That endpoint returns only what
is live today rather than all 107 nodes.

## Endpoint

```
POST /api/media?domain=<id>[&node=<id>][&caption=<text>]
```

Raw body or multipart. Downscales to 2048px, applies then strips EXIF,
re-encodes to JPEG. Appends `![caption](/media/…)` to the node's note.

Only works while the PC is awake. `data/media/` is not in git — one copy only.
