"""Lector de vectores_dorados.txt (compartido por las pruebas del codec y del simulador)."""
from pathlib import Path

import euler_proto as p

RUTA = Path(__file__).resolve().parent.parent / "vectores_dorados.txt"
ERRORES = {c.__name__: c for c in (p.TruncatedPacket, p.UnknownType, p.VersionMismatch,
                                   p.TrailingBytes, p.InvalidField)}


def _bytes(h):
    return b"" if h == "-" else bytes.fromhex(h)


def _objeto(campos):
    t = campos.pop("type")

    def i(k):
        return int(campos[k])

    if t == "HB":
        asg = []
        for k in range(i("n")):
            nx, tid, ra, dec = (int(x) for x in campos["a%d" % k].split(":"))
            asg.append(p.Assignment(nx, tid, ra, dec))
        return p.Heartbeat(i("base_id"), i("seq"), i("utc_ms"), i("lat_e7"), i("lon_e7"), i("flags"), tuple(asg))
    if t == "DOCK_REQ":
        return p.DockReq(i("nx"), i("seq"))
    if t == "DOCK_REF":
        q = tuple(float(x) for x in campos["q"].split(","))
        return p.DockRef(i("nx"), i("seq"), i("utc_ms"), q, i("stars"), i("flags"))
    if t == "ACK":
        return p.Ack(i("nx"), i("seq"))
    if t == "STATUS":
        return p.Status(i("nx"), i("battery_pct"), i("state"), i("since_sync_s"), i("correction_cdeg"), i("quality"))
    if t == "ASSIGN":
        return p.Assign(i("nx"), i("target_id"), i("ra_e7"), i("dec_e7"))
    raise ValueError(t)


def cargar():
    """Devuelve (validos, invalidos): [(nombre, bytes, objeto)] y [(nombre, bytes, clase_de_error)]."""
    validos, invalidos = [], []
    for linea in RUTA.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split()
        if partes[0] == "VALID":
            campos = dict(tok.split("=", 1) for tok in partes[3:])
            validos.append((partes[1], _bytes(partes[2]), _objeto(campos)))
        elif partes[0] == "INVALID":
            invalidos.append((partes[1], _bytes(partes[2]), ERRORES[partes[3]]))
        else:
            raise ValueError("linea desconocida: " + linea)
    return validos, invalidos
