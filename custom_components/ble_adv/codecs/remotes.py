"""No Name physical remotes."""

from .const import (
    ATTR_CMD,
    ATTR_CMD_BR_DOWN,
    ATTR_CMD_BR_UP,
    ATTR_CMD_CT_DOWN,
    ATTR_CMD_CT_UP,
    ATTR_CMD_TOGGLE,
    ATTR_COLD,
    ATTR_ON,
    ATTR_STEP,
    ATTR_WARM,
)
from .fanlamp import TRANS_FANLAMP_V2, FanLampEncoder
from .models import (
    BleAdvCodec,
    BleAdvConfig,
    BleAdvEncCmd,
    CTLightCmd,
    LightCmd,
    Trans,
)
from .models import EncoderMatcher as EncCmd


class RemoteEncoder(BleAdvCodec):
    """Phisical Remote encoder."""

    _len = 8

    def _checksum(self, buffer: bytearray) -> int:
        return sum(buffer) & 0xFF

    def decrypt(self, buffer: bytearray) -> bytearray | None:
        """Decrypt / unwhiten an incoming raw buffer into a readable buffer."""
        if not self.is_eq(self._checksum(buffer[:-1]), buffer[-1], "Checksum"):
            return None
        return buffer

    def encrypt(self, buffer: bytearray) -> bytearray:
        """Encrypt / whiten a readable buffer."""
        return buffer + bytearray([self._checksum(buffer)])

    def convert_to_enc(self, decoded: bytearray) -> tuple[BleAdvEncCmd | None, BleAdvConfig | None]:
        """Convert a readable buffer into an encoder command and a config."""
        conf = BleAdvConfig()
        conf.tx_count = decoded[6]
        conf.id = int.from_bytes(decoded[1:5], "little")

        enc_cmd = BleAdvEncCmd(decoded[5] & 0x3F)
        enc_cmd.arg0 = decoded[0]
        enc_cmd.arg1 = decoded[5] & 0xC0

        return enc_cmd, conf

    def convert_from_enc(self, enc_cmd: BleAdvEncCmd, conf: BleAdvConfig) -> bytearray:
        """Convert an encoder command and a config into a readable buffer."""
        uid = conf.id.to_bytes(4, "little")
        return bytearray([enc_cmd.arg0, *uid, enc_cmd.cmd | enc_cmd.arg1, conf.tx_count])


TRANS = [
    Trans(LightCmd().act(ATTR_ON, True), EncCmd(0x08)),
    Trans(LightCmd().act(ATTR_ON, False), EncCmd(0x06)),
    Trans(LightCmd(1).act(ATTR_CMD, ATTR_CMD_TOGGLE), EncCmd(0x13)).no_direct(),
    Trans(CTLightCmd().act(ATTR_COLD, 0.1).act(ATTR_WARM, 0.1), EncCmd(0x10)).no_direct(),
    Trans(CTLightCmd().act(ATTR_CMD, ATTR_CMD_CT_UP), EncCmd(0x02)).copy(ATTR_STEP, "arg0", 10).no_direct(),
    Trans(CTLightCmd().act(ATTR_CMD, ATTR_CMD_CT_DOWN), EncCmd(0x03)).copy(ATTR_STEP, "arg0", 10).no_direct(),
    Trans(CTLightCmd().act(ATTR_CMD, ATTR_CMD_BR_UP), EncCmd(0x0A)).copy(ATTR_STEP, "arg0", 10).no_direct(),
    Trans(CTLightCmd().act(ATTR_CMD, ATTR_CMD_BR_DOWN), EncCmd(0x0B)).copy(ATTR_STEP, "arg0", 10).no_direct(),
    # CCT / brightness Cycle: 0x07
]


