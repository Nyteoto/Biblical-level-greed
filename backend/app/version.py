"""What the browser and the server have to agree on, and how they find out.

The failure this exists to stop has happened three times: a backend change ships,
the long-running service keeps serving the old Python, and the app in front of it
looks broken in a way that has nothing to do with the code. The browser reloads
its own files off disk, so the frontend is always current; the Python process is
not, and nothing in the app could tell.

`API_VERSION` is bumped whenever a route, a payload or an event kind changes in a
way the frontend depends on. The browser carries the number it was built against
and asks the server for its own on start; if the server's is lower, it says so
and offers to restart the service. It is the same discipline as the golden
corpus — a number that has to be remembered — and the same argument: the check
costs nothing and the failure it catches is invisible.

Lower rather than merely different, on purpose: a browser holding a *stale page*
against a newer server is the other half of the same problem, and telling
somebody to restart a service that is already current would send them chasing a
thing that is not wrong. That case is a page reload, which the message says.
"""

# 1 — everything up to the phosphor re-skin.
# 2 — `shelf.latest`, `entries.places`, folder overviews (`overview`,
#     `overview_media`) and the two events behind them.
API_VERSION = 2
