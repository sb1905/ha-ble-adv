"""Remotes Unit Tests."""

# ruff: noqa: S101
import pytest
from ble_adv.codecs.models import BleAdvAdvertisement

from . import CODECS, _TestEncoderBase, _TestEncoderFull, _TestEncoderFullAll


@pytest.mark.parametrize(
    _TestEncoderBase.PARAM_NAMES,
    [
        ("remote_v4", 0xFF, "F0.FF.00.55.8F.24.04.08.65.79"),
        ("remote_fff0", 0x16, "FF.F0.7B.78.E2.7B.27.7B.84.62.7B.DE.7A.7B.51.37.62.F9.7B"),  # ON
        ("remote_fff0", 0x16, "FF.F0.7B.98.E2.81.30.7B.84.62.7B.D3.7A.7B.51.20.62.F4.7B"),  # FULL COLD
        ("remote_fff0", 0x16, "FF.F0.06.78.E2.06.2A.7B.84.62.7B.D3.7A.7B.51.3A.62.F4.7B"),  # HALF COLD + HALF WARM
    ],
)
class TestEncoderRemotes(_TestEncoderBase):
    """Remote Encoder tests."""


@pytest.mark.parametrize(
    _TestEncoderFull.PARAM_NAMES,
    [
        # ON
        (
            "remote_fff0",
            "02011A1416FFF07B78E27B277B84627BDE7A7B513762F97B",
            "cmd: 0x10, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 92, seed: 0x0000",
            "light_0: ['on'] / {'on': True}",
        ),
        # OFF
        (
            "remote_fff0",
            "02011A1416FFF07B7EE27B227B84627BDD7A7B513262FA7B",
            "cmd: 0x11, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 89, seed: 0x0000",
            "light_0: ['on'] / {'on': False}",
        ),
        # NIGHT MODE
        (
            "remote_fff0",
            "02011A1416FFF07B63E27B3E7B84627BDC7A7B512E62FB7B",
            "cmd: 0x23, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 69, seed: 0x0000",
            "light_0: ['on', 'cold', 'warm'] / {'sub_type': 'cww', 'on': True, 'cold': 0.1, 'warm': 0.1}",
        ),
        # FULL WARM
        (
            "remote_fff0",
            "02011A1416FFF08194E27B3C7B84627BD37A7B512C62F47B",
            "cmd: 0x21, param: 0x00, args: [64,0,255]",
            "id: 0x99FF192A, index: 0, tx: 71, seed: 0x0000",
            "light_0: ['cold', 'warm'] / {'sub_type': 'cww', 'cold': 0.0, 'warm': 1.0}",
        ),
        # FULL COLD
        (
            "remote_fff0",
            "02011A1416FFF07B98E281307B84627BD37A7B512062F47B",
            "cmd: 0x21, param: 0x00, args: [64,255,0]",
            "id: 0x99FF192A, index: 0, tx: 75, seed: 0x0000",
            "light_0: ['cold', 'warm'] / {'sub_type': 'cww', 'cold': 1.0, 'warm': 0.0}",
        ),
        # FULL COLD + FULL WARM
        (
            "remote_fff0",
            "02011A1416FFF08163E281317B84627BD37A7B512162F47B",
            "cmd: 0x21, param: 0x00, args: [64,255,255]",
            "id: 0x99FF192A, index: 0, tx: 74, seed: 0x0000",
            "light_0: ['cold', 'warm'] / {'sub_type': 'cww', 'cold': 1.0, 'warm': 1.0}",
        ),
        # HALF COLD + HALF WARM
        (
            "remote_fff0",
            "02011A1416FFF00678E2062A7B84627BD37A7B513A62F47B",
            "cmd: 0x21, param: 0x00, args: [1,127,127]",
            "id: 0x99FF192A, index: 0, tx: 81, seed: 0x0000",
            "light_0: ['cold', 'warm'] / {'sub_type': 'cww', 'cold': 0.5, 'warm': 0.5}",
        ),
        # BRIGHTNESS +
        (
            "remote_fff0",
            "02011A1416FFF07B65E27B367B84627BD27A7B512662F57B",
            "cmd: 0x21, param: 0x00, args: [20,0,0]",
            "id: 0x99FF192A, index: 0, tx: 77, seed: 0x0000",
            "light_0: ['cmd'] / {'sub_type': 'cww', 'cmd': 'B+', 'step': 0.1}",
        ),
        # BRIGHTNESS -
        (
            "remote_fff0",
            "02011A1416FFF07B7BE27B2B7B84627BD17A7B513B62F67B",
            "cmd: 0x21, param: 0x00, args: [40,0,0]",
            "id: 0x99FF192A, index: 0, tx: 80, seed: 0x0000",
            "light_0: ['cmd'] / {'sub_type': 'cww', 'cmd': 'B-', 'step': 0.1}",
        ),
        # COLDER
        (
            "remote_fff0",
            "02011A1416FFF07B79E27B287B84627BD07A7B513862F77B",
            "cmd: 0x21, param: 0x00, args: [36,0,0]",
            "id: 0x99FF192A, index: 0, tx: 83, seed: 0x0000",
            "light_0: ['cmd'] / {'sub_type': 'cww', 'cmd': 'K+', 'step': 0.1}",
        ),
        # WARMER
        (
            "remote_fff0",
            "02011A1416FFF07B7BE27B2D7B84627BD77A7B513D62F07B",
            "cmd: 0x21, param: 0x00, args: [24,0,0]",
            "id: 0x99FF192A, index: 0, tx: 86, seed: 0x0000",
            "light_0: ['cmd'] / {'sub_type': 'cww', 'cmd': 'K-', 'step': 0.1}",
        ),
        # SECOND LIGHT BUTTON (alternating codes)
        (
            "remote_fff0",
            "02011A1416FFF07B69E27B3C7B84627BD47A7B512C62F37B",
            "cmd: 0x12, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 71, seed: 0x0000",
            "light_1: ['on'] / {'on': True}",
        ),
        (
            "remote_fff0",
            "02011A1416FFF07B77E27B3D7B84627BCB7A7B512D62EC7B",
            "cmd: 0x13, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 70, seed: 0x0000",
            "light_1: ['on'] / {'on': False}",
        ),
    ],
)
class TestEncoderRemoteFff0(_TestEncoderFull):
    """Remote 0xFFF0 Encoder / Decoder tests, real captures."""

    _with_reverse = False


