"""Coordinator tests."""

# ruff: noqa: S101
import asyncio
from datetime import datetime, timedelta
from unittest import mock

from ble_adv.adapters import BleAdvQueueItem
from ble_adv.codecs.const import ATTR_CMD, ATTR_CMD_BR_UP, ATTR_STEP
from ble_adv.codecs.models import BleAdvAdvertisement, BleAdvCodec, BleAdvConfig, BleAdvEncCmd, BleAdvEntAttr
from ble_adv.const import CONF_ADAPTER_ID, CONF_DEVICE_QUEUE, CONF_DURATION, CONF_INTERVAL, CONF_RAW, CONF_REPEAT
from ble_adv.coordinator import BleAdvBaseDevice, BleAdvCoordinator, BleAdvRecvItem
from homeassistant.core import HomeAssistant
from homeassistant.loader import Manifest

from tests.conftest import MockEspProxy


class _Codec(mock.MagicMock):
    decode_adv = mock.MagicMock(return_value=(BleAdvEncCmd(0x10), BleAdvConfig(1, 0)))
    encode_advs = mock.MagicMock(return_value=[BleAdvAdvertisement(0xFF, b"bouhbouh")])
    enc_to_ent = mock.MagicMock(return_value=[])
    ign_duration = 2
    consolidate = mock.MagicMock(return_value=BleAdvEncCmd(0x20))
    get_translator_sets = mock.MagicMock(return_value={BleAdvCodec.DEF_TRANS_NAME: [], "tr_test": []})


class _Device(BleAdvBaseDevice):
    def __init__(self, coord: BleAdvCoordinator, name: str, codec_id: str, adapter_ids: list[str]) -> None:
        super().__init__(coord, name, codec_id, adapter_ids, 1, 10, 1000, BleAdvConfig(1, 1))


def _get_codecs() -> dict[str, BleAdvCodec]:
    cod1 = _Codec()
    cod1.codec_id = "cod1"
    cod1.match_id = "cod1"
    cod1.match_params = []
    cod2 = _Codec()
    cod2.codec_id = "cod2/a"
    cod2.match_id = "cod2"
    cod2.match_params = []
    return {cod1.codec_id: cod1, cod2.codec_id: cod2}


async def test_coordinator(hass: HomeAssistant, coord: BleAdvCoordinator) -> None:
    """Test coordinator."""
    coord.codecs = _get_codecs()
    assert list(coord.codecs.keys()) == ["cod1", "cod2/a"]
    assert coord.get_adapter_ids() == []
    dev1 = _Device(coord, "dev1", "cod1", ["esp/test"])
    coord.add_device(dev1)
    t1 = MockEspProxy(hass, "test")
    await t1.setup()
    assert coord.get_adapter_ids() == ["esp/test"]
    adv = BleAdvAdvertisement(0xFF, b"dtwithminlen", 0x1A)
    qi = BleAdvQueueItem(0x10, 1, 100, 20, [adv.to_raw()], 2)
    await coord.advertise("esp/not-exists", "q1", qi)
    await coord.advertise("esp/test", "q1", qi)
    await coord.bt_managers[1].adapters["esp/test"].drain()
    assert t1.get_adv_calls() == [{"raw": adv.to_raw().hex()}]
    await coord.handle_raw_adv("esp/test", "", adv.to_raw())
    await t1.recv(adv.to_raw().hex())
    adv.ad_flag = 0x1B
    await coord.handle_raw_adv("esp/test", "", adv.to_raw())
    await coord.handle_raw_adv("esp/test", "", b"invalid_adv")
    await coord.advertise("esp/test", "q1", qi)
    await coord.bt_managers[1].adapters["esp/test"].drain()
    coord.remove_device(dev1)

    dev2 = _Device(coord, "dev1", "cod1", ["other"])
    coord.add_device(dev2)
    adv2 = BleAdvAdvertisement(0xFF, b"2dt2", 0x1A)
    await coord.handle_raw_adv("esp/test", "", adv2.to_raw())
    coord.remove_device(dev2)
    assert coord.has_available_adapters()


