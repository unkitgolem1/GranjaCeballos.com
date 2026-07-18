from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.application.schemas import PedidoCreate, PedidoUpdateEstatus, SuscripcionCreate, SuscripcionUpdate


class TestPedidoCreate:
    def test_valid_minimal(self):
        s = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=UUID(int=1),
            direccion="Mérida, Yucatán",
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        assert s.telefono == "9991234567"
        assert s.cantidad == 1
        assert s.email is None

    def test_valid_with_email(self):
        s = PedidoCreate(
            telefono="+529991234567",
            nombre="Juan Pérez",
            email="juan@example.com",
            paquete_id=UUID(int=1),
            direccion="Calle 53 #298, Mérida",
            cantidad=3,
            metodo_pago="tarjeta",
            fecha_usuario=date.today(),
        )
        assert s.email == "juan@example.com"

    def test_invalid_telefono(self):
        with pytest.raises(ValidationError, match="telefono"):
            PedidoCreate(
                telefono="abc",
                nombre="Juan",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="efectivo",
                fecha_usuario=date.today(),
            )

    def test_invalid_email(self):
        with pytest.raises(ValidationError, match="email"):
            PedidoCreate(
                telefono="9991234567",
                nombre="Juan",
                email="not-an-email",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="efectivo",
                fecha_usuario=date.today(),
            )

    def test_invalid_metodo_pago(self):
        with pytest.raises(ValidationError, match="metodo_pago"):
            PedidoCreate(
                telefono="9991234567",
                nombre="Juan",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="transferencia",
                fecha_usuario=date.today(),
            )

    def test_empty_nombre(self):
        with pytest.raises(ValidationError, match="nombre"):
            PedidoCreate(
                telefono="9991234567",
                nombre="",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="efectivo",
                fecha_usuario=date.today(),
            )

    def test_cantidad_minima(self):
        with pytest.raises(ValidationError, match="cantidad"):
            PedidoCreate(
                telefono="9991234567",
                nombre="Juan",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="efectivo",
                cantidad=0,
                fecha_usuario=date.today(),
            )

    def test_with_notas(self):
        s = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=UUID(int=1),
            direccion="Mérida",
            metodo_pago="efectivo",
            notas="Llamar antes de entregar",
            fecha_usuario=date.today(),
        )
        assert s.notas == "Llamar antes de entregar"


class TestSuscripcionCreate:
    def test_valid(self):
        s = SuscripcionCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=UUID(int=1),
            direccion="Mérida, Yucatán",
            metodo_pago="tarjeta",
            dia_entrega=1,
            fecha_inicio=date.today(),
        )
        assert s.dia_entrega == 1

    def test_dia_entrega_bounds(self):
        with pytest.raises(ValidationError):
            SuscripcionCreate(
                telefono="9991234567",
                nombre="Juan",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="tarjeta",
                dia_entrega=0,
                fecha_inicio=date.today(),
            )
        with pytest.raises(ValidationError):
            SuscripcionCreate(
                telefono="9991234567",
                nombre="Juan",
                paquete_id=UUID(int=1),
                direccion="Mérida",
                metodo_pago="tarjeta",
                dia_entrega=8,
                fecha_inicio=date.today(),
            )


class TestPedidoUpdateEstatus:
    def test_valid_statuses(self):
        for st in ("pendiente", "aceptado", "entregado", "cancelado", "rechazado"):
            s = PedidoUpdateEstatus(estatus=st)
            assert s.estatus == st

    def test_invalid_status(self):
        with pytest.raises(ValidationError, match="estatus"):
            PedidoUpdateEstatus(estatus="invalid")


class TestSuscripcionUpdate:
    def test_partial_update(self):
        s = SuscripcionUpdate(dia_entrega=3)
        assert s.dia_entrega == 3
        assert s.direccion is None
        assert s.activa is None

    def test_all_fields(self):
        s = SuscripcionUpdate(dia_entrega=5, direccion="Nueva dirección", activa=False)
        assert s.activa is False