@pytest.mark.parametrize(
    _TestEncoderFullAll.PARAM_NAMES,
    [
        (
            "remote_fff0",
            [],
            "sl_as_full_cold",
            "02011A1416FFF07B69E27B3C7B84627BD47A7B512C62F37B",
            "cmd: 0x12, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 71, seed: 0x0000",
            "light_0: ['on', 'cold', 'warm'] / {'sub_type': 'cww', 'on': True, 'cold': 1.0, 'warm': 0.0}",
        ),
        (
            "remote_fff0",
            [],
            "sl_as_full_cold",
            "02011A1416FFF07B77E27B3D7B84627BCB7A7B512D62EC7B",
            "cmd: 0x13, param: 0x00, args: [0,0,0]",
            "id: 0x99FF192A, index: 0, tx: 70, seed: 0x0000",
            "light_0: ['on', 'cold', 'warm'] / {'sub_type': 'cww', 'on': True, 'cold': 1.0, 'warm': 0.0}",
        ),
    ],
)
class TestEncoderRemoteFff0Sets(_TestEncoderFullAll):
    """Remote 0xFFF0 translator sets, decoding only."""

    _with_reverse = False


@pytest.mark.parametrize(
    "raw",
    [
        # Garbled receptions (two advertisements mixed), must be rejected by the checks
        "02011A1416FFF081ECE27B447B1EF787409B348619C491FC6168A4830239DB",
        "02011A1416FFF081ECE27B447B84627BD37A7B5154C491FC6168A4830239DB",
        "02011A1416FFF081F5E27B5D7B3AF4807CF240FE6336E4798F43D66402D187",
        # Unknown button
        "02011A1416FFF07B7DE27B277B84627BDB7A7B513762FC7B",
    ],
)
def test_remote_fff0_rejected(raw: str) -> None:
    """Invalid 0xFFF0 advertisements are not decoded."""
    enc_cmd, conf = CODECS["remote_fff0"].decode_adv(BleAdvAdvertisement.FromRaw(bytes.fromhex(raw)))
    assert enc_cmd is None
    assert conf is None
