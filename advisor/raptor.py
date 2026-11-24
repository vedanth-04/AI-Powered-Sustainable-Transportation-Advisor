"""Round-based public transit routing (RAPTOR, Delling et al. 2012) over the Delhi network.

Round k holds the earliest arrival at every stop using at most k vehicles, so one
search returns the fastest journey for each number of rides (a time/transfer Pareto set).
Boarding respects rule-based buffers (metro security entry, interchange walking, ...).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from advisor.network import BUS, METRO, RAIL, Network

INF = np.iinfo(np.int32).max // 2


@dataclass
class Leg:
    kind: str                 # "walk" | "ride" | "cab"
    from_stop: int | None     # None = origin point
    to_stop: int | None       # None = destination point
    depart: int               # seconds after midnight
    arrive: int
    pattern: int | None = None
    trip: int | None = None
    board_pos: int | None = None
    alight_pos: int | None = None
    walk_m: float = 0.0


@dataclass
class RawJourney:
    legs: list[Leg]
    arrival: int
    rides: int


def _buffer_sec(net: Network, label: tuple, board_mode: int) -> int:
    b = net.config["transfer_buffers_min"]
    if label[0] == "ride":
        came = net.patterns[label[1]]["mode"]
        if came == METRO and board_mode == METRO:
            return b["metro_interchange"] * 60
        if came == RAIL and board_mode == RAIL:
            return b["rail_to_rail"] * 60
    if board_mode == METRO:
        return b["board_metro_from_street"] * 60
    if board_mode == RAIL:
        return b["board_rail_from_street"] * 60
    return b["board_bus"] * 60


def _buffer_table(net: Network) -> np.ndarray:
    """buf[came + 1, board_mode] in seconds; came = -1 (street/walk), 0 bus, 1 metro, 2 rail."""
    b = net.config["transfer_buffers_min"]
    street = [b["board_bus"] * 60, b["board_metro_from_street"] * 60, b["board_rail_from_street"] * 60]
    table = np.array([street] * 4, dtype=np.int64)
    table[METRO + 1, METRO] = b["metro_interchange"] * 60
    table[RAIL + 1, RAIL] = b["rail_to_rail"] * 60
    return table


def raptor(net: Network, access: dict[int, tuple[int, float]], egress: dict[int, tuple[int, float]], t0: int,
           active: np.ndarray, modes: set[int], max_rounds: int | None = None,
           horizon_sec: int | None = None) -> list[RawJourney]:
    """access/egress: stop -> (seconds, metres[, "walk" | "cab"]). Returns the best journey per ride count."""
    K = max_rounds or net.config["router"]["max_rounds"]
    horizon = t0 + (horizon_sec or net.config["router"]["search_window_min"] * 60)
    N = net.n_stops
    tau = [np.full(N, INF, dtype=np.int64)]
    came = [np.full(N, -1, dtype=np.int8)]  # how each stop was reached: -1 street/walk, else vehicle mode
    buf = _buffer_table(net)
    labels: list[dict] = [{}]
    best = np.full(N, INF, dtype=np.int64)
    for s, entry in access.items():
        sec, metres = entry[0], entry[1]
        tau[0][s] = t0 + sec
        best[s] = tau[0][s]
        labels[0][s] = ("access", sec, metres, entry[2] if len(entry) > 2 else "walk")
    marked = set(access)
    egress_items = list(egress.items())
    pattern_ok = np.array([active[p] and net.patterns[p]["mode"] in modes for p in range(len(net.patterns))])
    results: list[RawJourney] = []
    best_dest = INF

    for k in range(1, K + 1):
        cur = tau[k - 1].copy()
        tau.append(cur)
        cur_came = came[k - 1].copy()
        came.append(cur_came)
        prev_tau, prev_came = tau[k - 1], came[k - 1]
        labels.append({})
        queue: dict[int, int] = {}
        for s in marked:
            for p, i in net.stop_pat[net.stop_pat_off[s]:net.stop_pat_off[s + 1]]:
                if pattern_ok[p] and i < len(net.pat_stops[p]) - 1:
                    if queue.get(p, 1 << 30) > i:
                        queue[p] = int(i)
        new_marked = set()
        bound = min(best_dest, horizon + 3600)
        for p, start in queue.items():
            seq = net.pat_stops[p]
            arr = net.arr[p]
            dep_t = net.dep_t[p]
            pmode = net.patterns[p]["mode"]
            bufcol = buf[:, pmode]
            n_stops = len(seq)
            trip, board = -1, -1
            for i in range(start, n_stops):
                s = int(seq[i])
                if trip >= 0:
                    a = int(arr[trip, i])
                    if a < best[s] and a < bound:
                        cur[s] = a
                        best[s] = a
                        cur_came[s] = pmode
                        labels[k][s] = ("ride", p, trip, board, i)
                        new_marked.add(s)
                prev = prev_tau[s]
                if prev < INF and i < n_stops - 1:
                    need = prev + bufcol[prev_came[s] + 1]
                    if need > horizon or (trip >= 0 and need >= dep_t[i, trip]):
                        continue  # cannot catch an earlier trip here
                    col = dep_t[i]
                    j = int(col.searchsorted(need))
                    if j < len(col) and (trip < 0 or j < trip):
                        trip, board = j, i
        # walking transfers from stops reached by a vehicle in this round
        walked = set()
        for s in new_marked:
            base = cur[s]
            for e in range(net.fp_off[s], net.fp_off[s + 1]):
                s2 = int(net.fp_to[e])
                if s2 in new_marked:
                    continue
                t = base + int(net.fp_sec[e])
                if t < best[s2] and t < bound:
                    cur[s2] = t
                    best[s2] = t
                    cur_came[s2] = -1
                    labels[k][s2] = ("walk", s, int(net.fp_sec[e]))
                    walked.add(s2)
        marked = new_marked | walked
        # destination
        dest_t, dest_s = INF, None
        for s, entry in egress_items:
            sec = entry[0]
            if cur[s] < INF and cur[s] + sec < dest_t:
                dest_t, dest_s = int(cur[s] + sec), s
        if dest_s is not None and dest_t < best_dest:
            best_dest = dest_t
            results.append(_reconstruct(net, labels, k, dest_s, dest_t, egress[dest_s], tau))
        if not marked:
            break
    return results


def _reconstruct(net, labels, k, dest_s, dest_t, egress, tau) -> RawJourney:
    legs: list[Leg] = [Leg(egress[2] if len(egress) > 2 else "walk", dest_s, None, dest_t - egress[0], dest_t, walk_m=egress[1])]
    s, r = dest_s, k
    rides = 0
    while True:
        rr = r
        while rr >= 0 and s not in labels[rr]:
            rr -= 1
        lab = labels[rr][s]
        if lab[0] == "access":
            legs.append(Leg(lab[3], None, s, int(tau[0][s]) - lab[1], int(tau[0][s]), walk_m=lab[2]))
            break
        if lab[0] == "walk":
            src, sec = lab[1], lab[2]
            arrive = int(tau[rr][s])
            metres = sec * net.config["walking"]["speed_kmh"] / 3.6 / net.config["walking"]["detour_factor"]
            legs.append(Leg("walk", src, s, arrive - sec, arrive, walk_m=metres))
            s, r = src, rr
            continue
        _, p, trip, board, alight = lab
        seq = net.pat_stops[p]
        legs.append(Leg("ride", int(seq[board]), s, int(net.dep_t[p][board, trip]), int(net.arr[p][trip, alight]),
                        pattern=p, trip=trip, board_pos=board, alight_pos=alight))
        rides += 1
        s, r = int(seq[board]), rr - 1
    legs.reverse()
    return RawJourney(legs=[l for l in legs if not (l.kind == "walk" and l.from_stop == l.to_stop)],
                      arrival=dest_t, rides=rides)