async def test_device_pub(hass: HomeAssistant, coord: BleAdvCoordinator) -> None:
    """Test device publication."""
    codecs = _get_codecs()
    cod1: BleAdvCodec = codecs["cod1"]
    coord.codecs = _get_codecs()
    dev1 = _Device(coord, "dev1", "cod1", ["esp/test"])
    dev1.add_listener("cod1", BleAdvConfig(1, 0), True)
    assert dev1.prev_cmd is None
    coord.add_device(dev1)
    t1 = MockEspProxy(hass, "test")
    await t1.setup()
    base_adv1 = b"base_adv_nb1"
    adv1 = BleAdvAdvertisement(0xFF, base_adv1, 0x1A)
    await coord.handle_raw_adv("esp/test", "", bytes(adv1.to_raw()))
    cod1.consolidate.assert_called_once_with(BleAdvEncCmd(0x10), None)  # type: ignore[mock]
    cod1.consolidate.reset_mock()  # type: ignore[mock]
    recv1 = coord._dec_last_advs.get(base_adv1)  # noqa: SLF001
    assert recv1 is not None
    assert recv1.pub_devices == {"dev1"}
    assert recv1.enc_cmd.cmd == 0x10
    assert dev1.prev_cmd == BleAdvEncCmd(0x10)
    dev1.prev_cmd = BleAdvEncCmd(0x20)
    base_adv2 = b"base_adv_nb2"
    adv2 = BleAdvAdvertisement(0xFF, base_adv2, 0x1A)
    await coord.handle_raw_adv("esp/test", "", bytes(adv2.to_raw()))
    cod1.consolidate.assert_called_once_with(BleAdvEncCmd(0x10), BleAdvEncCmd(0x20))  # type: ignore[mock]
    recv2 = coord._dec_last_advs.get(base_adv2)  # noqa: SLF001
    assert recv2 is not None
    assert dev1.prev_cmd == BleAdvEncCmd(0x10)


async def test_deduplicate_tx_count_seed(coord: BleAdvCoordinator) -> None:
    """Test deduplication of received cmd with same tx_count and seed."""
    codecs = _get_codecs()
    cod1: BleAdvCodec = codecs["cod1"]
    coord.codecs = _get_codecs()
    dev1 = _Device(coord, "dev1", "cod1", ["esp/test"])
    dev1.add_listener("cod1", BleAdvConfig(1, 0), True)
    dev1.async_on_command = mock.AsyncMock()
    assert dev1.prev_cmd is None
    assert dev1.prev_seed == 0
    assert dev1.prev_tx_count == 0
    coord.add_device(dev1)
    conf1 = BleAdvConfig(1, 0)
    conf1.tx_count = 1
    recv1 = BleAdvRecvItem(datetime.now(), cod1, set(), conf1, BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv1)  # noqa: SLF001
    dev1.async_on_command.assert_called_once_with([], False)
    dev1.async_on_command.reset_mock()
    # Recv command with different tx_count: OK
    conf2 = BleAdvConfig(1, 0)
    conf2.tx_count = 2
    recv2 = BleAdvRecvItem(datetime.now(), cod1, set(), conf2, BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv2)  # noqa: SLF001
    dev1.async_on_command.assert_called_once_with([], False)
    dev1.async_on_command.reset_mock()
    # RE recv same: command ignored
    conf2 = BleAdvConfig(1, 0)
    conf2.tx_count = 2
    recv2 = BleAdvRecvItem(datetime.now(), cod1, set(), conf2, BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv2)  # noqa: SLF001
    dev1.async_on_command.assert_not_called()
    dev1.async_on_command.reset_mock()
    # receive with tx_count = 0 and seed = 0 => always ok
    conf0 = BleAdvConfig(1, 0)
    recv0 = BleAdvRecvItem(datetime.now(), cod1, set(), conf0, BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv0)  # noqa: SLF001
    dev1.async_on_command.assert_called_once_with([], False)
    dev1.async_on_command.reset_mock()
    # RE receive with tx_count = 0 and seed = 0 => always ok
    conf0 = BleAdvConfig(1, 0)
    recv0 = BleAdvRecvItem(datetime.now(), cod1, set(), conf0, BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv0)  # noqa: SLF001
    dev1.async_on_command.assert_called_once_with([], False)
    dev1.async_on_command.reset_mock()


