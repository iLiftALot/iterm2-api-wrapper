from __future__ import annotations

from typing_extensions import assert_type

from iterm2_api_wrapper.api.it2connection import Connection as ConcreteConnection
from iterm2_api_wrapper.core.gateway import Connection as ConnectionProtocol
from iterm2_api_wrapper.core.gateway import ConnectionFactory, _async_create_connection_with_retry
from tests.fake import FakeConnection


class ConcreteConnectionSubclass(ConcreteConnection):
    pass


class FactoryProduct:
    pass


class StaticFactory:
    @staticmethod
    async def async_create() -> FactoryProduct:
        return FactoryProduct()


def _check_instance_contracts() -> None:
    concrete: ConnectionProtocol = ConcreteConnection()
    fake: ConnectionProtocol = FakeConnection()

    del concrete, fake


def _check_factory_contracts() -> None:
    concrete_factory: ConnectionFactory[ConcreteConnection] = ConcreteConnection
    subclass_factory: ConnectionFactory[ConcreteConnectionSubclass] = ConcreteConnectionSubclass
    static_factory: ConnectionFactory[FactoryProduct] = StaticFactory

    del concrete_factory, subclass_factory, static_factory


async def _check_factory_results() -> None:
    concrete = await _async_create_connection_with_retry(ConcreteConnection, timeout_s=1.0)
    subclass = await _async_create_connection_with_retry(ConcreteConnectionSubclass, timeout_s=1.0)
    static_product = await _async_create_connection_with_retry(StaticFactory, timeout_s=1.0)

    assert_type(concrete, ConcreteConnection)
    assert_type(subclass, ConcreteConnectionSubclass)
    assert_type(static_product, FactoryProduct)