class RemoteFff0Encoder(FanLampEncoder):
    """Physical remote sending a short 0xFFF0 service data advertisement next to its Lamp Smart Pro advertisement.

    Each byte is XOR-ed with 0x7B. Decoded layout:
    [0] warm (0-250), [1] check, [2] id, [3] cold (0-250), [4] counter, [5] 0x00, [6-7] id, [8] 0x00,
    [9] button, [10] 0x01, [11] 0x00, [12] id, [13] counter ^ 0x10, [14] = [7], [15] button ^ 0x27, [16] 0x00
    The commands are converted to their Lamp Smart Pro equivalent so the same translators apply.
    """

    _len = 17
    _XOR = 0x7B
    _BUTTONS: dict[int, tuple[int, int]] = {
        0xA5: (0x10, 0x00),  # ON
        0xA6: (0x11, 0x00),  # OFF
        0xA7: (0x23, 0x00),  # Night Mode
        0xA8: (0x21, 0x40),  # Cold / Warm levels
        0xA9: (0x21, 0x14),  # Brightness +
        0xAA: (0x21, 0x28),  # Brightness -
        0xAB: (0x21, 0x24),  # Colder
        0xAC: (0x21, 0x18),  # Warmer
        0xAF: (0x12, 0x00),  # Second light button, alternating with 0xB0
        0xB0: (0x13, 0x00),  # Second light button, alternating with 0xAF
    }

    def _check(self, buffer: bytearray) -> int:
        return buffer[0] ^ buffer[3] ^ buffer[4] ^ buffer[9] ^ 0xFA

    def decrypt(self, buffer: bytearray) -> bytearray | None:
        """Decrypt / unwhiten an incoming raw buffer into a readable buffer."""
        decoded = bytearray(x ^ self._XOR for x in buffer)
        if (
            not self.is_eq(self._check(decoded), decoded[1], "Check")
            or not self.is_eq(decoded[4] ^ 0x10, decoded[13], "Counter Copy")
            or not self.is_eq(decoded[9] ^ 0x27, decoded[15], "Button Copy")
            or not self.is_eq(decoded[7], decoded[14], "Id Copy")
            or not self.is_eq_buf(
                bytes([0x00, 0x00, 0x01, 0x00, 0x00]), bytes([decoded[5], decoded[8], decoded[10], decoded[11], decoded[16]]), "Fixed"
            )
        ):
            return None
        return decoded

    def encrypt(self, decoded: bytearray) -> bytearray:
        """Encrypt / whiten a readable buffer."""
        return bytearray(x ^ self._XOR for x in decoded)

    def convert_to_enc(self, decoded: bytearray) -> tuple[BleAdvEncCmd | None, BleAdvConfig | None]:
        """Convert a readable buffer into an encoder command and a config."""
        if (button := self._BUTTONS.get(decoded[9])) is None:
            return None, None
        conf = BleAdvConfig(int.from_bytes(bytes([decoded[2], decoded[6], decoded[7], decoded[12]]), "big"), 0)
        conf.tx_count = decoded[4]
        enc_cmd = BleAdvEncCmd(button[0])
        enc_cmd.arg0 = button[1]
        if decoded[9] == 0xA8:
            if decoded[0] == decoded[3] == 125:  # Half / Half preset, same as the Lamp Smart Pro one
                enc_cmd.arg0 = 0x01
            enc_cmd.arg1 = int(decoded[3] * 255 / 250)
            enc_cmd.arg2 = int(decoded[0] * 255 / 250)
        return enc_cmd, conf

    def convert_from_enc(self, enc_cmd: BleAdvEncCmd, conf: BleAdvConfig) -> bytearray:
        """Convert an encoder command and a config into a readable buffer."""
        arg0 = 0x40 if (enc_cmd.cmd, enc_cmd.arg0) == (0x21, 0x01) else enc_cmd.arg0
        button = next(key for key, val in self._BUTTONS.items() if val == (enc_cmd.cmd, arg0))
        uid = conf.id.to_bytes(4, "big")
        cold = round(enc_cmd.arg1 * 250 / 255) if button == 0xA8 else 0
        warm = round(enc_cmd.arg2 * 250 / 255) if button == 0xA8 else 0
        counter = conf.tx_count & 0xFF
        decoded = bytearray(
            [warm, 0, uid[0], cold, counter, 0x00, uid[1], uid[2], 0x00, button, 0x01, 0x00, uid[3], counter ^ 0x10, uid[2], button ^ 0x27, 0x00]
        )
        decoded[1] = self._check(decoded)
        return decoded


CODECS = [
    RemoteEncoder().id("remote_v4").header([0xF0, 0xFF]).ble(0x1A, 0xFF).add_translators(TRANS),
    # Second advertisement sent by some Lamp Smart Pro physical remotes
    RemoteFff0Encoder().id("remote_fff0").header([0xFF, 0xF0]).ble(0x1A, 0x16).add_translators(TRANS_FANLAMP_V2),
]  # fmt: skip