async def test_listener_translator_set(coord: BleAdvCoordinator) -> None:
    """Test commands from a linked controller are decoded with that controller's translator set."""
    codecs = _get_codecs()
    cod1: BleAdvCodec = codecs["cod1"]
    cod2: BleAdvCodec = codecs["cod2/a"]
    coord.codecs = codecs
    dev1 = _Device(coord, "dev1", "cod1", ["esp/test"])
    dev1.add_listener("cod2/a", BleAdvConfig(2, 0, None, "tr_test"), True)
    dev1.add_listener("cod2/a", BleAdvConfig(3, 0), True)
    dev1.async_on_command = mock.AsyncMock()
    coord.add_device(dev1)
    assert dev1.listener_translator_set("cod1", "esp/test", BleAdvConfig(1, 1)) == BleAdvCodec.DEF_TRANS_NAME
    assert dev1.listener_translator_set("cod2", "esp/test", BleAdvConfig(2, 0)) == "tr_test"
    assert dev1.listener_translator_set("cod2", "esp/test", BleAdvConfig(3, 0)) == BleAdvCodec.DEF_TRANS_NAME
    assert dev1.listener_translator_set("cod2", "esp/other", BleAdvConfig(2, 0)) == BleAdvCodec.DEF_TRANS_NAME
    cod2.enc_to_ent.reset_mock()  # type: ignore[mock]
    recv = BleAdvRecvItem(datetime.now(), cod2, set(), BleAdvConfig(2, 0), BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv)  # noqa: SLF001
    cod2.enc_to_ent.assert_called_once_with(BleAdvEncCmd(0x20), "tr_test")  # type: ignore[mock]
    dev1.async_on_command.assert_called_once_with([], False)
    cod1.enc_to_ent.reset_mock()  # type: ignore[mock]
    recv = BleAdvRecvItem(datetime.now(), cod1, set(), BleAdvConfig(1, 1), BleAdvEncCmd(0x10))
    await coord._publish_to_devices("esp/test", recv)  # noqa: SLF001
    cod1.enc_to_ent.assert_called_once_with(BleAdvEncCmd(0x20), BleAdvCodec.DEF_TRANS_NAME)  # type: ignore[mock]


async def test_echo_from_other_format(coord: BleAdvCoordinator) -> None:
    """Test a change received in two formats from the same remote press is applied only once."""
    codecs = _get_codecs()
    cod1: BleAdvCodec = codecs["cod1"]
    cod2: BleAdvCodec = codecs["cod2/a"]
    coord.codecs = codecs
    dev1 = _Device(coord, "dev1", "cod1", ["esp/test"])
    dev1.add_listener("cod1", BleAdvConfig(1, 0), True)
    dev1.add_listener("cod2/a", BleAdvConfig(2, 0), True)
    dev1.async_on_command = mock.AsyncMock()
    coord.add_device(dev1)
    br_up = [BleAdvEntAttr([ATTR_CMD], {ATTR_CMD: ATTR_CMD_BR_UP, ATTR_STEP: 0.1}, "light", 0)]
    t0 = datetime.now()
    # Direct checks
    assert not dev1.is_echo(("cod1", 1, 0), br_up, t0)
    assert dev1.is_echo(("cod2", 2, 0), br_up, t0 + timedelta(milliseconds=100))  # same press, other format
    assert not dev1.is_echo(("cod1", 1, 0), br_up, t0 + timedelta(milliseconds=200))  # same source: new press
    assert not dev1.is_echo(("cod2", 2, 0), br_up, t0 + timedelta(seconds=1))  # too late: new press
    assert not dev1.is_echo(("cod1", 1, 0), [], t0 + timedelta(seconds=1))  # nothing to apply
    # Through the coordinator: both formats of one press, only the first is applied
    dev1._last_change = None  # noqa: SLF001
    cod1.enc_to_ent = mock.MagicMock(return_value=br_up)  # type: ignore[method-assign]
    cod2.enc_to_ent = mock.MagicMock(return_value=br_up)  # type: ignore[method-assign]
    conf1 = BleAdvConfig(1, 0)
    conf1.tx_count = 5
    await coord._publish_to_devices("esp/test", BleAdvRecvItem(datetime.now(), cod1, set(), conf1, BleAdvEncCmd(0x10)))  # noqa: SLF001
    conf2 = BleAdvConfig(2, 0)
    conf2.tx_count = 5  # same tx count as the other format: must not be dropped as a duplicate
    await coord._publish_to_devices("esp/test", BleAdvRecvItem(datetime.now(), cod2, set(), conf2, BleAdvEncCmd(0x10)))  # noqa: SLF001
    dev1.async_on_command.assert_called_once_with(br_up, False)
    cod2.enc_to_ent.assert_called_once()


