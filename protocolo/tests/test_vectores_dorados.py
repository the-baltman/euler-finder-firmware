"""El codec contra los vectores dorados armados a mano."""
import pytest

import euler_proto as p
from vectores import cargar

VALIDOS, INVALIDOS = cargar()


def test_el_archivo_trae_vectores_de_los_seis_tipos():
    tipos = {type(o) for _, _, o in VALIDOS}
    assert tipos == {p.Heartbeat, p.DockReq, p.DockRef, p.Ack, p.Status, p.Assign}
    assert len(INVALIDOS) >= 30


@pytest.mark.parametrize("nombre,datos,obj", VALIDOS, ids=[v[0] for v in VALIDOS])
def test_decodifica_el_vector(nombre, datos, obj):
    assert p.decode(datos) == obj


@pytest.mark.parametrize("nombre,datos,obj", VALIDOS, ids=[v[0] for v in VALIDOS])
def test_codifica_exactamente_los_bytes_dorados(nombre, datos, obj):
    assert p.encode(obj) == datos


@pytest.mark.parametrize("nombre,datos,clase", INVALIDOS, ids=[v[0] for v in INVALIDOS])
def test_rechaza_el_vector_invalido_con_su_clase(nombre, datos, clase):
    # Se exige la clase exacta (no una subclase) para que cada rechazo sea por la razon correcta.
    with pytest.raises(p.ProtocolError) as ei:
        p.decode(datos)
    assert type(ei.value) is clase


@pytest.mark.parametrize("nombre,datos,obj", VALIDOS, ids=[v[0] for v in VALIDOS])
def test_ningun_prefijo_propio_se_acepta(nombre, datos, obj):
    for n in range(len(datos)):
        with pytest.raises(p.ProtocolError):
            p.decode(datos[:n])