async def test_listening(coord: BleAdvCoordinator) -> None:
    """Test listening mode."""
    coord.codecs = _get_codecs()
    coord.start_listening(0.1)
    assert coord.is_listening()
    raw_adv = bytes([0x03, 0xFF, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34])
    await coord.handle_raw_adv("aaa", "mac", raw_adv)
    await coord.handle_raw_adv("bbb", "mac", raw_adv)
    await coord.handle_raw_adv("aaa", "mac", raw_adv)
    assert coord.listened_raw_advs == [raw_adv]
    assert coord.listened_decoded_confs == [("aaa", "cod1", "cod1", [], BleAdvConfig(1, 0)), ("aaa", "cod2/a", "cod2", [], BleAdvConfig(1, 0))]
    await asyncio.sleep(0.2)
    assert not coord.is_listening()


async def test_ign_cid(coord: BleAdvCoordinator) -> None:
    """Test Ignored Company IDs."""
    coord.ign_cids = {0x3412}
    coord.start_listening(0.1)
    raw_adv = bytes([0x03, 0xFF, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34])
    await coord.handle_raw_adv("aaa", "mac1", raw_adv)
    assert coord.listened_raw_advs == []


async def test_ign_mac(coord: BleAdvCoordinator) -> None:
    """Test Ignored Macs."""
    coord.ign_macs = {"mac1"}
    coord.start_listening(0.1)
    raw_adv = bytes([0x03, 0xFF, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34])
    await coord.handle_raw_adv("aaa", "mac1", raw_adv)
    assert coord.listened_raw_advs == []


async def test_adapter_mac(hass: HomeAssistant, coord: BleAdvCoordinator) -> None:
    """Test Adapter Macs are ignored."""
    t1 = MockEspProxy(hass, "test")
    await t1.setup()
    assert coord.get_adapter_ids() == ["esp/test"]
    coord.start_listening(0.1)
    raw_adv = bytes([0x03, 0xFF, 0x12, 0x34, 0x12, 0x34, 0x12, 0x34])
    await coord.handle_raw_adv("aaa", "00:00:00:00:00:00", raw_adv)
    assert coord.listened_raw_advs == []


async def test_inject_raw(hass: HomeAssistant, coord: BleAdvCoordinator) -> None:
    """Test Raw Injection."""
    coord.advertise = mock.AsyncMock()
    t1 = MockEspProxy(hass, "test")
    await t1.setup()
    assert coord.get_adapter_ids() == ["esp/test"]
    params = {CONF_DURATION: 100, CONF_REPEAT: 1, CONF_INTERVAL: 10, CONF_DEVICE_QUEUE: "test"}
    errors = await coord.inject_raw({CONF_RAW: "1234", CONF_ADAPTER_ID: "esp/test", **params})
    assert errors == {}
    coord.advertise.assert_awaited_once_with("esp/test", "test", BleAdvQueueItem(None, 1, 100, 10, [bytes([0x12, 0x34])], 2))
    errors = await coord.inject_raw({CONF_RAW: "123", CONF_ADAPTER_ID: "esp/test", **params})
    assert errors == {CONF_RAW: "Cannot convert to bytes"}
    errors = await coord.inject_raw({CONF_RAW: "123a", CONF_ADAPTER_ID: "not exists", **params})
    assert errors == {CONF_ADAPTER_ID: "Should be in ['esp/test']"}
    await coord.async_final()


async def test_decode_raw(coord: BleAdvCoordinator) -> None:
    """Test Raw Decoding."""
    coord.codecs = {"cod1": _Codec()}
    res = coord.decode_raw("123")
    assert res == ["Cannot convert to bytes"]
    res = coord.decode_raw("1234")
    assert res == ["cod1", "1234", "cmd: 0x10, param: 0x00, args: [0,0,0]", "id: 0x00000001, index: 0, tx: 0, seed: 0x0000", "", "<tr_test> "]
    coord.codecs.clear()
    res = coord.decode_raw("1234")
    assert res == ["Could not be decoded by any known codec"]


async def test_full_diagnostics(coord: BleAdvCoordinator) -> None:
    """Test Full Diagnostics."""

    class _MockIntegration:
        manifest = Manifest({"domain": "ble_adv", "version": "1.0"})

    async def _mock_async_get_integration(_: HomeAssistant, __: str) -> _MockIntegration:
        return _MockIntegration()

    with mock.patch("ble_adv.coordinator.async_get_integration", side_effect=_mock_async_get_integration):
        diag = await coord.full_diagnostic_dump()
        assert len(diag["coordinator"]) > 0
